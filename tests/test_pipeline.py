"""Tests for pipeline module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_triager.config import (
    TriageConfig,
    Config,
    DatabaseConfig,
    InputConfig,
    LlmConfig,
    OutputConfig,
    TextExtractionConfig,
)
from doc_triager.database import get_by_source_path, init_database
from doc_triager.pipeline import _is_file_direct_mode, process_file, process_files


@pytest.fixture()
def workspace(tmp_path: Path) -> dict:
    """Create source/output dirs, DB, and a test file."""
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()

    db_path = tmp_path / "test.db"
    init_database(db_path)

    f = source_dir / "design.pdf"
    f.write_text(
        "# Design Patterns\n\n" + "This is about software design patterns. " * 20
    )

    cfg = Config(
        input=InputConfig(directory=str(source_dir)),
        output=OutputConfig(directory=str(output_dir)),
        triage=TriageConfig(confidence_threshold=0.7),
        llm=LlmConfig(provider="openai", model="gpt-4o"),
        database=DatabaseConfig(path=str(db_path)),
        text_extraction=TextExtractionConfig(min_text_length=10),
    )

    return {
        "source_dir": source_dir,
        "output_dir": output_dir,
        "db_path": db_path,
        "file": f,
        "cfg": cfg,
    }


def _mock_summary_response(summary: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = summary
    return resp


def _mock_llm_response(triage: str, confidence: float) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(
        {
            "classification": triage,
            "confidence": confidence,
            "reason": "Test reason",
            "topics": ["test"],
        }
    )
    return resp


class TestProcessFile:
    """Tests for process_file function."""

    @patch("doc_triager.llm.litellm.completion")
    def test_full_pipeline_evergreen(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        mock_completion.return_value = _mock_llm_response("evergreen", 0.9)

        result = process_file(
            file_path=workspace["file"],
            cfg=workspace["cfg"],
            dry_run=False,
        )

        assert result["triage"] == "evergreen"
        assert result["confidence"] == 0.9
        assert result["skipped"] is False

        # ファイルが移動されている
        assert not workspace["file"].exists()
        dest = Path(result["destination_path"])
        assert dest.exists()
        assert "evergreen" in str(dest)

        # DBに記録されている
        record = get_by_source_path(workspace["db_path"], str(workspace["file"]))
        assert record is not None
        assert record["triage"] == "evergreen"

    @patch("doc_triager.llm.litellm.completion")
    def test_dry_run_does_not_move(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        mock_completion.return_value = _mock_llm_response("temporal", 0.85)

        result = process_file(
            file_path=workspace["file"],
            cfg=workspace["cfg"],
            dry_run=True,
        )

        assert result["triage"] == "temporal"
        # ファイルは移動されていない
        assert workspace["file"].exists()
        assert result["destination_path"] is None

        # DBには記録される
        record = get_by_source_path(workspace["db_path"], str(workspace["file"]))
        assert record is not None

    @patch("doc_triager.llm.litellm.completion")
    def test_low_confidence_becomes_unknown(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        mock_completion.return_value = _mock_llm_response("evergreen", 0.3)

        result = process_file(
            file_path=workspace["file"],
            cfg=workspace["cfg"],
            dry_run=False,
        )

        assert result["triage"] == "unknown"

    @patch("doc_triager.llm.litellm.completion")
    def test_skips_already_processed_file(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        mock_completion.return_value = _mock_llm_response("evergreen", 0.9)

        # 1回目
        process_file(file_path=workspace["file"], cfg=workspace["cfg"], dry_run=True)

        # 2回目（同じファイル、同じチェックサム）
        result = process_file(
            file_path=workspace["file"], cfg=workspace["cfg"], dry_run=True
        )

        assert result["skipped"] is True
        # LLMは1回目しか呼ばれない
        assert mock_completion.call_count == 1

    def test_extraction_error_records_unknown(self, workspace: dict) -> None:
        with patch("doc_triager.pipeline.extract_text") as mock_extract:
            from doc_triager.extractor import ExtractionResult

            mock_extract.return_value = ExtractionResult(
                text=None, error="Unsupported format"
            )

            result = process_file(
                file_path=workspace["file"], cfg=workspace["cfg"], dry_run=True
            )

        assert result["triage"] == "unknown"
        assert result["error"] is not None

        record = get_by_source_path(workspace["db_path"], str(workspace["file"]))
        assert record is not None
        assert record["error_message"] is not None

    def test_insufficient_text_records_unknown(self, workspace: dict) -> None:
        # min_text_lengthを大きく設定
        workspace["cfg"].text_extraction.min_text_length = 100000

        with patch("doc_triager.llm.litellm.completion") as mock_completion:
            result = process_file(
                file_path=workspace["file"], cfg=workspace["cfg"], dry_run=True
            )

        assert result["triage"] == "unknown"
        # LLMは呼ばれない
        mock_completion.assert_not_called()


class TestProcessFiles:
    """Tests for process_files function."""

    @patch("doc_triager.llm.litellm.completion")
    def test_returns_summary(self, mock_completion: MagicMock, workspace: dict) -> None:
        # 複数ファイルを作成
        source_dir = workspace["source_dir"]
        (source_dir / "a.pdf").write_text("Content A " * 20)
        (source_dir / "b.pdf").write_text("Content B " * 20)
        files = sorted(source_dir.glob("*.pdf"))

        mock_completion.return_value = _mock_llm_response("evergreen", 0.9)

        summary = process_files(
            files=files,
            cfg=workspace["cfg"],
            dry_run=True,
        )

        assert summary["total"] == len(files)
        assert summary["skipped"] >= 0
        assert (
            summary["evergreen"]
            + summary["temporal"]
            + summary["unknown"]
            + summary["error"]
            + summary["skipped"]
            == summary["total"]
        )


class TestSummaryIntegration:
    """Tests for LLM summary step in pipeline."""

    @patch("doc_triager.llm.litellm.completion")
    def test_summary_enabled_calls_twice(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        """When summary enabled, LLM is called twice (summary + classify)."""
        workspace["cfg"].text_extraction.llm_summary_enabled = True

        # 1st call: summary response, 2nd call: classification response
        mock_completion.side_effect = [
            _mock_summary_response("Summarized content about design"),
            _mock_llm_response("evergreen", 0.9),
        ]

        result = process_file(
            file_path=workspace["file"],
            cfg=workspace["cfg"],
            dry_run=True,
        )

        assert result["triage"] == "evergreen"
        assert mock_completion.call_count == 2

    @patch("doc_triager.llm.litellm.completion")
    def test_summary_disabled_calls_once(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        """When summary disabled (default), LLM is called once."""
        workspace["cfg"].text_extraction.llm_summary_enabled = False

        mock_completion.return_value = _mock_llm_response("evergreen", 0.9)

        result = process_file(
            file_path=workspace["file"],
            cfg=workspace["cfg"],
            dry_run=True,
        )

        assert result["triage"] == "evergreen"
        assert mock_completion.call_count == 1

    @patch("doc_triager.llm.litellm.completion")
    def test_summary_failure_falls_back(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        """When summary fails, classification still proceeds with original text."""
        workspace["cfg"].text_extraction.llm_summary_enabled = True

        # 1st call: summary fails, 2nd call: classification succeeds
        mock_completion.side_effect = [
            Exception("Summary API error"),
            _mock_llm_response("temporal", 0.85),
        ]

        result = process_file(
            file_path=workspace["file"],
            cfg=workspace["cfg"],
            dry_run=True,
        )

        assert result["triage"] == "temporal"
        assert result["confidence"] == 0.85


class TestIsFileDirectMode:
    """Tests for _is_file_direct_mode helper."""

    def test_cli_claude_returns_true(self) -> None:
        cfg = Config(
            llm=LlmConfig(mode="cli", provider="claude"),
        )
        assert _is_file_direct_mode(cfg) is True

    def test_cli_codex_returns_false(self) -> None:
        cfg = Config(
            llm=LlmConfig(mode="cli", provider="codex"),
        )
        assert _is_file_direct_mode(cfg) is False

    def test_api_returns_false(self) -> None:
        cfg = Config(
            llm=LlmConfig(mode="api", provider="openai"),
        )
        assert _is_file_direct_mode(cfg) is False


class TestFileDirectMode:
    """Tests for file direct mode in pipeline."""

    @pytest.fixture()
    def cli_workspace(self, tmp_path: Path) -> dict:
        """Create workspace configured for CLI claude mode."""
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_database(db_path)

        f = source_dir / "slides.pdf"
        f.write_bytes(b"%PDF-1.4 fake pdf content for testing " * 5)

        cfg = Config(
            input=InputConfig(directory=str(source_dir)),
            output=OutputConfig(directory=str(output_dir)),
            triage=TriageConfig(confidence_threshold=0.7),
            llm=LlmConfig(
                mode="cli", provider="claude", model="claude-sonnet-4-20250514"
            ),
            database=DatabaseConfig(path=str(db_path)),
            text_extraction=TextExtractionConfig(min_text_length=10),
        )

        return {
            "source_dir": source_dir,
            "output_dir": output_dir,
            "db_path": db_path,
            "file": f,
            "cfg": cfg,
        }

    @patch("doc_triager.pipeline.classify_document")
    @patch("doc_triager.pipeline.extract_text")
    def test_file_direct_skips_extraction(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        cli_workspace: dict,
    ) -> None:
        """ファイル直接モードでは extract_text が呼ばれない。"""
        from doc_triager.triage import TriageResult

        mock_classify.return_value = TriageResult(
            triage="evergreen", confidence=0.9, reason="Test", topics=["test"]
        )

        process_file(
            file_path=cli_workspace["file"],
            cfg=cli_workspace["cfg"],
            dry_run=True,
        )

        mock_extract.assert_not_called()

    @patch("doc_triager.pipeline.classify_document")
    @patch("doc_triager.pipeline.extract_text")
    def test_file_direct_passes_file_to_classify(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        cli_workspace: dict,
    ) -> None:
        """ファイル直接モードでは classify_document に file_path が渡される。"""
        from doc_triager.triage import TriageResult

        mock_classify.return_value = TriageResult(
            triage="evergreen", confidence=0.9, reason="Test", topics=["test"]
        )

        process_file(
            file_path=cli_workspace["file"],
            cfg=cli_workspace["cfg"],
            dry_run=True,
        )

        mock_classify.assert_called_once()
        call_kwargs = mock_classify.call_args.kwargs
        assert call_kwargs["file_path"] == cli_workspace["file"]

    @patch("doc_triager.pipeline.classify_document")
    @patch("doc_triager.pipeline.extract_text")
    def test_file_direct_db_record(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        cli_workspace: dict,
    ) -> None:
        """ファイル直接モードの DB 記録: extracted_text_length=0, truncated=False。"""
        from doc_triager.triage import TriageResult

        mock_classify.return_value = TriageResult(
            triage="evergreen", confidence=0.9, reason="Test", topics=["test"]
        )

        process_file(
            file_path=cli_workspace["file"],
            cfg=cli_workspace["cfg"],
            dry_run=True,
        )

        record = get_by_source_path(
            cli_workspace["db_path"], str(cli_workspace["file"])
        )
        assert record is not None
        assert record["extracted_text_length"] == 0
        assert record["truncated"] == 0  # SQLite boolean

    @patch("doc_triager.llm.litellm.completion")
    def test_api_mode_still_extracts(
        self, mock_completion: MagicMock, workspace: dict
    ) -> None:
        """API モードでは従来通り extract_text が呼ばれる。"""
        mock_completion.return_value = _mock_llm_response("evergreen", 0.9)

        with patch("doc_triager.pipeline.extract_text") as mock_extract:
            from doc_triager.extractor import ExtractionResult

            mock_extract.return_value = ExtractionResult(
                text="Extracted content " * 10,
            )

            process_file(
                file_path=workspace["file"],
                cfg=workspace["cfg"],
                dry_run=True,
            )

            mock_extract.assert_called_once()


class TestDryRunCliCommandOutput:
    """Tests for CLI command output during dry-run."""

    @pytest.fixture()
    def cli_claude_workspace(self, tmp_path: Path) -> dict:
        """Create workspace configured for CLI claude mode."""
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_database(db_path)

        f = source_dir / "slides.pdf"
        f.write_bytes(b"%PDF-1.4 fake pdf content for testing " * 5)

        cfg = Config(
            input=InputConfig(directory=str(source_dir)),
            output=OutputConfig(directory=str(output_dir)),
            triage=TriageConfig(confidence_threshold=0.7),
            llm=LlmConfig(
                mode="cli", provider="claude", model="claude-sonnet-4-20250514"
            ),
            database=DatabaseConfig(path=str(db_path)),
            text_extraction=TextExtractionConfig(min_text_length=10),
        )

        return {
            "source_dir": source_dir,
            "output_dir": output_dir,
            "db_path": db_path,
            "file": f,
            "cfg": cfg,
        }

    @pytest.fixture()
    def cli_codex_workspace(self, tmp_path: Path) -> dict:
        """Create workspace configured for CLI codex mode."""
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_database(db_path)

        f = source_dir / "doc.pdf"
        f.write_text("Design patterns content. " * 20)

        cfg = Config(
            input=InputConfig(directory=str(source_dir)),
            output=OutputConfig(directory=str(output_dir)),
            triage=TriageConfig(confidence_threshold=0.7),
            llm=LlmConfig(mode="cli", provider="codex", model="o3"),
            database=DatabaseConfig(path=str(db_path)),
            text_extraction=TextExtractionConfig(min_text_length=10),
        )

        return {
            "source_dir": source_dir,
            "output_dir": output_dir,
            "db_path": db_path,
            "file": f,
            "cfg": cfg,
        }

    @patch("doc_triager.pipeline.classify_document")
    @patch("doc_triager.pipeline.extract_text")
    def test_dry_run_cli_claude_logs_command(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        cli_claude_workspace: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """dry-run + CLI claude でコマンドがログ出力される（-f なし）。"""
        from doc_triager.triage import TriageResult

        mock_classify.return_value = TriageResult(
            triage="evergreen", confidence=0.9, reason="Test", topics=["test"]
        )

        import logging

        with caplog.at_level(logging.INFO, logger="doc_triager.pipeline"):
            process_file(
                file_path=cli_claude_workspace["file"],
                cfg=cli_claude_workspace["cfg"],
                dry_run=True,
            )

        cmd_logs = [r.message for r in caplog.records if "コマンド" in r.message]
        assert len(cmd_logs) >= 1
        cmd_log = cmd_logs[0]
        assert "claude" in cmd_log
        assert "-p" in cmd_log
        assert "--model" in cmd_log
        assert "claude-sonnet-4-20250514" in cmd_log
        # -f フラグが独立トークンとして含まれないこと（--output-format 内の -f は OK）
        cmd_part = cmd_log.split("コマンド:")[-1].strip()
        cmd_tokens = cmd_part.split()
        assert "-f" not in cmd_tokens

    @patch("doc_triager.pipeline.classify_document")
    @patch("doc_triager.pipeline.extract_text")
    def test_dry_run_cli_claude_default_model_omits_model_flag(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """CLI claude でデフォルトモデル（gpt-4o）の場合 --model が出力されない。"""
        from doc_triager.triage import TriageResult

        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_database(db_path)

        f = source_dir / "slides.pdf"
        f.write_bytes(b"%PDF-1.4 fake pdf content for testing " * 5)

        cfg = Config(
            input=InputConfig(directory=str(source_dir)),
            output=OutputConfig(directory=str(output_dir)),
            triage=TriageConfig(confidence_threshold=0.7),
            llm=LlmConfig(mode="cli", provider="claude"),  # model はデフォルト "gpt-4o"
            database=DatabaseConfig(path=str(db_path)),
            text_extraction=TextExtractionConfig(min_text_length=10),
        )

        mock_classify.return_value = TriageResult(
            triage="evergreen", confidence=0.9, reason="Test", topics=["test"]
        )

        import logging

        with caplog.at_level(logging.INFO, logger="doc_triager.pipeline"):
            process_file(file_path=f, cfg=cfg, dry_run=True)

        cmd_logs = [r.message for r in caplog.records if "コマンド" in r.message]
        assert len(cmd_logs) >= 1
        cmd_log = cmd_logs[0]
        assert "claude" in cmd_log
        assert "--model" not in cmd_log
        assert "gpt-4o" not in cmd_log

    @patch("doc_triager.llm.subprocess.run")
    def test_dry_run_cli_codex_logs_command(
        self,
        mock_run: MagicMock,
        cli_codex_workspace: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """dry-run + CLI codex でコマンドがログ出力される。"""
        import logging

        mock_run.return_value = __import__("subprocess").CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=__import__("json").dumps(
                {
                    "classification": "evergreen",
                    "confidence": 0.9,
                    "reason": "Test",
                    "topics": ["test"],
                }
            ),
            stderr="",
        )

        with caplog.at_level(logging.INFO, logger="doc_triager.pipeline"):
            process_file(
                file_path=cli_codex_workspace["file"],
                cfg=cli_codex_workspace["cfg"],
                dry_run=True,
            )

        cmd_logs = [r.message for r in caplog.records if "コマンド" in r.message]
        assert len(cmd_logs) >= 1
        cmd_log = cmd_logs[0]
        assert "codex" in cmd_log

    @patch("doc_triager.pipeline.classify_document")
    @patch("doc_triager.pipeline.extract_text")
    def test_non_dry_run_cli_does_not_log_command(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        cli_claude_workspace: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """dry-run でない場合はコマンドをログ出力しない。"""
        from doc_triager.triage import TriageResult

        mock_classify.return_value = TriageResult(
            triage="evergreen", confidence=0.9, reason="Test", topics=["test"]
        )

        import logging

        with caplog.at_level(logging.INFO, logger="doc_triager.pipeline"):
            process_file(
                file_path=cli_claude_workspace["file"],
                cfg=cli_claude_workspace["cfg"],
                dry_run=False,
            )

        cmd_logs = [r.message for r in caplog.records if "コマンド" in r.message]
        assert len(cmd_logs) == 0

    @patch("doc_triager.llm.litellm.completion")
    def test_dry_run_api_mode_does_not_log_command(
        self,
        mock_completion: MagicMock,
        workspace: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """dry-run + API モードではコマンドをログ出力しない。"""
        import logging

        mock_completion.return_value = _mock_llm_response("evergreen", 0.9)

        with caplog.at_level(logging.INFO, logger="doc_triager.pipeline"):
            process_file(
                file_path=workspace["file"],
                cfg=workspace["cfg"],
                dry_run=True,
            )

        cmd_logs = [r.message for r in caplog.records if "コマンド" in r.message]
        assert len(cmd_logs) == 0
