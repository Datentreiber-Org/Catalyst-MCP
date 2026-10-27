"""Catalog persistence and source associations in real temporary SQLite files."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from catalyst_mcp.models import BusinessArtifact, BusinessModel, UseCaseCatalog
from catalyst_mcp.repository import SQLiteRepository


@pytest.fixture
def database_path(tmp_path) -> Path:
    """Give each test its own persistent database file."""
    return tmp_path / "runtime data" / "catalyst.sqlite3"


@pytest.fixture
def repository(database_path) -> SQLiteRepository:
    """Create a repository without saving any domain records."""
    return SQLiteRepository(database_path)


@pytest.fixture
def artifact() -> BusinessArtifact:
    """Supply a synthetic source artifact without saving it automatically."""
    sections = {section: [] for section in BusinessModel.model_fields}
    sections["endUsers"] = ["Cyclists"]
    sections["activities"] = ["Repair bicycles"]
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return BusinessArtifact(
        id="ba_demo", name="Northstar Bikes",
        uri="catalyst://business-artifact/ba_demo",
        createdAt=timestamp, updatedAt=timestamp, businessModel=sections,
    )


@pytest.fixture
def catalog(artifact) -> UseCaseCatalog:
    """Supply a complete synthetic Catalog linked to the source fixture's ID."""
    return UseCaseCatalog(
        id="uc_catalog_demo",
        createdAt=artifact.createdAt,
        updatedAt=artifact.updatedAt,
        sourceArtifact={"id": artifact.id},
        useCases=[
            {
                "id": "uc_demo",
                "title": "Repair request triage",
                "focus": "Workshop efficiency",
                "problem": "Staff manually route repair requests.",
                "targetUsers": ["Workshop staff"],
                "proposedSolution": "Classify repair requests and suggest a work queue.",
                "businessElementAlignment": [
                    {
                        "section": "activities",
                        "element": "Repair bicycles",
                        "rationale": "Routes repair work to workshop staff.",
                    }
                ],
            }
        ],
    )


def test_adds_catalog_table_to_existing_artifact_database(database_path, artifact, catalog):
    """Open a step-4 database and add Catalog storage without replacing its source."""
    database_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute(
            """
            CREATE TABLE business_artifacts (
                id TEXT PRIMARY KEY NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO business_artifacts (id, payload_json) VALUES (?, ?)",
            (artifact.id, artifact.model_dump_json()),
        )
    repository = SQLiteRepository(database_path)
    assert repository.get_business_artifact(artifact.id) == artifact
    assert repository.list_use_case_catalogs() == []
    assert repository.save_use_case_catalog(catalog) == catalog
    assert repository.get_use_case_catalog(catalog.id) == catalog
    assert repository.get_business_artifact(artifact.id) == artifact


def test_save_get_and_list_preserve_complete_catalog(
    repository, database_path, artifact, catalog
):
    """Store every case and alignment in order, with the exact source association."""
    repository.save_business_artifact(artifact)
    case = catalog.useCases[0]
    case.title = "Northstar's Café <triage> & \"Workshop\""
    case.targetUsers = ["Workshop staff", "  Café riders\n*Weekend club*  "]
    case.businessElementAlignment.append(
        case.businessElementAlignment[0].model_copy(
            update={"section": "endUsers", "element": "Cyclists", "rationale": "Helps riders."}
        )
    )
    catalog.useCases.append(
        case.model_copy(deep=True, update={"id": "uc_second", "title": "Repair queue forecast"})
    )
    expected_json = catalog.model_dump_json()
    assert repository.save_use_case_catalog(catalog) == catalog
    assert repository.get_use_case_catalog(catalog.id) == catalog
    assert repository.list_use_case_catalogs() == [catalog]
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        row = connection.execute(
            "SELECT id, source_artifact_id, payload_json FROM use_case_catalogs"
        ).fetchone()
    assert row == (catalog.id, artifact.id, expected_json)
    assert "uri" not in json.loads(row[2])


def test_lists_catalogs_for_different_sources_in_id_order(repository, artifact, catalog):
    """Keep each source link intact while listing full Catalogs in ID order."""
    other_artifact = artifact.model_copy(
        update={"id": "ba_other", "uri": "catalyst://business-artifact/ba_other"}
    )
    repository.save_business_artifact(artifact)
    repository.save_business_artifact(other_artifact)
    first = catalog.model_copy(update={"id": "uc_catalog_a"})
    last = catalog.model_copy(
        update={
            "id": "uc_catalog_z",
            "sourceArtifact": catalog.sourceArtifact.model_copy(update={"id": other_artifact.id}),
        }
    )
    for record in (last, catalog, first):
        repository.save_use_case_catalog(record)
    assert repository.list_use_case_catalogs() == [first, catalog, last]


def test_catalog_and_source_persist_across_process_restart(
    repository, database_path, artifact, catalog, tmp_path
):
    """Retrieve both linked records from a new repository and Python process."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    reopened = SQLiteRepository(database_path)
    assert reopened.get_use_case_catalog(catalog.id) == catalog
    assert reopened.get_business_artifact(catalog.sourceArtifact.id) == artifact
    script = (
        "import json, sys\n"
        "from catalyst_mcp.repository import SQLiteRepository\n"
        "repository = SQLiteRepository(sys.argv[1])\n"
        "catalog = repository.get_use_case_catalog(sys.argv[2])\n"
        "artifact = repository.get_business_artifact(catalog.sourceArtifact.id)\n"
        "print(json.dumps({'catalog': catalog.model_dump(mode='json'), "
        "'artifact': artifact.model_dump(mode='json')}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(database_path), catalog.id],
        cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10,
    )
    assert json.loads(result.stdout) == {
        "catalog": catalog.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
    }


def test_catalog_reads_leave_both_records_unchanged(
    repository, database_path, artifact, catalog
):
    """Keep Catalog and source JSON and timestamps unchanged after repeated reads."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    original_catalog_json = catalog.model_dump_json()
    original_source_json = artifact.model_dump_json()
    catalog.useCases[0].title = "Unsaved title"
    loaded = repository.get_use_case_catalog(catalog.id)
    loaded.useCases[0].targetUsers.append("Unsaved target user")
    for _ in range(2):
        assert repository.get_use_case_catalog(catalog.id).model_dump_json() == original_catalog_json
        assert repository.list_use_case_catalogs()[0].model_dump_json() == original_catalog_json
        assert repository.get_business_artifact(artifact.id).model_dump_json() == original_source_json
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        stored_catalog = connection.execute(
            "SELECT payload_json FROM use_case_catalogs WHERE id = ?", (catalog.id,)
        ).fetchone()[0]
        stored_source = connection.execute(
            "SELECT payload_json FROM business_artifacts WHERE id = ?", (artifact.id,)
        ).fetchone()[0]
    assert stored_catalog == original_catalog_json
    assert stored_source == original_source_json


def test_unknown_source_is_rejected_without_changing_records(repository, artifact, catalog):
    """Reject a missing source through the foreign key and preserve existing data."""
    repository.save_business_artifact(artifact)
    invalid_catalog = catalog.model_copy(
        update={"sourceArtifact": catalog.sourceArtifact.model_copy(update={"id": "unknown"})}
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repository.save_use_case_catalog(invalid_catalog)
    assert repository.list_use_case_catalogs() == []
    assert repository.list_business_artifacts() == [artifact]


def test_duplicate_catalog_id_preserves_original_source_and_payload(
    repository, artifact, catalog
):
    """Fail a duplicate insert without replacing its JSON or source association."""
    other_artifact = artifact.model_copy(
        update={"id": "ba_other", "uri": "catalyst://business-artifact/ba_other"}
    )
    repository.save_business_artifact(artifact)
    repository.save_business_artifact(other_artifact)
    repository.save_use_case_catalog(catalog)
    replacement = catalog.model_copy(
        update={"sourceArtifact": catalog.sourceArtifact.model_copy(update={"id": other_artifact.id})}
    )
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_use_case_catalog(replacement)
    assert repository.get_use_case_catalog(catalog.id) == catalog
    assert repository.list_business_artifacts() == [artifact, other_artifact]


@pytest.mark.parametrize("corruption", ["timestamp", "source", "case_ids", "alignment"])
def test_invalid_mutated_catalogs_are_not_saved(repository, artifact, catalog, corruption):
    """Revalidate nested content and metadata before writing an existing model."""
    repository.save_business_artifact(artifact)
    if corruption == "timestamp":
        catalog.updatedAt += timedelta(days=1)
    elif corruption == "source":
        catalog.sourceArtifact.id = " \n"
    elif corruption == "case_ids":
        catalog.useCases.append(catalog.useCases[0].model_copy(deep=True))
    else:
        catalog.useCases[0].businessElementAlignment[0].rationale = " \n"
    with pytest.raises(ValidationError):
        repository.save_use_case_catalog(catalog)
    assert repository.list_use_case_catalogs() == []
    assert repository.get_business_artifact(artifact.id) == artifact


def test_catalog_commit_failure_rolls_back_complete_record(
    repository, database_path, artifact, catalog
):
    """Force commit failure and preserve the saved source and earlier Catalog."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.executescript(
            """
            CREATE TABLE catalog_commit_parents (id TEXT PRIMARY KEY);
            CREATE TABLE catalog_commit_children (
                parent_id TEXT REFERENCES catalog_commit_parents(id)
                DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER fail_catalog_commit
            AFTER INSERT ON use_case_catalogs
            WHEN NEW.id = 'uc_catalog_fail'
            BEGIN
                INSERT INTO catalog_commit_children (parent_id) VALUES ('missing');
            END;
            """
        )
    failing_catalog = catalog.model_copy(update={"id": "uc_catalog_fail"})
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repository.save_use_case_catalog(failing_catalog)
    reopened = SQLiteRepository(database_path)
    assert reopened.get_use_case_catalog(failing_catalog.id) is None
    assert reopened.list_use_case_catalogs() == [catalog]
    assert reopened.get_business_artifact(artifact.id) == artifact
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM catalog_commit_children").fetchone()[0]
    assert count == 0
    recovered_catalog = catalog.model_copy(update={"id": "uc_catalog_recovered"})
    assert reopened.save_use_case_catalog(recovered_catalog) == recovered_catalog


@pytest.mark.parametrize("reader", ["get", "list"])
@pytest.mark.parametrize("corruption", ["malformed_json", "invalid_shape", "catalog_id", "source_id"])
def test_rejects_invalid_stored_catalogs(
    repository, database_path, artifact, catalog, reader, corruption
):
    """Reject corrupted JSON or either mismatched ID without repairing stored data."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    expected_error = ValidationError
    error_pattern = None
    if corruption == "malformed_json":
        payload_json = "not JSON"
    elif corruption == "invalid_shape":
        payload_json = json.dumps({"id": catalog.id})
    else:
        if corruption == "catalog_id":
            altered = catalog.model_copy(update={"id": "uc_other"})
        else:
            other_artifact = artifact.model_copy(
                update={"id": "ba_other", "uri": "catalyst://business-artifact/ba_other"}
            )
            repository.save_business_artifact(other_artifact)
            altered = catalog.model_copy(
                update={"sourceArtifact": catalog.sourceArtifact.model_copy(update={"id": other_artifact.id})}
            )
        payload_json = altered.model_dump_json()
        expected_error = ValueError
        error_pattern = "Stored Catalog"
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute(
            "UPDATE use_case_catalogs SET payload_json = ? WHERE id = ?", (payload_json, catalog.id)
        )
    with pytest.raises(expected_error, match=error_pattern):
        if reader == "get":
            repository.get_use_case_catalog(catalog.id)
        else:
            repository.list_use_case_catalogs()
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        row = connection.execute(
            "SELECT id, source_artifact_id, payload_json FROM use_case_catalogs WHERE id = ?",
            (catalog.id,),
        ).fetchone()
    assert row == (catalog.id, artifact.id, payload_json)


@pytest.mark.parametrize("operation", ["delete", "change_id"])
def test_foreign_key_protects_linked_source(repository, database_path, artifact, catalog, operation):
    """Ensure SQLite itself prevents removal or renaming of a referenced source ID."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            if operation == "delete":
                connection.execute("DELETE FROM business_artifacts WHERE id = ?", (artifact.id,))
            else:
                connection.execute(
                    "UPDATE business_artifacts SET id = ? WHERE id = ?", ("ba_changed", artifact.id)
                )
    assert repository.get_business_artifact(artifact.id) == artifact
    assert repository.get_use_case_catalog(catalog.id) == catalog


def test_catalog_lookup_binds_id_as_data(repository, artifact, catalog):
    """Keep lookup text from changing the query or accessing another Catalog."""
    repository.save_business_artifact(artifact)
    repository.save_use_case_catalog(catalog)
    assert repository.get_use_case_catalog("missing' OR 1=1 --") is None
    assert repository.list_use_case_catalogs() == [catalog]
