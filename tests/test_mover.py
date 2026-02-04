"""Tests for mover module."""

from pathlib import Path

import pytest

from doc_triager.mover import move_file


class TestMoveFile:
    """Tests for move_file function."""

    @pytest.fixture()
    def dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        return source_dir, output_dir

    def test_moves_file_to_triage_dir(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs
        f = source_dir / "design.pdf"
        f.write_bytes(b"pdf content")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="evergreen"
        )

        assert dest == output_dir / "evergreen" / "design.pdf"
        assert dest.exists()
        assert not f.exists()

    def test_preserves_directory_hierarchy(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs
        sub = source_dir / "tech" / "java"
        sub.mkdir(parents=True)
        f = sub / "design.pdf"
        f.write_bytes(b"pdf content")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="evergreen"
        )

        assert dest == output_dir / "evergreen" / "tech" / "java" / "design.pdf"
        assert dest.exists()
        assert not f.exists()

    def test_temporal_triage(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs
        f = source_dir / "trends.pdf"
        f.write_bytes(b"trends")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="temporal"
        )

        assert dest == output_dir / "temporal" / "trends.pdf"
        assert dest.exists()

    def test_unknown_triage(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs
        f = source_dir / "unclear.pdf"
        f.write_bytes(b"unclear")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="unknown"
        )

        assert dest == output_dir / "unknown" / "unclear.pdf"
        assert dest.exists()

    def test_creates_parent_directories(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs
        sub = source_dir / "a" / "b" / "c"
        sub.mkdir(parents=True)
        f = sub / "deep.pdf"
        f.write_bytes(b"deep")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="evergreen"
        )

        assert dest == output_dir / "evergreen" / "a" / "b" / "c" / "deep.pdf"
        assert dest.exists()

    def test_duplicate_file_gets_suffix(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs

        # 出力先に同名ファイルを先に配置
        dest_dir = output_dir / "evergreen"
        dest_dir.mkdir(parents=True)
        existing = dest_dir / "design.pdf"
        existing.write_bytes(b"existing")

        f = source_dir / "design.pdf"
        f.write_bytes(b"new content")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="evergreen"
        )

        assert dest != existing
        assert dest.exists()
        assert existing.exists()
        assert "design_1.pdf" == dest.name
        assert not f.exists()

    def test_multiple_duplicates_increment_suffix(
        self, dirs: tuple[Path, Path]
    ) -> None:
        source_dir, output_dir = dirs

        dest_dir = output_dir / "evergreen"
        dest_dir.mkdir(parents=True)
        (dest_dir / "report.pdf").write_bytes(b"v0")
        (dest_dir / "report_1.pdf").write_bytes(b"v1")

        f = source_dir / "report.pdf"
        f.write_bytes(b"v2")

        dest = move_file(
            f, source_dir=source_dir, output_dir=output_dir, triage="evergreen"
        )

        assert dest.name == "report_2.pdf"
        assert dest.exists()

    def test_source_file_not_found_raises(self, dirs: tuple[Path, Path]) -> None:
        source_dir, output_dir = dirs
        f = source_dir / "missing.pdf"

        with pytest.raises(FileNotFoundError):
            move_file(
                f,
                source_dir=source_dir,
                output_dir=output_dir,
                triage="evergreen",
            )
