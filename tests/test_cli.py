"""Tests for cli module."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from doc_triager.cli import app
from doc_triager.database import init_database

runner = CliRunner()


class TestPreviewCmd:
    """Tests for preview-cmd subcommand."""

    def _write_config(
        self,
        tmp_path: Path,
        *,
        mode: str = "cli",
        provider: str = "claude",
        model: str = "claude-sonnet-4-20250514",
    ) -> Path:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            textwrap.dedent(f"""\
                [input]
                directory = "{tmp_path / "source"}"

                [output]
                directory = "{tmp_path / "output"}"

                [llm]
                mode = "{mode}"
                provider = "{provider}"
                model = "{model}"
                api_key_env = "OPENAI_API_KEY"

                [logging]
                level = "WARNING"
                file = "{tmp_path / "test.log"}"
            """)
        )
        return config_file

    def test_preview_cmd_cli_claude(self, tmp_path: Path) -> None:
        """CLI+claude 設定でコマンド・プロンプトが表示される。"""
        config_file = self._write_config(tmp_path)
        target = tmp_path / "slides.pdf"
        target.write_text("dummy")

        result = runner.invoke(
            app, ["preview-cmd", str(target), "--config", str(config_file)]
        )

        assert result.exit_code == 0
        output = result.stdout
        assert "ファイル直接" in output
        assert "claude" in output
        assert "-p" in output
        assert "--output-format" in output
        assert "text" in output
        assert "--model" in output
        assert "claude-sonnet-4-20250514" in output
        assert "-f" in output
        assert str(target) in output
        # プロンプト表示
        assert "プロンプト" in output
        assert "slides.pdf" in output

    def test_preview_cmd_cli_claude_with_file_flag(self, tmp_path: Path) -> None:
        """CLI claude モードではコマンドに -f <path> が含まれる。"""
        config_file = self._write_config(tmp_path)
        target = tmp_path / "doc.pdf"
        target.write_text("dummy")

        result = runner.invoke(
            app, ["preview-cmd", str(target), "--config", str(config_file)]
        )

        assert result.exit_code == 0
        assert "-f" in result.stdout

    def test_preview_cmd_api_mode(self, tmp_path: Path) -> None:
        """API モードではCLIコマンドなしの旨が表示される。"""
        config_file = self._write_config(
            tmp_path, mode="api", provider="openai", model="gpt-4o"
        )
        target = tmp_path / "doc.pdf"
        target.write_text("dummy")

        result = runner.invoke(
            app, ["preview-cmd", str(target), "--config", str(config_file)]
        )

        assert result.exit_code == 0
        output = result.stdout
        assert "API" in output
        # CLI コマンドは表示されない
        assert "claude -p" not in output

    def test_preview_cmd_cli_codex(self, tmp_path: Path) -> None:
        """CLI+codex 設定ではファイル直接モードではない旨が表示される。"""
        config_file = self._write_config(
            tmp_path, mode="cli", provider="codex", model="o3"
        )
        target = tmp_path / "doc.pdf"
        target.write_text("dummy")

        result = runner.invoke(
            app, ["preview-cmd", str(target), "--config", str(config_file)]
        )

        assert result.exit_code == 0
        output = result.stdout
        # codex CLI ではファイル直接モードではない
        assert "テキスト抽出" in output

    def test_preview_cmd_file_not_found(self, tmp_path: Path) -> None:
        """存在しないファイルでエラーになる。"""
        config_file = self._write_config(tmp_path)

        result = runner.invoke(
            app,
            [
                "preview-cmd",
                str(tmp_path / "nonexistent.pdf"),
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 1
        assert "見つかりません" in result.stdout or "見つかりません" in (
            result.stderr or ""
        )

    def test_preview_cmd_default_config(self, tmp_path: Path) -> None:
        """--config 未指定時にデフォルトの config.toml を探す。"""
        # config.toml が存在しない場合はエラーになる
        result = runner.invoke(app, ["preview-cmd", str(tmp_path / "test.pdf")])

        # config.toml が見つからないのでエラー
        assert result.exit_code == 1


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
