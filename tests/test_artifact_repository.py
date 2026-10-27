"""Business Artifact persistence checks against real temporary SQLite files."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from catalyst_mcp.models import BusinessArtifact, BusinessModel
from catalyst_mcp.repository import SQLiteRepository


@pytest.fixture
def database_path(tmp_path) -> Path:
    """Keep each test's database in its own temporary directory."""
    return tmp_path / "runtime data" / "catalyst.sqlite3"


@pytest.fixture
def repository(database_path) -> SQLiteRepository:
    """Create a repository backed by the test's persistent file."""
    return SQLiteRepository(database_path)


@pytest.fixture
def artifact() -> BusinessArtifact:
    """Supply a complete synthetic artifact with fixed backend metadata."""
    sections = {section: [] for section in BusinessModel.model_fields}
    sections["endUsers"] = ["Cyclists"]
    sections["activities"] = ["Repair bicycles"]
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return BusinessArtifact(
        id="ba_demo",
        name="Northstar Bikes",
        uri="catalyst://business-artifact/ba_demo",
        createdAt=timestamp,
        updatedAt=timestamp,
        businessModel=BusinessModel.model_validate(sections),
    )


def test_creates_database_tables(repository, database_path):
    """Create missing directories and both tables without writing domain records."""
    assert database_path.is_file()
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    assert tables == [("business_artifacts",), ("use_case_catalogs",)]
    assert repository.list_business_artifacts() == []
    assert repository.get_business_artifact("unknown") is None
    assert repository.list_use_case_catalogs() == []
    assert repository.get_use_case_catalog("unknown") is None


@pytest.mark.parametrize("path", ["", ":memory:", Path(":memory:")])
def test_rejects_nonpersistent_paths(path):
    """Reject SQLite's empty-name and in-memory database options."""
    with pytest.raises(ValueError, match="persistent SQLite file"):
        SQLiteRepository(path)


def test_save_and_get_preserve_complete_json(repository, database_path, artifact):
    """Commit every field and preserve special characters and array order."""
    artifact.name = "Northstar's Café <Workshop> & \"Partners\""
    artifact.businessModel.endUsers = ["Cyclists", "  Café riders\n*Weekend club*  "]
    expected_json = artifact.model_dump_json()

    saved = repository.save_business_artifact(artifact)
    loaded = repository.get_business_artifact(artifact.id)
    assert saved == loaded == artifact
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        row = connection.execute(
            "SELECT id, payload_json FROM business_artifacts"
        ).fetchone()
    assert row == (artifact.id, expected_json)


def test_lists_complete_artifacts_in_id_order(repository, artifact):
    """List full records deterministically rather than relying on insertion order."""
    last = artifact.model_copy(
        update={"id": "ba_z", "uri": "catalyst://business-artifact/ba_z", "name": "Last"}
    )
    first = artifact.model_copy(
        update={"id": "ba_a", "uri": "catalyst://business-artifact/ba_a", "name": "First"}
    )
    for record in (last, artifact, first):
        repository.save_business_artifact(record)
    assert repository.list_business_artifacts() == [first, artifact, last]


def test_persists_across_repository_and_process_restart(
    repository, database_path, artifact, tmp_path
):
    """Read committed JSON through a new repository and a separate Python process."""
    repository.save_business_artifact(artifact)
    reopened = SQLiteRepository(database_path)
    assert reopened.get_business_artifact(artifact.id) == artifact
    assert reopened.list_business_artifacts() == [artifact]

    script = (
        "import sys\n"
        "from catalyst_mcp.repository import SQLiteRepository\n"
        "repository = SQLiteRepository(sys.argv[1])\n"
        "artifact = repository.get_business_artifact(sys.argv[2])\n"
        "print(artifact.model_dump_json())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(database_path), artifact.id],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert json.loads(result.stdout) == artifact.model_dump(mode="json")


def test_reads_and_unsaved_mutations_do_not_change_storage(
    repository, database_path, artifact
):
    """Preserve stored JSON and timestamps despite reads or local object changes."""
    repository.save_business_artifact(artifact)
    original_json = artifact.model_dump_json()
    artifact.name = "Unsaved local change"
    loaded = repository.get_business_artifact(artifact.id)
    loaded.businessModel.activities.append("Unsaved activity")

    for _ in range(2):
        assert repository.get_business_artifact(artifact.id).model_dump_json() == original_json
        assert repository.list_business_artifacts()[0].model_dump_json() == original_json
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        stored_json = connection.execute(
            "SELECT payload_json FROM business_artifacts WHERE id = ?", (artifact.id,)
        ).fetchone()[0]
    assert stored_json == original_json


def test_duplicate_id_does_not_replace_saved_record(repository, artifact):
    """Fail a duplicate insert and leave the original artifact intact."""
    repository.save_business_artifact(artifact)
    replacement = artifact.model_copy(update={"name": "Replacement must not be saved"})
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_business_artifact(replacement)
    assert repository.get_business_artifact(artifact.id) == artifact
    assert repository.list_business_artifacts() == [artifact]


@pytest.mark.parametrize("corruption", ["name", "uri", "statement"])
def test_revalidates_mutated_artifacts_before_saving(repository, artifact, corruption):
    """Reject invalid changes even when the caller passes an existing model object."""
    if corruption == "name":
        artifact.name = " \n"
    elif corruption == "uri":
        artifact.uri = "catalyst://business-artifact/wrong_id"
    else:
        artifact.businessModel.activities.append(" \t")
    with pytest.raises(ValidationError):
        repository.save_business_artifact(artifact)
    assert repository.list_business_artifacts() == []


def test_commit_failure_rolls_back_complete_record(repository, database_path, artifact):
    """Force a deferred constraint failure at commit and verify a full rollback."""
    repository.save_business_artifact(artifact)
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
            WHEN NEW.id = 'ba_fail'
            BEGIN
                INSERT INTO commit_children (parent_id) VALUES ('missing');
            END;
            """
        )
    failing_artifact = artifact.model_copy(
        update={"id": "ba_fail", "uri": "catalyst://business-artifact/ba_fail"}
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repository.save_business_artifact(failing_artifact)

    reopened = SQLiteRepository(database_path)
    assert reopened.get_business_artifact("ba_fail") is None
    assert reopened.list_business_artifacts() == [artifact]
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM commit_children").fetchone() == (0,)
    recovered_artifact = artifact.model_copy(
        update={"id": "ba_recovered", "uri": "catalyst://business-artifact/ba_recovered"}
    )
    assert reopened.save_business_artifact(recovered_artifact) == recovered_artifact


@pytest.mark.parametrize("reader", ["get", "list"])
@pytest.mark.parametrize("corruption", ["malformed_json", "invalid_shape", "mismatched_id"])
def test_rejects_corrupt_or_misassociated_records(
    repository, database_path, artifact, reader, corruption
):
    """Reject invalid stored data without repairing it or changing its association."""
    repository.save_business_artifact(artifact)
    expected_error = ValidationError
    if corruption == "malformed_json":
        payload_json = "not JSON"
    elif corruption == "invalid_shape":
        payload_json = json.dumps({"id": artifact.id})
    else:
        other = artifact.model_copy(
            update={"id": "ba_other", "uri": "catalyst://business-artifact/ba_other"}
        )
        payload_json = other.model_dump_json()
        expected_error = ValueError
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        connection.execute(
            "UPDATE business_artifacts SET payload_json = ? WHERE id = ?",
            (payload_json, artifact.id),
        )
    with pytest.raises(expected_error):
        if reader == "get":
            repository.get_business_artifact(artifact.id)
        else:
            repository.list_business_artifacts()
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        stored_json = connection.execute(
            "SELECT payload_json FROM business_artifacts WHERE id = ?", (artifact.id,)
        ).fetchone()[0]
    assert stored_json == payload_json


def test_lookup_treats_id_as_data(repository, artifact):
    """Bind lookup IDs as values rather than allowing them to change the SQL query."""
    repository.save_business_artifact(artifact)
    assert repository.get_business_artifact("missing' OR 1=1 --") is None
    assert repository.list_business_artifacts() == [artifact]


def test_relative_database_path_stays_bound_to_original_location(
    tmp_path, artifact, monkeypatch
):
    """Keep the same database file when the process later changes directories."""
    monkeypatch.chdir(tmp_path)
    repository = SQLiteRepository("catalyst.sqlite3")
    other_directory = tmp_path / "elsewhere"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)
    repository.save_business_artifact(artifact)
    assert SQLiteRepository(tmp_path / "catalyst.sqlite3").get_business_artifact(artifact.id) == artifact
    assert not (other_directory / "catalyst.sqlite3").exists()
