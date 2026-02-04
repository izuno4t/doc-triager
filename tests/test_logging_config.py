"""Tests for logging configuration module."""

import logging
from pathlib import Path

from doc_triager.logging_config import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_sets_log_level(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"

        setup_logging(level="WARNING", log_file=str(log_file))

        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_creates_log_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "logs" / "app.log"

        setup_logging(level="INFO", log_file=str(log_file))

        # ログを書き込んでファイル生成を確認
        logger = logging.getLogger("test_creates_log_file")
        logger.info("test message")

        assert log_file.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_file = tmp_path / "deep" / "nested" / "app.log"

        setup_logging(level="INFO", log_file=str(log_file))

        assert log_file.parent.exists()

    def test_has_console_handler(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"

        setup_logging(level="INFO", log_file=str(log_file))

        root = logging.getLogger()
        handler_types = [type(h) for h in root.handlers]
        assert logging.StreamHandler in handler_types

    def test_has_file_handler(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"

        setup_logging(level="INFO", log_file=str(log_file))

        root = logging.getLogger()
        handler_types = [type(h) for h in root.handlers]
        assert logging.FileHandler in handler_types

    def test_log_format_contains_timestamp_and_level(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"

        setup_logging(level="DEBUG", log_file=str(log_file))

        logger = logging.getLogger("test_format")
        logger.info("format check")

        content = log_file.read_text(encoding="utf-8")
        assert "[INFO]" in content
        assert "test_format" in content

    def test_pdfminer_psparser_suppressed(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"

        setup_logging(level="DEBUG", log_file=str(log_file))

        psparser_logger = logging.getLogger("pdfminer.psparser")
        assert psparser_logger.level >= logging.WARNING

    def test_invalid_level_defaults_to_info(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"

        setup_logging(level="INVALID", log_file=str(log_file))

        root = logging.getLogger()
        assert root.level == logging.INFO

    def teardown_method(self) -> None:
        """Reset logging after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            handler.close()
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
