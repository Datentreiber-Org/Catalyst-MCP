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
- Name domain-specific test files `test_<domain>_<component>.py`. Use the short domains `artifact` and `catalog`, with singular component names such as `model` and `repository`: for example, `test_artifact_model.py` and `test_catalog_repository.py`. Follow this convention for future domain-specific tests as well.
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

The repository contains strict Business Artifact and Catalog models, SQLite persistence and deterministic Markdown renderers for both record types, with tests and a uv development setup. Catalog source associations are enforced through a foreign key and checked against stored JSON on reads. Both generation services validate requests and scripted fake-provider output, allow one corrective attempt, assign metadata and return complete committed records. Analysis defaults to a configurable 20,000-character limit. Ideation loads its saved source before generation, defaults to a configurable maximum of 10 ideas, checks the exact count and every alignment against the named source section, and preserves the source. The official MCP SDK 2.3.0 exposes both tools and canonical JSON resources over local stdio. Resource listing is deterministic and reads return complete saved JSON as `application/json` without provider calls or data changes. The command requires an explicit database path and accepts independent optional analysis (`--fake-response`) and ideation (`--fake-ideation-response`) scripts. It logs to stderr and supports ideation-only startup or JSON resource access with no scripts. The complete two-tool fake-provider flow and JSON reads after restart are verified. Markdown resource routes/links, live model integration, environment-based runtime settings and provider deadlines remain unimplemented; selected-host integration remains unverified. See the product document for open implementation choices.

## Implementation checklist

Steps 1 through 12 are authorized and complete. The user authorized and completed step 10 before returning to step 9. All unchecked steps require explicit authorization. Add only the dependencies, configuration, documentation, and tests needed by each authorized step.

Step 1 verification: Python 3.12.2, pytest 9.1.1, locked environment sync, package import, source-distribution and wheel builds, and placeholder command execution were verified. At that step, pytest collected zero tests and returned exit code 5 because no application tests existed yet.

Step 2 verification: all 158 Business Artifact contract test cases passed with Python 3.12.2, pytest 9.1.1 and Pydantic 2.14.1. Locked environment sync, source-distribution and wheel builds, and concrete input/artifact validation examples succeeded. Tests cover strict input and section types, required fields, metadata consistency, exact JSON shapes and content-preserving JSON round trips. These are local schema tests; fake-provider, live-model and host-integration checks have not been performed. Configurable input-size enforcement remains part of the later analysis workflow.

Step 3 verification: 124 new ideation and Catalog contract cases passed alongside the 158 existing cases, for 282 passing tests on the same Python, pytest and Pydantic versions. Source-distribution and wheel builds, ideation-input and complete Catalog examples, and JSON round trips succeeded. Checks cover optional input focus, positive strict counts, alignment structure, required content, metadata boundaries, unique case IDs and the absence of a Catalog URI field. These remain local schema checks; no provider or host integration was tested. The configurable upper count limit, exact requested count and matching references against a saved source artifact remain unimplemented.

Step 4 verification: 21 new repository cases passed alongside the 282 existing cases, for 303 passing tests with SQLite 3.46.0 on the same Python, pytest and Pydantic versions. Tests use real temporary SQLite files and verify a separate Python process can retrieve saved JSON. They cover complete save/read/list results, duplicate-ID rejection, invalid mutated inputs, special characters, unchanged JSON and timestamps after reads, row/payload ID consistency, and rollback on a deferred constraint failure at commit. Source-distribution and wheel builds and the complete README storage example succeeded. These are local schema and repository checks; fake-provider, live-model and MCP-host checks remained unperformed. Catalog storage was deferred to step 5.

Step 5 verification: 23 new Catalog repository cases passed alongside the 303 existing cases, for 326 passing tests on the same Python, SQLite, pytest and Pydantic versions. Checks cover adding the Catalog table to a step-4 database, complete save/get/list results, source foreign-key enforcement, missing sources, duplicate Catalog IDs, invalid mutated inputs, Catalog/source ID mismatches, unchanged JSON and timestamps after reads, cross-process persistence and failed-commit rollback. Both README storage examples ran successfully. These are local schema and real SQLite repository checks; no fake-provider, live-model or MCP-host checks were performed. Source lookup before generation, exact alignment matches and requested-count checks remain unimplemented.

Step 6 verification: 58 new Business Artifact Markdown cases passed alongside the 326 existing cases, for 384 passing tests. CommonMark parsing with development dependency markdown-it-py 4.2.0 verifies all five metadata values, all 12 sections, explicit empty sections, array order, duplicate and long statements, literal Markdown/HTML, Unicode and preserved whitespace. Rendering is identical after repeated calls and a separate-process read; saved JSON, timestamps and files remain unchanged. The README storage/rendering examples, source-distribution and wheel builds, and wheel inclusion of the renderer succeeded; the parser is not a runtime wheel dependency. At that step, MIME types, MCP routes, Catalog rendering and host display had not been implemented or verified. No provider calls were made.

Step 7 verification: 23 new Catalog Markdown cases passed alongside the 384 existing cases, for 407 passing tests on the same Python, Pydantic, pytest and Markdown parser versions. Parsed CommonMark verifies complete Catalog metadata, computed source URI, all cases, target users, solutions and alignment entries in saved order, exact section keys, empty target-user lists, literal text, long content and duplicate entries. Rendering is deterministic after JSON reloads and a separate-process read, with Catalog/source JSON, timestamps and saved files unchanged. All README storage and rendering examples ran successfully. The Catalog and its source reference still have no added URI field. MIME types, MCP routes and host display remain unimplemented and unverified; no provider calls were made.

Step 8 verification: 34 new analysis service cases passed alongside the 407 existing cases, for 441 passing tests. They use a scripted fake provider and real temporary SQLite files to verify complete committed results, UUID4 IDs and UTC metadata, repeated creation, strict input validation, default and configured character limits, one corrective attempt with fixed feedback, insufficient-content errors, provider failures and rollback on a real commit failure. The existing empty-model contract test now checks its distinct error code. All seven README Python examples ran in a temporary directory. Source-distribution and wheel builds succeeded; both contain the new analysis modules, which also import directly from the wheel. No dependencies were added. The fake returns supplied JSON and establishes orchestration only; live extraction quality, real-model prompt-injection resistance, provider deadline enforcement and MCP-host integration remain unimplemented or unverified.

Step 9 verification (performed after step 10): 67 new Catalog service cases passed alongside the 468 existing cases, for 535 passing tests. Scripted fake providers and real temporary SQLite files verify complete committed Catalogs, UUID4 metadata, exact source associations, optional focus preservation, default/configured count limits, references to all 12 sections and rejection of case/whitespace/Unicode near-matches. Checks cover every case/alignment, one fixed corrective attempt, missing/corrupt source rejection before generation, provider failure propagation, repeated creation, cross-process retrieval, unchanged source JSON/timestamps and rollback on a real deferred commit failure. All nine README Python examples ran successfully in a temporary directory. No dependencies were added and package builds were not rerun in this step. These checks establish orchestration and valid references with a fake; ideation exposure through MCP, semantic focus compliance, idea/rationale quality, live-model behavior and selected-host compatibility remain unimplemented or unverified.

Step 10 verification: 27 new analysis MCP cases passed alongside the 441 existing cases, for 468 passing tests with official MCP SDK 2.3.0. SDK-client checks verify exact discovery schemas, complete structured/JSON results, strict arguments and size limits, unregistered names, fixed provider-failure messages, insufficient-content failures and a real deferred SQLite commit rollback. Real console subprocesses verify MCP initialization with protocol 2025-06-18, discovery, calls, bounded correction, exhausted scripts, restart persistence, startup errors on stderr and JSON-RPC-only stdout. Imports start no server or database. All eight README examples, locked environment sync and source-distribution/wheel builds succeeded. The built packages contain the new server and entry point; direct wheel imports and its declared MCP dependency were checked. These were local protocol checks with a scripted fake, not live-model or selected-host integration checks. At that point, step 9, ideation exposure, resource routes/links, real provider integration and provider deadlines remained unimplemented.

Step 11 verification: 36 new Catalog MCP cases and three full stdio-flow cases passed alongside the 535 existing cases, for 574 passing tests. Checks verify two-tool discovery, exact schemas, strict ideation arguments and default count bounds, preserved focus, complete committed Catalog results, missing/corrupt source handling, bounded correction, independent scripts and real failed-commit rollback. A distinct missing-source exception preserves `LookupError` compatibility and prevents provider lookup errors from being mislabeled. Real stdio subprocesses verify analysis followed by ideation with the returned artifact ID, persistence of both records, ideation-only restart, unchanged source data, rejected count/alignment output and JSON-RPC-only stdout with fixed stderr diagnostics. All ten README Python examples ran in a temporary directory and `git diff --check` passed. No dependencies were added or package builds rerun in this step. These are fake-provider and local MCP protocol checks; resource routes/links, real adapters/prompts, deadline enforcement, live-model quality and selected-host compatibility remain unimplemented or unverified.

Step 12 verification: 40 new JSON resource cases and one new stdio restart case passed alongside the 574 existing cases, for 615 passing tests. Discovery/read checks verify empty and mixed sets, deterministic ordering, complete saved values and literal text, canonical URI matching, correct `application/json` MIME types, no Catalog URI field, current listings after saves, and zero provider calls. Repeated resource access preserves raw stored JSON, domain timestamps, database bytes and files. Missing/unsupported URIs and cursors return fixed `-32602` errors; corrupt records, inconsistent stored IDs/source associations and real database failures return fixed `-32603` errors without repair, partial listings or sensitive diagnostics. Existing full stdio flow checks now read created resources; a new check restarts the console command with no scripts and reads both complete records, including actual protocol-error responses. All eleven README Python examples and `git diff --check` passed. No dependencies were added or package builds rerun. These are repository and local MCP protocol checks; generation in the flow still uses scripted fakes. Markdown MCP routes/links, live-model behavior and selected-host compatibility remain unimplemented or unverified.

- [x] 1. Verify Python 3.12+, repair package metadata's missing README, and establish the test setup.
- [x] 2. Define and test Business Artifact input, generated-content, and saved-object models.
- [x] 3. Define and test ideation input, generated-content, alignment, and Catalog models.
- [x] 4. Add atomic Business Artifact storage, retrieval, and listing in SQLite.
- [x] 5. Add Catalog storage, retrieval, and listing with enforced source associations.
- [x] 6. Render complete, deterministic Business Artifact Markdown.
- [x] 7. Render complete, deterministic Catalog Markdown.
- [x] 8. Implement analysis generation, validation, bounded correction, and saving with a fake provider.
- [x] 9. Implement ideation from a saved artifact with exact count and alignment validation using a fake provider.
- [x] 10. Start the stdio MCP server and expose the analysis tool with complete saved-object results.
- [x] 11. Expose the ideation tool and verify the two-tool flow with a fake provider.
- [x] 12. Advertise and read canonical JSON resources for both saved object types.
- [ ] 13. Advertise and read Markdown resources and add links to both views in tool results.
- [ ] 14. Configure and test one real LLM-provider adapter and the runtime settings it needs.
- [ ] 15. Connect the analysis prompt to the real provider adapter.
- [ ] 16. Connect the ideation prompt to the real provider adapter.
- [ ] 17. Verify restart persistence and the complete flow; separately assess live-model quality and selected-host compatibility.
