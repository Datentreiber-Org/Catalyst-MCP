# Web-app implementation plan

Branch: `feature/web-app`

Planning date: 2026-11-07

Status: proposed implementation sequence; no web functionality is established by this document.

The user authorized replacing the MVP checklist with a thorough plan for V37-B's
UI and required backend capabilities. Implementation still requires explicit
authorization for each small step under [AGENTS.md](../AGENTS.md). Planning a
feature does not authorize live provider spending, deployment, contact submission,
commits or pushes. The checkboxes in AGENTS.md are the single active progress
tracker; task definitions here contain scope and completion criteria.

## 1. Target and boundaries

Deliver the five-step V37-B Included Catalog experience:

1. Required company website and optional PDF/PPT/PPTX document.
2. Three optional questions while business-model analysis runs.
3. Review and edit a twelve-box business model, then submit an approved snapshot.
4. Explore ten full use cases with three Next Best selections in an integrated
   selector/focus view, without a separate catalog overview screen.
5. Download all cases and optionally provide browser-local feedback/preferences.

The supporting backend must retrieve actual evidence, preserve its provenance,
save the reviewed source, generate and validate rich results, enforce correlation
and access rules, and make failures recoverable. A typed URL is not evidence;
sample output is not live analysis. Reuse the existing provider adapters,
validation, source-alignment and persistence patterns where compatible.

Keep the existing two-tool MCP interface, canonical JSON/Markdown resources,
create-only records and independent Python installation working. Web-specific
limits, item states and richer fields must not silently change legacy payloads.
Whether new capabilities also receive additive MCP tools/resources is a decision
in W02–W04, not an assumed rewrite of the existing tools.

Out of this branch unless separately requested: organizational hierarchy and
inheritance, general ROI calculation, a full portfolio-scoring product, CRM/email/
newsletter delivery, enterprise identity-provider integrations, variant A, MCP
Apps, and editing existing legacy records in place. V37-B's three-case selection
is in the target scope despite general scoring being outside the original MVP.
The Miro SVGs and editable PPTX are design references, not additional required
product exports. Website evidence extraction does not imply a general RAG system.

## 2. Source inventory and authority

The local proposal directory `Catalyst_V37_B_INCLUDED_CATALOG/` is currently
Git-ignored. A clean public clone does not contain it. W01 must curate approved,
licensed, synthetic source material into tracked documentation/test assets before
implementation relies on it. Do not unignore or publish the whole archive by
default. Record file hashes and any deliberate deviations from the reference.

| Reference inside that directory | Use |
| --- | --- |
| `README.md` | Offline/demo boundary and Included Catalog variant |
| `04_MCP_BACKEND/04_INTEGRATION_GUIDE_V37.md` | Flow, browser APIs, correlation and functional acceptance |
| `04_MCP_BACKEND/01_FIELDS_FORMATS_AND_LIMITS_V37.md` | Field semantics, questions, canvas, export and Unicode requirements |
| `04_MCP_BACKEND/00_VARIANT_LIMITS_V37.json` | Exact numerical budgets |
| `04_MCP_BACKEND/03_RESPONSE_SCHEMA_V37.json` | Job B wire-response structure, subject to reconciliation in W03 |
| `04_MCP_BACKEND/02_MCP_PROMPTS_V37.md` | Generation, selection and independent critic requirements |
| `04_MCP_BACKEND/05_VERSION_MANIFEST_V37.json` | Variant, contract and artifact inventory |
| `01_HTML/index.html`, `07_SOURCE/app.js`, `07_SOURCE/styles.css` | Working offline interactions; extracted files are duplicate review copies |
| `03_EXAMPLES/`, `05_QA/`, `06_SCREENSHOTS/` | Synthetic example/acceptance candidates and visual references |

The proposal's documents and code disagree in places. W03–W05 must record one
approved contract and shared limits, rather than treating whichever file is
convenient as authoritative. Prototype PASS reports are historical evidence of
the offline demo only. Recreate meaningful tests against the implemented app.

## 3. Decisions before dependent code

These are planning gates. Record the selected option and rationale in
[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) and update [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
Routine implementation choices can be made within an authorized step; unresolved
product or compatibility choices must be settled before encoding them.

| Decision | Resolve in | Required outcome |
| --- | --- | --- |
| D01: Application/deployment boundary | W02 | Same repository; separate frontend application, reusable Python services and thin browser interface. Choose local-only, self-hosted or publicly hosted first release, supported runtime/OS, frontend toolchain and whether handlers invoke services directly or an MCP bridge. Public hosting needs a separate release gate. |
| D02: Web access and storage policy | W02, W04 | Define anonymous/session or authenticated access, session expiry, origin/cookie/CSRF/CORS policy as applicable, upload/result authorization, retention/deletion and disk/concurrency bounds. A multiuser public service is not implied by a local demo. |
| D03: Complete application envelopes | W03 | Specify URL-check, upload, Job A/B request/acknowledgment/status/result/cancel/read/error shapes and HTTP behavior. Decide who creates job IDs and when; reconcile `sources[]` versus normalized URL/upload tokens; include evidence refs and correlations. Job A remains application `1.2`; Job B is `1.3` plus `variant_id: B`. |
| D04: Rich records and legacy mapping | W04 | Decide new/versioned models and storage, durable globally unique IDs versus wire `UC-01`…`UC-10` labels, approved snapshot/sourceArtifact mapping, optional additive MCP exposure, migration/rollback and complete JSON/Markdown views. Do not discard exact source alignment. |
| D05: Evidence and editing semantics | W04 | Distinguish retrieved fact, attributed uncertainty, user amendment and proposed hypothesis; specify item IDs/order/status, revision increments, deleted versus disabled items, source association, all-empty/all-inactive behavior, conflict handling and restart/resume policy. Do not silently claim edits were found on a website. |
| D06: Rich-field and validation discrepancies | W03, W05 | Decide whether all five evidence/context metadata fields are required; align schema, prompt and browser validation. Define trimming without changing legacy accepted text, Unicode code-point lengths and strict unknown-field/mode checks. |
| D07: Quality and generation budget | W05 | Decide how Job B generation/selection are combined, independent critic invocation and structured findings, one total Job B repair allowance, whole-result revalidation, maximum calls/tokens/time/cost, refusal/truncation behavior and supported model capability. Specify Job A's separate correction budget; do not share an allowance across independently submitted jobs or nest existing correction loops into more retries. |
| D08: Export execution and character support | W05 | Choose browser or server execution per format, a saved report projection, supported Unicode scripts/font coverage/shaping and safe unsupported-text handling, complete content, MIME/filenames and deterministic rendering expectations. PDF fidelity needs visual checks whichever side generates it; do not promise every Unicode script without testing it. |
| D09: UI and integration scope | W02, W05 | Confirm V37-B layout/copy, browser/device and accessibility targets, branding configuration, standalone and/or embedded widget support. Fullscreen is optional. Feedback/contact stays local unless transmission is separately authorized. |
| D10: Retry, recovery and release evidence | W05 | Define duplicate submission/idempotency behavior, interrupted-job outcomes, resume versus explicit expiry, last-valid-result/stale display, evidence required for local and hosted releases, and which live providers will actually be evaluated. |

## 4. Reviewable task sequence

Each row is a separate authorization unit with a concrete deliverable. File areas
are proposed, not permission to scaffold unused modules. Select exact filenames
when starting the task. If a task spans too many changes to review comfortably,
split it and obtain authorization for the smaller scope. Dependencies identify
prerequisites; the user may authorize a different order when those are met.
Every code step includes a synthetic input-to-output demonstration and relevant
tests; a final integration task does not replace per-step verification.

Prefer an early local website-only vertical slice over waiting for every document
converter. Before coding, W18/W19 may be split into explicitly authorized
website-only assembly/analysis and later document enrichment; the first slice
needs website retrieval, source persistence, schema and access prerequisites but
not PDF/PPT extraction. Frontend transport can similarly be reviewed against an
explicit fake provider. Parent tasks remain unchecked until their full stated
dependencies and acceptance pass; a demo must never be substituted in live mode.

### A. Requirements and contract gates

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W01 | None | Inventory the existing HTML/CSS/JS, embedded logo and other assets with proposed destinations/dispositions. Curate the reference inventory, asset provenance/licensing and synthetic fixtures in `docs/` and test assets. Capture required copy/options and known demo defects below. | Every runtime source/asset has a migration disposition; all reference categories mapped to this plan; clean-clone readers can inspect tracked requirements; no private inputs or unreviewed bulk binary import. |
| W02 | W01 | Document D01/D02/D09 architecture, deployment/access boundary and frontend tooling in the design/development guides. Keep Python/MCP independent of frontend builds. | One concrete launch/request/data-flow design, exposure decision and dependency rationale; identify decisions requiring the user. No runtime claims. |
| W03 | W02 | Specify complete strict web contracts and errors, shared limits, metadata requiredness and correlation lifecycle in tracked schemas/docs. | Valid/invalid synthetic Job A/B, URL-check, upload, status/read/cancel/error examples; every field accounted for; wrong variant/version/mode/IDs/revisions rejected by the agreed rules. |
| W04 | W03 | Specify evidence, snapshot/answers, rich result identity, provenance and legacy compatibility/storage decisions. | Worked example from original model through edit/disable/reorder to saved source and aligned cases; duplicate text, all-inactive input, old DB and restart outcomes defined. |
| W05 | W04 | Specify critic/repair budgets, safe retries, export execution, Unicode policy, browser/accessibility matrix and release acceptance. | Call-count/deadline diagram, refusal/failure examples, approved export content matrix and named local/public release gates; unresolved policy is recorded rather than guessed in code. |
| W06 | W01 | Record current backend verification and establish only the test/build tooling needed by the next authorized step (`pyproject.toml`, test configuration; frontend lockfile when first needed). | Existing relevant tests/builds run with actual results recorded; reproducible offline/fake test commands; no API key or database required to run public tests. |

### B. Contracts and durable data

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W07 | W03, W04, W06 | Strict evidence/source, questionnaire and editable twelve-box model input models in the Python package and shared contract assets. | Types/extra fields, valid question/option IDs, 0–3 choices including custom, 90 code points, initial item identity/order/active state, caps, malformed snapshots and agreed empty policy tested. |
| W08 | W03, W04, W05, W06 | Rich generated-case, selection, complete-result and wire-envelope models; one machine-readable set of V37-B limits for Python/browser. | Full/compact fields, exact ten-ID set, exact three selections, flags/reasons equality, code-point boundaries, whitespace, metadata, mode/versions and extra-field rejection tested; legacy schemas unchanged. |
| W09 | W04, W07 | Versioned persistence for source metadata and retained evidence, with approved file-storage references and migration handling (`repository`/new focused modules). | Old database opens without data loss; retained excerpts/source hashes and associations survive a new process; failed commit rolls back; internal file paths are not public tokens. |
| W10 | W09, W07 | Persistence for model edits, answer revisions and immutable approved snapshots. | Stable IDs/order, active/inactive/deleted semantics, user-amendment provenance, stale revision conflict, restart retrieval and failed-commit atomicity tested; old artifacts unchanged. |
| W11 | W10, W08 | Complete rich-result persistence and read services, source/evidence associations and global/wire case-ID mapping. | Full JSON round trip across restart, duplicate-ID/association rejection, exact snapshot link, transactional rollback and unchanged timestamps on reads; no orphan or partially saved result. |
| W12 | W02, W03, W06 | Selected session/access enforcement and request protections in the web runtime. | Policy-level tests cover ownership, expiry, tampered tokens, allowed origins and cookie/CSRF protections as applicable. Apply the policy to upload/job/snapshot/result routes as those arrive; full cross-session route checks are required in W25/W38. Credentials never appear in client assets or responses. |

### C. Website and document evidence

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W13 | W07, W12 | URL normalization and protected reachability service. | Bare domain/HTTP(S), credentials/ports/schemes, invalid URLs, private/loopback/link-local IPv4/IPv6, redirects and DNS rebinding covered with mocked resolution/HTTP. Checker unavailable differs from unreachable and from evidence retrieved. |
| W14 | W13, W09 | Bounded website retrieval/extraction retaining labeled source excerpts. | Allowed pages, redirect rechecks, byte/page/decompression/time budgets, unsupported MIME, malformed/empty content and partial failure; retained excerpt matches source reference; no URL-only citation. |
| W15 | W07, W09, W12 | One optional upload, genuine opaque file reference and protected file handling. | Agreed 10 MiB/reference policy, zero-byte/type/MIME/signature mismatch, malicious filename/path traversal, malware-control policy, expired/foreign references and cleanup on failed upload tested. No file execution. |
| W16 | W15 | PDF text extraction behind explicit resource/time limits. | Synthetic normal, Unicode, encrypted/corrupt/empty/scanned-only and oversized PDFs; page/excerpt provenance, parser failure and temporary-file cleanup. OCR is not silently assumed. |
| W17 | W15 | PPT and PPTX extraction with the selected parser/converter isolation. | Both claimed formats actually tested, slide/order provenance, Unicode, corrupt/encrypted/empty files, decompression/converter limits and cleanup. If a format cannot ship, obtain an explicit scope change and change UI/docs together. |
| W18 | W14, W16, W17 | Evidence assembly from website and optional document, preserving trust/source labels and generation input budgets. | Website-only, mixed sources, contradictions, partial failure and no-usable-evidence examples; deterministic source associations and explicit limits, no hidden truncation or fallback fixtures. |

### D. Generation, review and browser services

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W19 | W18, W10, W07 | Job A generation bridge and service using configured clients, packaged prompt and strict model validation. | All 12 categories, caps, backend-assigned item IDs/metadata and evidence links saved; missing facts/uncertainty follow D05. Fake/mocked-provider failure/refusal/truncation/injection and no-partial-save paths; no LLM metadata trusted. |
| W20 | W19, W10 | Approved edited-snapshot service for add/edit/move/delete/disable/reorder and answer association. | Edits increment revisions; stale/foreign writes rejected; inactive items retained but excluded from effective source; duplicate-text identity maintained; late Job A cannot overwrite amendments; saved source used by subsequent generation. |
| W21 | W20, W08, W11, W05 | Rich ideation provider/service producing transient drafts of ten distinct proposals with eight full and eight editorial compact fields, context and exact model alignment. | Exact count, complete/consistent fields, approved active source, no invented evidence and bad alignment/count/length handling; source unchanged, no final Catalog saved before W23's quality gate. The existing auto-saving ideation service cannot be reused unchanged for this draft stage. Exercise configured client paths with mocked HTTP where supported; report actual limits. |
| W22 | W21 | Three-case selection and bounded individual explanations on the transient draft, using only approved active evidence and confirmed answers. | Exactly three unique existing IDs, matching flags and identical case/map reasons; zero/one/many/custom/maximal answers, no fabricated personalization and inactive-item ranking regression. No final domain result published yet. |
| W23 | W22, W05 | Independent content critic, structured findings and a single orchestrated Job B correction/repair budget. | Critic checks in section 6, no automatic acceptance of model criticism as fact/instructions, fixed/validated findings, at most one repair across Job B generation/selection/criticism, complete revalidation and atomic final publication; failures return actionable errors. Job A has a separately defined budget. Fake/mocked tests count every model call. |
| W24 | W12, W19, W23, W03 | Job execution/state and correlation, overall deadlines/cancel, retry deduplication and interrupted-job recovery policy. | Session/job/revision mismatch, concurrent edits, duplicate POSTs, out-of-order completion, timeout/cancel/expiry and server restart tested. No endless running state or late successful publication; retries do not accidentally duplicate charges/results under the selected policy. |
| W25 | W24, W13, W15, W11 | Thin browser handlers for agreed endpoints, status/results/cancel and protected complete saved reads. | HTTP contract tests plus fake-provider browser-API flow; upload/source/snapshot association, safe errors, status codes/MIME and result commit ordering; no provider call or data mutation on reads. Existing stdio discovery/calls/resources still pass. |

### E. Saved views and exports

Location is selected in W05. An export implemented in the browser does not need
a redundant backend export endpoint. All formats consume the same saved result
and its approved snapshot, not mutable current inputs against an older result.
The web's compact fields are generated content, not replacements for the complete
legacy Markdown resources.

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W26 | W11, W23, W05 | Shared report projection and complete deterministic web-report Markdown, plus approved JSON/Markdown access for new saved types. | All cases/full+compact fields, metadata, source links, BMC states/revisions and selections preserved; Markdown/HTML metacharacters, Unicode/whitespace and links safe; no model call, writes or new timestamps on reads/exports. |
| W27 | W26 | XLSX export with all ten cases, full+compact fields, source basis and selection explanations. | Reopen actual file: ten data rows and complete expected values; cells containing `=`, `+`, `-`, `@` remain literal text; Unicode, MIME, variant filename and no truncation. No need for contact/feedback. |
| W28 | W26 | A4 landscape report and fonts implementing the exact thirteen-page layout. | Render actual PDF: combined cover/inputs + BMC + ten focus pages + continuation/contact; all ten included, equal-width bottom boxes, no web chrome/clipping, correct content/filename/MIME and Unicode. Inspect maximum-budget fixtures and fonts/license; repeated export does not change saved data. |

### F. Five-step frontend

Use `apps/web/` if adopted in W02. W29 explicitly migrates the existing UI from
the ignored proposal directory; it is not an instruction to recreate the design
from scratch. Begin with a separately reviewable migration substep before
transport wiring if the combined change would be too large:

- Extract the runtime HTML, CSS and JavaScript from `01_HTML/index.html` into
  maintainable application source. Reconcile the duplicate `07_SOURCE/` review
  copies; keep one authoritative runtime implementation.
- Move approved reusable visual elements, including the embedded logo after its
  licensing review, into the frontend's chosen static-asset location. Record each
  original path/embedded asset, destination and intentional modification.
- Put selected design/specification references under tracked `docs/ui/` or the
  location agreed in W01/W02. Screenshots, PDFs, Miro SVGs and presentation decks
  are references unless an individual asset is deliberately adopted by the app.
- Preserve the local original until migration is checked. Do not bulk-import or
  delete the proposal archive as part of the migration. The tracked frontend's
  build, tests and runtime must work without that ignored directory.
- Compare the migrated interface with the reference five-step flow and selected
  screenshots, record intended changes, and verify clean-clone operation. Keep
  fixtures explicitly in demo/test mode; never present them as live results.

Remove or isolate demo/unused variant-A behavior deliberately.
Frontend work may be authorized earlier against approved fake API contracts;
mark live integration incomplete until its backend dependencies pass.

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W29 | W25, W08, W06 | Migrate/refactor existing HTML/CSS/JS and approved assets into the tracked frontend application, with source/destination manifest and migration comparison; then implement five-step navigation/state and Step 1 URL/file controls with real transport. | Clean clone builds/runs without the ignored proposal directory; migrated visual elements and flow match the reference except recorded deliberate changes. Required URL and optional click/drop/keyboard file selection, genuine upload refs, clear validation/status/errors, pending analysis navigation and no silent demo fallback. New analysis invalidates old jobs without quietly clearing confirmed answers. Render filenames/source/user/model text inertly, with safe link schemes and the selected CSP; do not interpolate content into executable HTML/inline handlers. Apply this rendering rule throughout W30–W35. |
| W30 | W29, W07 | Step 2: exact three optional questions/options, custom confirmation/edit/removal and answer summaries. | Skip individual/all, reopen, 0–3 confirmed choices including one custom, 90 code points, unconfirmed draft excluded, keyboard Enter, no draft loss across renders and questions usable while Job A runs. |
| W31 | W30, W20 | Step 3: full twelve-box editor with approval/submission. | Add/edit/disable/re-enable/reorder/move/delete, paste as text, keyboard alternatives/focus restoration, destination caps, equal-width bottom boxes and no silent cuts; latest approved revision sent; stale/late replies cannot replace edits. |
| W32 | W31, W23 | Step 4: full focus opens immediately with all ten selectable titles and three highlights. | Correct eight fields/groups/title/ordinal, desktop sidebar/mobile two-column selector, previous/next bounds, per-case reasons and exact no-answer copy; no separate catalog page or IDs prefixed to titles. Malformed result preserves last valid view under D10. |
| W33 | W32, W26, W27, W28 | Step 5 downloads and current-focus print/navigation. | All actual downloads/filenames/content open correctly; export correlated saved snapshot, reject accidental mixing with new edits, current-focus print distinct from full report; no feedback/contact gate; recoverable export failure. |
| W34 | W33, W05 | Optional two ratings/comment and email/contact/newsletter preferences with browser-local storage only. | Explicit local-not-sent copy, opt-ins distinct, email validation when needed, optional/empty input, storage denial and preserved drafts. No contact transmission or third-party collection added. |
| W35 | W29, W02, W01 | Reviewed assets/configurable branding/contact destinations, optional fullscreen and selected embedding support. | Correct logo/artwork rights and attribution, no secrets/assets fetched unexpectedly, fullscreen failure harmless. If embedding ships: exact-origin/source resize messages, no parent DOM access and tested frame/CSP/allowed-origin policy. |
| W36 | W31, W32, W33, W34, W35 | Responsive, accessible behavior across declared browsers/devices. | Visual/interaction checks at 1280×720, 1440×900 and 390×844; no clipped controls/desktop unintended document scroll/mobile horizontal scroll; natural mobile vertical flow. Keyboard, touch, focus, labels/status announcements, contrast, zoom/reflow and reduced-motion checks; report automated versus manual coverage. |

### G. Operational readiness and acceptance

| Task | Dependencies | Deliverable / likely files | Completion evidence |
| --- | --- | --- | --- |
| W37 | W24, W12, W15, W05 | Web runtime settings, bounded resources, safe diagnostics and actual retention/cleanup controls. | Startup validation, server-only secrets, safe bind/proxy/origin settings, per-session/concurrency/rate/disk/token/deadline limits per D02/D07, expired evidence/files/results cleanup and diagnostics without business text/PII; backup/migration/rollback and interrupted cleanup tested. |
| W38 | W25, W33, W36, W37 | Executable integrated regression/security/fault suite and legacy MCP/storage checks. | Section 7 coverage on real browser + fake provider/mocked fetch, including restart and cross-session failures; old DB and both MCP tools/resources unchanged; no outbound network in ordinary tests; actual commands/results recorded. |
| W39 | W38 | Explicitly authorized live-provider/evidence evaluation and private quality review. | Real retrieval/extraction + generation + independent critic budget, ten rich cases/three reasons, exact source alignments, useful distinct ideas, approved-snapshot persistence and read/export checks. Record latency, calls/tokens/cost where available and unverified providers/failures; no public customer fixtures. |
| W40 | W38 | Reproducible web/core packaging, lockfiles/CI and public setup/operator/contributor docs. | Fresh isolated clone/install/build, optional frontend dependency separation, fake flow without a key, provider/storage configuration, asset/dependency notices, license/NOTICE preservation and documented browser/OS limits. CI runs appropriate offline contract/backend/frontend/export checks without secrets. |
| W41 | W39, W40, W36, W37 | User acceptance of the five-step workflow and selected local/self-hosted/public release gate. | User reviews real reviewed-model→ten cases/three selections→downloads flow. If public hosting is selected, deployed authorization/SSRF/upload/privacy/cleanup/proxy checks pass on target; actual deployment requires separate explicit authorization. Report every remaining limitation; do not equate local or fake success with production readiness. |

## 5. Exact content contract to preserve

### Twelve sections and editor budgets

The wire category IDs come from the prototype. Confirm their semantics, notably
`budget_owner` versus economic buyer, in W04. Each item has a stable backend ID,
text, active state and explicit zero-based order. Item caps include inactive
items under the reference rules; define tombstone/deletion handling separately.

| V37-B box / wire category | Existing field | Max items | Max code points/item |
| --- | --- | --- | --- |
| Partners / `partner` | `partnerships` | 4 | 48 |
| Resources / `resources` | `businessResources` | 5 | 48 |
| Activities / `activities` | `activities` | 4 | 48 |
| Solutions / `solutions` | `solutions` | 5 | 48 |
| Benefits / `benefits` | `benefits` | 4 | 48 |
| Relationships / `relationships` | `relationships` | 4 | 48 |
| Channels / `channels` | `channels` | 4 | 48 |
| End User / `end_user` | `endUsers` | 4 | 48 |
| Budget Owner / `budget_owner` | `economicBuyers` | 3 | 48 |
| Decision Maker / `decision_maker` | `decisionMakers` | 3 | 48 |
| Revenues & Advantages / `revenues_advantages` | `revenuesAndAdvantages` | 4 | 72 |
| Costs & Risks / `costs_risks` | `costsAndRisks` | 4 | 72 |

### Rich case fields

Each of ten cases needs a title (48 code points), description (140), full
`details`, matching editorial `catalog_short` and selection state. Compact
content must preserve meaning rather than cut substrings. Do not silently trim
stored legacy content to make it fit these budgets.

| Field | Full max | Compact max | Current reusable content |
| --- | --- | --- | --- |
| `user` | 40 | 42 | `targetUsers[]`; plural-to-single representation needs a policy |
| `objective` | 150 | 65 | New field |
| `key_result` | 125 | 70 | New field: observable definition/baseline, not a promised gain |
| `problem` | 205 | 90 | `problem`, subject to new budget |
| `solution` | 220 | 95 | `proposedSolution`, subject to new budget |
| `benefit` | 160 | 75 | New field |
| `information` | 180 | 85 | New field: sources/dependencies |
| `functions` | 170 | 80 | New field: observable system behavior |

Metadata maxima: `process_context` 100, `potential_benefit` 160, `required_data`
180, `open_question` 150, `source_basis` 200. Requiredness is D06. Every selection
reason is at most 300 code points. Exactly three selected IDs must exist among
the ten, match the true flags and exactly match the reason-map keys. Selected
case/map reason strings must be identical and individually substantive; unselected
reason is empty. Zero answers still yields ten cases and three selections with
the exact copy **“Selected by AI without further input.”** and no personalization
claim. `UC-01`…`UC-10` are wire labels, not replacements for backend UUIDs or title
prefixes. Preserve at least one exact active-source alignment per case.

### Questionnaire and focus presentation

The exact reference mapping from `qdata` and `Q_OPTION_IDS` is below. Local UI
keys `q0`…`q2` map to payload IDs `q1`…`q3`; do not shift these accidentally.

| Payload ID | Question | Option ID → visible label |
| --- | --- | --- |
| `q1` | What would you like to improve in your company? | `efficiency_cost` → Efficiency and costs; `growth` → Sales and growth; `quality_service` → Quality and service; `decisions` → Better decisions; `innovation` → Innovation; `employees` → Employees; `risks_compliance` → Risk and compliance; `sustainability` → Sustainability |
| `q2` | Who or what should benefit most? | `customers` → Customers; `employees` → Employees; `managers` → Management; `partners` → Partners; `other` → Others |
| `q3` | What data or information do you currently use? | `business_systems` → Business systems; `spreadsheets` → Spreadsheets; `documents` → Documents; `internal_knowledge` → Internal knowledge; `other` → Other |

Each supports 0–3 confirmed selections total, including at most one
90-code-point custom answer. Skipping preserves already confirmed answers;
unconfirmed custom drafts are not answers. Backend validation must not rely on
disabled browser buttons. Revising a confirmed answer invalidates the old Job B
correlation; define no-op/clear semantics explicitly.

Focus groups are Understand (user/objective/problem), Design
(solution/information/functions) and Align (benefit/key_result). All ten titles
stay selectable; the mobile selector has two columns. Display the selected case,
position, bounded previous/next navigation and its selection reason where relevant.

### Download content

- PDF: exactly 13 A4 landscape pages: combined input/cover, full BMC, ten full
  focus pages, continuation/contact page. Equal-width bottom BMC boxes, no web
  chrome or clipped text, all ten cases rather than only the shortlist.
- XLSX and Markdown: all ten cases, all eight full and eight compact fields,
  selection markers/reasons and the agreed provenance/revision content. Markdown
  also retains the reviewed BMC state. Maintain actual report/wire consistency.
- Reference names: `catalyst-v37-b-a4-landscape-13-pages.pdf`,
  `catalyst-v37-b-10-use-cases.xlsx`, `catalyst-v37-b-10-use-cases.md`; correct
  `application/pdf`, XLSX MIME and `text/markdown` responses/downloads.
- Export mode/source statements must reflect real processing. Reads/downloads
  do not call the model or modify source/result data. Downloads remain ungated.

## 6. Requirement coverage and known discrepancies

This crosswalk supplements the exact budgets above so a future implementation
review can trace every requirement to tasks and evidence.

| Requirement group | Source | Tasks |
| --- | --- | --- |
| Safe required URL, actual bounded evidence, verified/unverified distinction | Integration/fields guide; URL code | W03, W07, W09, W12–W14, W18, W29, W38 |
| Optional genuine PDF/PPT/PPTX upload, validation, extraction, source associations | Integration/fields guide; upload code | W09, W12, W15–W18, W29, W37–W38 |
| Twelve categories, stable items, caps, truthful analysis | Fields/limits/Job A prompt | W04, W07, W10, W19, W31, W39 |
| Three optional questions, skipped/confirmed state, custom answer budgets | Fields/limits; questionnaire code | W03, W07, W10, W20, W22, W30, W38 |
| Edits, moves/deletion, disable/order, active-only source, approved revisions | Integration/fields guide; editor code | W04, W10, W20–W22, W24, W31, W38 |
| Ten distinct full+compact cases, correct metadata and exact alignment | Job B prompt/schema/limits plus legacy contracts | W04, W08, W11, W21, W23, W39 |
| Three matching selections/reasons, zero-answer copy | Fields/Job B prompt/schema | W08, W22–W23, W30, W32, W38–W39 |
| Independent quality critic and one repair, whole-output validation | Critic prompt | W05, W21–W24, W38–W39 |
| Job/session/variant/revision checking, async status and finite retry/cancel | Integration/fields guide | W03, W12, W24–W25, W29–W33, W38 |
| Complete saved JSON/Markdown, atomic success, restart persistence | Existing Catalyst contracts; reviewed-source requirement | W04, W09–W11, W20, W23–W26, W38–W40 |
| Integrated selector, eight focus fields, no separate catalog | Included Catalog README/guide/screenshots | W29, W32, W35–W36, W38, W41 |
| Complete PDF/XLSX/Markdown, Unicode, correct revision and ungated access | Fields/guide/export code | W05, W26–W28, W33, W36, W38, W41 |
| Optional local feedback/contact, truthful consent and storage behavior | README/guide/feedback code | W05, W34, W38, W41 |
| Responsive, keyboard, devices, fullscreen and selected widget embedding | Guide/QA/frontend code | W02, W05, W29–W36, W38, W41 |
| Access, upload/fetch safety, retention, diagnostics/version/timing | Integration guide/critic prompt | W02–W05, W12–W18, W24–W25, W37–W41 |
| Open-source provenance, reproducibility and existing MCP compatibility | Contributor guidance/current contracts; branch engineering needs | W01–W06, W09–W11, W25–W28, W35, W38–W41 |

The independent critic must assess source traceability, evidence fit, full/compact
consistency, distinct workflows, human decision/control point, data feasibility,
operational/privacy risks, KPI observability, absence of fabricated ROI/facts,
variant fit and zero-question behavior. It returns structured path/code/instruction
findings, not an automatically trusted replacement result. Keep trusted metadata
and correction policy in backend code. Do not claim model criticism proves truth.

Resolve or fix these concrete reference discrepancies during their owning tasks:

| Reference issue | Tasks |
| --- | --- |
| `catalystStep23Payload()` omits job ID/evidence refs required by the guide; Job A request builders and guide use different shapes; status/errors are underspecified. | W03, W24–W25 |
| Evidence metadata is optional in JSON Schema but required by browser checks and requested by the prompt; mode/extra-field validation differs. | W03, W08, W25, W32 |
| Prompt asks the model to echo IDs/session/revisions/mode; existing backend correctly owns metadata. Assign/validate correlation in code. | W03–W04, W19, W21–W25 |
| V37 allows uncertainty/hypotheses; current extraction leaves unsupported sections empty. Define evidence status and preserve legacy behavior. | W04, W18–W21 |
| Snapshot builder labels every item edited; analysis response application resets active=true/ignores order and can overwrite edits. | W04, W07, W20, W24, W31 |
| Demo ranking includes inactive items although its rationale filters them. | W20–W22, W38 |
| Canvas edits use silent UTF-16 slicing and custom input uses UTF-16 maxlength, against code-point budgets. Reject/explain overlength without silent loss. | W07–W08, W30–W31, W36 |
| Stale-state handling discards prior output while error policy promises to preserve last valid UI. Define labeled stale/read-only recovery and prevent wrong-revision export. | W05, W24, W29–W33 |
| PDF exporter rejects non-WinAnsi text; Markdown hardcodes demo wording. | W05, W26, W28, W33 |
| Unused separate-catalog renderer remains in demo source; do not revive variant-A navigation. | W29, W32 |
| Current token cap is not evidence that ten rich cases plus criticism fit the budget; existing retries cannot be nested without analysis. | W05, W21–W24, W39 |

## 7. Verification and release evidence

For each task, report exact checks run, their results and limitations. Keep public
fixtures synthetic and private real-source/live evidence outside Git. Test only
new or affected behavior per step; broaden checks when integration risk warrants
it. Maintain source hashes/timestamps across read/export tests.

The integrated acceptance matrix must cover:

- Happy path with website only and website plus each supported document type;
  zero, one, many, custom and maximal answers, including three simultaneous
  90-code-point custom answers; all ten correct focus panels and three reasons.
- Invalid URL, blocked destination, redirect/DNS changes, fetch/parser failure,
  absent/partial/conflicting evidence, corrupt/encrypted files and resource limits.
- BMC add/edit/move/delete/disable/re-enable/reorder, moving a 72-character item
  into a 48-character box, duplicate text, empty/all-inactive policy and late Job A.
- Wrong variant/version/mode/session/job/evidence/answer/BMC revision, strict
  extra fields, stale concurrent responses and one session trying another's data.
- Browser XSS through website/model/user text, filenames, labels and rationales:
  content remains inert, link schemes/external-link behavior are safe and CSP
  is enforced. Model prompt-injection tests do not replace these browser checks.
- Malformed/blank/refused/truncated provider/critic output, wrong counts/alignment,
  disagreeing full/compact text, duplicate ideas, inconsistent reasons and repair
  exhaustion. Injection in websites, files, edits, answers and model findings
  cannot override task instructions or metadata.
- Deadline, cancellation, duplicate retry, provider/network/database failure,
  interrupted job, process restart/expiry and cleanup; no partial committed result,
  orphaned file or stale overwrite. State each workflow's actual call budget.
- Generated PDF layout/page count/Unicode; reopened XLSX ten rows/literal cells;
  parsed Markdown/complete fields; correct variant names/MIME and saved revisions.
- Required screen sizes and declared browsers/devices; keyboard/touch/zoom/focus,
  announced errors/progress and safe embedding where selected. Browser fixture
  success is separate from live backend and deployed-origin acceptance.
- Legacy schema/tool/resource payloads and JSON/Markdown links, old SQLite data,
  restart persistence, unchanged canonical URIs/timestamps and no Node requirement
  for Python/MCP users. New saved types get the agreed complete views.
- Fresh-clone runtime/build instructions, placeholder-only environment examples,
  safe credential storage, licenses/attribution and independently reproducible CI.

Use separate evidence labels: **schema/repository**, **scripted provider**,
**mocked retrieval/HTTP**, **real browser**, **live model/evidence**,
**actual MCP host**, **target deployment**, and **user acceptance**. Existing MVP
evidence is in [MVP_IMPLEMENTATION_HISTORY.md](MVP_IMPLEMENTATION_HISTORY.md).
Pending legacy host/provider acceptance is not erased by this branch plan.

No web task may be called complete merely because the prototype's JSON reports
PASS. No public-release claim may be made from local fake flow alone. If only a
local release is chosen, document that boundary; do not imply web authentication,
public deployment or other-provider quality has been verified.
