"""Tests for extractor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from doc_triager.extractor import extract_text, truncate_text


class TestExtractText:
    """Tests for extract_text function."""

    def test_extracts_text_from_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Hello\n\nThis is a test document with enough content.")

        result = extract_text(f)

        assert result.text is not None
        assert len(result.text) > 0
        assert result.error is None

    def test_returns_error_on_conversion_failure(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.xyz"
        f.write_bytes(b"\x00\x01\x02")

        with patch("doc_triager.extractor.MarkItDown") as mock_cls:
            mock_md = MagicMock()
            mock_md.convert.side_effect = Exception("Unsupported format")
            mock_cls.return_value = mock_md

            result = extract_text(f)

        assert result.text is None
        assert result.error is not None
        assert "Unsupported format" in result.error

    def test_insufficient_text(self, tmp_path: Path) -> None:
        f = tmp_path / "short.md"
        f.write_text("Hi")

        result = extract_text(f, min_text_length=100)

        assert result.insufficient is True

    def test_sufficient_text(self, tmp_path: Path) -> None:
        f = tmp_path / "long.md"
        f.write_text("A" * 200)

        result = extract_text(f, min_text_length=100)

        assert result.insufficient is False

    def test_default_min_text_length(self, tmp_path: Path) -> None:
        f = tmp_path / "short.md"
        f.write_text("x" * 50)

        result = extract_text(f)

        # デフォルト100文字未満なのでinsufficient
        assert result.insufficient is True

    def test_debug_dir_outputs_file(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        f = source_dir / "test.pdf"
        f.write_text("# Hello\n\nThis is a test document with enough content.")
        debug_dir = tmp_path / "debug_output"

        extract_text(f, source_dir=source_dir, debug_dir=debug_dir)

        output_file = debug_dir / "test.pdf.md"
        assert output_file.exists()
        assert len(output_file.read_text(encoding="utf-8")) > 0

    def test_debug_dir_preserves_hierarchy(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        sub = source_dir / "tech" / "java"
        sub.mkdir(parents=True)
        f = sub / "design.md"
        f.write_text(
            "# Design Patterns\n\nThis is about design patterns and architecture."
        )
        debug_dir = tmp_path / "debug_output"

        extract_text(f, source_dir=source_dir, debug_dir=debug_dir)

        output_file = debug_dir / "tech" / "java" / "design.md.md"
        assert output_file.exists()

    def test_no_debug_dir_skips_output(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Hello\n\nThis is a test document with enough content.")
        debug_dir = tmp_path / "debug_output"

        extract_text(f)

        assert not debug_dir.exists()


class TestTruncateText:
    """Tests for truncate_text function."""

    def test_short_text_not_truncated(self) -> None:
        text = "short text"

        result = truncate_text(text, max_length=1000)

        assert result.text == text
        assert result.truncated is False

    def test_long_text_truncated(self) -> None:
        head = "HEAD " * 100  # 500 chars
        middle = "MIDDLE " * 200  # 1400 chars
        tail = "TAIL " * 100  # 500 chars
        text = head + middle + tail

        result = truncate_text(text, max_length=1200)

        assert result.truncated is True
        assert len(result.text) <= 1200
        # 先頭と末尾が含まれる
        assert result.text.startswith("HEAD")
        assert result.text.endswith("TAIL ")

    def test_truncated_text_contains_marker(self) -> None:
        text = "A" * 2000

        result = truncate_text(text, max_length=500)

        assert result.truncated is True
        assert "\n\n[...truncated...]\n\n" in result.text

    def test_exact_length_not_truncated(self) -> None:
        text = "A" * 500

        result = truncate_text(text, max_length=500)

        assert result.truncated is False
        assert result.text == text
