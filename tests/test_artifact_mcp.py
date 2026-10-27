"""Analysis MCP checks using a scripted fake, SQLite and real stdio processes."""

import asyncio
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from mcp import Client

from catalyst_mcp.llm_client import FakeAnalysisProvider, FakeIdeationProvider
from catalyst_mcp.models import AnalyzeBusinessModelInput, BusinessArtifact, BusinessModel
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.server import create_server


BUSINESS_CONTENT = "Northstar Bikes repairs bicycles for cyclists."
COMMAND = Path(sys.executable).with_name("catalyst-mcp")


@pytest.fixture
def database_path(tmp_path):
    """Keep every MCP check's database separate from development data."""
    return tmp_path / "catalyst.sqlite3"


@pytest.fixture
def repository(database_path):
    """Exercise actual SQLite transactions behind the MCP interface."""
    return SQLiteRepository(database_path)


@pytest.fixture
def response_json():
    """Script a synthetic response without assigning backend metadata."""
    sections = {key: [] for key in BusinessModel.model_fields}
    sections["endUsers"] = ["Cyclists"]
    sections["activities"] = ["Repair bicycles"]
    return json.dumps({"name": "Northstar Bikes", "businessModel": sections})


@pytest.fixture
def response_path(tmp_path, response_json):
    """Supply the CLI with a synthetic UTF-8 provider response file."""
    path = tmp_path / "response.json"
    path.write_text(response_json, encoding="utf-8")
    return path


async def _call_tools(provider, repository, arguments, name="analyze-business-model"):
    """Discover and call a real SDK server in process on the asyncio backend."""
    server = create_server(
        provider=provider, ideation_provider=FakeIdeationProvider(), repository=repository
    )
    async with Client(server, raise_exceptions=True, read_timeout_seconds=5) as client:
        tools = await client.list_tools()
        results = [await client.call_tool(name, args) for args in arguments]
    return tools.tools, results


async def _stdio_exchange(database_path, response_paths, arguments):
    """Speak JSON-RPC to the installed console command and check every stdout line."""
    command_args = [str(COMMAND), "--database", str(database_path)]
    for path in response_paths:
        command_args.extend(["--fake-response", str(path)])
    process = await asyncio.create_subprocess_exec(
        *command_args, cwd=database_path.parent,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    wire_messages = []

    async def exchange(message):
        """Send one request and read its JSON response, allowing notifications."""
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert line, "Server closed stdout before replying"
            response = json.loads(line)
            assert response["jsonrpc"] == "2.0"
            wire_messages.append(response)
            if response.get("id") == message["id"]:
                assert "error" not in response, response
                return response["result"]

    try:
        initialized = await exchange({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "catalyst-test", "version": "1.0"},
            },
        })
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        tools = await exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        results = []
        for request_id, args in enumerate(arguments, start=3):
            results.append(await exchange({
                "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                "params": {"name": "analyze-business-model", "arguments": args},
            }))
    finally:
        process.stdin.close()
        try:
            remaining_stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise
    assert process.returncode == 0, stderr.decode()
    for line in remaining_stdout.splitlines():
        message = json.loads(line)
        assert message["jsonrpc"] == "2.0"
        wire_messages.append(message)
    return initialized, tools, results, stderr.decode(), wire_messages


def test_discovery_preserves_exact_schemas(repository):
    """Keep analysis's strict flat input and complete output alongside ideation."""
    provider = FakeAnalysisProvider()
    tools, results = asyncio.run(_call_tools(provider, repository, []))
    assert results == []
    assert [tool.name for tool in tools] == ["analyze-business-model", "ideate-use-case"]
    tool = tools[0]
    assert tool.name == "analyze-business-model"
    expected_input = AnalyzeBusinessModelInput.model_json_schema()
    expected_input["properties"]["businessContent"]["maxLength"] = 20_000
    assert tool.input_schema == expected_input
    assert tool.input_schema["additionalProperties"] is False
    assert tool.output_schema == BusinessArtifact.model_json_schema(mode="serialization")
    assert provider.calls == []
    assert repository.list_business_artifacts() == []


def test_call_returns_complete_saved_object(repository, response_json):
    """Return the full committed object in structured content and JSON text."""
    provider = FakeAnalysisProvider(response_json)
    _, results = asyncio.run(_call_tools(
        provider, repository, [{"businessContent": BUSINESS_CONTENT}]
    ))
    result = results[0]
    assert result.is_error is False
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert json.loads(result.content[0].text) == result.structured_content
    artifact = BusinessArtifact.model_validate_json(result.content[0].text)
    assert result.structured_content == artifact.model_dump(mode="json")
    assert set(result.structured_content) == {
        "id", "name", "uri", "createdAt", "updatedAt", "businessModel"
    }
    assert repository.list_business_artifacts() == [artifact]
    assert repository.list_use_case_catalogs() == []
    assert provider.calls == [(BUSINESS_CONTENT, None)]


@pytest.mark.parametrize("arguments", [
    {}, {"businessContent": ""}, {"businessContent": " \t\n"},
    {"businessContent": None}, {"businessContent": 123}, {"businessContent": True},
    {"businessContent": ["Repairs"]},
    {"businessContent": BUSINESS_CONTENT, "extra": "private-marker"},
    {"business_content": BUSINESS_CONTENT}, {"businessContent": "x" * 20_001},
])
def test_invalid_arguments_do_not_consume_script(repository, response_json, arguments):
    """Reject invalid calls while preserving the response for a later valid call."""
    provider = FakeAnalysisProvider(response_json)
    _, results = asyncio.run(_call_tools(
        provider, repository, [arguments, {"businessContent": BUSINESS_CONTENT}]
    ))
    error, success = results
    assert error.is_error is True
    assert error.structured_content is None
    assert "private-marker" not in error.content[0].text
    assert success.is_error is False
    assert provider.calls == [(BUSINESS_CONTENT, None)]
    assert len(repository.list_business_artifacts()) == 1


def test_unknown_tool_does_not_generate(repository, response_json):
    """Reject unregistered names without silently routing them to analysis."""
    provider = FakeAnalysisProvider(response_json)
    _, results = asyncio.run(_call_tools(
        provider, repository, [{"businessContent": BUSINESS_CONTENT}], name="unregistered-tool"
    ))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert provider.calls == []
    assert repository.list_business_artifacts() == []


@pytest.mark.parametrize("failure", [
    TimeoutError("private-provider-marker"), RuntimeError("private-provider-marker"),
    ValueError("private-provider-marker"), Exception("private-provider-marker"),
])
def test_provider_failures_return_safe_tool_errors(repository, failure, caplog):
    """Map execution failures without exposing provider details or saving a record."""
    provider = FakeAnalysisProvider(failure)
    _, results = asyncio.run(_call_tools(
        provider, repository, [{"businessContent": "private-business-marker"}]
    ))
    error = results[0]
    assert error.is_error is True
    assert error.structured_content is None
    assert "private-provider-marker" not in error.content[0].text + caplog.text
    assert "private-business-marker" not in error.content[0].text + caplog.text
    assert len(provider.calls) == 1
    assert repository.list_business_artifacts() == []


def test_empty_extraction_is_a_tool_error(repository):
    """Expose insufficient content as failure, without triggering a correction."""
    response = json.dumps({
        "name": "Unknown business",
        "businessModel": {key: [] for key in BusinessModel.model_fields},
    })
    provider = FakeAnalysisProvider(response)
    _, results = asyncio.run(_call_tools(
        provider, repository, [{"businessContent": BUSINESS_CONTENT}]
    ))
    assert results[0].is_error is True
    assert "usable Business Artifact" in results[0].content[0].text
    assert results[0].structured_content is None
    assert len(provider.calls) == 1
    assert repository.list_business_artifacts() == []


def test_commit_failure_is_a_tool_error(repository, database_path, response_json):
    """Return a failed MCP result when a real SQLite commit is rolled back."""
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.executescript(
            """
            CREATE TABLE commit_parents (id TEXT PRIMARY KEY);
            CREATE TABLE commit_children (
                parent_id TEXT REFERENCES commit_parents(id)
                DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER fail_artifact_commit
            AFTER INSERT ON business_artifacts
            BEGIN
                INSERT INTO commit_children (parent_id) VALUES ('missing');
            END;
            """
        )
    provider = FakeAnalysisProvider(response_json)
    _, results = asyncio.run(_call_tools(
        provider, repository, [{"businessContent": BUSINESS_CONTENT}]
    ))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert results[0].content[0].text == "Could not save the Business Artifact."
    assert len(provider.calls) == 1
    assert SQLiteRepository(database_path).list_business_artifacts() == []
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM commit_children").fetchone() == (0,)


def test_stdio_command_and_restart_preserve_results(database_path, response_path):
    """Verify real stdio discovery, complete results and persistence after restart."""
    initialized, tools, results, stderr, wire = asyncio.run(_stdio_exchange(
        database_path, [response_path], [{"businessContent": BUSINESS_CONTENT}]
    ))
    assert initialized["serverInfo"]["name"] == "Catalyst"
    assert initialized["protocolVersion"] == "2025-06-18"
    assert "tools" in initialized["capabilities"]
    assert initialized["capabilities"]["resources"] == {"subscribe": False, "listChanged": False}
    assert "prompts" not in initialized["capabilities"]
    assert [tool["name"] for tool in tools["tools"]] == ["analyze-business-model", "ideate-use-case"]
    assert "outputSchema" in tools["tools"][0]
    first = results[0]
    assert first["isError"] is False
    assert json.loads(first["content"][0]["text"]) == first["structuredContent"]
    first_artifact = BusinessArtifact.model_validate_json(first["content"][0]["text"])
    assert SQLiteRepository(database_path).get_business_artifact(first_artifact.id) == first_artifact
    assert "scripted fake responses; no LLM is connected" in stderr
    assert "saved artifact_id=" + first_artifact.id in stderr
    assert BUSINESS_CONTENT not in stderr
    assert len(wire) == 3

    _, _, restarted_results, _, _ = asyncio.run(_stdio_exchange(
        database_path, [response_path], [{"businessContent": BUSINESS_CONTENT}]
    ))
    assert restarted_results[0]["structuredContent"]["id"] != first_artifact.id
    reopened = SQLiteRepository(database_path)
    assert reopened.get_business_artifact(first_artifact.id) == first_artifact
    assert len(reopened.list_business_artifacts()) == 2
    assert reopened.list_use_case_catalogs() == []


def test_stdio_corrects_invalid_response(database_path, response_path, tmp_path):
    """Consume a second CLI response for correction and save exactly one artifact."""
    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_text("private-invalid-output-marker", encoding="utf-8")
    _, _, results, stderr, _ = asyncio.run(_stdio_exchange(
        database_path, [invalid_path, response_path], [{"businessContent": BUSINESS_CONTENT}]
    ))
    assert results[0]["isError"] is False
    assert results[0]["structuredContent"]["name"] == "Northstar Bikes"
    assert "private-invalid-output-marker" not in stderr
    assert len(SQLiteRepository(database_path).list_business_artifacts()) == 1


def test_stdio_failures_have_no_success_payload(database_path, response_path, tmp_path):
    """Fail malformed output and exhausted scripts while keeping stdout valid JSON."""
    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_text("private-invalid-output-marker", encoding="utf-8")
    _, _, results, stderr, _ = asyncio.run(_stdio_exchange(
        database_path, [invalid_path, invalid_path],
        [{"businessContent": BUSINESS_CONTENT}, {"businessContent": BUSINESS_CONTENT}],
    ))
    for result in results:
        assert result["isError"] is True
        assert result.get("structuredContent") is None
        assert "private-invalid-output-marker" not in result["content"][0]["text"]
    assert "private-invalid-output-marker" not in stderr
    assert "Analysis failed" in stderr
    assert SQLiteRepository(database_path).list_business_artifacts() == []


@pytest.mark.parametrize("problem", ["arguments", "missing_file", "utf8", "database"])
def test_cli_configuration_errors_use_stderr(tmp_path, response_path, problem):
    """Fail startup clearly without putting diagnostics on MCP stdout."""
    database_path = tmp_path / "command.sqlite3"
    args = ["--database", str(database_path), "--fake-response", str(response_path)]
    if problem == "arguments":
        args = []
    elif problem == "missing_file":
        args[-1] = str(tmp_path / "missing.json")
    elif problem == "utf8":
        response_path.write_bytes(b"\xff")
    elif problem == "database":
        database_path.mkdir()
    result = subprocess.run([str(COMMAND), *args], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
    if problem != "database":
        assert not database_path.exists()


def test_import_has_no_server_side_effects(tmp_path):
    """Importing the package and server must not start stdio or create a database."""
    result = subprocess.run(
        [sys.executable, "-c", "import catalyst_mcp; import catalyst_mcp.server"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []
