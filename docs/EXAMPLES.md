# Catalyst Python and MCP examples

These examples use synthetic business content, scripted providers or mocked HTTP.
They need no real credentials, running model server or live-model calls. For
installation and an actual client workflow, use [Client setup](CLIENT_SETUP.md).

## Running the examples

Install development dependencies with `uv sync --locked` in the checkout first.
Use a fresh demo directory outside the checkout so the examples' relative
`data/` paths cannot write synthetic records into your normal Catalyst database.
Save each Python block as a script and run it from that demo directory with:

```bash
uv run --project /absolute/path/to/Catalyst-MCP --locked --no-sync python example.py
```

Run the scripts in the order below, as separate processes with the same working
directory. Some examples reuse files or saved records from earlier examples.
The storage examples use fixed IDs and need fresh demo data if repeated.
All 17 Python examples retain their original code and expected output.
Architecture, configuration and implementation notes are in the
[developer guide](DEVELOPMENT.md).

## Analysis over MCP

Run this Python example in the fresh demo directory with the project's environment.
It creates a synthetic analysis response file and launches the console command
through the SDK client. It uses a separate demo database from the storage examples.

```python
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from catalyst_mcp.models import BusinessModel
from catalyst_mcp.repository import SQLiteRepository

data_directory = Path("data").resolve()
data_directory.mkdir(exist_ok=True)
response_path = data_directory / "fake-analysis.json"
database_path = data_directory / "stdio-demo.sqlite3"
sections = {section: [] for section in BusinessModel.model_fields}
sections["endUsers"] = ["Cyclists"]
sections["activities"] = ["Repair bicycles"]
response_path.write_text(json.dumps({
    "name": "Northstar Bikes", "businessModel": sections,
}), encoding="utf-8")


async def demonstrate_analysis():
    """Discover the analysis tool, call it over stdio and verify its saved result."""
    parameters = StdioServerParameters(
        command=str(Path(sys.executable).with_name("catalyst-mcp")),
        args=["--database", str(database_path), "--fake-response", str(response_path)],
    )
    async with Client(parameters, read_timeout_seconds=10) as client:
        tools = await client.list_tools()
        print(tools.tools[0].name)
        result = await client.call_tool("analyze-business-model", {
            "businessContent": "Northstar Bikes repairs bicycles for cyclists.",
        })
        assert not result.is_error
        artifact = result.structured_content
        print(artifact["name"])
        print(artifact["businessModel"]["activities"])
        assert json.loads(result.content[0].text) == artifact
        assert [item.type for item in result.content] == ["text", "resource_link", "resource_link"]
        assert [link.uri for link in result.content[1:]] == [
            artifact["uri"], f"{artifact['uri']}/view.md",
        ]
    saved = SQLiteRepository(database_path).get_business_artifact(artifact["id"])
    print(saved.model_dump(mode="json") == artifact)


asyncio.run(demonstrate_analysis())
```

Output on stdout:

```text
analyze-business-model
Northstar Bikes
['Repair bicycles']
True
```

The client completes protocol setup, discovers the tool and sends the business
text. The fake returns the supplied JSON; it performs no extraction. The final
`True` confirms that the complete MCP result matches the saved record after the
server exits. This is a local SDK-client check, separate from integration with a
selected AI host or a live model.

## Two-tool MCP flow

After the analysis example creates `data/fake-analysis.json`, run this example to
create the ideation response file and call both tools through a new stdio process:

```python
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from catalyst_mcp.repository import SQLiteRepository

data_directory = Path("data").resolve()
database_path = data_directory / "two-tool-demo.sqlite3"
ideation_path = data_directory / "fake-ideation.json"
ideation_path.write_text(json.dumps({"useCases": [{
    "title": "Repair request triage", "focus": "Workshop efficiency",
    "problem": "Staff manually route repair requests.",
    "targetUsers": ["Workshop staff"],
    "proposedSolution": "Classify repair requests and suggest a work queue.",
    "businessElementAlignment": [{
        "section": "activities", "element": "Repair bicycles",
        "rationale": "Routes repair work to workshop staff.",
    }],
}]}), encoding="utf-8")


async def demonstrate_two_tool_flow():
    """Analyze, ideate with the returned ID and confirm both saved results."""
    parameters = StdioServerParameters(
        command=str(Path(sys.executable).with_name("catalyst-mcp")),
        args=[
            "--database", str(database_path),
            "--fake-response", str(data_directory / "fake-analysis.json"),
            "--fake-ideation-response", str(ideation_path),
        ],
    )
    async with Client(parameters, read_timeout_seconds=10) as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])
        analysis = await client.call_tool("analyze-business-model", {
            "businessContent": "Northstar Bikes repairs bicycles for cyclists.",
        })
        assert not analysis.is_error
        artifact = analysis.structured_content
        ideation = await client.call_tool("ideate-use-case", {
            "artifactId": artifact["id"],
            "numberOfIdeas": 1,
            "focus": "Workshop efficiency",
        })
        assert not ideation.is_error
        catalog = ideation.structured_content
        assert json.loads(ideation.content[0].text) == catalog
        markdown_link = ideation.content[2]
        assert markdown_link.type == "resource_link"
        markdown = await client.read_resource(markdown_link.uri)
        assert markdown.contents[0].mime_type == "text/markdown"
        assert markdown.contents[0].text.startswith("# Use-case Catalog\n")
        print(catalog["useCases"][0]["title"])
        print(catalog["sourceArtifact"]["id"] == artifact["id"])
    repository = SQLiteRepository(database_path)
    print(
        repository.get_business_artifact(artifact["id"]).model_dump(mode="json") == artifact
        and repository.get_use_case_catalog(catalog["id"]).model_dump(mode="json") == catalog
    )


asyncio.run(demonstrate_two_tool_flow())
```

Output printed by the client:

```text
['analyze-business-model', 'ideate-use-case']
Repair request triage
True
True
```

The first `True` verifies the source association; the second verifies both complete
saved records after the server exits. These are two explicit tool calls. Analysis
does not automatically trigger ideation, and the scripted providers perform no
extraction or idea generation. Source data remains unchanged during ideation.

To ideate from a saved artifact after restarting, supply `--database` and only
`--fake-ideation-response`; pass the saved ID to `ideate-use-case`. Both tools remain
discoverable. Calls to analysis fail until an analysis script is supplied.

`SourceArtifactNotFoundError` in `services.py` remains a `LookupError` subclass.
It identifies a missing saved source so `ideate` can return a not-found tool error
without misclassifying a provider's own lookup failure. These local fake-provider
checks do not establish live-model quality or compatibility with a selected AI host.

## Business Artifact models

`src/catalyst_mcp/models.py` separates analysis input, generated content and the
complete record. A small input-validation example:

```python
from catalyst_mcp.models import AnalyzeBusinessModelInput

request = AnalyzeBusinessModelInput(
    businessContent="Northstar Bikes repairs bicycles for cyclists."
)
print(request.model_dump())
```

Output:

```text
{'businessContent': 'Northstar Bikes repairs bicycles for cyclists.'}
```

The class validates the supplied text. The analysis service below handles
generation and saving. Blank text and undocumented fields raise a Pydantic
`ValidationError`.

## Ideation and Catalog models

The same module defines ideation input, alignment entries, generated cases and
the complete Catalog. For example:

```python
from catalyst_mcp.models import IdeateUseCaseInput

request = IdeateUseCaseInput(artifactId="ba_demo", numberOfIdeas=2)
print(request.model_dump())
```

Output:

```text
{'artifactId': 'ba_demo', 'numberOfIdeas': 2, 'focus': None}
```

Omitting input `focus` or supplying `null` means no focus was supplied. Provided
focus text must be non-blank. Every use case still requires its own non-blank
focus, the `targetUsers` array and at least one alignment entry.

Generated cases have no IDs. A complete `UseCase` adds its backend-supplied ID;
`UseCaseCatalog` adds the catalog ID, equal UTC timestamps and `sourceArtifact.id`.
Case IDs must be unique within the catalog, and the Catalog has no `uri` field.

These schemas require a positive idea count. The ideation service below enforces
a configurable maximum of 10 by default, checks source existence before generation,
and validates the exact requested result count and source-element matches.

## Business Artifact storage

`SQLiteRepository` takes an explicit persistent file path and creates its parent
directory and both record tables if needed. With a new database, this
synthetic example saves a complete artifact and reads it through a new repository:

```python
from datetime import UTC, datetime

from catalyst_mcp.models import BusinessArtifact, BusinessModel
from catalyst_mcp.repository import SQLiteRepository

sections = {section: [] for section in BusinessModel.model_fields}
sections["activities"] = ["Repair bicycles"]
timestamp = datetime(2026, 1, 1, tzinfo=UTC)
artifact = BusinessArtifact(
    id="ba_demo",
    name="Northstar Bikes",
    uri="catalyst://business-artifact/ba_demo",
    createdAt=timestamp,
    updatedAt=timestamp,
    businessModel=sections,
)

repository = SQLiteRepository("data/catalyst.sqlite3")
repository.save_business_artifact(artifact)
reopened = SQLiteRepository("data/catalyst.sqlite3")
print(reopened.get_business_artifact("ba_demo").name)
print([record.id for record in reopened.list_business_artifacts()])
```

Output:

```text
Northstar Bikes
['ba_demo']
```

Saving the same ID again raises `sqlite3.IntegrityError`. The repository preserves
IDs, timestamps, text and array order; callers supply the complete metadata.
`get_business_artifact` returns `None` for an unknown ID, and listing returns
complete artifacts ordered by ID. Invalid records and failed writes raise errors.
The example database is covered by the repository's existing ignore rules.

## Catalog storage

After running the Business Artifact storage example, the same database contains
the source `ba_demo`. This example supplies a complete synthetic Catalog linked
to that saved artifact:

```python
from datetime import UTC, datetime

from catalyst_mcp.models import UseCaseCatalog
from catalyst_mcp.repository import SQLiteRepository

timestamp = datetime(2026, 1, 1, tzinfo=UTC)
catalog = UseCaseCatalog(
    id="uc_catalog_demo",
    createdAt=timestamp,
    updatedAt=timestamp,
    sourceArtifact={"id": "ba_demo"},
    useCases=[{
        "id": "uc_demo",
        "title": "Repair request triage",
        "focus": "Workshop efficiency",
        "problem": "Staff manually route repair requests.",
        "targetUsers": ["Workshop staff"],
        "proposedSolution": "Classify repair requests and suggest a work queue.",
        "businessElementAlignment": [{
            "section": "activities",
            "element": "Repair bicycles",
            "rationale": "Routes repair work to workshop staff.",
        }],
    }],
)

repository = SQLiteRepository("data/catalyst.sqlite3")
repository.save_use_case_catalog(catalog)
reopened = SQLiteRepository("data/catalyst.sqlite3")
loaded = reopened.get_use_case_catalog("uc_catalog_demo")
print(loaded.sourceArtifact.id)
print(loaded.useCases[0].title)
print([record.id for record in reopened.list_use_case_catalogs()])
```

Output:

```text
ba_demo
Repair request triage
['uc_catalog_demo']
```

The repository returns the complete Catalog after commit, preserving its cases,
source ID and timestamps. A missing source or duplicate Catalog ID raises
`sqlite3.IntegrityError`. Reads validate the JSON and its Catalog/source IDs against
their database columns. A Catalog has no `uri` field.

Source existence is enforced when saving. The ideation service also loads the
source before generation and checks every alignment and the requested idea count.

## JSON resources over MCP

After the two storage examples, the database contains `ba_demo` and
`uc_catalog_demo`. This example starts a new server with no provider scripts and
reads their canonical JSON resources:

```python
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from catalyst_mcp.repository import SQLiteRepository

database_path = Path("data/catalyst.sqlite3").resolve()


async def demonstrate_json_resources():
    """Discover JSON resources and verify both complete records after restart."""
    parameters = StdioServerParameters(
        command=str(Path(sys.executable).with_name("catalyst-mcp")),
        args=["--database", str(database_path)],
    )
    async with Client(parameters, read_timeout_seconds=10) as client:
        listing = await client.list_resources()
        assert listing.next_cursor is None
        json_resources = [
            resource for resource in listing.resources
            if resource.mime_type == "application/json"
        ]
        print([resource.mime_type for resource in json_resources])
        artifact_result = await client.read_resource("catalyst://business-artifact/ba_demo")
        catalog_result = await client.read_resource("catalyst://use-case-catalog/uc_catalog_demo")
        artifact_content = artifact_result.contents[0]
        catalog_content = catalog_result.contents[0]
        assert artifact_content.mime_type == catalog_content.mime_type == "application/json"
        artifact = json.loads(artifact_content.text)
        catalog = json.loads(catalog_content.text)
        print(artifact["name"])
        print(catalog["useCases"][0]["title"])
    repository = SQLiteRepository(database_path)
    print(
        repository.get_business_artifact("ba_demo").model_dump(mode="json") == artifact
        and repository.get_use_case_catalog("uc_catalog_demo").model_dump(mode="json") == catalog
    )


asyncio.run(demonstrate_json_resources())
```

Output printed by the client:

```text
['application/json', 'application/json']
Northstar Bikes
Repair request triage
True
```

Each read returns one text content item whose URI equals the requested canonical
URI, whose MIME type is `application/json` and whose text contains the complete
saved JSON. The final `True` verifies both complete records, including metadata,
all 12 business-model sections, every case and every alignment. The Catalog still
has no `uri` field; its resource URI is constructed in the MCP layer.

## Business Artifact Markdown

After the Business Artifact storage example, load the same saved record and
render its Markdown view:

```python
from catalyst_mcp.markdown_views import render_business_artifact
from catalyst_mcp.repository import SQLiteRepository

repository = SQLiteRepository("data/catalyst.sqlite3")
artifact = repository.get_business_artifact("ba_demo")
print(render_business_artifact(artifact))
```

The result includes the name, ID, canonical JSON URI, both saved timestamps and
all 12 business-model sections. For example, its Activities section is:

```markdown
## Activities

- Repair bicycles
```

Empty sections contain `Not specified`. Text is escaped as literal content;
multiline values remain within their original bullet. Rendering returns a string
without calling a model, writing a Markdown file or changing the saved record.
The MCP route returns this same string with MIME type `text/markdown`.

## Catalog Markdown

After the Catalog storage example, render the saved Catalog from the same database:

```python
from catalyst_mcp.markdown_views import render_use_case_catalog
from catalyst_mcp.repository import SQLiteRepository

repository = SQLiteRepository("data/catalyst.sqlite3")
catalog = repository.get_use_case_catalog("uc_catalog_demo")
print(render_use_case_catalog(catalog))
```

The result includes Catalog ID and timestamps, source artifact ID and its computed
canonical JSON URI, every case's fields, all target users and all alignment entries.
For example, the first alignment in the generated Markdown source is:

```markdown
#### Alignment 1

- **Section:** activities
- **Element:** Repair bicycles
- **Rationale:** Routes repair work to workshop staff\.
```

Cases and alignment entries are numbered by their saved array positions. Stored
IDs, content order and duplicate entries are preserved. Empty target-user lists
contain `Not specified`. The source URI is computed for display; no URI field is
added to the Catalog or source reference.

Like the artifact renderer, this returns text without model calls, database or
file writes, source lookups or new timestamps. The MCP route returns the same text;
the recorded Codex display is plain Markdown text. See the
[current verification limits](CLIENT_SETUP.md#verification-limits).

## Markdown resources over MCP

After the storage examples, start another server with no provider scripts and read
both saved Markdown views. This compares their complete contents with the existing
renderers and repeats a read to check determinism:

```python
import asyncio
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from catalyst_mcp.markdown_views import render_business_artifact, render_use_case_catalog
from catalyst_mcp.repository import SQLiteRepository

database_path = Path("data/catalyst.sqlite3").resolve()
repository = SQLiteRepository(database_path)
expected = {
    "catalyst://business-artifact/ba_demo/view.md": render_business_artifact(
        repository.get_business_artifact("ba_demo")
    ),
    "catalyst://use-case-catalog/uc_catalog_demo/view.md": render_use_case_catalog(
        repository.get_use_case_catalog("uc_catalog_demo")
    ),
}


async def demonstrate_markdown_resources():
    """Discover both Markdown views and read the complete deterministic text."""
    parameters = StdioServerParameters(
        command=str(Path(sys.executable).with_name("catalyst-mcp")),
        args=["--database", str(database_path)],
    )
    async with Client(parameters, read_timeout_seconds=10) as client:
        listing = await client.list_resources()
        markdown_resources = [
            resource for resource in listing.resources
            if resource.mime_type == "text/markdown"
        ]
        assert {resource.uri for resource in markdown_resources} == set(expected)
        for resource in markdown_resources:
            result = await client.read_resource(resource.uri)
            content = result.contents[0]
            assert content.uri == resource.uri
            assert content.mime_type == "text/markdown"
            assert content.text == expected[resource.uri]
            repeated = await client.read_resource(resource.uri)
            assert repeated.contents[0].text == content.text
            print(content.mime_type, content.text.splitlines()[0])
        print(True)


asyncio.run(demonstrate_markdown_resources())
```

Output printed by the client:

```text
text/markdown # Business Artifact
text/markdown # Use-case Catalog
True
```

For example, reading `catalyst://business-artifact/ba_demo/view.md` returns the
complete artifact document, including `## Activities` followed by `- Repair bicycles`.
The canonical URI without `/view.md` continues to return saved JSON. Successful
tool results link directly to both URIs with the same names and MIME types used
by discovery. Clients can follow either link through `resources/read`.

## Analysis with a fake provider

This self-contained example uses synthetic text and a scripted response. The fake
returns the supplied JSON; it does not extract information from the business text.

```python
import json

from catalyst_mcp.llm_client import FakeAnalysisProvider
from catalyst_mcp.models import BusinessModel
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.services import analyze_business_model

sections = {section: [] for section in BusinessModel.model_fields}
sections["endUsers"] = ["Cyclists"]
sections["solutions"] = ["Bicycle repairs"]
sections["activities"] = ["Repair bicycles"]
sections["revenuesAndAdvantages"] = ["Repair fees"]
provider = FakeAnalysisProvider(json.dumps({
    "name": "Northstar Bikes",
    "businessModel": sections,
}))
repository = SQLiteRepository("data/catalyst.sqlite3")
artifact = analyze_business_model(
    "Northstar Bikes repairs bicycles for cyclists and charges repair fees.",
    provider=provider,
    repository=repository,
)
print(artifact.name)
print(artifact.businessModel.activities)
print(repository.get_business_artifact(artifact.id) == artifact)
```

Output:

```text
Northstar Bikes
['Repair bicycles']
True
```

The returned `artifact` contains all 12 sections plus `id`, `name`, `uri`,
`createdAt` and `updatedAt`. Its ID is `ba_` followed by a UUID4 hex value, its URI
is `catalyst://business-artifact/{id}`, and both timestamps use the same UTC
creation time. Each successful call creates a new record.

## Analysis with the configured provider

This example uses a scripted JSON client to demonstrate the complete bridge
without a paid API request or a local model server:

```python
import json
from unittest.mock import Mock

from catalyst_mcp.llm_client import JSONClient, LLMAnalysisProvider
from catalyst_mcp.models import BusinessModel
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.services import analyze_business_model

sections = {key: [] for key in BusinessModel.model_fields}
sections["endUsers"] = ["Cyclists"]
sections["activities"] = ["Repair bicycles"]
client = Mock(spec=JSONClient)
client.generate_json.return_value = json.dumps({
    "name": "Northstar Bikes", "businessModel": sections,
})
repository = SQLiteRepository("data/prompt-analysis-demo.sqlite3")
artifact = analyze_business_model(
    "Northstar Bikes repairs bicycles for cyclists.",
    provider=LLMAnalysisProvider(client), repository=repository,
)
print(artifact.name)
print(artifact.businessModel.activities)
print(len(artifact.businessModel.model_dump()))
print(repository.get_business_artifact(artifact.id) == artifact)
print(json.loads(client.generate_json.call_args.kwargs["input_text"])["businessContent"])
```

Output:

```text
Northstar Bikes
['Repair bicycles']
12
True
Northstar Bikes repairs bicycles for cyclists.
```

For an actual configured call, construct the bridge with
`LLMAnalysisProvider(create_json_client(LLMSettings.from_env()))`. The CLI does this
only when `--live-analysis` is selected. Credentials/model access and local model
availability must be configured by the caller; no default model or fallback is
introduced. New integration tests use the real SDKs/HTTP clients with mocked
responses, and a subprocess checks the live-analysis stdio path with a mocked
Ollama endpoint. Those checks do not establish real extraction quality.

## Ideation with a fake provider

After the Business Artifact storage example, `ba_demo` contains the activity
`Repair bicycles`. This example requests one idea from that saved artifact:

```python
import json

from catalyst_mcp.llm_client import FakeIdeationProvider
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.services import ideate_use_case

provider = FakeIdeationProvider(json.dumps({
    "useCases": [{
        "title": "Repair request triage",
        "focus": "Workshop efficiency",
        "problem": "Staff manually route repair requests.",
        "targetUsers": ["Workshop staff"],
        "proposedSolution": "Classify repair requests and suggest a work queue.",
        "businessElementAlignment": [{
            "section": "activities",
            "element": "Repair bicycles",
            "rationale": "Routes repair work to workshop staff.",
        }],
    }],
}))
repository = SQLiteRepository("data/catalyst.sqlite3")
catalog = ideate_use_case(
    "ba_demo", 1, focus="Workshop efficiency",
    provider=provider, repository=repository,
)
print(catalog.sourceArtifact.id)
print(catalog.useCases[0].title)
print(len(catalog.useCases))
print(repository.get_use_case_catalog(catalog.id) == catalog)
```

Output:

```text
ba_demo
Repair request triage
1
True
```

The returned Catalog contains the complete cases, `sourceArtifact.id`, a new
`uc_catalog_` UUID4 ID, a `uc_` UUID4 ID for each case and equal UTC timestamps.
It has no `uri` field. The source artifact and its timestamps remain unchanged.
The fake returns the supplied JSON; it does not create or evaluate ideas.

## Ideation with the configured provider

After the storage examples create `ba_demo`, this runnable example demonstrates
the complete bridge with a scripted JSON client, without a live API request:

```python
import json
from unittest.mock import Mock

from catalyst_mcp.llm_client import JSONClient, LLMIdeationProvider
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.services import ideate_use_case

repository = SQLiteRepository("data/catalyst.sqlite3")
source = repository.get_business_artifact("ba_demo")
client = Mock(spec=JSONClient)
client.generate_json.return_value = json.dumps({"useCases": [{
    "title": "Repair request triage", "focus": "Workshop efficiency",
    "problem": "Opportunity to route repair requests consistently.",
    "targetUsers": ["Workshop staff"],
    "proposedSolution": "Classify repair requests and suggest a work queue.",
    "businessElementAlignment": [{
        "section": "activities", "element": "Repair bicycles",
        "rationale": "Supports routing repair work.",
    }],
}]})
catalog = ideate_use_case(
    source.id, 1, focus="Workshop efficiency",
    provider=LLMIdeationProvider(client), repository=repository,
)
print(catalog.useCases[0].title)
print(len(catalog.useCases))
print(catalog.sourceArtifact.id)
alignment = catalog.useCases[0].businessElementAlignment[0]
print(f"{alignment.section}: {alignment.element}")
print(
    repository.get_use_case_catalog(catalog.id) == catalog
    and repository.get_business_artifact(source.id) == source
)
```

Output:

```text
Repair request triage
1
ba_demo
activities: Repair bicycles
True
```

The last `True` verifies the complete saved Catalog and unchanged source. For an
actual configured call, use
`LLMIdeationProvider(create_json_client(LLMSettings.from_env()))`, or enable
`--live-ideation` in the console command. Integration tests exercise all three
real clients with mocked HTTP. Real stdio checks cover ideation from an existing
artifact, both live tools, mixed fake/live modes and correction, including reads
of both JSON and Markdown resources. These checks do not establish live idea
quality, semantic focus compliance, prompt-injection resistance or host support.

## OpenAI client example

This runnable example uses synthetic settings and mocked HTTP, so it makes no
network request and needs no real API key:

```python
from unittest.mock import patch

import httpx
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from catalyst_mcp.llm_client import JSONClient, create_json_client
from catalyst_mcp.settings import LLMSettings

settings = LLMSettings.from_env({
    "CATALYST_LLM_PROVIDER": "openai",
    "CATALYST_LLM_MODEL": "synthetic-model",
    "OPENAI_API_KEY": "synthetic-key",
})


class Label(BaseModel):
    """Describe the JSON expected by this synthetic example."""
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


reply = {
    "id": "resp_synthetic", "object": "response", "created_at": 0,
    "model": "synthetic-model", "status": "completed",
    "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
    "output": [{
        "id": "msg_synthetic", "type": "message", "role": "assistant",
        "status": "completed", "content": [{
            "type": "output_text", "text": '{"value":"bicycle"}', "annotations": [],
        }],
    }],
}
transport = httpx.MockTransport(lambda request: httpx.Response(200, json=reply))
sdk = OpenAI(
    api_key="synthetic-key", timeout=60.0, max_retries=0,
    http_client=httpx.Client(transport=transport, trust_env=False),
)
with patch("catalyst_mcp.llm_client.OpenAI", return_value=sdk):
    client: JSONClient = create_json_client(settings)
    text = client.generate_json(
        instructions="Return JSON with value equal to the supplied word.",
        input_text="bicycle", output_model=Label,
    )
    print(text)
    print(Label.model_validate_json(text).value)
print(sdk.is_closed())
```

Output:

```text
{"value":"bicycle"}
bicycle
True
```

The mock supplies the answer; this verifies transport and validation behavior.
This example does not assess live model access, business quality, prompt-injection
resistance or host display. See the [recorded verification limits](CLIENT_SETUP.md#verification-limits)
for separate live-model and host evidence.

## Anthropic client example

This example selects Anthropic from configuration and exercises its real SDK with
a synthetic HTTP reply. No live API key or network access is needed:

```python
from unittest.mock import patch

import httpx2
from anthropic import Anthropic
from pydantic import BaseModel, ConfigDict

from catalyst_mcp.llm_client import create_json_client
from catalyst_mcp.settings import LLMSettings


class Label(BaseModel):
    """Define the output for this synthetic transport example."""
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


settings = LLMSettings.from_env({
    "CATALYST_LLM_PROVIDER": "anthropic",
    "CATALYST_LLM_MODEL": "synthetic-model",
    "ANTHROPIC_API_KEY": "synthetic-key",
})
reply = {
    "id": "msg_synthetic", "type": "message", "role": "assistant",
    "model": "synthetic-model", "stop_reason": "end_turn", "stop_sequence": None,
    "content": [{"type": "text", "text": '{"value":"bicycle"}'}],
    "usage": {"input_tokens": 10, "output_tokens": 5},
}
http = httpx2.Client(
    transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=reply)),
    trust_env=False,
)
sdk = Anthropic(api_key="synthetic-key", http_client=http, max_retries=0)
with patch("catalyst_mcp.llm_client.Anthropic", return_value=sdk):
    text = create_json_client(settings).generate_json(
        instructions="Return JSON with value equal to the supplied word.",
        input_text="bicycle", output_model=Label,
    )
    print(text)
    print(Label.model_validate_json(text).value)
print(sdk.is_closed())
```

Output:

```text
{"value":"bicycle"}
bicycle
True
```

The adapter returns the complete text and closes the SDK client. The SDK may
simplify constraints for its request schema; the original Pydantic model still
enforces the full contract when the calling workflow validates the text.

## Ollama client example

This example selects a local model without credentials. Mocked HTTP provides the
response, so it does not need an installed model or running Ollama server:

```python
from unittest.mock import patch

import httpx2
from pydantic import BaseModel, ConfigDict

from catalyst_mcp.llm_client import create_json_client
from catalyst_mcp.settings import LLMSettings


class Label(BaseModel):
    """Define the output for this synthetic local transport example."""
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


settings = LLMSettings.from_env({
    "CATALYST_LLM_PROVIDER": "ollama",
    "CATALYST_LLM_MODEL": "synthetic-local-model",
})
reply = {
    "message": {"role": "assistant", "content": '{"value":"bicycle"}'},
    "done": True, "done_reason": "stop",
}
http = httpx2.Client(
    base_url=str(settings.ollama_host),
    transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=reply)),
    trust_env=False,
)
with patch("catalyst_mcp.llm_client.httpx2.Client", return_value=http):
    text = create_json_client(settings).generate_json(
        instructions="Return JSON with value equal to the supplied word.",
        input_text="bicycle", output_model=Label,
    )
    print(text)
    print(Label.model_validate_json(text).value)
print(http.is_closed)
```

Output:

```text
{"value":"bicycle"}
bicycle
True
```

For a live check, the configured local server must already be running with
the selected model installed. Local model compatibility, quality and resource use
remain unverified; these examples establish request/response behavior only.
