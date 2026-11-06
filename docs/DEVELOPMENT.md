# Catalyst development guide

Run the shell commands in this guide from the repository root. For cloning,
provider setup and client registration, start with [Client setup](CLIENT_SETUP.md).
The [Python and MCP examples](EXAMPLES.md) contain the complete runnable scripts
and their expected outputs; use a separate demo directory for those scripts.

## Architecture overview

Catalyst is one Python application. The MCP adapter invokes generation services,
which validate provider output and commit complete records to SQLite. Resource
reads load saved JSON and render Markdown without another model call.

| Module | Responsibility |
|---|---|
| [models.py](../src/catalyst_mcp/models.py) | Strict input, generated-content and saved-record schemas |
| [services.py](../src/catalyst_mcp/services.py) | Validation, bounded correction, metadata, source alignment and saving |
| [repository.py](../src/catalyst_mcp/repository.py) | Atomic SQLite persistence and complete-record reads |
| [markdown_views.py](../src/catalyst_mcp/markdown_views.py) | Deterministic views of saved records |
| [llm_client.py](../src/catalyst_mcp/llm_client.py) | Scripted providers, JSON adapters and packaged-prompt bridges |
| [settings.py](../src/catalyst_mcp/settings.py) | Provider/model selection and runtime LLM settings |
| [server.py](../src/catalyst_mcp/server.py) | MCP tool handlers, native links and resource readers |
| [__init__.py](../src/catalyst_mcp/__init__.py) | Console command and independent live/scripted mode selection |

See [Product scope](PROJECT_CONTEXT.md) for requirements and
[System design](SYSTEM_DESIGN.md) for complete contracts, decisions and remaining work.

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

## Run the stdio development server

```bash
uv run --locked catalyst-mcp \
  --database data/two-tool-demo.sqlite3 \
  --fake-response data/fake-analysis.json \
  --fake-ideation-response data/fake-ideation.json
```

The command now starts an MCP server and waits for a client on stdin. It does not
print a greeting. Application logs and the explicit fake-provider startup notice
go to stderr; stdout carries MCP messages. Use `--help` to see its arguments.

Create the two synthetic response files using the
[analysis](EXAMPLES.md#analysis-over-mcp) and [two-tool](EXAMPLES.md#two-tool-mcp-flow)
examples. `--database`
is required. The response options are optional and independent: `--fake-response`
supplies analysis output and `--fake-ideation-response` supplies ideation output.
Each provider call consumes its next file, including correction attempts. Repeat
the corresponding option to supply more responses. An omitted or exhausted script
returns a tool error when that provider is called. No LLM or credentials are used.

To use a configured provider for analysis, set the environment variables described
under [LLM configuration](#llm-configuration-and-provider-clients), then run:

```bash
uv run --locked catalyst-mcp --database data/catalyst.sqlite3 --live-analysis
```

`--live-analysis` and `--fake-response` are mutually exclusive. An environment
setting alone never enables live calls. Startup validates the selected provider's
configuration and selected packaged prompts before opening the database, without
calling the model. Generation starts only when the corresponding tool is called.
`--fake-ideation-response` can still supply scripted ideation in this mode.

To enable both tools with the same configured provider/model:

```bash
uv run --locked catalyst-mcp --database data/catalyst.sqlite3 --live-analysis --live-ideation
```

`--live-ideation` and `--fake-ideation-response` are mutually exclusive. Either tool
may independently use live or scripted generation. `--live-ideation` also works
alone against an artifact already saved in the selected database. When both live
flags are supplied, configuration is loaded once and the two prompt bridges share
one stateless JSON client. Each generation request still owns its connection and
sends its own complete input; no conversation history is shared. The tools remain
two separate calls, and analysis never automatically triggers ideation. Default
fake/resource-only startup needs no LLM settings. Resource reads use saved data
without another model call.

The server advertises exactly two tools, both rejecting extra input fields:

| Tool | Input |
|---|---|
| `analyze-business-model` | Non-blank `businessContent`, maximum 20,000 characters |
| `ideate-use-case` | Saved `artifactId`, integer `numberOfIdeas` from 1 to 10, optional non-blank `focus` or `null` |

A successful call returns the complete saved artifact or Catalog as
`structuredContent` and matching JSON text, conforming to its `outputSchema`.
The text is followed by two native MCP `resource_link` items, for JSON and Markdown.
A Catalog has no `uri` field. Failures have `isError: true` and no structured success
payload or resource links. Both resource views are available through
`resources/list` and `resources/read`. The artifact's canonical URI stays in its payload.

The server uses the [official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/),
version 2.3.0 recorded in `uv.lock`, with its documented
[low-level server API](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/).

## Models, persistence and rendering

Input, generated content and saved records have separate strict models. All 12
business-model sections are required. Generated content supplies no IDs,
timestamps or source associations; the services assign those fields. Catalog
cases use `targetUsers` and have exact saved-source alignments. The Catalog has
no `uri` field. See the [model examples](EXAMPLES.md#business-artifact-models)
and [domain contracts](SYSTEM_DESIGN.md#3-tool-contracts).

`SQLiteRepository` stores each complete record as JSON. Saves commit atomically;
duplicate IDs fail, and a foreign key enforces each Catalog's source artifact.
Reads validate stored IDs and source associations without changing the records.
The [storage examples](EXAMPLES.md#business-artifact-storage) demonstrate save,
read and listing operations for both types.

`render_business_artifact` and `render_use_case_catalog` format saved values
deterministically, escaping supplied Markdown/HTML as text. They do not call a
model, write another document or assign new timestamps. See the
[rendering examples](EXAMPLES.md#business-artifact-markdown).

## MCP handlers

In `server.py`, `create_server` keeps both injected providers and the shared
repository in small callbacks. `list_tools` advertises the exact schemas from our
models. `call_tool` dispatches the two registered names to `analyze` or `ideate`.
Each validates its arguments, runs its service in a worker thread and returns the
complete committed record. `_tool_error` logs the known operation name and a fixed
failure summary without echoing business text or provider exception details.
`run_stdio` connects the SDK's stdin/stdout streams to its server runner. The
updated package `main` loads the explicit file paths, configures stderr logging
and starts that runner. Imports do not start a server or create a database.

### Resource helpers

The resource and result helpers in `server.py` share the same descriptions:

- `_resource_views` creates two descriptions for a saved record: canonical JSON,
  then `/view.md` Markdown, each with its name, URI and MIME type. It renders nothing.
- `_saved_tool_result` returns the complete saved JSON in text and structured
  content, followed by native resource links made from those two descriptions.
- `_list_saved_resources` loads validated records and describes both views.
  Artifacts come first in ID order, followed by Catalogs in ID order. Duplicate
  advertised URIs cause a fixed listing error.
- `_load_saved_record` matches a literal canonical prefix and loads the exact saved
  ID. It does not decode URI escapes, normalize IDs or perform filesystem lookups.
- `_read_saved_resource` first checks for an exact canonical JSON record. Otherwise,
  a literal `/view.md` suffix selects the existing renderer for the base record.
  It returns one content item with the requested URI and correct MIME type.
- `_resource_error` logs a fixed operation summary and constructs an MCP protocol
  error without copying URI values, stored content or exception details into it.
- `list_resources` runs discovery in a worker thread and returns a single page.
  An explicit cursor is rejected; pagination and change notifications are not enabled.
- `read_resource` runs loading and rendering in a worker thread and returns the
  content or a protocol error. Missing/unsupported resources use `-32602`; database,
  invalid-record or rendering failures use `-32603`, following the current
  [resource error contract](https://modelcontextprotocol.io/specification/draft/server/resources#error-handling).

Listing and reading make no provider calls, writes or new timestamps. JSON reads
preserve stored text, field names and array order. Both Markdown renderers also
work directly in Python as shown in the [rendering examples](EXAMPLES.md#business-artifact-markdown). Backend-generated IDs avoid URI collisions.
For manually stored IDs ending in `/view.md`, an exact canonical JSON record takes
precedence; a collision between two advertised views causes listing to fail.
Live-model and selected-host checks remain separate.

See the [JSON](EXAMPLES.md#json-resources-over-mcp) and
[Markdown](EXAMPLES.md#markdown-resources-over-mcp) SDK examples for discovery,
complete reads and deterministic views after restarting the server.

## Analysis service

The analysis service has three parts:

- `AnalysisProvider` declares the `generate_business_model` operation: accept
  business text and optional backend correction separately, and return JSON.
  Providers satisfy this interface by implementing that method.
- `FakeAnalysisProvider.__init__` stores an ordered script and starts an empty
  call history. Its `generate_business_model` method records each call, then
  returns the next JSON string or raises the next scripted exception. An exhausted
  script raises `RuntimeError`.
- `analyze_business_model` validates the text, asks the provider for generated
  content, validates that content, adds metadata, saves and returns the complete
  committed artifact. It uses the existing repository for transaction handling.

The service accepts at most 20,000 Python characters by default. Override this
through the positive integer `max_business_content_chars` keyword. It preserves
input text without trimming or truncation. Blank or wrongly typed input raises
`ValidationError`; oversized input raises `ValueError` before a provider call.

Malformed JSON or schema-invalid output receives one corrective attempt. The
`_ANALYSIS_CORRECTION` constant supplies fixed backend feedback; rejected model
output and input text are not copied into it. Two invalid outputs raise
`RuntimeError`. The existing non-empty model validator now emits the distinct
`empty_business_model` error code, which the service translates into an
insufficient-content `ValueError` without retrying. Provider and database failures
propagate without a success result or a partially saved artifact.

These scripted checks verify workflow behavior. The configured-provider bridge
below supplies the real analysis prompt. Broader model quality, prompt-injection
resistance and overall provider deadlines remain open; see the
[project status](PROJECT_CONTEXT.md#8-implementation-status-and-open-choices)
for the separate live-model and host checks.

### Analysis prompt bridge

`LLMAnalysisProvider` connects the existing analysis workflow to any `JSONClient`.
Its constructor loads `prompts/analyze_business_model.md` through
`importlib.resources`, so the same UTF-8 prompt works from source and an installed
wheel regardless of the working directory. Missing or empty prompts fail before
generation. The prompt is internal backend content, not a registered MCP Prompt.

`generate_business_model` sends business text as a separate JSON data object:
`{"businessContent": "..."}`. It requests the existing `GeneratedBusinessArtifact`
schema and returns the response text unchanged. Backend correction requirements
are appended to the trusted instructions for that call only; rejected output and
business text are never inserted into those instructions. The service continues
to own validation, its one-correction limit, metadata and atomic saving.

The prompt defines all 12 sections, distinguishes user/buyer/decision-maker roles,
requires source-supported statements and leaves unsupported sections empty. It
uses `Unnamed business` when the text gives no business name. If no usable facts
can be extracted, it requests all arrays empty so the existing service returns an
insufficient-content error without saving. These instructions follow official
guidance on [insufficient input](https://developers.openai.com/api/docs/guides/structured-outputs)
and [separating untrusted data](https://developers.openai.com/api/docs/guides/agent-builder-safety).
Broader extraction quality and prompt-injection resistance remain unverified.

Runnable [fake-provider](EXAMPLES.md#analysis-with-a-fake-provider) and
[prompt-bridge](EXAMPLES.md#analysis-with-the-configured-provider) examples show
the complete input-to-saved-record path.

## Ideation service

The ideation service has four parts:

- `IdeationProvider.generate_use_cases` declares the provider operation: receive
  the saved artifact as JSON, the requested count, optional focus and separate
  correction feedback; return JSON containing only `useCases`.
- `FakeIdeationProvider.__init__` stores the response script and starts an empty
  call history. Its `generate_use_cases` method records the arguments, then returns
  the next JSON string or raises the scripted exception. Exhaustion raises `RuntimeError`.
- `_validate_generated_use_cases` checks the exact count and every alignment in
  every case. Each element must match a string in its named source section
  exactly, including case, whitespace and Unicode characters.
- `ideate_use_case` validates the request, loads the saved source, calls the
  provider, validates its output, assigns metadata and saves the complete Catalog.
  It returns the repository's result only after commit succeeds.

The `max_number_of_ideas` keyword defaults to 10 and requires a positive integer.
Invalid input raises `ValidationError`; a count above the configured maximum
raises `ValueError`. A missing source raises `SourceArtifactNotFoundError`, a
`LookupError` subclass, before any provider call.
Optional focus is preserved exactly, with omitted or `None` meaning no constraint.

Malformed JSON, schema errors, wrong counts or invalid alignments get at most one
corrective provider call. `_IDEATION_CORRECTION` supplies fixed backend feedback;
source JSON, count and focus stay unchanged and rejected output is not included in
the feedback. Two invalid responses raise `RuntimeError`. Provider, source-read
and database-save failures propagate without generation retries or partial Catalogs.

These fake-provider checks establish orchestration and valid references. They do
not assess idea relevance, rationale quality or semantic focus compliance.
Packaged live prompts and both MCP tools are implemented; overall provider
deadlines and broader real-model evaluation remain open. Independent CLI modes
select each workflow's provider.

### Ideation prompt bridge

`LLMIdeationProvider` connects saved-artifact ideation to any `JSONClient`. Its
constructor loads the packaged UTF-8 `prompts/ideate_use_case.md` file once through
`importlib.resources`, independently of the working directory. Missing or empty
prompts fail before generation. These are backend instructions, not an MCP Prompt.

`generate_use_cases` decodes the saved artifact JSON and sends a separate JSON
input object containing the complete `sourceArtifact`, integer `numberOfIdeas`
and `focus` (including `null` when absent). It requests `GeneratedUseCaseCatalog`
and returns response text unchanged. Only backend correction requirements are
added to trusted instructions for that call; source/focus values and rejected
output are never interpolated into those instructions.

The prompt requests exactly the specified number of Data & AI proposals, all
documented fields including `targetUsers`, and at least one exact source alignment
per case. An alignment must copy an entire element from its named saved section,
including case, Unicode and whitespace. Ideas are proposals rather than claims
about existing systems, datasets, measured pain points or results. When a problem
is not stated in the source, the prompt asks for an opportunity or hypothesis.
The existing service still loads the source before generation, enforces count and
alignment, allows one correction, assigns metadata and commits atomically.

Runnable [fake-provider](EXAMPLES.md#ideation-with-a-fake-provider) and
[prompt-bridge](EXAMPLES.md#ideation-with-the-configured-provider) examples use
a saved source and verify the complete Catalog and unchanged artifact.

## LLM configuration and provider clients

OpenAI, Anthropic and local Ollama share the same JSON client contract. Clients
are available from Python and through the independent `--live-analysis` and
`--live-ideation` options. The examples use mocked HTTP; separate live-model
and host checks are recorded in the [project status](PROJECT_CONTEXT.md#8-implementation-status-and-open-choices).

`LLMSettings.from_env()` reads these environment variables when called:

| Variable | Meaning |
|---|---|
| `CATALYST_LLM_PROVIDER` | Required: `openai`, `anthropic` or `ollama` |
| `CATALYST_LLM_MODEL` | Required model ID; no implicit model or fallback |
| `OPENAI_API_KEY` | Required credential for OpenAI |
| `ANTHROPIC_API_KEY` | Required credential for Anthropic |
| `CATALYST_LLM_TIMEOUT_SECONDS` | Positive finite SDK network timeout; defaults to 60 |
| `CATALYST_LLM_MAX_OUTPUT_TOKENS` | Positive integer output-token limit; defaults to 8192 |
| `CATALYST_OLLAMA_HOST` | Ollama HTTP(S) origin; defaults to `http://localhost:11434` |

For local setup, copy the configuration example from the repository root:

```bash
cp .env.example .env
```

Choose exactly one provider block in `.env`, commenting out OpenAI before
uncommenting Claude or Ollama. Replace the selected cloud provider's placeholder
key with your key; local Ollama needs no key and requires a running server with
the selected model installed. OpenAI with `gpt-6.1-sol` is active in the example;
change `CATALYST_LLM_MODEL` to use another supported model. Git ignores `.env`
and allows `.env.example`, which contains only placeholder credentials.
Load your local file explicitly when starting both tools:

```bash
uv run --locked --env-file .env catalyst-mcp \
  --database data/catalyst.sqlite3 \
  --live-analysis --live-ideation
```

You can also set these variables directly in the launching environment. No `.env`
file is automatically loaded by Catalyst, and imports do not read configuration
or make requests. The API key is held as a
Pydantic `SecretStr`, excluded from the settings representation and serialization.
Invalid environment configuration raises a fixed message without supplied values.
Model access and Structured Outputs support must be verified for the chosen model.
Only the selected cloud provider's key is read. Local Ollama needs no key and
ignores cloud credentials. Its host must contain no username, password, path,
query or fragment. No model is downloaded or started by these clients.

The OpenAI client uses the official `openai` 2.x SDK, locked to 2.54.0, and its
[Responses API](https://developers.openai.com/api/reference/python).
It requests [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
using the supplied Pydantic model's JSON Schema, `strict: true` and `store: false`.
Backend instructions and input data are separate request fields. The caller must
supply an object schema supported by the chosen provider/model; both existing
generated-content schemas are exercised in offline tests.

The provider code has five classes and one selection function:

- `LLMSettings` in `settings.py` validates provider, model, credential and timeout
  values. `validate_api_key` rejects empty or whitespace-containing credentials.
  `from_env` accepts an optional environment mapping for deterministic tests; it
  reads values without loading files or changing the process environment.
  `validate_provider_credentials` requires a key for cloud providers and keeps
  local Ollama credential-free. `validate_ollama_host` validates the server origin.
- `JSONClient` in `llm_client.py` is the shared `Protocol`: `generate_json` accepts
  trusted instructions, input text and an output model, and returns completed
  response text for the calling workflow to validate.
- `OpenAIJSONClient` implements that contract. Its constructor captures settings
  without I/O. `generate_json` opens one SDK client, makes one Responses request,
  closes the client, rejects incomplete/failed responses, refusals and blank text,
  then returns the original text. Timeouts become `TimeoutError`; other SDK API
  failures become `RuntimeError`, with fixed messages and no provider details.
- `AnthropicJSONClient` uses the official `anthropic` SDK, locked to 1.17.0.
  Its constructor checks provider selection. `generate_json` calls Messages with
  separate system/user content and `output_config.format`. The SDK's public
  `transform_schema` helper prepares supported constraints without changing our
  original models. Only `end_turn` with non-blank text succeeds; refusals and token
  truncation fail. See [Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
- `OllamaJSONClient` implements the documented
  [non-streaming chat endpoint](https://docs.ollama.com/api/chat) with HTTPX2 2.16.0.
  Its constructor checks provider selection; `generate_json` sends system/user
  messages and the schema as `format`, requires `done=true` and `done_reason=stop`,
  and returns non-blank assistant text. This one-endpoint adapter uses HTTPX2
  directly rather than adding another SDK. It sends no credentials, ignores
  environment proxy settings, follows no redirects and never pulls a missing model.
- `create_json_client(settings)` selects one of these three implementations.
  It performs no I/O and provides no fallback to another provider or model.

SDK retries are disabled. The services validate generated content and make at
most one corrective generation call. The network timeout applies to connection, read,
write and pool operations; it is not a total wall-clock deadline for a complete
tool call. Cloud endpoints are explicit; Ollama uses the configured origin. Every
request has no previous conversation history. OpenAI requests no stored response;
that API-specific option is not sent to Anthropic or Ollama. Clients write no
domain records. The token cap maps to OpenAI `max_output_tokens`, Anthropic
`max_tokens`, or Ollama `options.num_predict`; an exhausted cap is a failure.
Ollama has no separate refusal flag in this endpoint; generated-content validation
remains essential. Its [Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)
support is used with a local server; Ollama Cloud is outside this adapter's scope.

See the mocked [OpenAI](EXAMPLES.md#openai-client-example),
[Anthropic](EXAMPLES.md#anthropic-client-example) and
[Ollama](EXAMPLES.md#ollama-client-example) examples for concrete requests,
returned JSON and client cleanup without model calls.

## Tests

[pytest](https://docs.pytest.org/en/stable/) is a development dependency.

```bash
uv run --locked pytest
```

The current tests cover analysis and ideation inputs, generated content and the
complete Business Artifact and Catalog shapes, plus persistence of both record
types in real temporary SQLite files. They check strict types, all 12 business-model
sections, alignment structure, metadata consistency, source associations, JSON
round trips, process restart persistence and failure rollback. Markdown tests for
both record types parse the output as CommonMark and verify content preservation,
escaping, completeness and determinism. Analysis and ideation workflow tests use
scripted fake providers to check limits, bounded correction, metadata, exact idea
counts, source-element matches and failure atomicity. MCP tests use the official client in process and real console-command
subprocesses, checking discovery, complete results, failures, restart persistence
and JSON-RPC stdout. The full two-tool sequence and ideation after process restart
are also exercised. OpenAI adapter checks use the real SDK with HTTPX mock
transport to verify serialization, responses, failure handling, disabled retries
and connection cleanup. No live model provider or selected AI host is exercised.
JSON/Markdown resource checks verify complete data, native tool links, MIME types,
exact URI matching, deterministic rendering, literal special characters, safe
protocol errors, unchanged stored records and reads without provider calls.

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
- `tests/test_catalog_markdown.py` covers Catalog metadata, source references,
  all case fields and alignments, literal text and unchanged saved records.
- `tests/test_artifact_service.py` covers analysis with scripted responses,
  correction limits, provider failures and a real SQLite commit failure.
- `tests/test_artifact_provider.py` covers the packaged analysis prompt, separate
  source data, correction, and the complete configured-provider/MCP/storage path
  through all three adapters with mocked HTTP.
- `tests/test_catalog_service.py` covers ideation from saved sources, exact counts
  and alignments, limits, correction, source preservation and failed-commit rollback.
- `tests/test_catalog_provider.py` covers the packaged ideation prompt, source/count/focus
  data, corrections and complete MCP/storage results through all three adapters
  with mocked HTTP, including failed-generation atomicity and source preservation.
- `tests/test_artifact_mcp.py` covers analysis discovery and schemas, strict
  arguments, safe failure results, CLI startup and real stdio exchanges.
- `tests/test_catalog_mcp.py` covers ideation discovery and schemas, strict
  arguments, saved-source handling, complete results, correction and failed commits.
- `tests/test_mcp_flow.py` covers both tools through real stdio, independent scripts,
  ideation after restart, rejected count/alignment output, tool links and both
  resource formats after restart, plus configured mixed/live modes with mocked HTTP.
- `tests/test_mcp_resource.py` covers JSON/Markdown discovery and reads, exact
  URIs, complete payloads, MIME types, determinism, safe errors and unchanged data/files.
- `tests/test_llm_settings.py` covers provider/model selection, credentials,
  finite positive timeouts, safe configuration errors and unsupported providers.
- `tests/test_llm_client.py` covers the OpenAI JSON client through the actual SDK
  with mocked HTTP, including schemas, request separation, failures and cleanup.
- `tests/test_llm_anthropic.py` covers the real Anthropic SDK with mocked HTTP,
  schema conversion, stop reasons, failures, credentials and cleanup.
- `tests/test_llm_ollama.py` covers Ollama HTTP requests, configured origins,
  completion checks, malformed envelopes, failures and cleanup.

`markdown-it-py` is a development dependency used to parse Markdown in tests.
The production renderer uses Python's standard library and the existing models.

## Build the package

```bash
uv build
```

This creates a source distribution and a wheel in the ignored `dist/` directory.

## Project guidance

- [Product scope and requirements](PROJECT_CONTEXT.md)
- [MVP system design](SYSTEM_DESIGN.md)
- [Contributor agreement and implementation checklist](../AGENTS.md)

Implementation proceeds in small, explicitly authorized steps. Dependency
requirements are declared in `pyproject.toml`; `uv.lock` records the resolved
versions for reproducible development installs.
