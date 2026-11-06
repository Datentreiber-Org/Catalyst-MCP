**Catalyst — Open-Source MCP Server for Data & AI Business Design**

**From business context to AI opportunities — with humans and AI working together.**

**Why Catalyst?**

Data & AI Business Design often involves disconnected tools, workshops, documents, and teams. Important business context can be lost between discussions, decisions, and implementation.

AI can accelerate the process, but it also introduces new challenges: fragmented workflows, unverified outputs, and the need for human judgment.

**What is Catalyst?**

Catalyst is Datentreiber's open-source MCP (Model Context Protocol) server in development, designed to make Data & AI Business Design methods and capabilities accessible through compatible AI applications.

Our goal is to help business professionals, data experts, and AI agents work together to explore opportunities, challenge assumptions, and develop value-oriented Data & AI solutions.

**Building Catalyst Together**

We are developing Catalyst in public and inviting early users, developers, and business professionals to share ideas, test features, and provide feedback.

**The more you share, the more you learn.**

Join our Catalyst Co-Creation Community:

[https://community.datentreiber.com/gruppen/catalyst-co-creation/](https://community.datentreiber.com/gruppen/catalyst-co-creation/)

**Explore Catalyst**

View the Catalyst presentation from our first Co-Creation Community Circle:
[https://miro.com/app/board/uXjVEZUGFeQ=/](https://miro.com/app/board/uXjVEZUGFeQ=/)

## Current MVP

Catalyst turns business text into a saved business model, then uses that model
to develop aligned Data & AI use cases:

```text
Business text → Business Artifact → Use-case Catalog
```

| Tool | What it does |
|---|---|
| `analyze-business-model` | Extracts all 12 business-model sections and saves a complete Business Artifact |
| `ideate-use-case` | Loads a saved artifact and creates a Catalog with the requested number of aligned ideas |

Each successful tool call returns the complete saved record and links to JSON
and Markdown views. Results persist in a local SQLite database across restarts.
Markdown is rendered from the saved JSON without another model call.

OpenAI, Anthropic and local Ollama adapters are available. You select the
provider and model; both tools use that selection.

## Get started

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Catalyst requires Python 3.12 or later; uv can install a missing interpreter.

```bash
git clone https://github.com/Datentreiber-Org/Catalyst-MCP.git
cd Catalyst-MCP
uv sync --locked --no-dev
cp .env.example .env
uv run --locked --no-sync catalyst-mcp --help
```

Then follow the [installation and client setup guide](docs/CLIENT_SETUP.md):

1. Edit `.env` to select OpenAI, Anthropic or Ollama and configure that provider.
2. Choose a persistent database location.
3. Register Catalyst as a local stdio MCP server in your AI application.
4. Verify the connection and try the example below.

In PowerShell, use `Copy-Item .env.example .env` for the copy step.
Environment activation is unnecessary. Your AI application starts the server
when it connects.

Codex can register Catalyst at user level, so chats can use it from any folder
without creating a Codex project. An optional
[Codex workflow plugin](docs/CLIENT_SETUP.md#optional-codex-workflow-plugin)
provides a guided business conversation after the MCP connection is configured.

## Example

After connecting, ask your AI application:

```text
Use Catalyst to analyze this business: Northstar Bikes repairs bicycles for
local cyclists. Customers book repairs by phone and pay per repair. The workshop
has two mechanics. Then generate two Data & AI ideas focused on appointment
planning, using the saved business artifact.
```

The expected flow is one saved Business Artifact followed by a Catalog containing
exactly two ideas linked to that artifact. Your AI application makes two tool
calls and passes the returned artifact ID to ideation. Model wording varies;
review the extracted facts, assumptions and proposed ideas.

Generation uses your configured provider and can incur cloud API charges.
Reading saved results makes no model call. See
[connection verification](docs/CLIENT_SETUP.md#verify-the-connection-and-try-an-example)
for resource access and restart checks.

## Development status and limits

Catalyst is in development. Automated checks cover strict schemas, persistence,
source alignment, deterministic Markdown and MCP behavior using scripted
providers or mocked HTTP.

Separate checks have verified one OpenAI live-model flow and Codex desktop
tool/resource access with restart persistence. These are limited samples.
Broader model quality, live Anthropic/Ollama behavior, other operating systems
and other clients remain unverified. The optional plugin's desktop business-user
acceptance retry is still pending.

The MVP accepts text up to 20,000 characters and requests for 1–10 ideas.
PDF extraction is a separate preparation step. The current server uses local
stdio; editing saved records, custom UI, ROI and prioritization are future work.
See [product scope and open choices](docs/PROJECT_CONTEXT.md) for details.

## Documentation

| Guide | Contents |
|---|---|
| [Client setup](docs/CLIENT_SETUP.md) | Installation, provider setup, storage, Codex/generic client configuration, optional plugin and troubleshooting |
| [Examples](docs/EXAMPLES.md) | Complete runnable Python and MCP examples with expected outputs |
| [Development](docs/DEVELOPMENT.md) | Architecture, modules, provider configuration, tests and builds |
| [Product scope](docs/PROJECT_CONTEXT.md) | MVP requirements, current verification and future capabilities |
| [System design](docs/SYSTEM_DESIGN.md) | Tool contracts, storage/resource behavior and implementation decisions |

## Contributing and support

Early feedback, testing and contributions are welcome. Use the Co-Creation
Community linked above to share questions, ideas and feedback.

Before changing the project, read the
[contributor guidance and checklist](AGENTS.md) and the
[development guide](docs/DEVELOPMENT.md). Keep contributions focused and include
relevant verification. Use synthetic business content in public examples and
reports.

## License

Copyright 2026 Datentreiber. Licensed under [Apache-2.0](LICENSE).
See [NOTICE](NOTICE) for the project attribution.
