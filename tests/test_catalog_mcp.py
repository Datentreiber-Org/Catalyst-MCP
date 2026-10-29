"""Ideation MCP schemas, complete results and failures using scripted fakes."""

import asyncio
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mcp import Client

from catalyst_mcp.llm_client import FakeAnalysisProvider, FakeIdeationProvider
from catalyst_mcp.models import BusinessArtifact, BusinessModel, IdeateUseCaseInput, UseCaseCatalog
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.server import create_server


@pytest.fixture
def database_path(tmp_path):
    """Keep each MCP check's database separate from development records."""
    return tmp_path / "catalyst.sqlite3"


@pytest.fixture
def repository(database_path):
    """Exercise real SQLite validation and atomic writes behind the MCP handler."""
    return SQLiteRepository(database_path)


@pytest.fixture
def source(repository):
    """Save a synthetic source for ideation without calling analysis."""
    sections = {section: [] for section in BusinessModel.model_fields}
    sections["activities"] = ["Repair bicycles"]
    sections["endUsers"] = ["Cyclists"]
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return repository.save_business_artifact(BusinessArtifact(
        id="ba_demo", name="Northstar Bikes", uri="catalyst://business-artifact/ba_demo",
        createdAt=timestamp, updatedAt=timestamp, businessModel=sections,
    ))


@pytest.fixture
def generated_payload():
    """Supply one complete synthetic idea with two valid source references."""
    return {"useCases": [{
        "title": "Repair request triage", "focus": "Workshop efficiency",
        "problem": "Staff manually route repair requests.",
        "targetUsers": ["Workshop staff"],
        "proposedSolution": "Classify repair requests and suggest a work queue.",
        "businessElementAlignment": [
            {"section": "activities", "element": "Repair bicycles",
             "rationale": "Routes repair work to workshop staff."},
            {"section": "endUsers", "element": "Cyclists",
             "rationale": "Helps cyclists receive a response."},
        ],
    }]}


async def _call_tools(ideation_provider, repository, arguments):
    """Use the official SDK client to discover both tools and call ideation."""
    server = create_server(
        provider=FakeAnalysisProvider(), ideation_provider=ideation_provider, repository=repository
    )
    async with Client(server, raise_exceptions=True, read_timeout_seconds=5) as client:
        tools = await client.list_tools()
        results = [await client.call_tool("ideate-use-case", args) for args in arguments]
    return tools.tools, results


def test_discovery_preserves_ideation_contract(repository):
    """Advertise singular ideation with strict inputs and a complete Catalog schema."""
    provider = FakeIdeationProvider()
    tools, results = asyncio.run(_call_tools(provider, repository, []))
    assert [tool.name for tool in tools] == ["analyze-business-model", "ideate-use-case"]
    tool = tools[1]
    expected_input = IdeateUseCaseInput.model_json_schema()
    expected_input["properties"]["numberOfIdeas"]["maximum"] = 10
    assert tool.input_schema == expected_input
    assert tool.input_schema["required"] == ["artifactId", "numberOfIdeas"]
    assert tool.input_schema["additionalProperties"] is False
    assert tool.output_schema == UseCaseCatalog.model_json_schema(mode="serialization")
    assert "uri" not in tool.output_schema["properties"]
    assert provider.calls == results == []


@pytest.mark.parametrize("focus", [None, "  Workshop focus-marker\n"])
def test_complete_result_and_preserved_focus(repository, source, generated_payload, focus):
    """Return the full committed Catalog in both channels and preserve the source."""
    provider = FakeIdeationProvider(json.dumps(generated_payload))
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1, "focus": focus,
    }]))
    result = results[0]
    assert result.is_error is False
    assert len(result.content) == 3 and result.content[0].type == "text"
    catalog = UseCaseCatalog.model_validate_json(result.content[0].text)
    assert result.structured_content == catalog.model_dump(mode="json")
    assert set(result.structured_content) == {
        "id", "createdAt", "updatedAt", "sourceArtifact", "useCases"
    }
    assert result.structured_content["sourceArtifact"] == {"id": source.id}
    links = result.content[1:]
    canonical_uri = f"catalyst://use-case-catalog/{catalog.id}"
    assert [link.type for link in links] == ["resource_link", "resource_link"]
    assert [link.uri for link in links] == [canonical_uri, f"{canonical_uri}/view.md"]
    assert [link.mime_type for link in links] == ["application/json", "text/markdown"]
    assert "JSON" in links[0].name and "Markdown" in links[1].name
    assert catalog.useCases[0].model_dump(exclude={"id"}) == generated_payload["useCases"][0]
    assert provider.calls == [(source.model_dump_json(), 1, focus, None)]
    assert repository.list_use_case_catalogs() == [catalog]
    assert repository.list_business_artifacts() == [source]


def test_exact_count_at_advertised_maximum(repository, source, generated_payload):
    """Accept ten ideas and preserve all of them with distinct backend IDs."""
    generated_payload["useCases"] *= 10
    provider = FakeIdeationProvider(json.dumps(generated_payload))
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 10,
    }]))
    assert results[0].is_error is False
    cases = results[0].structured_content["useCases"]
    assert len(cases) == len({case["id"] for case in cases}) == 10
    assert provider.calls[0][1:] == (10, None, None)


@pytest.mark.parametrize("updates", [
    {"artifactId": ""}, {"artifactId": None}, {"artifactId": 1},
    {"numberOfIdeas": 0}, {"numberOfIdeas": -1}, {"numberOfIdeas": 11},
    {"numberOfIdeas": True}, {"numberOfIdeas": "1"}, {"numberOfIdeas": 1.0},
    {"numberOfIdeas": None}, {"focus": " \t"}, {"focus": 123},
    {"extra": "private-input-marker"},
])
def test_invalid_input_does_not_consume_script(repository, source, generated_payload, updates, caplog):
    """Reject invalid requests without losing the response for a later valid call."""
    provider = FakeIdeationProvider(json.dumps(generated_payload))
    valid = {"artifactId": source.id, "numberOfIdeas": 1}
    _, results = asyncio.run(_call_tools(provider, repository, [valid | updates, valid]))
    error, success = results
    assert error.is_error is True
    assert error.structured_content is None
    assert [item.type for item in error.content] == ["text"]
    assert "private-input-marker" not in error.content[0].text + caplog.text
    assert success.is_error is False
    assert len(provider.calls) == 1
    assert len(repository.list_use_case_catalogs()) == 1
    assert repository.get_business_artifact(source.id) == source


@pytest.mark.parametrize("arguments", [{}, {"artifactId": "ba_demo"}, {"numberOfIdeas": 1}])
def test_missing_arguments_stop_before_generation(repository, arguments):
    """Require both source ID and count without supplying silent defaults."""
    provider = FakeIdeationProvider()
    _, results = asyncio.run(_call_tools(provider, repository, [arguments]))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert provider.calls == []
    assert repository.list_use_case_catalogs() == []


@pytest.mark.parametrize("problem", [
    "missing_provider", "missing_model", "missing_key", "invalid_provider", "conflicting_scripts",
])
def test_live_ideation_startup_errors_do_not_open_database(tmp_path, monkeypatch, problem):
    """Validate explicit ideation setup on stderr before storage or model requests."""
    monkeypatch.setenv("CATALYST_LLM_PROVIDER", "openai")
    monkeypatch.setenv("CATALYST_LLM_MODEL", "synthetic-model")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-private-key-marker")
    if problem == "missing_provider":
        monkeypatch.delenv("CATALYST_LLM_PROVIDER")
    elif problem == "missing_model":
        monkeypatch.delenv("CATALYST_LLM_MODEL")
    elif problem == "missing_key":
        monkeypatch.delenv("OPENAI_API_KEY")
    elif problem == "invalid_provider":
        monkeypatch.setenv("CATALYST_LLM_PROVIDER", "private-invalid-provider-marker")
    database_path = tmp_path / "live.sqlite3"
    command = Path(sys.executable).with_name("catalyst-mcp")
    arguments = [str(command), "--database", str(database_path), "--live-ideation"]
    if problem == "conflicting_scripts":
        arguments.extend(["--fake-ideation-response", str(tmp_path / "unused.json")])
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and result.stdout == ""
    assert "error:" in result.stderr and "Traceback" not in result.stderr
    assert "synthetic-private-key-marker" not in result.stderr
    assert "private-invalid-provider-marker" not in result.stderr
    assert not database_path.exists()


def test_missing_source_is_distinct_and_does_not_consume_script(repository, source, generated_payload):
    """Report a missing source before generation, then accept the saved source ID."""
    provider = FakeIdeationProvider(json.dumps(generated_payload))
    _, results = asyncio.run(_call_tools(provider, repository, [
        {"artifactId": "ba_missing", "numberOfIdeas": 1},
        {"artifactId": source.id, "numberOfIdeas": 1},
    ]))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert results[0].content[0].text == "Source Business Artifact was not found."
    assert results[1].is_error is False
    assert len(provider.calls) == 1


def test_corrupt_source_returns_safe_error(repository, database_path, source, caplog):
    """Leave invalid stored JSON untouched and do not pass it to the provider."""
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute("UPDATE business_artifacts SET payload_json = 'private-corrupt-marker'")
    provider = FakeIdeationProvider()
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1,
    }]))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert provider.calls == []
    assert "private-corrupt-marker" not in results[0].content[0].text + caplog.text
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT payload_json FROM business_artifacts").fetchone() == ("private-corrupt-marker",)


@pytest.mark.parametrize("problem", ["json", "count", "alignment", "metadata"])
def test_invalid_output_is_corrected_before_success(repository, source, generated_payload, problem):
    """Run the service's bounded correction for invalid shapes, counts or references."""
    invalid = deepcopy(generated_payload)
    if problem == "count":
        invalid["useCases"] *= 2
    elif problem == "alignment":
        invalid["useCases"][0]["businessElementAlignment"][1]["element"] = "Unknown rider"
    elif problem == "metadata":
        invalid["sourceArtifact"] = {"id": "ba_untrusted"}
    invalid_json = "private-output-marker" if problem == "json" else json.dumps(invalid)
    provider = FakeIdeationProvider(invalid_json, json.dumps(generated_payload))
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1,
    }]))
    assert results[0].is_error is False
    assert len(provider.calls) == 2
    assert provider.calls[0][:3] == provider.calls[1][:3]
    assert provider.calls[1][3]
    assert results[0].structured_content["sourceArtifact"] == {"id": source.id}
    assert len(repository.list_use_case_catalogs()) == 1
    assert repository.get_business_artifact(source.id) == source


def test_two_invalid_outputs_have_no_success_payload(repository, source, generated_payload):
    """Stop after two provider responses without exposing or saving invalid output."""
    provider = FakeIdeationProvider("bad-one", "bad-two", json.dumps(generated_payload))
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1,
    }]))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert len(provider.calls) == 2
    assert repository.list_use_case_catalogs() == []
    assert repository.list_business_artifacts() == [source]


@pytest.mark.parametrize("failure", [
    TimeoutError("private-provider-marker"), RuntimeError("private-provider-marker"),
    ValueError("private-provider-marker"), KeyError("private-provider-marker"),
    Exception("private-provider-marker"),
])
def test_provider_failures_do_not_leak_details(repository, source, failure, caplog):
    """Keep provider errors distinct from missing sources and avoid secret logging."""
    provider = FakeIdeationProvider(failure)
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1, "focus": "private-focus-marker",
    }]))
    error = results[0]
    assert error.is_error is True
    assert error.structured_content is None
    assert error.content[0].text != "Source Business Artifact was not found."
    assert "private-provider-marker" not in error.content[0].text + caplog.text
    assert "private-focus-marker" not in error.content[0].text + caplog.text
    assert "ideate-use-case failed:" in caplog.text
    assert len(provider.calls) == 1
    assert repository.list_use_case_catalogs() == []
    assert repository.list_business_artifacts() == [source]


def test_empty_script_is_an_execution_error(repository, source):
    """Fail clearly at the MCP boundary when no ideation response was configured."""
    provider = FakeIdeationProvider()
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1,
    }]))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert len(provider.calls) == 1
    assert repository.list_use_case_catalogs() == []


def test_failed_commit_preserves_existing_records(repository, database_path, source, generated_payload):
    """Report a real deferred commit failure without losing a prior Catalog or source."""
    response = json.dumps(generated_payload)
    _, baseline_results = asyncio.run(_call_tools(FakeIdeationProvider(response), repository, [{
        "artifactId": source.id, "numberOfIdeas": 1,
    }]))
    baseline = UseCaseCatalog.model_validate_json(baseline_results[0].content[0].text)
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.executescript(
            """
            CREATE TABLE commit_parents (id TEXT PRIMARY KEY);
            CREATE TABLE commit_children (
                parent_id TEXT REFERENCES commit_parents(id)
                DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER fail_catalog_commit
            AFTER INSERT ON use_case_catalogs
            BEGIN
                INSERT INTO commit_children (parent_id) VALUES ('missing');
            END;
            """
        )
    provider = FakeIdeationProvider(response, response)
    _, results = asyncio.run(_call_tools(provider, repository, [{
        "artifactId": source.id, "numberOfIdeas": 1,
    }]))
    assert results[0].is_error is True
    assert results[0].structured_content is None
    assert results[0].content[0].text == "Could not read the source or save the Use-case Catalog."
    assert len(provider.calls) == 1
    reopened = SQLiteRepository(database_path)
    assert reopened.list_use_case_catalogs() == [baseline]
    assert reopened.list_business_artifacts() == [source]
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM commit_children").fetchone() == (0,)


@pytest.mark.parametrize("problem", ["missing", "utf8"])
def test_ideation_response_file_errors_use_stderr(tmp_path, problem):
    """Read all response files before opening a database and keep stdout clean."""
    response_path = tmp_path / "ideation.json"
    if problem == "utf8":
        response_path.write_bytes(b"\xff")
    database_path = tmp_path / "catalyst.sqlite3"
    result = subprocess.run([
        str(Path(sys.executable).with_name("catalyst-mcp")),
        "--database", str(database_path), "--fake-ideation-response", str(response_path),
    ], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Could not read a fake-response file." in result.stderr
    assert "Traceback" not in result.stderr
    assert not database_path.exists()
