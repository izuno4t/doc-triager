"""File move module for doc-triager."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_destination(dest: Path) -> Path:
    """If dest already exists, add a numeric suffix to avoid overwriting."""
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_file(
    file_path: Path,
    *,
    source_dir: Path,
    output_dir: Path,
    triage: str,
) -> Path:
    """Move a file to the triage directory, preserving hierarchy.

    Args:
        file_path: Path to the source file.
        source_dir: Root source directory.
        output_dir: Root output directory.
        triage: Triage label (evergreen/temporal/unknown).

    Returns:
        Path to the destination file.

    Raises:
        FileNotFoundError: If the source file does not exist.
    """
    if not file_path.exists():
        msg = f"ファイルが見つかりません: {file_path}"
        raise FileNotFoundError(msg)

    relative = file_path.relative_to(source_dir)
    dest = output_dir / triage / relative
    dest = _resolve_destination(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(dest))

    logger.info("移動: %s → %s", relative, dest.relative_to(output_dir))
    return dest
