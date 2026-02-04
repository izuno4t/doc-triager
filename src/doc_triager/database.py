"""Database module for doc-triager."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS triage_results (
    id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL,
    destination_path TEXT,
    checksum TEXT NOT NULL,
    file_size INTEGER,
    file_extension TEXT,
    triage TEXT NOT NULL,
    confidence REAL,
    reason TEXT,
    topics TEXT,
    llm_provider TEXT,
    llm_model TEXT,
    extracted_text_length INTEGER,
    truncated BOOLEAN,
    error_message TEXT,
    processed_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_checksum ON triage_results (checksum)",
    "CREATE INDEX IF NOT EXISTS idx_triage ON triage_results (triage)",
    "CREATE INDEX IF NOT EXISTS idx_source_path ON triage_results (source_path)",
]


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: Path) -> None:
    """Create the triage_results table and indexes."""
    conn = _connect(db_path)
    try:
        conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            conn.execute(idx_sql)
        conn.commit()
    finally:
        conn.close()


def insert_result(db_path: Path, record: dict[str, Any]) -> None:
    """Insert a triage result."""
    topics = record.get("topics")
    topics_json = json.dumps(topics) if topics is not None else None

    processed_at = record["processed_at"]
    if hasattr(processed_at, "isoformat"):
        processed_at = processed_at.isoformat()

    conn = _connect(db_path)
    try:
        conn.execute(
            """\
            INSERT INTO triage_results (
                source_path, destination_path, checksum, file_size, file_extension,
                triage, confidence, reason, topics,
                llm_provider, llm_model, extracted_text_length, truncated,
                error_message, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["source_path"],
                record.get("destination_path"),
                record["checksum"],
                record.get("file_size"),
                record.get("file_extension"),
                record["triage"],
                record.get("confidence"),
                record.get("reason"),
                topics_json,
                record.get("llm_provider"),
                record.get("llm_model"),
                record.get("extracted_text_length"),
                record.get("truncated"),
                record.get("error_message"),
                processed_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_by_source_path(db_path: Path, source_path: str) -> dict[str, Any] | None:
    """Look up a result by source path."""
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM triage_results WHERE source_path = ?",
            (source_path,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_by_checksum(db_path: Path, checksum: str) -> dict[str, Any] | None:
    """Look up a result by checksum."""
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM triage_results WHERE checksum = ?",
            (checksum,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_summary(db_path: Path) -> dict[str, int]:
    """Get counts by triage category."""
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT triage, COUNT(*) as cnt FROM triage_results GROUP BY triage"
        )
        counts = {row["triage"]: row["cnt"] for row in cursor.fetchall()}
        total = sum(counts.values())
        return {
            "evergreen": counts.get("evergreen", 0),
            "temporal": counts.get("temporal", 0),
            "unknown": counts.get("unknown", 0),
            "total": total,
        }
    finally:
        conn.close()


def list_by_triage(db_path: Path, triage: str) -> list[dict[str, Any]]:
    """List all results with a given triage category."""
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM triage_results WHERE triage = ? ORDER BY processed_at",
            (triage,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def export_all(db_path: Path) -> list[dict[str, Any]]:
    """Export all triage results."""
    conn = _connect(db_path)
    try:
        cursor = conn.execute("SELECT * FROM triage_results ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
