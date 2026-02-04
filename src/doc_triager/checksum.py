"""Checksum calculation and deduplication module for doc-triager."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from doc_triager.database import get_by_source_path

logger = logging.getLogger(__name__)

_BUF_SIZE = 65536  # 64KB


def compute_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex-encoded SHA-256 digest.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        msg = f"ファイルが見つかりません: {file_path}"
        raise FileNotFoundError(msg)

    sha256 = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            data = f.read(_BUF_SIZE)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()


def is_processed(db_path: Path, file_path: Path) -> bool:
    """Check if a file has already been processed with the same checksum.

    Args:
        db_path: Path to the SQLite database.
        file_path: Path to the file to check.

    Returns:
        True if the file exists in DB with the same checksum, False otherwise.
    """
    record = get_by_source_path(db_path, str(file_path))
    if record is None:
        return False

    current_checksum = compute_checksum(file_path)
    return record["checksum"] == current_checksum
