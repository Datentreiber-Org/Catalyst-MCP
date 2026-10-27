# Catalyst product scope and requirements

Status: MVP requirements with a proposed implementation. Business Artifact and Use-case Catalog schemas, SQLite persistence for both record types, and their tests are implemented; the tool workflows are not implemented.

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
| Generation | Backend calls one configurable LLM-provider adapter |
| Storage | Persistent SQLite file containing complete JSON records |
| Creation | Each successful call creates a new record; no update operations |
| Model sections | Arrays of strings; unspecified sections use empty arrays |
| Analysis input name | `businessContent` |
| Ideation input names | `artifactId`, `numberOfIdeas`, optional `focus` |
| Idea count | Configurable initial range of 1–10 |
| Alignment entry | `section`, exact source `element` and `rationale` |
| Invalid generation | At most one corrective generation attempt |
| MCP result | Complete object in `structuredContent`, JSON text and a resource link |

Step 2 adopts `businessContent` as the analysis input name and arrays of non-blank strings for all 12 business-model sections. Every section is required; an unspecified section is an explicit empty array. At least one section must contain a statement. Input text, artifact names and statements must contain non-whitespace text, and accepted text is preserved without trimming or rewriting. Unknown fields and incorrect types are rejected.

Generated Business Artifact content contains only `name` and `businessModel`. The complete artifact requires backend-supplied metadata: `uri` must equal `catalyst://business-artifact/{id}`, and both timestamps must be timezone-aware UTC values and equal under the create-only contract. Schema validation does not assign metadata or save a record. See the [recorded schema decisions](SYSTEM_DESIGN.md#recorded-business-artifact-schema-decisions-step-2) for the Python and JSON representations.

Step 3 adopts required `artifactId` and a strictly positive integer `numberOfIdeas`. Input `focus` may be omitted or `null`; provided text must be non-blank. Every use case requires its documented fields, with `targetUsers` as an array of non-blank strings (an empty array is allowed) and at least one alignment entry. Alignment entries contain an exact section name, non-blank `element` and non-blank `rationale`.

Generated ideation content contains only `useCases`, with no case IDs or catalog metadata. The complete Catalog requires backend-supplied IDs, equal UTC timestamps, `sourceArtifact.id` and at least one case. Case IDs must be unique within a catalog. The Catalog has no `uri` field. See the [recorded Catalog schema decisions](SYSTEM_DESIGN.md#recorded-ideation-and-catalog-schema-decisions-step-3).

The configurable upper idea-count limit (initially proposed as 10), exact requested-count checks, source existence and exact source-element matches belong to the later ideation workflow and are not enforced by these standalone schemas. Input-size and timeout limits also remain operational choices; the configurable business-content size limit will be implemented with the analysis workflow.

Under the create-only proposal, `createdAt` and `updatedAt` are equal at creation. Repeated successful requests can create duplicate records; retry deduplication is not included. Creating an artifact does not automatically invoke ideation.

Step 4 adopts Python's built-in `sqlite3` module for Business Artifact persistence. The repository takes an explicit persistent file path, stores complete validated JSON, and provides save, get-by-ID and listing operations. Saving an existing ID fails rather than replacing its record. A missing ID returns `None` internally, and lists are ordered by ID. Each successful save returns the complete validated artifact after commit; reads preserve saved content and timestamps. See the [recorded persistence decisions](SYSTEM_DESIGN.md#recorded-business-artifact-persistence-decisions-step-4).

Step 5 extends the same repository with Catalog save, get-by-ID and listing operations. The database stores each complete Catalog as JSON and copies its `sourceArtifact.id` into a non-null foreign-key column referencing a saved Business Artifact. Missing sources and duplicate Catalog IDs fail atomically. Reads check both stored IDs against their JSON values and preserve all content and timestamps. Opening a step-4 database adds the Catalog table without replacing its artifacts. Source-element matching and the source lookup before generation remain later workflow checks. See the [recorded Catalog persistence decisions](SYSTEM_DESIGN.md#recorded-catalog-persistence-decisions-step-5).

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

The repository has a `src/catalyst_mcp/` package with a placeholder entry point and strict Pydantic 2 models for analysis and ideation inputs, generated content, alignment entries, and complete Business Artifact and Catalog payloads. `SQLiteRepository` saves, retrieves and lists both complete record types in a persistent SQLite file, enforcing each Catalog's source association through a foreign key. Contract and repository tests cover these models and storage operations, including process restart persistence, opening step-4 databases, association consistency and failed-commit rollback. `pyproject.toml` declares Python 3.12 or later and uses the `uv_build` backend; uv manages dependencies and pytest runs the tests.

MCP handlers, resource readers and generation are not implemented. Metadata assignment, runtime database-path settings, source lookup before generation, exact source-element checks, exact requested-count checks, and configurable input-size and idea-count limits also remain unimplemented. The current repository accepts complete records supplied by callers and enforces source existence at save time; it does not execute either tool workflow.

Open choices include:

- LLM provider, model and runtime configuration.
- Target MCP host and connection settings.
- MCP and model-client dependency versions. Pydantic 2 is selected for validation; the exact installed version is recorded in `uv.lock`.
- Final contract details identified in the implementation proposal.
- Input size, timeout and generation limits.

A deterministic fake provider can support initial development and integration tests. Live generation and compatibility with the selected host require separate verification.

## 9. Development priorities

Follow the build order and completion criteria in the [system design](SYSTEM_DESIGN.md#9-build-order-and-completion-criteria). Prioritize a complete working flow, persistence across restart, accurate output shapes, faithful JSON and Markdown views, source alignment and failure atomicity. Record material implementation decisions as the design becomes executable.
