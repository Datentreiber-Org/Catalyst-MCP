# Catalyst contributor guidance

## Project references

Read [Product scope and requirements](docs/PROJECT_CONTEXT.md), the
[system design](docs/SYSTEM_DESIGN.md) and the
[web-app implementation plan](docs/WEB_APP_PLAN.md) before making implementation
changes. The MVP contracts remain the compatibility baseline. The web-app plan
defines the proposed post-MVP work on `feature/web-app`; keep all three documents
consistent as decisions are made.

The [development guide](docs/DEVELOPMENT.md) covers modules, configuration, tests
and builds. Complete runnable Python/MCP examples and expected outputs are in
[the examples guide](docs/EXAMPLES.md); the README remains the public entry point.

## Incremental working agreement

- Build Catalyst in small steps that the user can comfortably review and understand. The checklist below is a proposed sequence, not authorization to implement it.
- Before editing code for a step, explain its purpose, the files involved, and how it will be verified. Resolve any contract decisions needed for that step before encoding them.
- Implement only the step the user explicitly authorizes. Keep the code straightforward and add only what that step needs; do not scaffold future features. Split a step that would become too large to review and obtain authorization for the smaller scope before implementing it.
- After implementation, explain every new function or class and demonstrate at least one concrete input-to-output example for the step.
- Run the relevant checks, report the results actually observed, and state what remains unimplemented. Distinguish fake-provider tests, live-model checks, and host-integration checks.
- Stop after each step and wait for explicit authorization before implementing the next one. Questions about current code, explanations, and discussion of the plan do not authorize further implementation.
- Maintain the short checklist below as work progresses. Check an item only when its scope is implemented and verified; record any verification limitations alongside its status. Keep the project documents consistent with decisions and actual behavior.
- Do not commit or push automatically.

## Branch goal and compatibility contracts

On `feature/web-app`, plan and incrementally implement the V37-B workflow:

`company URL + optional document → retained evidence → analyzed model → user-reviewed saved snapshot + optional answers → ten aligned cases + three selections → exploration and downloads`.

Keep the existing text-based MCP flow working independently of the web app:

`business text → analyze-business-model → saved Business Artifact → ideate-use-case → saved Use-case Catalog`.

- Preserve the documented payloads, including `ideate-use-case` (singular), `targetUsers`, and all 12 business-model sections.
- Return the complete saved artifact or catalog from each tool.
- The Business Artifact payload includes `uri`. Construct the Catalog resource URI in the MCP layer without requiring a Catalog `uri` field.
- Add web requirements through explicit new/versioned contracts. Do not silently
  add required fields, output caps or editing behavior to existing MCP payloads.
- V37-B's Job A `1.2` and Job B `1.3`/variant `B` are application contract
  versions, not MCP protocol versions. Resolve specification disagreements before
  implementing their affected steps.
- The checklist is planning, not blanket authorization to implement it. Only
  documentation planning is authorized by the request that created this list.

## Implementation guidance

The baseline uses one Python backend, the official MCP SDK, Pydantic, SQLite,
local stdio and LLM-provider adapters. Reuse the backend services for the web
workflow. Choose browser transport, frontend tooling, richer record contracts
and deployment policy in the plan's decision steps before implementation.

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
- Keep core Python/MCP installation usable without frontend tooling. Place the
  frontend in a separate application directory once its first step is authorized.
- Never substitute demo fixtures for a failed live request or represent a typed
  URL, user amendment or model hypothesis as verified website evidence.
- Generate and rank only against the approved active model snapshot. Preserve
  inactive items, revisions, evidence associations and the selected source.
- Keep secrets and trusted metadata server-side. Treat fetched text, files,
  answers, edited items and critic output as untrusted data.
- Do not transmit feedback/contact details or publish/deploy the app without
  explicit authorization. Local optional feedback is the reference behavior.

## Verification and reporting

- Verify output shapes, persistence across restart, source links, alignment validation, requested idea counts and failure atomicity.
- Verify both resource formats, complete and deterministic Markdown rendering, correct MIME types, handling of special characters, and unchanged data and timestamps after reads.
- Distinguish tests with a fake provider from live-model and host-integration checks.
- Report the checks actually performed and any remaining limitations. Do not describe planned behavior as implemented.
- Keep changes within the requested scope and preserve unrelated work.
- Verify frontend/backend schema and Unicode-limit parity, stale response
  rejection, inactive-item exclusion, access isolation, deadlines and retry bounds.
- Verify all ten cases, three consistent selections and complete exports against
  the saved result's snapshot, including Unicode and literal special characters.
- Separate fake-provider, mocked retrieval/HTTP, real browser, live-model,
  MCP-host and deployment checks. The prototype's QA reports do not verify this
  branch. Record actual commands, outcomes and remaining limitations per step.

## Baseline and current status

The existing backend implements both MCP tools, strict models, exact source
alignment, atomic SQLite persistence, deterministic JSON/Markdown resource reads,
and OpenAI/Anthropic/Ollama adapters. Automated evidence uses fake providers and
mocked HTTP; limited OpenAI live-model and Codex desktop checks are recorded in
the [MVP history](docs/MVP_IMPLEMENTATION_HISTORY.md). Their limitations remain.

The V37-B package is an ignored local offline prototype. Its reported QA is
reference material, not verification of a live web integration. No web-app task
below is implemented or verified by the planning changes. Keep the MVP history
as a historical record rather than repeating its completed checklist here.

## Web-app implementation checklist

Details, dependencies, likely files and completion checks for every task are in
[WEB_APP_PLAN.md](docs/WEB_APP_PLAN.md). Each checkbox is a separate authorization
and review unit. Split further before coding if a unit becomes too large.
Do not skip the decision gates or mark a task complete on fake checks when its
specified live/browser/deployment acceptance remains outstanding.

- [ ] W01. Inventory existing UI files/assets and curate licensed references, synthetic fixtures and tracked requirements.
- [ ] W02. Decide application boundaries, browser transport, deployment target and access policy.
- [ ] W03. Reconcile and specify Job A/B, upload, status, read and error wire contracts.
- [ ] W04. Decide evidence, edited-snapshot, identity, revision and MCP compatibility semantics.
- [ ] W05. Decide quality/call budgets, export location, Unicode support and release acceptance.
- [ ] W06. Record the baseline and establish only the verification tooling needed next.
- [ ] W07. Implement strict evidence, questionnaire and editable-model input schemas.
- [ ] W08. Implement rich-case/result schemas and shared V37-B output limits.
- [ ] W09. Add versioned persistence for evidence and uploaded-source metadata.
- [ ] W10. Persist reviewed model/answer revisions and immutable source snapshots.
- [ ] W11. Persist complete rich results, source links and wire/backend case-ID mappings.
- [ ] W12. Implement session/access isolation and the selected web request protections.
- [ ] W13. Implement protected URL normalization and reachability checking.
- [ ] W14. Implement bounded website retrieval and evidence extraction.
- [ ] W15. Implement protected document upload and genuine file references.
- [ ] W16. Implement bounded PDF extraction and failure handling.
- [ ] W17. Implement bounded PPT/PPTX extraction and failure handling.
- [ ] W18. Assemble traceable, bounded website/document evidence for generation.
- [ ] W19. Implement evidence-based Job A with all twelve bounded model sections.
- [ ] W20. Validate and save the approved edited model used by Job B.
- [ ] W21. Generate ten rich, aligned cases and matching compact representations.
- [ ] W22. Select three Next Best cases with consistent, bounded explanations.
- [ ] W23. Add independent content criticism and one bounded Job B repair path.
- [ ] W24. Implement correlated jobs, deadlines, cancellation, safe retries and restart outcomes.
- [ ] W25. Expose browser endpoints and complete saved-result reads through thin handlers.
- [ ] W26. Render complete deterministic web-report Markdown from saved results.
- [ ] W27. Produce complete, literal-text-safe XLSX downloads.
- [ ] W28. Produce and visually verify the thirteen-page Unicode-capable PDF report.
- [ ] W29. Migrate the existing UI into the tracked frontend directory, then implement navigation states and the company-information step.
- [ ] W30. Implement the three optional questions during Job A.
- [ ] W31. Implement the twelve-box model editor and approved-snapshot submission.
- [ ] W32. Implement the integrated ten-case selector and eight-field focus view.
- [ ] W33. Connect downloads and print controls to the correct saved revision.
- [ ] W34. Implement optional browser-local feedback/contact preferences without transmission.
- [ ] W35. Apply reviewed branding and the agreed standalone/embedding/fullscreen behavior.
- [ ] W36. Verify responsive layouts, accessibility and declared browser/device support.
- [ ] W37. Complete runtime configuration, cleanup, cost/resource bounds and deployment protections.
- [ ] W38. Verify integrated fake/mocked flows, hostile inputs, faults and MCP/storage compatibility.
- [ ] W39. Evaluate an authorized live-provider flow and business-content quality separately.
- [ ] W40. Finish open-source packaging, reproducible setup, CI and operator/contributor documentation.
- [ ] W41. Complete user acceptance and the selected deployment release gate; record exclusions.
