"""File scanner module for doc-triager."""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SUPPORTED_EXTENSIONS: set[str] = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".md",
    ".txt",
    ".zip",
}

DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "*.DS_Store",
    "*.gitkeep",
    ".git/**",
    "__MACOSX/**",
]


def _is_excluded(file_path: Path, root: Path, exclude_patterns: list[str]) -> bool:
    """Check if a file matches any exclude pattern."""
    relative = file_path.relative_to(root)
    rel_str = str(relative)
    name = file_path.name

    for pattern in exclude_patterns:
        if "**" in pattern or "/" in pattern:
            if fnmatch.fnmatch(rel_str, pattern):
                return True
            if any(
                fnmatch.fnmatch(part, pattern.split("/")[0]) for part in relative.parts
            ):
                return True
        else:
            if fnmatch.fnmatch(name, pattern):
                return True
    return False


def scan_files(
    source_dir: Path,
    *,
    exclude_patterns: list[str] | None = None,
    target_extensions: list[str] | None = None,
) -> list[Path]:
    """Scan a directory recursively and return supported files.

    Args:
        source_dir: Directory to scan.
        exclude_patterns: Glob patterns to exclude. Defaults to DEFAULT_EXCLUDE_PATTERNS.
        target_extensions: If provided, only include these extensions.

    Returns:
        Sorted list of file paths.
    """
    if not source_dir.exists():
        msg = f"ソースディレクトリが見つかりません: {source_dir}"
        raise FileNotFoundError(msg)

    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS

    supported = (
        {ext.lower() for ext in target_extensions}
        if target_extensions
        else DEFAULT_SUPPORTED_EXTENSIONS
    )

    result: list[Path] = []

    for file_path in sorted(source_dir.rglob("*")):
        if not file_path.is_file():
            continue

        relative = file_path.relative_to(source_dir)

        if _is_excluded(file_path, source_dir, exclude_patterns):
            logger.debug("除外: %s", relative)
            continue

        if file_path.suffix.lower() not in supported:
            logger.debug("非対応拡張子をスキップ: %s", relative)
            continue

        logger.debug("対象ファイル: %s", relative)
        result.append(file_path)

    logger.debug("スキャン完了: %d 件のファイルを検出 (%s)", len(result), source_dir)
    return result
