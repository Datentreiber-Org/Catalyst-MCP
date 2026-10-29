# Catalyst

Catalyst is being built to turn business text into a saved Business Artifact,
then generate a saved Use-case Catalog linked to that artifact through MCP.

The repository contains validated Business Artifact and Use-case Catalog models,
SQLite persistence and deterministic Markdown renderers. A local stdio MCP server
exposes `analyze-business-model` and `ideate-use-case` using scripted fake-provider
responses. Both return complete committed records. Ideation validates the exact
idea count and every source reference before saving its Catalog. Both saved types
can be listed and read as canonical JSON and on-demand Markdown resources. Tool
results link to both views. OpenAI, Anthropic and local Ollama JSON clients and
provider selection are implemented and tested with mocked HTTP. Analysis and
ideation can each use the configured provider with packaged prompts and explicit
`--live-analysis` and `--live-ideation` options.

## Development setup

Use Python 3.12 or later and [uv](https://docs.astral.sh/uv/). The project pins
Python 3.12 in `.python-version`.

From the repository root, install the project and its development dependencies:

```bash
uv sync --locked
```

This creates or reuses the project's `.venv` and installs the versions recorded
in `uv.lock`. `uv run` uses that environment without requiring activation.

Check the interpreter and package import:

```bash
uv run --locked python --version
uv run --locked python -c "import catalyst_mcp; print(catalyst_mcp.__file__)"
```

## Run the stdio development server

```bash
uv run --locked catalyst-mcp \
  --database data/two-tool-demo.sqlite3 \
  --fake-response data/fake-analysis.json \
  --fake-ideation-response data/fake-ideation.json
```

The command now starts an MCP server and waits for a client on stdin. It does not
print a greeting. Application logs and the explicit fake-provider startup notice
go to stderr; stdout carries MCP messages. Use `--help` to see its arguments.

Create the two synthetic response files using the examples below. `--database`
is required. The response options are optional and independent: `--fake-response`
supplies analysis output and `--fake-ideation-response` supplies ideation output.
Each provider call consumes its next file, including correction attempts. Repeat
the corresponding option to supply more responses. An omitted or exhausted script
returns a tool error when that provider is called. No LLM or credentials are used.

To use a configured provider for analysis, set the environment variables described
under [LLM configuration](#llm-configuration-and-provider-clients), then run:

```bash
uv run --locked catalyst-mcp --database data/catalyst.sqlite3 --live-analysis
```

`--live-analysis` and `--fake-response` are mutually exclusive. An environment
setting alone never enables live calls. Startup validates the selected provider's
configuration and selected packaged prompts before opening the database, without
calling the model. Generation starts only when the corresponding tool is called.
`--fake-ideation-response` can still supply scripted ideation in this mode.

To enable both tools with the same configured provider/model:

```bash
uv run --locked catalyst-mcp --database data/catalyst.sqlite3 --live-analysis --live-ideation
```

`--live-ideation` and `--fake-ideation-response` are mutually exclusive. Either tool
may independently use live or scripted generation. `--live-ideation` also works
alone against an artifact already saved in the selected database. When both live
flags are supplied, configuration is loaded once and the two prompt bridges share
one stateless JSON client. Each generation request still owns its connection and
sends its own complete input; no conversation history is shared. The tools remain
two separate calls, and analysis never automatically triggers ideation. Default
fake/resource-only startup needs no LLM settings. Resource reads use saved data
without another model call.

The server advertises exactly two tools, both rejecting extra input fields:

| Tool | Input |
|---|---|
| `analyze-business-model` | Non-blank `businessContent`, maximum 20,000 characters |
| `ideate-use-case` | Saved `artifactId`, integer `numberOfIdeas` from 1 to 10, optional non-blank `focus` or `null` |

A successful call returns the complete saved artifact or Catalog as
`structuredContent` and matching JSON text, conforming to its `outputSchema`.
The text is followed by two native MCP `resource_link` items, for JSON and Markdown.
A Catalog has no `uri` field. Failures have `isError: true` and no structured success
payload or resource links. Both resource views are available through
`resources/list` and `resources/read`. The artifact's canonical URI stays in its payload.

The server uses the [official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/),
version 2.3.0 recorded in `uv.lock`, with its documented
[low-level server API](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/).

## Analysis over MCP

Run this Python example from the repository root with the project's environment.
It creates the synthetic analysis file used above and launches the console command
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

In `server.py`, `create_server` keeps both injected providers and the shared
repository in small callbacks. `list_tools` advertises the exact schemas from our
models. `call_tool` dispatches the two registered names to `analyze` or `ideate`.
Each validates its arguments, runs its service in a worker thread and returns the
complete committed record. `_tool_error` logs the known operation name and a fixed
failure summary without echoing business text or provider exception details.
`run_stdio` connects the SDK's stdin/stdout streams to its server runner. The
updated package `main` loads the explicit file paths, configures stderr logging
and starts that runner. Imports do not start a server or create a database.

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

## Tests

[pytest](https://docs.pytest.org/en/stable/) is a development dependency.

```bash
uv run --locked pytest
```

The current tests cover analysis and ideation inputs, generated content and the
complete Business Artifact and Catalog shapes, plus persistence of both record
types in real temporary SQLite files. They check strict types, all 12 business-model
sections, alignment structure, metadata consistency, source associations, JSON
round trips, process restart persistence and failure rollback. Markdown tests for
both record types parse the output as CommonMark and verify content preservation,
escaping, completeness and determinism. Analysis and ideation workflow tests use
scripted fake providers to check limits, bounded correction, metadata, exact idea
counts, source-element matches and failure atomicity. MCP tests use the official client in process and real console-command
subprocesses, checking discovery, complete results, failures, restart persistence
and JSON-RPC stdout. The full two-tool sequence and ideation after process restart
are also exercised. OpenAI adapter checks use the real SDK with HTTPX mock
transport to verify serialization, responses, failure handling, disabled retries
and connection cleanup. No live model provider or selected AI host is exercised.
JSON/Markdown resource checks verify complete data, native tool links, MIME types,
exact URI matching, deterministic rendering, literal special characters, safe
protocol errors, unchanged stored records and reads without provider calls.

- `tests/test_artifact_model.py` covers analysis input and Business
  Artifact validation.
- `tests/test_catalog_model.py` covers ideation input,
  alignment entries and Use-case Catalog validation.
- `tests/test_artifact_repository.py` covers Business Artifact storage, reads, listing,
  restart persistence and failure atomicity.
- `tests/test_catalog_repository.py` covers Catalog storage, source associations,
  restart persistence and failure atomicity.
- `tests/test_artifact_markdown.py` covers the complete Business Artifact view,
  literal text, deterministic rendering and unchanged saved records.
- `tests/test_catalog_markdown.py` covers Catalog metadata, source references,
  all case fields and alignments, literal text and unchanged saved records.
- `tests/test_artifact_service.py` covers analysis with scripted responses,
  correction limits, provider failures and a real SQLite commit failure.
- `tests/test_artifact_provider.py` covers the packaged analysis prompt, separate
  source data, correction, and the complete configured-provider/MCP/storage path
  through all three adapters with mocked HTTP.
- `tests/test_catalog_service.py` covers ideation from saved sources, exact counts
  and alignments, limits, correction, source preservation and failed-commit rollback.
- `tests/test_catalog_provider.py` covers the packaged ideation prompt, source/count/focus
  data, corrections and complete MCP/storage results through all three adapters
  with mocked HTTP, including failed-generation atomicity and source preservation.
- `tests/test_artifact_mcp.py` covers analysis discovery and schemas, strict
  arguments, safe failure results, CLI startup and real stdio exchanges.
- `tests/test_catalog_mcp.py` covers ideation discovery and schemas, strict
  arguments, saved-source handling, complete results, correction and failed commits.
- `tests/test_mcp_flow.py` covers both tools through real stdio, independent scripts,
  ideation after restart, rejected count/alignment output, tool links and both
  resource formats after restart, plus configured mixed/live modes with mocked HTTP.
- `tests/test_mcp_resource.py` covers JSON/Markdown discovery and reads, exact
  URIs, complete payloads, MIME types, determinism, safe errors and unchanged data/files.
- `tests/test_llm_settings.py` covers provider/model selection, credentials,
  finite positive timeouts, safe configuration errors and unsupported providers.
- `tests/test_llm_client.py` covers the OpenAI JSON client through the actual SDK
  with mocked HTTP, including schemas, request separation, failures and cleanup.
- `tests/test_llm_anthropic.py` covers the real Anthropic SDK with mocked HTTP,
  schema conversion, stop reasons, failures, credentials and cleanup.
- `tests/test_llm_ollama.py` covers Ollama HTTP requests, configured origins,
  completion checks, malformed envelopes, failures and cleanup.

`markdown-it-py` is a development dependency used to parse Markdown in tests.
The production renderer uses Python's standard library and the existing models.

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

The resource and result helpers in `server.py` share the same descriptions:

- `_resource_views` creates two descriptions for a saved record: canonical JSON,
  then `/view.md` Markdown, each with its name, URI and MIME type. It renders nothing.
- `_saved_tool_result` returns the complete saved JSON in text and structured
  content, followed by native resource links made from those two descriptions.
- `_list_saved_resources` loads validated records and describes both views.
  Artifacts come first in ID order, followed by Catalogs in ID order. Duplicate
  advertised URIs cause a fixed listing error.
- `_load_saved_record` matches a literal canonical prefix and loads the exact saved
  ID. It does not decode URI escapes, normalize IDs or perform filesystem lookups.
- `_read_saved_resource` first checks for an exact canonical JSON record. Otherwise,
  a literal `/view.md` suffix selects the existing renderer for the base record.
  It returns one content item with the requested URI and correct MIME type.
- `_resource_error` logs a fixed operation summary and constructs an MCP protocol
  error without copying URI values, stored content or exception details into it.
- `list_resources` runs discovery in a worker thread and returns a single page.
  An explicit cursor is rejected; pagination and change notifications are not enabled.
- `read_resource` runs loading and rendering in a worker thread and returns the
  content or a protocol error. Missing/unsupported resources use `-32602`; database,
  invalid-record or rendering failures use `-32603`, following the current
  [resource error contract](https://modelcontextprotocol.io/specification/draft/server/resources#error-handling).

Listing and reading make no provider calls, writes or new timestamps. JSON reads
preserve stored text, field names and array order. Both Markdown renderers also
work directly in Python as shown below. Backend-generated IDs avoid URI collisions.
For manually stored IDs ending in `/view.md`, an exact canonical JSON record takes
precedence; a collision between two advertised views causes listing to fail.
Live-model and selected-host checks remain separate.

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
display in a selected AI host remains unverified.

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

The new code has three parts:

- `AnalysisProvider` declares the `generate_business_model` operation: accept
  business text and optional backend correction separately, and return JSON.
  Providers satisfy this interface by implementing that method.
- `FakeAnalysisProvider.__init__` stores an ordered script and starts an empty
  call history. Its `generate_business_model` method records each call, then
  returns the next JSON string or raises the next scripted exception. An exhausted
  script raises `RuntimeError`.
- `analyze_business_model` validates the text, asks the provider for generated
  content, validates that content, adds metadata, saves and returns the complete
  committed artifact. It uses the existing repository for transaction handling.

The service accepts at most 20,000 Python characters by default. Override this
through the positive integer `max_business_content_chars` keyword. It preserves
input text without trimming or truncation. Blank or wrongly typed input raises
`ValidationError`; oversized input raises `ValueError` before a provider call.

Malformed JSON or schema-invalid output receives one corrective attempt. The
`_ANALYSIS_CORRECTION` constant supplies fixed backend feedback; rejected model
output and input text are not copied into it. Two invalid outputs raise
`RuntimeError`. The existing non-empty model validator now emits the distinct
`empty_business_model` error code, which the service translates into an
insufficient-content `ValueError` without retrying. Provider and database failures
propagate without a success result or a partially saved artifact.

This verifies workflow behavior with a fake. The configured-provider bridge below
adds the real analysis prompt; live model quality, overall provider deadlines and
selected-host integration remain unverified or later work.

## Analysis with the configured provider

`LLMAnalysisProvider` connects the existing analysis workflow to any `JSONClient`.
Its constructor loads `prompts/analyze_business_model.md` through
`importlib.resources`, so the same UTF-8 prompt works from source and an installed
wheel regardless of the working directory. Missing or empty prompts fail before
generation. The prompt is internal backend content, not a registered MCP Prompt.

`generate_business_model` sends business text as a separate JSON data object:
`{"businessContent": "..."}`. It requests the existing `GeneratedBusinessArtifact`
schema and returns the response text unchanged. Backend correction requirements
are appended to the trusted instructions for that call only; rejected output and
business text are never inserted into those instructions. The service continues
to own validation, its one-correction limit, metadata and atomic saving.

The prompt defines all 12 sections, distinguishes user/buyer/decision-maker roles,
requires source-supported statements and leaves unsupported sections empty. It
uses `Unnamed business` when the text gives no business name. If no usable facts
can be extracted, it requests all arrays empty so the existing service returns an
insufficient-content error without saving. These instructions follow official
guidance on [insufficient input](https://developers.openai.com/api/docs/guides/structured-outputs)
and [separating untrusted data](https://developers.openai.com/api/docs/guides/agent-builder-safety).
They still need live quality and prompt-injection evaluation.

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

The new code has four parts:

- `IdeationProvider.generate_use_cases` declares the provider operation: receive
  the saved artifact as JSON, the requested count, optional focus and separate
  correction feedback; return JSON containing only `useCases`.
- `FakeIdeationProvider.__init__` stores the response script and starts an empty
  call history. Its `generate_use_cases` method records the arguments, then returns
  the next JSON string or raises the scripted exception. Exhaustion raises `RuntimeError`.
- `_validate_generated_use_cases` checks the exact count and every alignment in
  every case. Each element must match a string in its named source section
  exactly, including case, whitespace and Unicode characters.
- `ideate_use_case` validates the request, loads the saved source, calls the
  provider, validates its output, assigns metadata and saves the complete Catalog.
  It returns the repository's result only after commit succeeds.

The `max_number_of_ideas` keyword defaults to 10 and requires a positive integer.
Invalid input raises `ValidationError`; a count above the configured maximum
raises `ValueError`. A missing source raises `SourceArtifactNotFoundError`, a
`LookupError` subclass, before any provider call.
Optional focus is preserved exactly, with omitted or `None` meaning no constraint.

Malformed JSON, schema errors, wrong counts or invalid alignments get at most one
corrective provider call. `_IDEATION_CORRECTION` supplies fixed backend feedback;
source JSON, count and focus stay unchanged and rejected output is not included in
the feedback. Two invalid responses raise `RuntimeError`. Provider, source-read
and database-save failures propagate without generation retries or partial Catalogs.

These fake-provider checks establish orchestration and valid references. They do
not assess idea relevance, rationale quality or semantic focus compliance. Live
prompts, overall provider deadlines and real model evaluation remain later work. Both tools
are exposed through MCP with independent CLI scripts.

## Ideation with the configured provider

`LLMIdeationProvider` connects saved-artifact ideation to any `JSONClient`. Its
constructor loads the packaged UTF-8 `prompts/ideate_use_case.md` file once through
`importlib.resources`, independently of the working directory. Missing or empty
prompts fail before generation. These are backend instructions, not an MCP Prompt.

`generate_use_cases` decodes the saved artifact JSON and sends a separate JSON
input object containing the complete `sourceArtifact`, integer `numberOfIdeas`
and `focus` (including `null` when absent). It requests `GeneratedUseCaseCatalog`
and returns response text unchanged. Only backend correction requirements are
added to trusted instructions for that call; source/focus values and rejected
output are never interpolated into those instructions.

The prompt requests exactly the specified number of Data & AI proposals, all
documented fields including `targetUsers`, and at least one exact source alignment
per case. An alignment must copy an entire element from its named saved section,
including case, Unicode and whitespace. Ideas are proposals rather than claims
about existing systems, datasets, measured pain points or results. When a problem
is not stated in the source, the prompt asks for an opportunity or hypothesis.
The existing service still loads the source before generation, enforces count and
alignment, allows one correction, assigns metadata and commits atomically.

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

## LLM configuration and provider clients

Step 14 is split into separately authorized parts: 14a adds shared configuration
and OpenAI, 14b adds Anthropic, and 14c adds Ollama. All three parts are implemented
with offline verification. Clients are available from Python and through the
independent `--live-analysis` and `--live-ideation` options.

`LLMSettings.from_env()` reads these environment variables when called:

| Variable | Meaning |
|---|---|
| `CATALYST_LLM_PROVIDER` | Required: `openai`, `anthropic` or `ollama` |
| `CATALYST_LLM_MODEL` | Required model ID; no implicit model or fallback |
| `OPENAI_API_KEY` | Required credential for OpenAI |
| `ANTHROPIC_API_KEY` | Required credential for Anthropic |
| `CATALYST_LLM_TIMEOUT_SECONDS` | Positive finite SDK network timeout; defaults to 60 |
| `CATALYST_LLM_MAX_OUTPUT_TOKENS` | Positive integer output-token limit; defaults to 8192 |
| `CATALYST_OLLAMA_HOST` | Ollama HTTP(S) origin; defaults to `http://localhost:11434` |

Set these in the launching environment. No `.env` file is automatically loaded,
and imports do not read configuration or make requests. The API key is held as a
Pydantic `SecretStr`, excluded from the settings representation and serialization.
Invalid environment configuration raises a fixed message without supplied values.
Model access and Structured Outputs support must be verified for the chosen model.
Only the selected cloud provider's key is read. Local Ollama needs no key and
ignores cloud credentials. Its host must contain no username, password, path,
query or fragment. No model is downloaded or started by these clients.

The OpenAI client uses the official `openai` 2.x SDK, locked to 2.54.0, and its
[Responses API](https://developers.openai.com/api/reference/python).
It requests [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
using the supplied Pydantic model's JSON Schema, `strict: true` and `store: false`.
Backend instructions and input data are separate request fields. The caller must
supply an object schema supported by the chosen provider/model; both existing
generated-content schemas are exercised in offline tests.

The provider code has five classes and one selection function:

- `LLMSettings` in `settings.py` validates provider, model, credential and timeout
  values. `validate_api_key` rejects empty or whitespace-containing credentials.
  `from_env` accepts an optional environment mapping for deterministic tests; it
  reads values without loading files or changing the process environment.
  `validate_provider_credentials` requires a key for cloud providers and keeps
  local Ollama credential-free. `validate_ollama_host` validates the server origin.
- `JSONClient` in `llm_client.py` is the shared `Protocol`: `generate_json` accepts
  trusted instructions, input text and an output model, and returns completed
  response text for the calling workflow to validate.
- `OpenAIJSONClient` implements that contract. Its constructor captures settings
  without I/O. `generate_json` opens one SDK client, makes one Responses request,
  closes the client, rejects incomplete/failed responses, refusals and blank text,
  then returns the original text. Timeouts become `TimeoutError`; other SDK API
  failures become `RuntimeError`, with fixed messages and no provider details.
- `AnthropicJSONClient` uses the official `anthropic` SDK, locked to 1.17.0.
  Its constructor checks provider selection. `generate_json` calls Messages with
  separate system/user content and `output_config.format`. The SDK's public
  `transform_schema` helper prepares supported constraints without changing our
  original models. Only `end_turn` with non-blank text succeeds; refusals and token
  truncation fail. See [Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
- `OllamaJSONClient` implements the documented
  [non-streaming chat endpoint](https://docs.ollama.com/api/chat) with HTTPX2 2.16.0.
  Its constructor checks provider selection; `generate_json` sends system/user
  messages and the schema as `format`, requires `done=true` and `done_reason=stop`,
  and returns non-blank assistant text. This one-endpoint adapter uses HTTPX2
  directly rather than adding another SDK. It sends no credentials, ignores
  environment proxy settings, follows no redirects and never pulls a missing model.
- `create_json_client(settings)` selects one of these three implementations.
  It performs no I/O and provides no fallback to another provider or model.

SDK retries are disabled. The existing services will remain responsible for
validating generated content and making at most one corrective generation call
when connected in later steps. The network timeout applies to connection, read,
write and pool operations; it is not a total wall-clock deadline for a complete
tool call. Cloud endpoints are explicit; Ollama uses the configured origin. Every
request has no previous conversation history. OpenAI requests no stored response;
that API-specific option is not sent to Anthropic or Ollama. Clients write no
domain records. The token cap maps to OpenAI `max_output_tokens`, Anthropic
`max_tokens`, or Ollama `options.num_predict`; an exhausted cap is a failure.
Ollama has no separate refusal flag in this endpoint; generated-content validation
remains essential. Its [Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)
support is used with a local server; Ollama Cloud is outside this adapter's scope.

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
Live requests, credentials/model access, business quality, prompt-injection
resistance and selected-host integration have not been verified.

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

For a live check later, the configured local server must already be running with
the selected model installed. Local model compatibility, quality and resource use
remain unverified; these examples establish request/response behavior only.

## Build the package

```bash
uv build
```

This creates a source distribution and a wheel in the ignored `dist/` directory.

## Project guidance

- [Product scope and requirements](docs/PROJECT_CONTEXT.md)
- [MVP system design](docs/SYSTEM_DESIGN.md)
- [Contributor agreement and implementation checklist](AGENTS.md)

Implementation proceeds in small, explicitly authorized steps. Dependency
requirements are declared in `pyproject.toml`; `uv.lock` records the resolved
versions for reproducible development installs.
