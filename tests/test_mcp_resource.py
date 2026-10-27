"""Canonical JSON resource discovery and reads with real SQLite persistence."""

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest
from mcp import Client, MCPError

from catalyst_mcp.llm_client import FakeAnalysisProvider, FakeIdeationProvider
from catalyst_mcp.models import BusinessArtifact, BusinessModel, UseCaseCatalog
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.server import create_server


@pytest.fixture
def database_path(tmp_path):
    """Keep each resource test's persistent file separate from development data."""
    return tmp_path / "catalyst.sqlite3"


@pytest.fixture
def repository(database_path):
    """Use actual stored JSON and repository validation for every resource call."""
    return SQLiteRepository(database_path)


@pytest.fixture
def providers():
    """Detect any accidental generation call while listing or reading resources."""
    return FakeAnalysisProvider(), FakeIdeationProvider()


@pytest.fixture
def server(repository, providers):
    """Create the SDK server with empty scripts so resources cannot rely on generation."""
    analysis, ideation = providers
    return create_server(provider=analysis, ideation_provider=ideation, repository=repository)


@pytest.fixture
def artifact():
    """Supply complete synthetic content with explicit empty sections and literal text."""
    sections = {section: [] for section in BusinessModel.model_fields}
    sections["activities"] = ["Repair bicycles", "Diagnose <brakes> & \"gears\"\n🚲"]
    sections["endUsers"] = ["Cyclists", "  Café riders\n*Weekend club*  "]
    timestamp = datetime(2026, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)
    return BusinessArtifact(
        id="ba_demo", name="Northstar's Café <bikes> & \"Repairs\"",
        uri="catalyst://business-artifact/ba_demo", createdAt=timestamp,
        updatedAt=timestamp, businessModel=sections,
    )


@pytest.fixture
def catalog(artifact):
    """Supply all Catalog fields, multiple cases and multiple alignment references."""
    return UseCaseCatalog(
        id="uc_catalog_demo", createdAt=artifact.createdAt, updatedAt=artifact.updatedAt,
        sourceArtifact={"id": artifact.id},
        useCases=[{
            "id": f"uc_{number}", "title": f"Repair idea {number} <triage> & planning",
            "focus": "Workshop efficiency", "problem": "Staff manually route repair requests.",
            "targetUsers": ["Workshop staff", "Café riders\n🚲"] if number == 1 else [],
            "proposedSolution": "Classify requests and suggest a queue.\nKeep the original text.",
            "businessElementAlignment": [
                {"section": "activities", "element": "Repair bicycles", "rationale": "Helps staff route work."},
                {"section": "endUsers", "element": "Cyclists", "rationale": "Helps riders receive a response."},
            ],
        } for number in (1, 2)],
    )


@pytest.fixture
def saved_records(repository, artifact, catalog):
    """Persist both object types before testing discovery or resource reads."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    return artifact, catalog


async def _listing(server, cursor=None):
    """Exercise resources/list through the official client without cached results."""
    result = None
    failure = None
    async with Client(server, raise_exceptions=True) as client:
        try:
            result = await client.list_resources(cursor=cursor, cache_mode="bypass")
        except MCPError as error:
            failure = error
    # Let the client's task groups close before propagating an expected error.
    if failure is not None:
        raise failure
    return result


async def _read(server, uri):
    """Exercise resources/read through the official client without cached results."""
    result = None
    failure = None
    async with Client(server, raise_exceptions=True) as client:
        try:
            result = await client.read_resource(uri, cache_mode="bypass")
        except MCPError as error:
            failure = error
    if failure is not None:
        raise failure
    return result


def test_empty_listing_has_no_next_page(server, providers):
    """Advertise an empty current set without a placeholder or future-format entry."""
    result = asyncio.run(_listing(server))
    assert result.resources == []
    assert result.next_cursor is None
    assert all(provider.calls == [] for provider in providers)


def test_lists_all_saved_records_in_deterministic_order(server, repository, artifact, catalog, providers):
    """List artifact IDs first, then Catalog IDs, independently of insertion order."""
    other_artifact = artifact.model_copy(update={
        "id": "ba_z", "uri": "catalyst://business-artifact/ba_z"
    })
    other_catalog = catalog.model_copy(update={"id": "uc_catalog_z"})
    for record in (other_artifact, artifact):
        repository.save_business_artifact(record)
    for record in (other_catalog, catalog):
        repository.save_use_case_catalog(record)
    first = asyncio.run(_listing(server))
    second = asyncio.run(_listing(server))
    assert first.resources == second.resources
    assert [resource.uri for resource in first.resources] == [
        artifact.uri, other_artifact.uri,
        f"catalyst://use-case-catalog/{catalog.id}",
        f"catalyst://use-case-catalog/{other_catalog.id}",
    ]
    for resource, record in zip(first.resources, (artifact, other_artifact, catalog, other_catalog), strict=True):
        assert resource.mime_type == "application/json"
        assert record.id in resource.name and "JSON" in resource.name
        assert "/view.md" not in resource.uri
    assert artifact.name in first.resources[0].name
    assert first.next_cursor is None
    assert all(provider.calls == [] for provider in providers)


def test_listing_observes_new_saves_in_same_session(server, repository, artifact, catalog):
    """Refresh the current set after saves without requiring a server restart."""
    async def check():
        """List before either save, after the artifact and after the Catalog."""
        async with Client(server, raise_exceptions=True) as client:
            assert (await client.list_resources()).resources == []
            repository.save_business_artifact(artifact)
            assert len((await client.list_resources()).resources) == 1
            repository.save_use_case_catalog(catalog)
            assert len((await client.list_resources()).resources) == 2
    asyncio.run(check())


@pytest.mark.parametrize("kind", ["artifact", "catalog"])
def test_reads_complete_json_and_correct_mime(server, saved_records, providers, kind):
    """Recover every saved field, array, timestamp and literal character from JSON."""
    artifact, catalog = saved_records
    record = artifact if kind == "artifact" else catalog
    uri = artifact.uri if kind == "artifact" else f"catalyst://use-case-catalog/{catalog.id}"
    result = asyncio.run(_read(server, uri))
    assert len(result.contents) == 1
    content = result.contents[0]
    assert content.uri == uri
    assert content.mime_type == "application/json"
    assert content.text == record.model_dump_json()
    assert json.loads(content.text) == record.model_dump(mode="json")
    if kind == "catalog":
        assert "uri" not in json.loads(content.text)
        assert json.loads(content.text)["sourceArtifact"] == {"id": artifact.id}
    assert all(provider.calls == [] for provider in providers)


def test_exact_percent_literal_id_is_not_decoded(server, repository, artifact):
    """Preserve a canonical URI and identifier that contain a literal percent escape."""
    selected = artifact.model_copy(update={
        "id": "ba_literal%2Fid", "uri": "catalyst://business-artifact/ba_literal%2Fid"
    })
    repository.save_business_artifact(selected)
    result = asyncio.run(_read(server, selected.uri))
    assert result.contents[0].uri == selected.uri
    assert json.loads(result.contents[0].text)["id"] == "ba_literal%2Fid"
    with pytest.raises(MCPError) as error:
        asyncio.run(_read(server, "catalyst://business-artifact/ba_literal/id"))
    assert error.value.code == -32602


@pytest.mark.parametrize("uri", [
    "", "catalyst://business-artifact/", "catalyst://use-case-catalog/",
    "catalyst://business-artifact/ba_missing", "catalyst://use-case-catalog/uc_missing",
    "file:///private/private-uri-marker.json", "https://example.invalid/private-uri-marker",
    "catalyst://other/ba_demo", "CATALYST://business-artifact/ba_demo",
    "catalyst://business-artifact/ba_demo/view.md",
    "catalyst://use-case-catalog/uc_catalog_demo/view.md",
    "catalyst://business-artifact/ba_demo/", "catalyst://business-artifact/%62a_demo",
    "catalyst://business-artifact/ba_demo?format=json", "catalyst://business-artifact/ba_demo#fragment",
    "catalyst://business-artifact/../ba_demo", "catalyst://business-artifact/missing' OR 1=1 --",
])
def test_unknown_or_alternate_uri_is_a_safe_protocol_error(server, saved_records, providers, uri, caplog):
    """Reject unsupported/missing literal URIs without aliases, data leaks or generation."""
    with pytest.raises(MCPError) as error:
        asyncio.run(_read(server, uri))
    assert error.value.code == -32602
    assert error.value.message == "Resource not found."
    assert error.value.data is None
    assert "private-uri-marker" not in str(error.value) + caplog.text
    assert "resources/read failed:" in caplog.text
    assert all(provider.calls == [] for provider in providers)


@pytest.mark.parametrize("cursor", ["", "private-cursor-marker"])
def test_supplied_cursor_is_rejected(server, saved_records, cursor, caplog):
    """A one-page listing never silently ignores an unsupported cursor."""
    with pytest.raises(MCPError) as error:
        asyncio.run(_listing(server, cursor=cursor))
    assert error.value.code == -32602
    assert error.value.message == "Resource listing does not accept a cursor."
    assert "private-cursor-marker" not in str(error.value) + caplog.text


@pytest.mark.parametrize("kind,corruption", [
    ("artifact", "json"), ("artifact", "id"),
    ("catalog", "json"), ("catalog", "id"), ("catalog", "source"),
])
@pytest.mark.parametrize("operation", ["read", "list"])
def test_corrupt_records_fail_without_repair(
    server, database_path, saved_records, kind, corruption, operation, providers, caplog
):
    """Return an internal protocol error without partial listings or changed records."""
    artifact, catalog = saved_records
    record = artifact if kind == "artifact" else catalog
    table = "business_artifacts" if kind == "artifact" else "use_case_catalogs"
    payload = record.model_dump(mode="json")
    if corruption == "id":
        payload["id"] = "different-id"
        if kind == "artifact":
            payload["uri"] = "catalyst://business-artifact/different-id"
    elif corruption == "source":
        payload["sourceArtifact"]["id"] = "ba_other"
    stored = "private-corrupt-marker" if corruption == "json" else json.dumps(payload)
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute(f"UPDATE {table} SET payload_json = ?", (stored,))
    uri = artifact.uri if kind == "artifact" else f"catalyst://use-case-catalog/{catalog.id}"
    with pytest.raises(MCPError) as error:
        asyncio.run(_read(server, uri) if operation == "read" else _listing(server))
    assert error.value.code == -32603
    expected_message = "Could not read saved resource." if operation == "read" else "Could not list saved resources."
    assert error.value.message == expected_message
    assert "private-corrupt-marker" not in str(error.value) + caplog.text
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute(f"SELECT payload_json FROM {table}").fetchone() == (stored,)
    assert all(provider.calls == [] for provider in providers)


@pytest.mark.parametrize("kind", ["artifact", "catalog"])
@pytest.mark.parametrize("operation", ["read", "list"])
def test_real_database_failure_is_a_protocol_error(server, database_path, saved_records, kind, operation):
    """Handle a missing SQLite table without leaking SQL or database-path details."""
    artifact, catalog = saved_records
    table = "business_artifacts" if kind == "artifact" else "use_case_catalogs"
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute(f"DROP TABLE {table}")
    before = database_path.read_bytes()
    uri = artifact.uri if kind == "artifact" else f"catalyst://use-case-catalog/{catalog.id}"
    with pytest.raises(MCPError) as error:
        asyncio.run(_read(server, uri) if operation == "read" else _listing(server))
    assert error.value.code == -32603
    assert "SELECT" not in error.value.message
    assert str(database_path) not in error.value.message
    assert database_path.read_bytes() == before


def test_repeated_reads_leave_raw_data_and_files_unchanged(
    server, database_path, saved_records, providers, tmp_path
):
    """Keep JSON, domain timestamps, database bytes and files unchanged on resource access."""
    artifact, catalog = saved_records
    before_bytes = database_path.read_bytes()
    before_files = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    with closing(sqlite3.connect(database_path)) as connection:
        original_artifacts = connection.execute("SELECT id, payload_json FROM business_artifacts").fetchall()
        original_catalogs = connection.execute("SELECT id, source_artifact_id, payload_json FROM use_case_catalogs").fetchall()
    for _ in range(3):
        listing = asyncio.run(_listing(server))
        for resource in listing.resources:
            asyncio.run(_read(server, resource.uri))
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT id, payload_json FROM business_artifacts").fetchall() == original_artifacts
        assert connection.execute("SELECT id, source_artifact_id, payload_json FROM use_case_catalogs").fetchall() == original_catalogs
    assert database_path.read_bytes() == before_bytes
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before_files
    assert all(provider.calls == [] for provider in providers)
    assert json.loads(original_artifacts[0][1]) == artifact.model_dump(mode="json")
    assert json.loads(original_catalogs[0][2]) == catalog.model_dump(mode="json")
