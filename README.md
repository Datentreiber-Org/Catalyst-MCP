# Catalyst

Catalyst is being built to turn business text into a saved Business Artifact,
then generate a saved Use-case Catalog linked to that artifact through MCP.

The repository currently contains a Python package with a placeholder command
and a development setup. MCP tools, resource readers, persistence, model
integration, and application tests are not implemented yet.

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

There are no application tests yet. Until the first tests are added, pytest
reports that no tests were collected and exits with code 5; this is not a passing
test suite. Tests will be added alongside each authorized implementation step.

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
