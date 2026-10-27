# Catalyst

Catalyst is being built to turn business text into a saved Business Artifact,
then generate a saved Use-case Catalog linked to that artifact through MCP.

The repository currently contains a Python package with a placeholder command,
a development setup, and validated Business Artifact and Use-case Catalog models
with contract tests. Business Artifacts and Catalogs can be saved, read and listed
through a SQLite repository, with Catalog source associations enforced by a
foreign key. Business Artifacts have a deterministic Markdown renderer. Catalog
rendering, MCP tools, resource readers and model integration are not implemented yet.

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
round trips, process restart persistence and failure rollback. Business Artifact
Markdown tests parse the output as CommonMark and verify content preservation,
escaping, completeness and determinism. These local tests do not call a fake or
live model provider or connect to an MCP host.

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

The class validates the supplied text. Generation and saving belong to later
steps. Blank text and undocumented fields raise a Pydantic `ValidationError`.

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
Catalog rendering and the MCP Markdown routes remain later steps.

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
