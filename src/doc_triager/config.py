"""Configuration module for doc-triager."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InputConfig:
    directory: str = ""
    max_files: int = 0
    exclude_patterns: list[str] = field(
        default_factory=lambda: [
            "*.DS_Store",
            "*.gitkeep",
            ".git/**",
            "__MACOSX/**",
        ]
    )


@dataclass
class OutputConfig:
    directory: str = ""


@dataclass
class TriageConfig:
    confidence_threshold: float = 0.7
    max_input_tokens: int = 8000


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 30
    max_retries: int = 3
    retry_delay_sec: int = 5
    request_timeout_sec: int = 120


@dataclass
class LlmConfig:
    mode: str = "api"
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


@dataclass
class DatabaseConfig:
    path: str = "./triage.db"


@dataclass
class TextExtractionConfig:
    min_text_length: int = 100
    llm_summary_enabled: bool = False
    debug_dir: str = ""


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "./doc-triager.log"


@dataclass
class Config:
    input: InputConfig = field(default_factory=InputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    triage: TriageConfig = field(default_factory=TriageConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    text_extraction: TextExtractionConfig = field(default_factory=TextExtractionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _build_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """Build a dataclass instance from a dict, ignoring unknown keys."""
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**filtered)


def load_config(path: Path) -> Config:
    """Load configuration from a TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {path}")

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        msg = f"設定ファイルの解析に失敗しました: {path}: {e}"
        raise ValueError(msg) from e

    input_cfg = _build_dataclass(InputConfig, raw.get("input", {}))
    output = _build_dataclass(OutputConfig, raw.get("output", {}))
    triage = _build_dataclass(TriageConfig, raw.get("triage", {}))

    llm_raw = raw.get("llm", {})
    rate_limit_raw = llm_raw.pop("rate_limit", {})
    rate_limit = _build_dataclass(RateLimitConfig, rate_limit_raw)
    llm = _build_dataclass(LlmConfig, llm_raw)
    llm.rate_limit = rate_limit

    database = _build_dataclass(DatabaseConfig, raw.get("database", {}))
    text_extraction = _build_dataclass(
        TextExtractionConfig, raw.get("text_extraction", {})
    )
    logging_config = _build_dataclass(LoggingConfig, raw.get("logging", {}))

    return Config(
        input=input_cfg,
        output=output,
        triage=triage,
        llm=llm,
        database=database,
        text_extraction=text_extraction,
        logging=logging_config,
    )


def resolve_config(
    config: Config,
    *,
    source: str | None = None,
    output: str | None = None,
) -> Config:
    """Apply CLI overrides and validate required fields."""
    if source is not None:
        config.input.directory = source
    if output is not None:
        config.output.directory = output

    if not config.input.directory:
        msg = "input ディレクトリが指定されていません（CLIオプション --source または設定ファイル [input] directory）"
        raise ValueError(msg)
    if not config.output.directory:
        msg = "output ディレクトリが指定されていません（CLIオプション --output または設定ファイル [output] directory）"
        raise ValueError(msg)

    return config


def resolve_api_key(config: Config, *, env_file: Path | None = None) -> str:
    """Resolve API key from .env file or environment variable.

    Priority: .env file > OS environment variable.
    """
    from dotenv import dotenv_values

    env_name = config.llm.api_key_env

    if env_file is not None and env_file.exists():
        dotenv_vars = dotenv_values(env_file)
        api_key = dotenv_vars.get(env_name)
        if api_key:
            return api_key

    api_key = os.environ.get(env_name)
    if api_key:
        return api_key

    msg = f"環境変数 {env_name} が設定されていません"
    raise ValueError(msg)
