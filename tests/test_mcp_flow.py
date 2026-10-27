"""The complete two-tool workflow through real stdio console subprocesses."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

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


async def _stdio_flow(database_path, analysis_paths, ideation_paths, artifact_id=None):
    """Run both tools, or ideation against a saved ID, while parsing every stdout line."""
    args = [str(Path(sys.executable).with_name("catalyst-mcp")), "--database", str(database_path)]
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
        assert "resources" not in initialized["capabilities"]
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        tools = await request("tools/list")
        artifact = None
        if artifact_id is None:
            analysis_result = await request("tools/call", {
                "name": "analyze-business-model",
                "arguments": {"businessContent": "Northstar Bikes repairs bicycles."},
            })
            assert analysis_result["isError"] is False
            artifact = analysis_result["structuredContent"]
            assert json.loads(analysis_result["content"][0]["text"]) == artifact
            artifact_id = artifact["id"]
        catalog_result = await request("tools/call", {
            "name": "ideate-use-case",
            "arguments": {"artifactId": artifact_id, "numberOfIdeas": 1, "focus": "Workshop efficiency"},
        })
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
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
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
    assert len(wire) == 4
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
    assert len(restarted_wire) == 3
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
    assert len(wire) == 4


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
    assert len(wire) == 4
