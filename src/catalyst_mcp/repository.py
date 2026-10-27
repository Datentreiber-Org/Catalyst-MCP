"""SQLite persistence for complete Business Artifacts and Use-case Catalogs."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from catalyst_mcp.models import BusinessArtifact, UseCaseCatalog


class SQLiteRepository:
    """Store complete artifact and Catalog JSON in one persistent SQLite file."""

    def __init__(self, database_path: str | Path) -> None:
        """Create the parent directory and both record tables if needed."""
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS use_case_catalogs (
                    id TEXT PRIMARY KEY NOT NULL,
                    source_artifact_id TEXT NOT NULL REFERENCES business_artifacts(id),
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

    def save_use_case_catalog(self, catalog: UseCaseCatalog) -> UseCaseCatalog:
        """Validate and insert a complete Catalog linked to an existing artifact."""
        payload_json = catalog.model_dump_json()
        validated_catalog = UseCaseCatalog.model_validate_json(payload_json)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO use_case_catalogs (id, source_artifact_id, payload_json)
                VALUES (?, ?, ?)
                """,
                (validated_catalog.id, validated_catalog.sourceArtifact.id, payload_json),
            )
        return validated_catalog

    def get_use_case_catalog(self, catalog_id: str) -> UseCaseCatalog | None:
        """Read a complete Catalog, or return None when its ID is unknown."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, source_artifact_id, payload_json
                FROM use_case_catalogs WHERE id = ?
                """,
                (catalog_id,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_use_case_catalog(row)

    def list_use_case_catalogs(self) -> list[UseCaseCatalog]:
        """Read complete Catalogs in deterministic ID order."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_artifact_id, payload_json
                FROM use_case_catalogs ORDER BY id
                """
            ).fetchall()
        return [self._decode_use_case_catalog(row) for row in rows]

    @staticmethod
    def _decode_business_artifact(row: tuple[str, str]) -> BusinessArtifact:
        """Validate stored JSON and its association with the row identifier."""
        row_id, payload_json = row
        artifact = BusinessArtifact.model_validate_json(payload_json)
        if artifact.id != row_id:
            raise ValueError("Stored Business Artifact ID does not match its row ID")
        return artifact

    @staticmethod
    def _decode_use_case_catalog(row: tuple[str, str, str]) -> UseCaseCatalog:
        """Validate Catalog JSON and both identifiers stored alongside it."""
        row_id, source_artifact_id, payload_json = row
        catalog = UseCaseCatalog.model_validate_json(payload_json)
        if catalog.id != row_id:
            raise ValueError("Stored Catalog ID does not match its row ID")
        if catalog.sourceArtifact.id != source_artifact_id:
            raise ValueError("Stored Catalog source ID does not match its row association")
        return catalog
