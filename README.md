# Catalyst

Catalyst is being built to turn business text into a saved Business Artifact,
then generate a saved Use-case Catalog linked to that artifact through MCP.

The repository currently contains a Python package with a placeholder command,
a development setup, and validated Business Artifact and Use-case Catalog models
with contract tests. Business Artifacts and Catalogs can be saved, read and listed
through a SQLite repository, with Catalog source associations enforced by a
foreign key. Both record types have deterministic Markdown renderers. MCP tools,
resource readers and live model integration are not implemented yet. An analysis
service now validates scripted fake-provider output, assigns metadata and returns
the complete committed Business Artifact.

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

## Run the current placeholder

```bash
uv run --locked catalyst-mcp
```

Expected output:

```text
Hello from catalyst-mcp!
```

The command currently prints this greeting and exits. It does not start an MCP
server yet.

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
escaping, completeness and determinism. Analysis workflow tests use a scripted
fake provider to check input limits, bounded correction, metadata and failure
atomicity. No live model provider or MCP host is exercised.

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

These schemas require a positive idea count. A configurable maximum (initially
proposed as 10), the exact requested result count, source existence and exact
alignment-element matches remain checks for the later ideation workflow.

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

Source existence is enforced when saving. Loading the source before generation,
checking exact alignment-element matches and checking the requested idea count
remain part of the later ideation workflow.

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
The MCP Markdown routes remain later steps.

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
file writes, source lookups or new timestamps. The MCP Markdown routes and host
display remain later integration work.

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

This verifies workflow behavior with a fake. Real analysis prompts, model quality,
provider deadline enforcement, ideation and MCP integration remain later work.

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
