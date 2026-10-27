# Catalyst

Catalyst is being built to turn business text into a saved Business Artifact,
then generate a saved Use-case Catalog linked to that artifact through MCP.

The repository currently contains a Python package with a placeholder command,
a development setup, and validated Business Artifact and Use-case Catalog models
with contract tests. Business Artifacts can be saved, read and listed through a
SQLite repository. Catalog persistence, MCP tools, resource readers and model
integration are not implemented yet.

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
complete Business Artifact and Catalog shapes, plus Business Artifact persistence
in real temporary SQLite files. They check strict types, all 12 business-model
sections, alignment structure, metadata consistency, JSON round trips, process
restart persistence and failure rollback. These local tests do not call a fake
or live model provider or connect to an MCP host.

- `tests/test_business_artifact.py` covers analysis input and Business
  Artifact validation.
- `tests/test_use_case_catalog.py` covers ideation input,
  alignment entries and Use-case Catalog validation.
- `tests/test_repository.py` covers Business Artifact storage, reads, listing,
  restart persistence and failure atomicity.

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
directory and Business Artifact table if needed. With a new database, this
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
