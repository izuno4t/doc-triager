"""Tests for database module."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def sample_record() -> dict:
    return {
        "source_path": "/src/docs/design.pdf",
        "destination_path": "/out/evergreen/docs/design.pdf",
        "checksum": "abc123def456",
        "file_size": 1024,
        "file_extension": ".pdf",
        "triage": "evergreen",
        "confidence": 0.85,
        "reason": "設計原則に関する文書",
        "topics": ["design", "architecture"],
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "extracted_text_length": 5000,
        "truncated": False,
        "error_message": None,
        "processed_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }


class TestInitDatabase:
    """Tests for database initialization."""

    def test_creates_table_and_indexes(self, db_path: Path) -> None:
        from doc_triager.database import init_database

        init_database(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "triage_results" in tables

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_checksum" in indexes
        assert "idx_triage" in indexes
        assert "idx_source_path" in indexes
        conn.close()

    def test_idempotent_init(self, db_path: Path) -> None:
        from doc_triager.database import init_database

        init_database(db_path)
        init_database(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='triage_results'"
        )
        assert cursor.fetchone()[0] == 1
        conn.close()


class TestInsertResult:
    """Tests for inserting triage results."""

    def test_insert_and_retrieve(self, db_path: Path, sample_record: dict) -> None:
        from doc_triager.database import (
            init_database,
            insert_result,
            get_by_source_path,
        )

        init_database(db_path)
        insert_result(db_path, sample_record)

        row = get_by_source_path(db_path, "/src/docs/design.pdf")

        assert row is not None
        assert row["source_path"] == "/src/docs/design.pdf"
        assert row["checksum"] == "abc123def456"
        assert row["triage"] == "evergreen"
        assert row["confidence"] == 0.85
        assert row["reason"] == "設計原則に関する文書"
        assert json.loads(row["topics"]) == ["design", "architecture"]
        assert row["llm_provider"] == "openai"
        assert row["llm_model"] == "gpt-4o"
        assert row["file_size"] == 1024
        assert row["file_extension"] == ".pdf"
        assert row["extracted_text_length"] == 5000
        assert row["truncated"] == 0
        assert row["error_message"] is None

    def test_insert_with_error(self, db_path: Path) -> None:
        from doc_triager.database import (
            init_database,
            insert_result,
            get_by_source_path,
        )

        init_database(db_path)
        record = {
            "source_path": "/src/broken.pdf",
            "destination_path": None,
            "checksum": "broken123",
            "file_size": 512,
            "file_extension": ".pdf",
            "triage": "unknown",
            "confidence": None,
            "reason": None,
            "topics": None,
            "llm_provider": None,
            "llm_model": None,
            "extracted_text_length": 0,
            "truncated": False,
            "error_message": "テキスト抽出失敗",
            "processed_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        }
        insert_result(db_path, record)

        row = get_by_source_path(db_path, "/src/broken.pdf")
        assert row is not None
        assert row["triage"] == "unknown"
        assert row["error_message"] == "テキスト抽出失敗"


class TestGetByChecksum:
    """Tests for checksum-based lookup."""

    def test_found(self, db_path: Path, sample_record: dict) -> None:
        from doc_triager.database import init_database, insert_result, get_by_checksum

        init_database(db_path)
        insert_result(db_path, sample_record)

        row = get_by_checksum(db_path, "abc123def456")
        assert row is not None
        assert row["source_path"] == "/src/docs/design.pdf"

    def test_not_found(self, db_path: Path) -> None:
        from doc_triager.database import init_database, get_by_checksum

        init_database(db_path)

        row = get_by_checksum(db_path, "nonexistent")
        assert row is None


class TestGetSummary:
    """Tests for triage summary."""

    def test_summary_counts(self, db_path: Path) -> None:
        from doc_triager.database import init_database, insert_result, get_summary

        init_database(db_path)

        base = {
            "destination_path": None,
            "file_size": 100,
            "file_extension": ".pdf",
            "confidence": 0.9,
            "reason": "test",
            "topics": None,
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "extracted_text_length": 500,
            "truncated": False,
            "error_message": None,
            "processed_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }

        for i, cls in enumerate(["evergreen", "evergreen", "temporal", "unknown"]):
            record = {
                **base,
                "source_path": f"/src/doc{i}.pdf",
                "checksum": f"hash{i}",
                "triage": cls,
            }
            insert_result(db_path, record)

        summary = get_summary(db_path)
        assert summary["evergreen"] == 2
        assert summary["temporal"] == 1
        assert summary["unknown"] == 1
        assert summary["total"] == 4

    def test_empty_summary(self, db_path: Path) -> None:
        from doc_triager.database import init_database, get_summary

        init_database(db_path)

        summary = get_summary(db_path)
        assert summary["evergreen"] == 0
        assert summary["temporal"] == 0
        assert summary["unknown"] == 0
        assert summary["total"] == 0


class TestListByTriage:
    """Tests for listing results by triage."""

    def test_list_filtered(self, db_path: Path) -> None:
        from doc_triager.database import (
            init_database,
            insert_result,
            list_by_triage,
        )

        init_database(db_path)

        base = {
            "destination_path": None,
            "file_size": 100,
            "file_extension": ".pdf",
            "confidence": 0.9,
            "reason": "test",
            "topics": None,
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "extracted_text_length": 500,
            "truncated": False,
            "error_message": None,
            "processed_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }

        for i, cls in enumerate(["evergreen", "temporal", "evergreen"]):
            record = {
                **base,
                "source_path": f"/src/doc{i}.pdf",
                "checksum": f"hash{i}",
                "triage": cls,
            }
            insert_result(db_path, record)

        rows = list_by_triage(db_path, "evergreen")
        assert len(rows) == 2

        rows = list_by_triage(db_path, "temporal")
        assert len(rows) == 1

        rows = list_by_triage(db_path, "unknown")
        assert len(rows) == 0


class TestExportAll:
    """Tests for exporting all results."""

    def test_export_returns_all_rows(self, db_path: Path, sample_record: dict) -> None:
        from doc_triager.database import init_database, insert_result, export_all

        init_database(db_path)
        insert_result(db_path, sample_record)

        rows = export_all(db_path)
        assert len(rows) == 1
        assert rows[0]["source_path"] == "/src/docs/design.pdf"
