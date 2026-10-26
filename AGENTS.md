# Catalyst contributor guidance

## Project references

Read [Product scope and requirements](docs/PROJECT_CONTEXT.md) and the [MVP system design](docs/SYSTEM_DESIGN.md) before making implementation changes. The product document defines the MVP scope; the system design records a proposed implementation. Keep both documents consistent as decisions are made.

## Goal and contracts

Implement this complete flow:

`business text → analyze-business-model → saved Business Artifact → ideate-use-case → saved Use-case Catalog`.

- Preserve the documented payloads, including `ideate-use-case` (singular), `targetUsers`, and all 12 business-model sections.
- Return the complete saved artifact or catalog from each tool.
- The Business Artifact payload includes `uri`. Construct the Catalog resource URI in the MCP layer without requiring a Catalog `uri` field.
- Keep additional required fields and capabilities outside the documented MVP scope unless the requirements change.

## Implementation guidance

The proposed implementation uses one Python backend, the official MCP SDK, Pydantic, SQLite, local stdio and an LLM-provider adapter. These are design recommendations; document alternatives and their rationale before departing from them.

- Follow the existing `src/catalyst_mcp/` package layout and Python requirements in `pyproject.toml`.
- Assign IDs, resource URIs, timestamps and source associations in backend code.
- Expose each saved Business Artifact and Use-case Catalog as both JSON and an on-demand Markdown view.
- Keep stored JSON as the source of truth. Render Markdown deterministically without another model call, a separately stored document, or a change to the saved record.
- Preserve the existing tool payloads and canonical JSON URIs; advertise Markdown through separate resource URIs and links.
- Validate generated content before saving and return success only after an atomic commit.
- Treat supplied business content as data, not instructions that override the generation task.
- Verify SDK APIs against official documentation when selecting dependencies.
- With stdio transport, send logs to stderr and reserve stdout for MCP messages.
- Keep credentials, real business inputs and generated customer records out of source files, fixtures and documentation. Use synthetic examples for public tests and examples.
- Keep modules in one application and record material decisions and run instructions in the repository.

## Verification and reporting

- Verify output shapes, persistence across restart, source links, alignment validation, requested idea counts and failure atomicity.
- Verify both resource formats, complete and deterministic Markdown rendering, correct MIME types, handling of special characters, and unchanged data and timestamps after reads.
- Distinguish tests with a fake provider from live-model and host-integration checks.
- Report the checks actually performed and any remaining limitations. Do not describe planned behavior as implemented.
- Keep changes within the requested scope and preserve unrelated work.

## Implementation status

The repository currently contains Python package scaffolding and a placeholder entry point. MCP tools, resource readers, persistence, model integration and automated tests are not implemented. See the product document for open implementation choices.
