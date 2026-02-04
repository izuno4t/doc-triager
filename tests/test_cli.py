"""Tests for cli module."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from doc_triager.cli import app
from doc_triager.database import init_database

runner = CliRunner()


def _setup_workspace(tmp_path: Path, *, max_files: int = 0) -> Path:
    """Create source dir with 5 files, output dir, DB, and config."""
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    db_path = tmp_path / "test.db"
    init_database(db_path)

    for i in range(5):
        (source / f"doc{i}.pdf").write_text(f"Content for document {i}. " * 20)

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        textwrap.dedent(f"""\
            [input]
            directory = "{source}"
            max_files = {max_files}

            [output]
            directory = "{output}"

            [llm]
            provider = "openai"
            model = "gpt-4o"
            api_key_env = "OPENAI_API_KEY"

            [database]
            path = "{db_path}"

            [text_extraction]
            min_text_length = 10

            [logging]
            level = "WARNING"
            file = "{tmp_path / "test.log"}"
        """)
    )
    return config_file


def _mock_llm_response():
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(
        {
            "classification": "evergreen",
            "confidence": 0.9,
            "reason": "Test",
            "topics": [],
        }
    )
    return resp


class TestLimitAndMaxFiles:
    """Tests for --limit CLI option and max_files config interaction."""

    @patch("doc_triager.llm.litellm.completion")
    def test_config_max_files_limits_processing(
        self, mock_completion, tmp_path: Path
    ) -> None:
        mock_completion.return_value = _mock_llm_response()
        config_file = _setup_workspace(tmp_path, max_files=2)

        result = runner.invoke(app, ["run", "--config", str(config_file), "--dry-run"])

        assert result.exit_code == 0
        # max_files=2 なので LLM は最大 2 回呼ばれる
        assert mock_completion.call_count <= 2

    @patch("doc_triager.llm.litellm.completion")
    def test_cli_limit_overrides_config_max_files(
        self, mock_completion, tmp_path: Path
    ) -> None:
        mock_completion.return_value = _mock_llm_response()
        config_file = _setup_workspace(tmp_path, max_files=10)

        result = runner.invoke(
            app, ["run", "--config", str(config_file), "--dry-run", "--limit", "1"]
        )

        assert result.exit_code == 0
        # CLI --limit=1 が config の max_files=10 より優先
        assert mock_completion.call_count <= 1

    @patch("doc_triager.llm.litellm.completion")
    def test_max_files_zero_means_no_limit(
        self, mock_completion, tmp_path: Path
    ) -> None:
        mock_completion.return_value = _mock_llm_response()
        config_file = _setup_workspace(tmp_path, max_files=0)

        result = runner.invoke(app, ["run", "--config", str(config_file), "--dry-run"])

        assert result.exit_code == 0
        # 5 ファイル全部処理される
        assert mock_completion.call_count == 5

    @patch("doc_triager.llm.litellm.completion")
    def test_cli_limit_without_config_max_files(
        self, mock_completion, tmp_path: Path
    ) -> None:
        mock_completion.return_value = _mock_llm_response()
        config_file = _setup_workspace(tmp_path, max_files=0)

        result = runner.invoke(
            app, ["run", "--config", str(config_file), "--dry-run", "--limit", "3"]
        )

        assert result.exit_code == 0
        assert mock_completion.call_count <= 3
