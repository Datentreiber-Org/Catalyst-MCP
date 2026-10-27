"""SQLite persistence for complete Business Artifact records."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from catalyst_mcp.models import BusinessArtifact


class SQLiteRepository:
    """Store complete artifact JSON in one persistent SQLite file."""

    def __init__(self, database_path: str | Path) -> None:
        """Create the parent directory and Business Artifact table if needed."""
        if str(database_path) in ("", ":memory:"):
            raise ValueError("database_path must name a persistent SQLite file")
        self._database_path = Path(database_path).resolve()
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS business_artifacts (
                    id TEXT PRIMARY KEY NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Enable constraints, manage one transaction, and always close."""
        connection = sqlite3.connect(self._database_path, autocommit=True)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.autocommit = False
            with connection:
                yield connection
        finally:
            connection.close()

    def save_business_artifact(self, artifact: BusinessArtifact) -> BusinessArtifact:
        """Validate and insert a complete artifact, returning after commit."""
        payload_json = artifact.model_dump_json()
        validated_artifact = BusinessArtifact.model_validate_json(payload_json)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO business_artifacts (id, payload_json) VALUES (?, ?)",
                (validated_artifact.id, payload_json),
            )
        return validated_artifact

    def get_business_artifact(self, artifact_id: str) -> BusinessArtifact | None:
        """Read a complete artifact, or return None when its ID is unknown."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, payload_json FROM business_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_business_artifact(row)

    def list_business_artifacts(self) -> list[BusinessArtifact]:
        """Read complete artifacts in deterministic ID order."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, payload_json FROM business_artifacts ORDER BY id"
            ).fetchall()
        return [self._decode_business_artifact(row) for row in rows]

    @staticmethod
    def _decode_business_artifact(row: tuple[str, str]) -> BusinessArtifact:
        """Validate stored JSON and its association with the row identifier."""
        row_id, payload_json = row
        artifact = BusinessArtifact.model_validate_json(payload_json)
        if artifact.id != row_id:
            raise ValueError("Stored Business Artifact ID does not match its row ID")
        return artifact
