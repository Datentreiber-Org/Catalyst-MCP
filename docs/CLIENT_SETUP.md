# Install Catalyst and connect an MCP client

Catalyst runs locally as a stdio MCP server. A compatible AI application launches
the process and calls its tools; Catalyst calls the LLM provider you configure
and saves results in your SQLite database. Your application's chat subscription
does not supply Catalyst's provider credentials.

The client must support launching a local stdio server. Catalyst currently
provides no HTTP endpoint for clients that accept only remote server URLs.
The optional Codex workflow plugin is described below.

## Clone and install

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/), then
run these commands in a terminal:

```bash
git clone https://github.com/Datentreiber-Org/Catalyst-MCP.git
cd Catalyst-MCP
uv sync --locked --no-dev
```

The project selects Python 3.12 through `.python-version` and requires Python
3.12 or later. uv can install a missing interpreter automatically. To install
Python 3.12 explicitly, use `uv python install 3.12` as described in the
[uv Python guide](https://docs.astral.sh/uv/guides/install-python/).

`uv sync --locked --no-dev` creates `.venv` and installs the locked runtime
dependencies. Environment activation is unnecessary. Contributors can instead
use `uv sync --locked` to include development dependencies.

## Configure your provider

Copy the example once, then edit your local `.env`:

```bash
cp .env.example .env
```

In PowerShell, use `Copy-Item .env.example .env`.

Choose exactly one provider block, commenting out the others:

| Provider | Settings in `.env` | Preparation |
|---|---|---|
| OpenAI | `CATALYST_LLM_PROVIDER=openai`, `CATALYST_LLM_MODEL`, `OPENAI_API_KEY` | Replace the placeholder key and choose a model your API account can access |
| Anthropic | `CATALYST_LLM_PROVIDER=anthropic`, `CATALYST_LLM_MODEL`, `ANTHROPIC_API_KEY` | Replace the placeholder key and choose a supported model |
| Local Ollama | `CATALYST_LLM_PROVIDER=ollama`, `CATALYST_LLM_MODEL`, optional `CATALYST_OLLAMA_HOST` | Start Ollama and install the selected model; no API key is required |

Both tools use the same selected provider/model. The model must support the
adapter's structured JSON output. Cloud generation sends the supplied business
content or saved artifact/focus to the selected provider and can incur API charges.
Resource reads use saved data without another model call.

The example also documents optional network-timeout and output-token settings.
See the [configuration reference](DEVELOPMENT.md#llm-configuration-and-provider-clients)
for their defaults and validation. `.env` is Git-ignored; keep real keys there.
Catalyst reads environment variables; the launch command below uses uv to load
`.env` explicitly.

## Locate the installation and choose storage

Check the command and obtain absolute paths:

```bash
uv run --locked --no-sync catalyst-mcp --help
command -v uv
pwd
```

In PowerShell, use `(Get-Command uv).Source` and `(Get-Location).Path` for the
last two commands. Use the absolute `uv.exe` path on Windows. Forward slashes
such as `C:/tools/uv.exe` avoid backslash escaping in JSON and TOML examples.

Replace `/absolute/path/to/uv` and `/absolute/path/to/Catalyst-MCP` below with
your own paths. Choose a persistent, writable database file. The examples use
`data/catalyst.sqlite3` inside the checkout; Catalyst creates missing parent
directories. `data/` and SQLite files are Git-ignored.

Keep the same database path to retrieve previous records after restarting.
Back it up if you need to retain those records. Each successful tool call creates
a new record; repeating a successful generation creates another saved result.

## Register in Codex

Add this table to your user-level `~/.codex/config.toml`, preserving other settings.
If a Catalyst entry already exists, update it rather than adding a duplicate.
This follows the [official Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp).

```toml
[mcp_servers.catalyst]
command = "/absolute/path/to/uv"
args = [
  "run", "--directory", "/absolute/path/to/Catalyst-MCP",
  "--locked", "--no-sync", "--env-file", ".env",
  "catalyst-mcp",
  "--database", "/absolute/path/to/Catalyst-MCP/data/catalyst.sqlite3",
  "--live-analysis", "--live-ideation",
]
startup_timeout_sec = 30
tool_timeout_sec = 180
```

`--directory` selects the backend installation regardless of the chat's folder.
The relative `.env` path is resolved there and works with checkout paths
containing spaces. Each `args` entry is one argument; keep paths containing
spaces in a single quoted entry. The host can launch Catalyst without a `cwd`
setting, an activated environment or a separate running server terminal.

`--no-sync` uses the environment installed above without installing packages
when the host connects. Both live flags enable generation when a tool is called;
startup itself makes no model request. The host's 180-second tool timeout allows
room for a corrective generation; it does not add a total backend deadline.

With the Codex CLI installed and on your `PATH`, check the resolved registration:

```bash
codex mcp get catalyst --json
```

Fully quit and reopen Codex to load the connection, then start or return to a
chat in any folder. A Codex project is unnecessary. Configuration discovery
alone does not prove that the server starts; verify the two tools below too.
If you use only the desktop app, skip the CLI check and verify the tools in a
chat after restarting.

## Register in another local MCP client

For clients that accept an `mcpServers` JSON configuration, adapt this entry:

```json
{
  "mcpServers": {
    "catalyst": {
      "command": "/absolute/path/to/uv",
      "args": [
        "run", "--directory", "/absolute/path/to/Catalyst-MCP",
        "--locked", "--no-sync", "--env-file", ".env",
        "catalyst-mcp",
        "--database", "/absolute/path/to/Catalyst-MCP/data/catalyst.sqlite3",
        "--live-analysis", "--live-ideation"
      ]
    }
  }
}
```

Configuration locations, wrapper keys, timeout options and reload controls vary
by client. Consult its documentation; if it has a command/arguments form, enter
the same executable and argument list there. Set an appropriate tool timeout
where supported. The JSON wrapper is a client convention, not an MCP protocol
requirement. Other clients' display and tool behavior have not been verified.

## Verify the connection and try an example

Ask your host to list Catalyst's available tools. Expect:

- `analyze-business-model`
- `ideate-use-case`

Then try this synthetic request. These generation calls use your configured
provider; connection discovery and reading results do not generate content.

```text
Use Catalyst to analyze this business: Northstar Bikes repairs bicycles for
local cyclists. Customers book repairs by phone and pay per repair. The workshop
has two mechanics. Then generate two Data & AI ideas focused on appointment
planning, using the saved business artifact.
```

Expect one saved Business Artifact followed by a Catalog with exactly two cases
and `sourceArtifact.id` equal to that artifact's ID. Model wording varies.
Each successful result includes the complete saved JSON and links to its JSON
and Markdown views. Resource discovery lists four views for these two records.
An existing database may list additional records. Markdown display depends on
the host; the observed Codex interface opened it as plain text.

Restart the client and ask it to retrieve these same saved records without
generating again. IDs, content, timestamps and the Catalog's source association
should be preserved. PDF extraction is a separate preparation step; the analysis
tool accepts text, up to 20,000 characters. Ideation accepts 1–10 ideas and an
optional focus, using a saved artifact from the selected database.

## Optional Codex workflow plugin

After the MCP connection is configured, install the local workflow package
with a Codex CLI that supports plugin commands and is available on your `PATH`:

```bash
codex plugin marketplace add /absolute/path/to/Catalyst-MCP
codex plugin add catalyst@catalyst-local
```

Quote the checkout path in the shell if it contains spaces. Restart Codex, select
the Catalyst skill in the composer (it may appear as `$catalyst:catalyst`), and
ask it to help develop business-aligned Data & AI ideas. It asks for missing
business text and preferences, calls the tools and presents saved results.

The plugin supplies workflow instructions and display metadata. It requires
the separately configured MCP backend, environment and provider. Client support
for these plugin commands depends on the installed Codex version.

## Troubleshooting and updates

| Symptom | Check |
|---|---|
| Executable not found | Use the absolute path returned for uv; GUI applications may have a different `PATH` |
| Catalyst command missing | Run `uv sync --locked --no-dev` in the checkout before using `--no-sync` |
| `.env` not found | Keep `--directory` set to the checkout and `--env-file` set to `.env` |
| Live configuration error | Enable exactly one provider block and replace the selected key; Catalyst does not automatically load `.env` |
| Tools appear but generation fails | Check model access/structured-output support, provider availability and output limits; Ollama must be running with the selected model |
| Timeout | Check both the client's tool timeout and Catalyst's provider network timeout; a corrective attempt can require a second request |
| Saved artifact not found | Use the original database file and the actual saved artifact ID |
| Terminal waits after starting the server | This is normal for stdio: it waits for MCP messages; use the client to launch it |
| Checkout moved or renamed | Update the absolute executable, checkout and database paths in the client configuration |

After updating the checkout, run `uv sync --locked --no-dev` again and restart
the MCP connection. Keep your `.env` and database. Removing the client's server
entry disconnects it without deleting those local files.

## Verification limits

The clone-based launch is checked locally on macOS with Python 3.12.2 and uv
0.12.23, using a separate environment, a checkout path containing spaces and a
client working outside the checkout. Synthetic fake responses verify both tools,
source linkage, both resource formats and restart persistence. Live-mode startup
is checked without making a model request.

Earlier checks cover one actual OpenAI live-model flow and actual Codex desktop
tool/resource/restart operations. A desktop business-user retry with the optional
plugin remains pending. This guide does not establish fresh operating-system
installation, Windows/Linux execution, live Anthropic/Ollama behavior or other
clients' compatibility.
