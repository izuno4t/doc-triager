"""Tests for config module."""

import textwrap
from pathlib import Path

import pytest


@pytest.fixture()
def config_toml(tmp_path: Path) -> Path:
    """Create a minimal valid TOML config file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        textwrap.dedent("""\
            [input]
            directory = "/path/to/source"
            exclude_patterns = ["*.DS_Store", "__MACOSX/**"]

            [output]
            directory = "/path/to/output"

            [triage]
            confidence_threshold = 0.8
            max_input_tokens = 4000

            [llm]
            provider = "openai"
            model = "gpt-4o"
            api_key_env = "OPENAI_API_KEY"

            [llm.rate_limit]
            requests_per_minute = 60
            max_retries = 5
            retry_delay_sec = 10
            request_timeout_sec = 180

            [database]
            path = "./test.db"

            [text_extraction]
            min_text_length = 200
            llm_summary_enabled = false

            [logging]
            level = "DEBUG"
            file = "./test.log"
        """)
    )
    return config_file


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, config_toml: Path) -> None:
        from doc_triager.config import load_config

        config = load_config(config_toml)

        assert config.input.directory == "/path/to/source"
        assert config.input.exclude_patterns == ["*.DS_Store", "__MACOSX/**"]
        assert config.output.directory == "/path/to/output"
        assert config.triage.confidence_threshold == 0.8
        assert config.triage.max_input_tokens == 4000
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"
        assert config.llm.api_key_env == "OPENAI_API_KEY"
        assert config.llm.rate_limit.requests_per_minute == 60
        assert config.llm.rate_limit.max_retries == 5
        assert config.llm.rate_limit.retry_delay_sec == 10
        assert config.llm.rate_limit.request_timeout_sec == 180
        assert config.database.path == "./test.db"
        assert config.text_extraction.min_text_length == 200
        assert config.text_extraction.llm_summary_enabled is False
        assert config.logging.level == "DEBUG"
        assert config.logging.file == "./test.log"

    def test_default_values_applied(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config

        config_file = tmp_path / "minimal.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"

                [output]
                directory = "/path/to/output"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)

        assert config.input.max_files == 0
        assert config.triage.confidence_threshold == 0.7
        assert config.triage.max_input_tokens == 8000
        assert config.llm.mode == "api"
        assert config.llm.rate_limit.requests_per_minute == 30
        assert config.llm.rate_limit.max_retries == 3
        assert config.llm.rate_limit.retry_delay_sec == 5
        assert config.llm.rate_limit.request_timeout_sec == 120
        assert config.database.path == "./triage.db"
        assert config.text_extraction.min_text_length == 100
        assert config.text_extraction.llm_summary_enabled is False
        assert config.logging.level == "INFO"
        assert config.logging.file == "./doc-triager.log"
        assert config.input.exclude_patterns == [
            "*.DS_Store",
            "*.gitkeep",
            ".git/**",
            "__MACOSX/**",
        ]

    def test_default_mode_is_api(self, tmp_path: Path) -> None:
        from doc_triager.config import LlmConfig, load_config

        # dataclass デフォルト
        llm = LlmConfig()
        assert llm.mode == "api"

        # TOML で mode を指定しない場合もデフォルトは "api"
        config_file = tmp_path / "no_mode.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"

                [output]
                directory = "/path/to/output"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)
        assert config.llm.mode == "api"

    def test_mode_loaded_from_toml(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config

        config_file = tmp_path / "claude_mode.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"

                [output]
                directory = "/path/to/output"

                [llm]
                mode = "claude"
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)
        assert config.llm.mode == "claude"

    def test_max_files_default_is_zero(self, tmp_path: Path) -> None:
        from doc_triager.config import InputConfig, load_config

        assert InputConfig().max_files == 0

        config_file = tmp_path / "no_max.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"

                [output]
                directory = "/path/to/output"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)
        assert config.input.max_files == 0

    def test_max_files_loaded_from_toml(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config

        config_file = tmp_path / "with_max.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"
                max_files = 50

                [output]
                directory = "/path/to/output"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)
        assert config.input.max_files == 50

    def test_file_not_found(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config

        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_invalid_toml(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config

        config_file = tmp_path / "invalid.toml"
        config_file.write_text("[[invalid toml content")

        with pytest.raises(ValueError, match="設定ファイル"):
            load_config(config_file)


class TestTextExtractionConfig:
    """Tests for TextExtractionConfig fields."""

    def test_llm_summary_enabled_default_false(self) -> None:
        from doc_triager.config import TextExtractionConfig

        te = TextExtractionConfig()
        assert te.llm_summary_enabled is False

    def test_no_llm_description_fields(self) -> None:
        from doc_triager.config import TextExtractionConfig

        assert not hasattr(TextExtractionConfig, "llm_description_enabled")
        assert not hasattr(TextExtractionConfig, "llm_description_model")

    def test_llm_summary_enabled_loaded_from_toml(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config

        config_file = tmp_path / "summary.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"

                [output]
                directory = "/path/to/output"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"

                [text_extraction]
                llm_summary_enabled = true
            """)
        )
        config = load_config(config_file)
        assert config.text_extraction.llm_summary_enabled is True


class TestResolveConfig:
    """Tests for resolve_config function."""

    def test_cli_overrides_source_and_output(self, config_toml: Path) -> None:
        from doc_triager.config import load_config, resolve_config

        config = load_config(config_toml)
        resolved = resolve_config(config, source="/cli/source", output="/cli/output")

        assert resolved.input.directory == "/cli/source"
        assert resolved.output.directory == "/cli/output"

    def test_cli_none_keeps_config_values(self, config_toml: Path) -> None:
        from doc_triager.config import load_config, resolve_config

        config = load_config(config_toml)
        resolved = resolve_config(config, source=None, output=None)

        assert resolved.input.directory == "/path/to/source"
        assert resolved.output.directory == "/path/to/output"

    def test_missing_source_raises_error(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config, resolve_config

        config_file = tmp_path / "no_source.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [output]
                directory = "/path/to/output"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)

        with pytest.raises(ValueError, match="input"):
            resolve_config(config, source=None, output=None)

    def test_missing_output_raises_error(self, tmp_path: Path) -> None:
        from doc_triager.config import load_config, resolve_config

        config_file = tmp_path / "no_output.toml"
        config_file.write_text(
            textwrap.dedent("""\
                [input]
                directory = "/path/to/source"

                [llm]
                provider = "openai"
                model = "gpt-4o"
                api_key_env = "OPENAI_API_KEY"
            """)
        )
        config = load_config(config_file)

        with pytest.raises(ValueError, match="output"):
            resolve_config(config, source=None, output=None)


class TestResolveApiKey:
    """Tests for API key resolution from environment variables."""

    def test_resolve_api_key_from_env_var(
        self, config_toml: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from doc_triager.config import load_config, resolve_api_key

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")
        config = load_config(config_toml)

        api_key = resolve_api_key(config)

        assert api_key == "sk-test-key-123"

    def test_resolve_api_key_from_dotenv(
        self, config_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from doc_triager.config import load_config, resolve_api_key

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=sk-from-dotenv-456\n")
        config = load_config(config_toml)

        api_key = resolve_api_key(config, env_file=env_file)

        assert api_key == "sk-from-dotenv-456"

    def test_dotenv_overrides_env_var(
        self, config_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from doc_triager.config import load_config, resolve_api_key

        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=sk-from-dotenv\n")
        config = load_config(config_toml)

        api_key = resolve_api_key(config, env_file=env_file)

        assert api_key == "sk-from-dotenv"

    def test_missing_env_var_and_no_dotenv_raises_error(
        self, config_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from doc_triager.config import load_config, resolve_api_key

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = load_config(config_toml)

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            resolve_api_key(config, env_file=tmp_path / "nonexistent.env")
