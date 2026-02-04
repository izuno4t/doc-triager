"""Tests for scanner module."""

import logging
from pathlib import Path

import pytest


@pytest.fixture()
def source_tree(tmp_path: Path) -> Path:
    """Create a source directory with various file types."""
    src = tmp_path / "source"
    src.mkdir()

    # Supported files
    (src / "design.pdf").write_bytes(b"pdf content")
    (src / "report.docx").write_bytes(b"docx content")
    (src / "slides.pptx").write_bytes(b"pptx content")
    (src / "data.xlsx").write_bytes(b"xlsx content")
    (src / "page.html").write_bytes(b"html content")
    (src / "notes.md").write_text("# Notes")
    (src / "readme.txt").write_text("readme")
    (src / "data.csv").write_text("a,b,c")
    (src / "config.json").write_text("{}")
    (src / "schema.xml").write_text("<root/>")
    (src / "photo.jpg").write_bytes(b"jpg")
    (src / "image.png").write_bytes(b"png")
    (src / "pic.jpeg").write_bytes(b"jpeg")
    (src / "archive.zip").write_bytes(b"zip")
    (src / "index.htm").write_bytes(b"htm")

    # Nested directory
    sub = src / "sub" / "deep"
    sub.mkdir(parents=True)
    (sub / "nested.pdf").write_bytes(b"nested pdf")

    # Files that should be excluded by default
    (src / ".DS_Store").write_bytes(b"ds")
    (src / ".gitkeep").write_bytes(b"gk")

    git_dir = src / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")

    macosx = src / "__MACOSX"
    macosx.mkdir()
    (macosx / "junk.pdf").write_bytes(b"junk")

    # Unsupported extension
    (src / "binary.exe").write_bytes(b"exe")
    (src / "movie.mp4").write_bytes(b"mp4")

    return src


class TestScanFiles:
    """Tests for scan_files function."""

    def test_finds_supported_files(self, source_tree: Path) -> None:
        from doc_triager.scanner import scan_files

        files = scan_files(source_tree)
        extensions = {f.suffix for f in files}

        assert ".pdf" in extensions
        assert ".docx" in extensions
        assert ".pptx" in extensions
        assert ".xlsx" in extensions
        assert ".html" in extensions
        assert ".htm" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions
        assert ".csv" in extensions
        assert ".json" in extensions
        assert ".xml" in extensions
        assert ".jpg" in extensions
        assert ".png" in extensions
        assert ".jpeg" in extensions
        assert ".zip" in extensions

    def test_finds_nested_files(self, source_tree: Path) -> None:
        from doc_triager.scanner import scan_files

        files = scan_files(source_tree)
        nested = [f for f in files if "nested.pdf" in f.name]

        assert len(nested) == 1

    def test_excludes_default_patterns(self, source_tree: Path) -> None:
        from doc_triager.scanner import scan_files

        files = scan_files(source_tree)
        names = {f.name for f in files}
        paths_str = [str(f) for f in files]

        assert ".DS_Store" not in names
        assert ".gitkeep" not in names
        assert not any(".git/" in p or ".git\\" in p for p in paths_str)
        assert not any("__MACOSX" in p for p in paths_str)

    def test_excludes_unsupported_extensions(self, source_tree: Path) -> None:
        from doc_triager.scanner import scan_files

        files = scan_files(source_tree)
        extensions = {f.suffix for f in files}

        assert ".exe" not in extensions
        assert ".mp4" not in extensions

    def test_custom_exclude_patterns(self, source_tree: Path) -> None:
        from doc_triager.scanner import scan_files

        files = scan_files(source_tree, exclude_patterns=["*.DS_Store", "*.pdf"])
        extensions = {f.suffix for f in files}

        assert ".pdf" not in extensions
        assert ".docx" in extensions

    def test_filter_by_extensions(self, source_tree: Path) -> None:
        from doc_triager.scanner import scan_files

        files = scan_files(source_tree, target_extensions=[".pdf", ".docx"])

        assert all(f.suffix in {".pdf", ".docx"} for f in files)
        assert len(files) >= 2

    def test_empty_directory(self, tmp_path: Path) -> None:
        from doc_triager.scanner import scan_files

        empty = tmp_path / "empty"
        empty.mkdir()

        files = scan_files(empty)

        assert files == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        from doc_triager.scanner import scan_files

        with pytest.raises(FileNotFoundError):
            scan_files(tmp_path / "nonexistent")

    def test_debug_logging_outputs_relative_paths(
        self, source_tree: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from doc_triager.scanner import scan_files

        with caplog.at_level(logging.DEBUG, logger="doc_triager.scanner"):
            files = scan_files(source_tree)

        assert len(files) > 0
        # ネストしたファイルは相対パスで出力される
        assert any("sub/deep/nested.pdf" in msg for msg in caplog.messages)
        # ルート直下のファイルも相対パスで出力される
        assert any("対象ファイル: design.pdf" in msg for msg in caplog.messages)

    def test_debug_logging_skipped_files_relative_paths(
        self, source_tree: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from doc_triager.scanner import scan_files

        with caplog.at_level(logging.DEBUG, logger="doc_triager.scanner"):
            scan_files(source_tree)

        # 除外・スキップも相対パスで出力される
        assert any("binary.exe" in msg for msg in caplog.messages)
        assert any("除外: .DS_Store" in msg for msg in caplog.messages)
