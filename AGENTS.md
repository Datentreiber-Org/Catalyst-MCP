# Catalyst contributor guidance

## Project references

Read [Product scope and requirements](docs/PROJECT_CONTEXT.md) and the [MVP system design](docs/SYSTEM_DESIGN.md) before making implementation changes. The product document defines the MVP scope; the system design records a proposed implementation. Keep both documents consistent as decisions are made.

## Incremental working agreement

- Build Catalyst in small steps that the user can comfortably review and understand. The checklist below is a proposed sequence, not authorization to implement it.
- Before editing code for a step, explain its purpose, the files involved, and how it will be verified. Resolve any contract decisions needed for that step before encoding them.
- Implement only the step the user explicitly authorizes. Keep the code straightforward and add only what that step needs; do not scaffold future features. Split a step that would become too large to review and obtain authorization for the smaller scope before implementing it.
- After implementation, explain every new function or class and demonstrate at least one concrete input-to-output example for the step.
- Run the relevant checks, report the results actually observed, and state what remains unimplemented. Distinguish fake-provider tests, live-model checks, and host-integration checks.
- Stop after each step and wait for explicit authorization before implementing the next one. Questions about current code, explanations, and discussion of the plan do not authorize further implementation.
- Maintain the short checklist below as work progresses. Check an item only when its scope is implemented and verified; record any verification limitations alongside its status. Keep the project documents consistent with decisions and actual behavior.
- Do not commit or push automatically.

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

The repository currently contains a placeholder entry point, a uv development setup, and strict Business Artifact and Catalog models with contract tests. MCP tools, resource readers, persistence, Markdown views, metadata assignment and model integration are not implemented. Source-existence, exact source-element and requested-count checks remain part of the later workflows. See the product document for open implementation choices.

## Implementation checklist

Steps 1, 2 and 3 are authorized and complete. Later steps remain unimplemented and require explicit authorization. Add only the dependencies, configuration, documentation, and tests needed by each authorized step.

Step 1 verification: Python 3.12.2, pytest 9.1.1, locked environment sync, package import, source-distribution and wheel builds, and placeholder command execution were verified. At that step, pytest collected zero tests and returned exit code 5 because no application tests existed yet.

Step 2 verification: all 158 Business Artifact contract test cases passed with Python 3.12.2, pytest 9.1.1 and Pydantic 2.14.1. Locked environment sync, source-distribution and wheel builds, and concrete input/artifact validation examples succeeded. Tests cover strict input and section types, required fields, metadata consistency, exact JSON shapes and content-preserving JSON round trips. These are local schema tests; fake-provider, live-model and host-integration checks have not been performed. Configurable input-size enforcement remains part of the later analysis workflow.

Step 3 verification: 124 new ideation and Catalog contract cases passed alongside the 158 existing cases, for 282 passing tests on the same Python, pytest and Pydantic versions. Source-distribution and wheel builds, ideation-input and complete Catalog examples, and JSON round trips succeeded. Checks cover optional input focus, positive strict counts, alignment structure, required content, metadata boundaries, unique case IDs and the absence of a Catalog URI field. These remain local schema checks; no provider or host integration was tested. The configurable upper count limit, exact requested count and matching references against a saved source artifact remain unimplemented.

- [x] 1. Verify Python 3.12+, repair package metadata's missing README, and establish the test setup.
- [x] 2. Define and test Business Artifact input, generated-content, and saved-object models.
- [x] 3. Define and test ideation input, generated-content, alignment, and Catalog models.
- [ ] 4. Add atomic Business Artifact storage, retrieval, and listing in SQLite.
- [ ] 5. Add Catalog storage, retrieval, and listing with enforced source associations.
- [ ] 6. Render complete, deterministic Business Artifact Markdown.
- [ ] 7. Render complete, deterministic Catalog Markdown.
- [ ] 8. Implement analysis generation, validation, bounded correction, and saving with a fake provider.
- [ ] 9. Implement ideation from a saved artifact with exact count and alignment validation using a fake provider.
- [ ] 10. Start the stdio MCP server and expose the analysis tool with complete saved-object results.
- [ ] 11. Expose the ideation tool and verify the two-tool flow with a fake provider.
- [ ] 12. Advertise and read canonical JSON resources for both saved object types.
- [ ] 13. Advertise and read Markdown resources and add links to both views in tool results.
- [ ] 14. Configure and test one real LLM-provider adapter and the runtime settings it needs.
- [ ] 15. Connect the analysis prompt to the real provider adapter.
- [ ] 16. Connect the ideation prompt to the real provider adapter.
- [ ] 17. Verify restart persistence and the complete flow; separately assess live-model quality and selected-host compatibility.
