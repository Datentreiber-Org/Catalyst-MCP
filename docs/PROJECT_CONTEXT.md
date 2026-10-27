# Catalyst product scope and requirements

Status: MVP requirements with a proposed implementation. Business Artifact and Use-case Catalog schemas, SQLite persistence, deterministic Markdown rendering and both generation workflows with scripted fake providers are implemented and tested. Both tools, canonical JSON and Markdown resources, and native links to both views are exposed over local MCP stdio, including restart reads of both saved types. OpenAI, Anthropic and local Ollama JSON adapters and provider selection are implemented with mocked-HTTP verification. Live analysis/ideation and selected-host integration remain unimplemented or unverified.

## 1. Product purpose

Catalyst helps develop Data & AI use cases aligned with an organization's business model. The MVP converts business content into a structured Business Artifact, then uses that artifact to generate a saved Use-case Catalog.

The central product requirement is traceability: each generated idea must connect to the business model used to produce it. Saved artifacts provide reusable context that later operations can retrieve by ID.

## 2. MVP requirements

Implement the complete flow:

**Business content text → analyze-business-model → saved Business Artifact → ideate-use-case → saved Use-case Catalog.**

| Tool | Input | Required behavior |
|---|---|---|
| `analyze-business-model` | Business content as text | Extract business-model elements, create and save a Business Artifact, and return the complete artifact |
| `ideate-use-case` | Saved artifact ID, number of ideas and focus | Generate aligned use cases, save a catalog linked to the source artifact, and return the complete catalog |

Expose both types of saved object as readable MCP Resources in JSON and Markdown. Markdown support is part of the MVP; choosing to read that view is optional for clients. The [system design](SYSTEM_DESIGN.md#3-tool-contracts) contains the full output contracts and proposed data types.

### Resource views

The JSON record is the source of truth. Provide a human-readable Markdown representation of each saved Business Artifact and Use-case Catalog using deterministic backend templates. Include all saved fields and explicitly label empty sections. Rendering must not summarize, invent information, call the LLM, or modify saved data.

The design exposes Markdown under a separate `/view.md` URI with MIME type `text/markdown`, while the existing resource URIs continue to return JSON. Both views refer to the same saved record. A Markdown URI does not require a physical `.md` file, and no additional domain fields or tools are needed. See [resource behavior](SYSTEM_DESIGN.md#4-mcp-result-and-resource-behavior) for the URI patterns.

### Business Artifact contract

The output contains `id`, `name`, `uri`, `createdAt`, `updatedAt` and a `businessModel` object with these 12 array fields:

```text
endUsers[]
economicBuyers[]
decisionMakers[]
solutions[]
benefits[]
channels[]
relationships[]
businessResources[]
activities[]
partnerships[]
revenuesAndAdvantages[]
costsAndRisks[]
```

### Use-case Catalog contract

The output contains `id`, `createdAt`, `updatedAt`, `sourceArtifact.id` and `useCases[]`. Each use case contains:

```text
id
title
focus
problem
targetUsers[]
proposedSolution
businessElementAlignment[]
```

The field name is `targetUsers`. The Catalog payload does not require a `uri` field; its resource URI can be constructed from its ID.

### Outside the MVP

Direct PDF/PPT extraction, custom UI/MCP Apps, editing, confirmation workflows, organizational hierarchy propagation, ROI, retrieval-augmented generation, scoring and prioritization are outside the current implementation scope. The MVP schemas do not require ownership, revision, approval or evidence fields.

## 3. Proposed implementation

The [system design](SYSTEM_DESIGN.md) provides the following implementation baseline. These details are recommendations rather than additional product requirements.

| Area | Proposed approach |
|---|---|
| Backend | One Python application with internal modules |
| MCP interface | Official MCP SDK, local stdio and an existing MCP-capable host |
| Validation | Strict Pydantic models with extra fields forbidden |
| Generation | Backend calls a configured LLM-provider adapter through a shared JSON client contract |
| Storage | Persistent SQLite file containing complete JSON records |
| Creation | Each successful call creates a new record; no update operations |
| Model sections | Arrays of strings; unspecified sections use empty arrays |
| Analysis input name | `businessContent` |
| Ideation input names | `artifactId`, `numberOfIdeas`, optional `focus` |
| Idea count | Configurable initial range of 1–10 |
| Alignment entry | `section`, exact source `element` and `rationale` |
| Invalid generation | At most one corrective generation attempt |
| MCP result | Complete object in `structuredContent`, JSON text and native resource links to JSON and Markdown |

Step 2 adopts `businessContent` as the analysis input name and arrays of non-blank strings for all 12 business-model sections. Every section is required; an unspecified section is an explicit empty array. At least one section must contain a statement. Input text, artifact names and statements must contain non-whitespace text, and accepted text is preserved without trimming or rewriting. Unknown fields and incorrect types are rejected.

Generated Business Artifact content contains only `name` and `businessModel`. The complete artifact requires backend-supplied metadata: `uri` must equal `catalyst://business-artifact/{id}`, and both timestamps must be timezone-aware UTC values and equal under the create-only contract. Schema validation does not assign metadata or save a record. See the [recorded schema decisions](SYSTEM_DESIGN.md#recorded-business-artifact-schema-decisions-step-2) for the Python and JSON representations.

Step 3 adopts required `artifactId` and a strictly positive integer `numberOfIdeas`. Input `focus` may be omitted or `null`; provided text must be non-blank. Every use case requires its documented fields, with `targetUsers` as an array of non-blank strings (an empty array is allowed) and at least one alignment entry. Alignment entries contain an exact section name, non-blank `element` and non-blank `rationale`.

Generated ideation content contains only `useCases`, with no case IDs or catalog metadata. The complete Catalog requires backend-supplied IDs, equal UTC timestamps, `sourceArtifact.id` and at least one case. Case IDs must be unique within a catalog. The Catalog has no `uri` field. See the [recorded Catalog schema decisions](SYSTEM_DESIGN.md#recorded-ideation-and-catalog-schema-decisions-step-3).

The configurable upper idea-count limit, exact requested-count checks, source existence and exact source-element matches are enforced by the ideation workflow in step 9, outside these standalone schemas. The analysis workflow implements its configurable business-content size limit in step 8 below; provider deadline enforcement and environment-based settings remain later work.

Under the create-only proposal, `createdAt` and `updatedAt` are equal at creation. Repeated successful requests can create duplicate records; retry deduplication is not included. Creating an artifact does not automatically invoke ideation.

Step 4 adopts Python's built-in `sqlite3` module for Business Artifact persistence. The repository takes an explicit persistent file path, stores complete validated JSON, and provides save, get-by-ID and listing operations. Saving an existing ID fails rather than replacing its record. A missing ID returns `None` internally, and lists are ordered by ID. Each successful save returns the complete validated artifact after commit; reads preserve saved content and timestamps. See the [recorded persistence decisions](SYSTEM_DESIGN.md#recorded-business-artifact-persistence-decisions-step-4).

Step 5 extends the same repository with Catalog save, get-by-ID and listing operations. The database stores each complete Catalog as JSON and copies its `sourceArtifact.id` into a non-null foreign-key column referencing a saved Business Artifact. Missing sources and duplicate Catalog IDs fail atomically. Reads check both stored IDs against their JSON values and preserve all content and timestamps. Opening a step-4 database adds the Catalog table without replacing its artifacts. Step 9 adds source-element matching and source lookup before generation. See the [recorded Catalog persistence decisions](SYSTEM_DESIGN.md#recorded-catalog-persistence-decisions-step-5).

Step 6 adopts a fixed CommonMark template for the Business Artifact view: five metadata fields followed by all 12 labeled business-model sections, with statements in saved order and explicit empty sections. Rendering is a pure function over a complete artifact, with no model calls, database writes or separate stored Markdown document. CommonMark parsing in tests verifies that escaped content remains text and the template structure stays intact. See the [recorded renderer decisions](SYSTEM_DESIGN.md#recorded-business-artifact-rendering-decisions-step-6).

Step 7 adopts the same approach for Catalogs: Catalog metadata and source artifact ID/URI followed by every use case, target user and alignment entry in saved order. Numbered view headings identify case and alignment positions without changing their stored IDs. Empty target-user lists are explicit. The source URI is computed from `sourceArtifact.id` for display; no URI field is added to the Catalog or source reference. See the [recorded Catalog renderer decisions](SYSTEM_DESIGN.md#recorded-catalog-rendering-decisions-step-7).

Step 8 adopts a synchronous analysis service with an injected provider and repository. It validates raw business text, enforces a configurable initial limit of 20,000 Python characters, validates generated JSON, assigns a `ba_`-prefixed UUID4 ID, canonical URI and equal UTC timestamps, then returns the complete committed artifact. Malformed output gets at most one corrective attempt with fixed backend feedback. An entirely empty extracted model is an insufficient-content error and is not retried. Provider and database failures propagate without a success result. The scripted fake provider returns supplied responses rather than analyzing the input; live prompts, provider deadlines and business-quality evaluation remain later work. See the [recorded analysis decisions](SYSTEM_DESIGN.md#recorded-analysis-workflow-decisions-step-8).

Step 9 adds synchronous ideation from a saved artifact. It validates the request, enforces a configurable maximum of 10 ideas by default and stops before generation if the source is missing. The provider receives immutable saved-artifact JSON, count and optional focus as separate arguments. Generated output must have exactly the requested count, and every alignment must match an element in its named source section exactly. Invalid output gets one corrective attempt with fixed feedback. Backend code assigns Catalog/case UUID4 IDs, equal UTC timestamps and the source association, then returns the complete committed Catalog without a URI field or source changes. Scripted fake checks do not assess idea relevance or semantic focus compliance. See the [recorded ideation decisions](SYSTEM_DESIGN.md#recorded-ideation-workflow-decisions-step-9).

Step 10 initially exposed `analyze-business-model` through the official MCP SDK 2.3.0 over local stdio. It was authorized before step 9. The low-level SDK server advertises the existing strict schemas, enforces the default character limit and returns the complete committed artifact in structured content and JSON text. Fixed tool-error results do not echo supplied content or provider details. Application logs use stderr and stdout carries MCP messages. Local SDK-client and stdio subprocess checks are separate from live-model and selected-host verification. See the [recorded analysis MCP decisions](SYSTEM_DESIGN.md#recorded-analysis-mcp-decisions-step-10).

Step 11 adds `ideate-use-case` with `artifactId`, `numberOfIdeas` from 1 to 10 and optional/null `focus`. It invokes the ideation service and returns the complete committed Catalog in structured content and matching JSON text. A distinct `SourceArtifactNotFoundError`, still a `LookupError`, separates missing saved sources from provider failures. The command requires a database path and accepts independent repeatable analysis (`--fake-response`) and ideation (`--fake-ideation-response`) scripts. Omitting a script leaves that provider empty; ideation-only startup can use a source saved before restart. Tests verify both tools' contracts, failure atomicity, the full two-tool stdio flow, independent corrections and persistence after restart. Steps 12 and 13 add resource readers and links below. See the [recorded two-tool MCP decisions](SYSTEM_DESIGN.md#recorded-two-tool-mcp-decisions-step-11).

Step 12 advertises and reads each complete saved object as a canonical JSON resource with `application/json`. Listing returns artifacts in ID order followed by Catalogs in ID order, in one page. Reads use the existing repository and return one JSON text content item with the requested URI. Catalog URIs are constructed in the MCP layer, with no payload change. Exact canonical URI matching, missing/corrupt records, safe protocol errors, zero provider calls and unchanged saved data are verified, including real stdio reads after restart with no provider scripts. See the [recorded JSON resource decisions](SYSTEM_DESIGN.md#recorded-json-resource-decisions-step-12).

Step 13 adds a `/view.md` resource with `text/markdown` for each saved object and two native resource links in every successful tool result. Listing pairs JSON then Markdown for each record. Markdown reads load the same saved JSON and invoke the existing complete renderer without provider calls, writes or new timestamps. The complete domain payload, canonical JSON URI and output schema remain unchanged. Exact canonical JSON records take precedence when manually stored IDs end in `/view.md`; colliding advertised URIs fail listing. Both formats, links, deterministic literal text, safe errors and restart reads without scripts are verified locally. See the [recorded Markdown MCP decisions](SYSTEM_DESIGN.md#recorded-markdown-mcp-decisions-step-13).

The user expanded step 14 to support OpenAI, Anthropic and Ollama as separately reviewable parts. Step 14a adds `LLMSettings`, the shared `JSONClient` contract and `OpenAIJSONClient`; the user subsequently authorized Anthropic (14b) and Ollama (14c), which are now implemented. Configuration requires an explicit provider/model and OpenAI API key, with a positive finite network timeout defaulting to 60 seconds. Step 14a initially accepted only `openai`; steps 14b and 14c extend selection below. The adapter makes one Responses API request with JSON Schema output, separate instructions/input, disabled retries and `store: false`; it closes its client and returns completed text for workflow validation. It adds no storage or tool-payload fields. Mocked HTTP exercises the real SDK; live credentials, model access and quality remain unverified. Analysis/ideation prompt integration and runtime wiring remain steps 15 and 16. See the [recorded adapter decisions](SYSTEM_DESIGN.md#recorded-llm-client-decisions-step-14a).

Step 14b adds `AnthropicJSONClient`, matching `ANTHROPIC_API_KEY` selection and a shared positive output-token limit (`CATALYST_LLM_MAX_OUTPUT_TOKENS`, default 8192). A small `create_json_client` function selects the configured provider without I/O or fallback. Anthropic requests use the SDK's schema conversion and keep original domain validation in the workflows. Step 14c adds `OllamaJSONClient` for a configured local server origin (`CATALYST_OLLAMA_HOST`, default `http://localhost:11434`) without credentials, downloads or server startup. All three clients close their connections and return only normally completed non-blank text; output-token exhaustion fails rather than returning partial results. Mocked requests verify all adapters, configuration and failure handling. Local model installation/compatibility and cloud model access remain unverified. See the [provider decisions](SYSTEM_DESIGN.md#recorded-anthropic-and-ollama-decisions-steps-14b-and-14c).

## 4. Domain and MCP concepts

- **Business content:** text supplied for analysis. Input files and extracted text are not automatically registered MCP Resources.
- **Business Artifact:** a saved, structured business model.
- **Use-case Catalog:** saved ideas associated with a source Business Artifact.
- **MCP Tool:** a callable operation exposed by Catalyst.
- **MCP Resource:** saved content exposed under a URI. The MCP interface is separate from its backing database.
- **MCP Prompt:** reusable instructions exposed to a client. Registered MCP Prompts are not required for this MVP.
- **MCP App:** an optional interface served by a server and rendered by a compatible host. Custom Apps are outside this MVP.

Backend generation prompt files are internal implementation assets and are not automatically registered MCP Prompts. In logical diagrams, resource-to-tool arrows represent data dependencies, not resources independently invoking tools.

Suggested resource URIs are `catalyst://business-artifact/{id}` and `catalyst://use-case-catalog/{id}`. The custom scheme and lowercase hyphenated tool names are project conventions.

## 5. Data and quality requirements

- Backend code assigns IDs, timestamps, URIs and source associations; the model generates business content.
- Ideation loads its source artifact by ID rather than reconstructing it from chat history.
- JSON resource reads return the saved object; Markdown resource reads format the same object without a new model call.
- Both representations must be discoverable and available after a server restart. Markdown reads must preserve the saved values, IDs and timestamps.
- Validate before saving and persist complete results atomically.
- Reject an unknown source artifact before generation.
- Analysis should extract source-supported information rather than invent facts to fill the canvas. Ideation produces proposed solutions.
- Validate alignment references against the selected source artifact. The proposed entry structure makes each reference machine-checkable.
- Evaluate business relevance separately from schema validity. Valid references do not establish a convincing business rationale.
- Use synthetic business briefs in public examples and tests. Credentials and real business records belong in local runtime configuration and storage.

## 6. Business-model canvas reference

The business-model fields map to Datentreiber's Business Model / Case Canvas, which distinguishes end users, economic buyers and decision makers alongside the other sections listed above.

- [Datentreiber canvas description](https://www.datentreiber.com/de/geschaftsmodell-fall-canvas/#canvas)
- [English canvas PDF, version 1.1](https://www.datentreiber.com/wp-content/uploads/2024/12/Datentreiber_EN_Business-Model-Case_v1-1_20240710.pdf)

`businessResources` represents business assets and is distinct from MCP Resources. The data model maps the canvas's concepts; it does not reproduce the printed template's visual layout.

## 7. Future capabilities

These capabilities require further design and are not part of the two-tool MVP.

### Living artifacts and organizational hierarchy

- Corporate, business unit, department, team and squad levels can each have their own business-model artifact.
- Each child artifact represents its organizational unit's model.
- Some content is inherited, while other content is adapted or expanded locally.
- Relevant parent changes should propagate to child artifacts. Merge, override and propagation rules remain open.
- Use cases can link to artifacts at different organizational levels.
- Editing and change assessment can keep the models and their associated ideas current.

The create-only MVP postpones these editing and propagation semantics.

### Additional capabilities

- Assess business changes, flag affected use cases and suggest revisions.
- Estimate costs and benefits using prior data-product evidence and calculate ROI from reviewed assumptions.
- Define, score and prioritize use cases.
- Assess data readiness, design data products and identify riskiest assumptions.
- Provide canvas-based editors and visualizations.

## 8. Implementation status and open choices

The repository has a `src/catalyst_mcp/` package with a stdio development-server entry point and strict Pydantic 2 models for analysis and ideation inputs, generated content, alignment entries, and complete Business Artifact and Catalog payloads. `SQLiteRepository` saves, retrieves and lists both complete record types in a persistent SQLite file, enforcing each Catalog's source association through a foreign key. `render_business_artifact` and `render_use_case_catalog` produce complete deterministic Markdown views from supplied records. `analyze_business_model` and `ideate_use_case` validate requests and provider output, assign metadata and return committed records; `FakeAnalysisProvider` and `FakeIdeationProvider` supply scripted responses or failures. Ideation checks source existence, exact counts and every source-element match. `server.py` exposes both tools with complete results and native links, plus JSON/Markdown resource listing and reads. Tests cover schemas, storage, association consistency, failed-commit rollback, both fake-provider services, the full local two-tool MCP flow, resource completeness/MIME types, links and Markdown text recovery through a CommonMark parser, including consistency across process restarts. `pyproject.toml` declares Python 3.12 or later and uses the `uv_build` backend; uv manages dependencies and pytest runs the tests. `markdown-it-py` is a development-only parser for rendering checks.

`settings.py` reads explicit provider/model/credential, network-timeout, output-token limit and Ollama-origin values on request. `llm_client.py` includes all three JSON adapters and `create_json_client` for provider selection without fallback. Live workflow integration, environment-based database/input/count settings and overall provider deadlines are not implemented. The services have configurable limits: 20,000 input characters for analysis and 10 ideas for ideation by default. The MCP interface advertises and enforces these defaults. The CLI still takes an explicit database path and independent optional fake-response scripts for both tools. Both workflows are exercised only with scripted fake providers; JSON/Markdown resource listing and reads need no provider scripts. The repository accepts complete records and enforces Catalog source existence at save time. Both Markdown renderers return text directly and through MCP; selected-host display remains unverified.

Open choices include:

- Runtime model selection and live verification of cloud credentials/model access and local Ollama compatibility. All three adapters are implemented; live checks remain separate work.
- Target MCP host and connection settings.
- Future dependency upgrades. The official OpenAI SDK 2.54.0, Anthropic SDK 1.17.0, HTTPX2 2.16.0, MCP SDK 2.3.0 and Pydantic 2 are selected; resolved versions are recorded in `uv.lock`.
- Final contract details identified in the implementation proposal.
- Overall provider deadlines, runtime configuration of input size and the upper idea-count limit. All adapters have configurable network timeouts, which are not total tool deadlines.

Scripted fake providers support local analysis and ideation workflow tests. Live extraction and ideation quality, semantic focus compliance, prompt-injection resistance and compatibility with the selected host require separate verification.

## 9. Development priorities

Follow the build order and completion criteria in the [system design](SYSTEM_DESIGN.md#9-build-order-and-completion-criteria). Prioritize a complete working flow, persistence across restart, accurate output shapes, faithful JSON and Markdown views, source alignment and failure atomicity. Record material implementation decisions as the design becomes executable.
