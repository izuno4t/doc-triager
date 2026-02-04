"""Tests for checksum module."""

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from doc_triager.checksum import compute_checksum, is_processed


class TestComputeChecksum:
    """Tests for compute_checksum function."""

    def test_returns_sha256_hex(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        content = b"hello world"
        f.write_bytes(content)

        result = compute_checksum(f)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected

    def test_different_content_different_checksum(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        assert compute_checksum(f1) != compute_checksum(f2)

    def test_same_content_same_checksum(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"identical")
        f2.write_bytes(b"identical")

        assert compute_checksum(f1) == compute_checksum(f2)

    def test_large_file(self, tmp_path: Path) -> None:
        f = tmp_path / "large.bin"
        # 1MB のデータ
        data = b"x" * (1024 * 1024)
        f.write_bytes(data)

        result = compute_checksum(f)
        expected = hashlib.sha256(data).hexdigest()

        assert result == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")

        result = compute_checksum(f)
        expected = hashlib.sha256(b"").hexdigest()

        assert result == expected

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compute_checksum(tmp_path / "no_such_file.txt")


class TestIsProcessed:
    """Tests for is_processed function."""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> Path:
        from doc_triager.database import init_database

        p = tmp_path / "test.db"
        init_database(p)
        return p

    def _insert_record(self, db_path: Path, *, source_path: str, checksum: str) -> None:
        from doc_triager.database import insert_result

        insert_result(
            db_path,
            {
                "source_path": source_path,
                "checksum": checksum,
                "triage": "evergreen",
                "confidence": 0.9,
                "processed_at": datetime.now(),
            },
        )

    def test_unprocessed_file(self, db_path: Path, tmp_path: Path) -> None:
        f = tmp_path / "new.txt"
        f.write_bytes(b"new content")

        result = is_processed(db_path, f)

        assert result is False

    def test_processed_same_checksum(self, db_path: Path, tmp_path: Path) -> None:
        f = tmp_path / "done.txt"
        content = b"already done"
        f.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        self._insert_record(db_path, source_path=str(f), checksum=checksum)

        result = is_processed(db_path, f)

        assert result is True

    def test_changed_file_returns_false(self, db_path: Path, tmp_path: Path) -> None:
        """ファイルが変更された場合（チェックサム不一致）は未処理扱い。"""
        f = tmp_path / "changed.txt"
        f.write_bytes(b"original")
        old_checksum = hashlib.sha256(b"original").hexdigest()
        self._insert_record(db_path, source_path=str(f), checksum=old_checksum)

        # ファイル内容を変更
        f.write_bytes(b"modified")

        result = is_processed(db_path, f)

        assert result is False
