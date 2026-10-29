"""The complete two-tool workflow through real stdio console subprocesses."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from mcp import Client, MCPError
from mcp.client.stdio import StdioServerParameters

from catalyst_mcp.markdown_views import render_business_artifact, render_use_case_catalog
from catalyst_mcp.models import BusinessArtifact, BusinessModel, UseCaseCatalog
from catalyst_mcp.repository import SQLiteRepository


@pytest.fixture
def response_files(tmp_path):
    """Write synthetic analysis and ideation scripts with matching source elements."""
    sections = {section: [] for section in BusinessModel.model_fields}
    sections["activities"] = ["Repair bicycles"]
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps({
        "name": "Northstar Bikes", "businessModel": sections,
    }), encoding="utf-8")
    ideation_path = tmp_path / "ideation.json"
    ideation_path.write_text(json.dumps({"useCases": [{
        "title": "Repair request triage", "focus": "Workshop efficiency",
        "problem": "Staff manually route repair requests.", "targetUsers": ["Workshop staff"],
        "proposedSolution": "Classify repair requests and suggest a work queue.",
        "businessElementAlignment": [{
            "section": "activities", "element": "Repair bicycles",
            "rationale": "Routes repair work to workshop staff.",
        }],
    }]}), encoding="utf-8")
    return analysis_path, ideation_path


async def _stdio_flow(
    database_path, analysis_paths, ideation_paths, artifact_id=None, *,
    command=None, live_analysis=False, live_ideation=False,
):
    """Run both tools, or ideation against a saved ID, while parsing every stdout line."""
    args = [*(command or [str(Path(sys.executable).with_name("catalyst-mcp"))]), "--database", str(database_path)]
    if live_analysis:
        args.append("--live-analysis")
    if live_ideation:
        args.append("--live-ideation")
    for path in analysis_paths:
        args.extend(["--fake-response", str(path)])
    for path in ideation_paths:
        args.extend(["--fake-ideation-response", str(path)])
    process = await asyncio.create_subprocess_exec(
        *args, cwd=database_path.parent, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    wire = []
    request_id = 0

    async def request(method, params=None):
        """Send one JSON-RPC request and wait for its matching protocol response."""
        nonlocal request_id
        request_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert line, "Server closed stdout before replying"
            response = json.loads(line)
            assert response["jsonrpc"] == "2.0"
            wire.append(response)
            if response.get("id") == request_id:
                assert "error" not in response, response
                return response["result"]

    try:
        initialized = await request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "catalyst-flow-test", "version": "1.0"},
        })
        assert initialized["capabilities"]["resources"] == {"subscribe": False, "listChanged": False}
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        tools = await request("tools/list")
        artifact = None
        tool_results = []
        if artifact_id is None:
            analysis_result = await request("tools/call", {
                "name": "analyze-business-model",
                "arguments": {"businessContent": "Northstar Bikes repairs bicycles."},
            })
            assert analysis_result["isError"] is False
            artifact = analysis_result["structuredContent"]
            tool_results.append(analysis_result)
            assert json.loads(analysis_result["content"][0]["text"]) == artifact
            artifact_id = artifact["id"]
        catalog_result = await request("tools/call", {
            "name": "ideate-use-case",
            "arguments": {"artifactId": artifact_id, "numberOfIdeas": 1, "focus": "Workshop efficiency"},
        })
        tool_results.append(catalog_result)
        resources = await request("resources/list")
        listed = {resource["uri"]: resource for resource in resources["resources"]}
        for result in tool_results:
            if result["isError"]:
                assert [item["type"] for item in result["content"]] == ["text"]
                continue
            assert [item["type"] for item in result["content"]] == ["text", "resource_link", "resource_link"]
            payload = result["structuredContent"]
            canonical = payload.get("uri") or f"catalyst://use-case-catalog/{payload['id']}"
            assert [item["uri"] for item in result["content"][1:]] == [canonical, f"{canonical}/view.md"]
            for link in result["content"][1:]:
                assert link["name"] == listed[link["uri"]]["name"]
                assert link["mimeType"] == listed[link["uri"]]["mimeType"]
        saved = SQLiteRepository(database_path)
        for resource in resources["resources"]:
            result = await request("resources/read", {"uri": resource["uri"]})
            assert len(result["contents"]) == 1
            content = result["contents"][0]
            assert content["uri"] == resource["uri"]
            assert content["mimeType"] == resource["mimeType"]
            canonical = resource["uri"]
            markdown = content["mimeType"] == "text/markdown"
            if markdown:
                assert canonical.endswith("/view.md")
                canonical = canonical[:-len("/view.md")]
            else:
                assert content["mimeType"] == "application/json"
            if canonical.startswith("catalyst://business-artifact/"):
                record = saved.get_business_artifact(canonical.removeprefix("catalyst://business-artifact/"))
                expected = render_business_artifact(record) if markdown else record.model_dump_json()
            else:
                assert canonical.startswith("catalyst://use-case-catalog/")
                record = saved.get_use_case_catalog(canonical.removeprefix("catalyst://use-case-catalog/"))
                expected = render_use_case_catalog(record) if markdown else record.model_dump_json()
            assert content["text"] == expected
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
        response = json.loads(line)
        assert response["jsonrpc"] == "2.0"
        wire.append(response)
    return tools, artifact, catalog_result, stderr.decode(), wire


def test_two_tool_flow_and_ideation_after_restart(tmp_path, response_files):
    """Use the returned artifact ID for ideation, then restart with only an ideation script."""
    analysis_path, ideation_path = response_files
    database_path = tmp_path / "catalyst.sqlite3"
    tools, artifact_data, result, stderr, wire = asyncio.run(_stdio_flow(
        database_path, [analysis_path], [ideation_path]
    ))
    assert [tool["name"] for tool in tools["tools"]] == ["analyze-business-model", "ideate-use-case"]
    assert result["isError"] is False
    assert len(result["content"]) == 3 and result["content"][0]["type"] == "text"
    catalog = UseCaseCatalog.model_validate_json(result["content"][0]["text"])
    artifact = BusinessArtifact.model_validate_json(json.dumps(artifact_data))
    assert result["structuredContent"] == catalog.model_dump(mode="json")
    assert catalog.sourceArtifact.id == artifact.id
    assert len(catalog.useCases) == 1
    assert catalog.useCases[0].businessElementAlignment[0].element == artifact.businessModel.activities[0]
    assert "uri" not in result["structuredContent"]
    repository = SQLiteRepository(database_path)
    assert repository.get_business_artifact(artifact.id) == artifact
    assert repository.get_use_case_catalog(catalog.id) == catalog
    assert len(wire) == 9
    assert "analyze-business-model saved artifact_id=" in stderr
    assert "ideate-use-case saved catalog_id=" in stderr
    assert "Northstar Bikes" not in stderr

    _, restarted_artifact, restarted_result, restarted_stderr, restarted_wire = asyncio.run(_stdio_flow(
        database_path, [], [ideation_path], artifact_id=artifact.id
    ))
    assert restarted_artifact is None
    assert restarted_result["isError"] is False
    assert restarted_result["structuredContent"]["sourceArtifact"] == {"id": artifact.id}
    assert restarted_result["structuredContent"]["id"] != catalog.id
    assert "0 analysis and 1 ideation scripted fake responses" in restarted_stderr
    assert len(restarted_wire) == 10
    reopened = SQLiteRepository(database_path)
    assert reopened.list_business_artifacts() == [artifact]
    assert reopened.get_use_case_catalog(catalog.id) == catalog
    assert len(reopened.list_use_case_catalogs()) == 2


def test_two_script_corrections_are_independent(tmp_path, response_files):
    """Consume correction responses separately for each tool in one stdio session."""
    analysis_path, ideation_path = response_files
    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_text("private-provider-output-marker", encoding="utf-8")
    database_path = tmp_path / "catalyst.sqlite3"
    _, artifact, result, stderr, wire = asyncio.run(_stdio_flow(
        database_path, [invalid_path, analysis_path], [invalid_path, ideation_path]
    ))
    assert result["isError"] is False
    assert result["structuredContent"]["sourceArtifact"] == {"id": artifact["id"]}
    assert "private-provider-output-marker" not in stderr
    repository = SQLiteRepository(database_path)
    assert len(repository.list_business_artifacts()) == len(repository.list_use_case_catalogs()) == 1
    assert len(wire) == 9


def test_failed_ideation_keeps_saved_artifact_and_no_catalog(tmp_path, response_files):
    """Reject two count/alignment failures even with a valid third ideation response."""
    analysis_path, ideation_path = response_files
    payload = json.loads(ideation_path.read_text(encoding="utf-8"))
    wrong_count = deepcopy(payload)
    wrong_count["useCases"] *= 2
    wrong_alignment = deepcopy(payload)
    wrong_alignment["useCases"][0]["businessElementAlignment"][0]["element"] = "private-invalid-reference"
    invalid_count_path = tmp_path / "wrong-count.json"
    invalid_count_path.write_text(json.dumps(wrong_count), encoding="utf-8")
    invalid_alignment_path = tmp_path / "wrong-alignment.json"
    invalid_alignment_path.write_text(json.dumps(wrong_alignment), encoding="utf-8")
    database_path = tmp_path / "catalyst.sqlite3"
    _, artifact_data, result, stderr, wire = asyncio.run(_stdio_flow(
        database_path, [analysis_path], [invalid_count_path, invalid_alignment_path, ideation_path]
    ))
    assert result["isError"] is True
    assert result.get("structuredContent") is None
    assert "private-invalid-reference" not in result["content"][0]["text"] + stderr
    assert "ideate-use-case failed:" in stderr
    artifact = BusinessArtifact.model_validate_json(json.dumps(artifact_data))
    repository = SQLiteRepository(database_path)
    assert repository.list_business_artifacts() == [artifact]
    assert repository.list_use_case_catalogs() == []
    assert len(wire) == 7


def test_both_resource_formats_after_restart_without_provider_scripts(tmp_path, response_files):
    """Read both formats of both tool-created records with no configured generation scripts."""
    analysis_path, ideation_path = response_files
    database_path = tmp_path / "catalyst.sqlite3"
    _, artifact, result, _, _ = asyncio.run(_stdio_flow(
        database_path, [analysis_path], [ideation_path]
    ))
    catalog = result["structuredContent"]

    async def read_after_restart():
        """Use the official SDK client for both views after a process restart."""
        parameters = StdioServerParameters(
            command=str(Path(sys.executable).with_name("catalyst-mcp")),
            args=["--database", str(database_path)],
        )
        async with Client(parameters, read_timeout_seconds=10) as client:
            listing = await client.list_resources()
            assert listing.next_cursor is None
            values = {}
            for resource in listing.resources:
                content = (await client.read_resource(resource.uri)).contents[0]
                assert content.uri == resource.uri
                assert content.mime_type == resource.mime_type
                if content.mime_type == "application/json":
                    values[resource.uri] = json.loads(content.text)
                else:
                    assert content.mime_type == "text/markdown"
                    values[resource.uri] = content.text
            with pytest.raises(MCPError) as missing:
                await client.read_resource("catalyst://business-artifact/ba_missing")
            assert missing.value.code == -32602
            assert missing.value.message == "Resource not found."
            with pytest.raises(MCPError) as missing_markdown:
                await client.read_resource("catalyst://use-case-catalog/uc_missing/view.md")
            assert missing_markdown.value.code == -32602
            with pytest.raises(MCPError) as cursor:
                await client.list_resources(cursor="invalid-cursor", cache_mode="bypass")
            assert cursor.value.code == -32602
            return values

    values = asyncio.run(read_after_restart())
    saved_artifact = BusinessArtifact.model_validate_json(json.dumps(artifact))
    saved_catalog = UseCaseCatalog.model_validate_json(json.dumps(catalog))
    assert values == {
        artifact["uri"]: artifact,
        f"{artifact['uri']}/view.md": render_business_artifact(saved_artifact),
        f"catalyst://use-case-catalog/{catalog['id']}": catalog,
        f"catalyst://use-case-catalog/{catalog['id']}/view.md": render_use_case_catalog(saved_catalog),
    }
    repository = SQLiteRepository(database_path)
    assert repository.get_business_artifact(artifact["id"]).model_dump(mode="json") == artifact
    assert repository.get_use_case_catalog(catalog["id"]).model_dump(mode="json") == catalog


@pytest.mark.parametrize("mode", ["ideation", "analysis", "both", "saved_source"])
@pytest.mark.parametrize("correct_first", [False, True])
def test_configured_stdio_generation_modes(tmp_path, response_files, monkeypatch, mode, correct_first):
    """Run real CLI/stdio mode combinations with mocked Ollama and complete resource reads."""
    analysis_path, ideation_path = response_files
    analysis_json = analysis_path.read_text(encoding="utf-8")
    ideation_json = ideation_path.read_text(encoding="utf-8")
    live_analysis = mode in ("analysis", "both")
    live_ideation = mode in ("ideation", "both", "saved_source")
    ideation_replies = (["private-rejected-output-marker"] if correct_first else []) + [ideation_json]
    reply_path = tmp_path / "http-replies.json"
    reply_path.write_text(json.dumps({
        "analysis": analysis_json, "ideation": ideation_replies,
        "live_analysis": live_analysis, "live_ideation": live_ideation,
    }), encoding="utf-8")
    monkeypatch.setenv("CATALYST_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("CATALYST_LLM_MODEL", "synthetic-local-model")
    monkeypatch.setenv("CATALYST_OLLAMA_HOST", "http://localhost:11434")
    database_path = tmp_path / "configured.sqlite3"
    artifact_id = None
    original_source = None
    if mode == "saved_source":
        from catalyst_mcp.llm_client import FakeAnalysisProvider
        from catalyst_mcp.services import analyze_business_model

        original_source = analyze_business_model(
            "Northstar Bikes repairs bicycles.", provider=FakeAnalysisProvider(analysis_json),
            repository=SQLiteRepository(database_path),
        )
        artifact_id = original_source.id
    fake_ideation_paths = []
    if not live_ideation:
        for index, text in enumerate(ideation_replies):
            path = tmp_path / f"fake-ideation-{index}.json"
            path.write_text(text, encoding="utf-8")
            fake_ideation_paths.append(path)
    bootstrap = '''
import json
import sys
from pathlib import Path
import httpx2
import catalyst_mcp.llm_client as llm
from catalyst_mcp import main

script = json.loads(Path(sys.argv.pop(1)).read_text(encoding="utf-8"))
real_http_client = httpx2.Client
real_factory = llm.create_json_client
selection_count = 0
analysis_calls = 0
ideation_calls = 0
expected_ideation_calls = len(script["ideation"]) if script["live_ideation"] else 0

def respond(request):
    global analysis_calls, ideation_calls
    body = json.loads(request.content)
    data = json.loads(body["messages"][1]["content"])
    assert body["stream"] is False
    if "businessContent" in data:
        analysis_calls += 1
        assert script["live_analysis"]
        text = script["analysis"]
    else:
        ideation_calls += 1
        assert script["live_ideation"]
        assert data["sourceArtifact"]["businessModel"]["activities"] == ["Repair bicycles"]
        assert data["numberOfIdeas"] == 1 and data["focus"] == "Workshop efficiency"
        assert "Propose Data & AI use cases" in body["messages"][0]["content"]
        text = script["ideation"].pop(0)
    return httpx2.Response(200, json={
        "done": True, "done_reason": "stop", "message": {"role": "assistant", "content": text},
    })

def local_http_client(**options):
    return real_http_client(**options, transport=httpx2.MockTransport(respond))

def selected_client(settings):
    global selection_count
    selection_count += 1
    return real_factory(settings)

llm.httpx2.Client = local_http_client
llm.create_json_client = selected_client
main()
assert selection_count == 1
assert analysis_calls == (1 if script["live_analysis"] else 0)
assert ideation_calls == expected_ideation_calls
'''
    tools, artifact, result, stderr, wire = asyncio.run(_stdio_flow(
        database_path, [] if live_analysis or mode == "saved_source" else [analysis_path],
        fake_ideation_paths, artifact_id,
        command=[sys.executable, "-c", bootstrap, str(reply_path)],
        live_analysis=live_analysis, live_ideation=live_ideation,
    ))
    assert [tool["name"] for tool in tools["tools"]] == ["analyze-business-model", "ideate-use-case"]
    assert result["isError"] is False
    catalog = UseCaseCatalog.model_validate_json(result["content"][0]["text"])
    source_id = original_source.id if original_source is not None else artifact["id"]
    assert catalog.sourceArtifact.id == source_id
    reopened = SQLiteRepository(database_path)
    assert reopened.get_use_case_catalog(catalog.id) == catalog
    if original_source is not None:
        assert reopened.get_business_artifact(source_id) == original_source
    else:
        assert reopened.get_business_artifact(source_id).model_dump(mode="json") == artifact
    assert wire and "no LLM is connected" not in stderr
    if live_ideation:
        assert "live ideation provider=ollama" in stderr
    if live_analysis:
        assert "live analysis provider=ollama" in stderr
    assert "private-rejected-output-marker" not in stderr
