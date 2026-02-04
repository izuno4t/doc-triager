"""Logging configuration module for doc-triager."""

from __future__ import annotations

import logging
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(*, level: str, log_file: str) -> None:
    """Configure logging with console and file handlers.

    Args:
        level: Log level string (DEBUG/INFO/WARNING/ERROR).
        log_file: Path to the log file.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), None)
    if not isinstance(log_level, int):
        log_level = logging.INFO

    root = logging.getLogger()
    root.setLevel(log_level)

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # サードパーティライブラリのノイズ抑制
    logging.getLogger("pdfminer.psparser").setLevel(logging.WARNING)
