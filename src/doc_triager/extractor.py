"""Text extraction module for doc-triager using MarkItDown."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from markitdown import MarkItDown

logger = logging.getLogger(__name__)

_DEFAULT_MIN_TEXT_LENGTH = 100
_TRUNCATE_MARKER = "\n\n[...truncated...]\n\n"


@dataclass
class ExtractionResult:
    """Result of text extraction from a file."""

    text: str | None
    insufficient: bool = False
    error: str | None = None


@dataclass
class TruncateResult:
    """Result of text truncation."""

    text: str
    truncated: bool


def extract_text(
    file_path: Path,
    *,
    min_text_length: int = _DEFAULT_MIN_TEXT_LENGTH,
    source_dir: Path | None = None,
    debug_dir: Path | None = None,
) -> ExtractionResult:
    """Extract text from a file using MarkItDown.

    Args:
        file_path: Path to the file.
        min_text_length: Minimum text length to consider extraction sufficient.
        source_dir: Source root directory (used for relative path in debug output).
        debug_dir: If specified, write extracted text as .md files to this directory.

    Returns:
        ExtractionResult with extracted text or error information.
    """
    try:
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.markdown
    except Exception as e:
        logger.warning("テキスト抽出失敗: %s - %s", file_path.name, e)
        return ExtractionResult(text=None, error=str(e))

    if debug_dir is not None and text:
        _write_debug_file(file_path, text, source_dir=source_dir, debug_dir=debug_dir)

    if not text or len(text.strip()) < min_text_length:
        logger.debug(
            "テキスト不足: %s (%d文字)",
            file_path.name,
            len(text.strip()) if text else 0,
        )
        return ExtractionResult(text=text, insufficient=True)

    logger.debug("テキスト抽出成功: %s (%d文字)", file_path.name, len(text))
    return ExtractionResult(text=text)


def _write_debug_file(
    file_path: Path,
    text: str,
    *,
    source_dir: Path | None,
    debug_dir: Path,
) -> None:
    """Write extracted text to a debug directory."""
    if source_dir is not None:
        relative = file_path.relative_to(source_dir)
    else:
        relative = Path(file_path.name)

    output_path = debug_dir / f"{relative}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    logger.debug("デバッグ出力: %s", output_path)


def truncate_text(text: str, *, max_length: int) -> TruncateResult:
    """Truncate text preserving head and tail portions.

    When text exceeds max_length, keeps the beginning and end of the text
    with a truncation marker in the middle.

    Args:
        text: Original text.
        max_length: Maximum allowed length.

    Returns:
        TruncateResult with possibly truncated text and truncation flag.
    """
    if len(text) <= max_length:
        return TruncateResult(text=text, truncated=False)

    marker_len = len(_TRUNCATE_MARKER)
    available = max_length - marker_len
    head_len = available * 2 // 3
    tail_len = available - head_len

    truncated = text[:head_len] + _TRUNCATE_MARKER + text[-tail_len:]
    return TruncateResult(text=truncated, truncated=True)
