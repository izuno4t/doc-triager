"""CLI entry point for doc-triager."""

import logging
from pathlib import Path

import typer

from doc_triager.config import load_config, resolve_config
from doc_triager.database import init_database
from doc_triager.llm import build_claude_cmd
from doc_triager.logging_config import setup_logging
from doc_triager.pipeline import process_files
from doc_triager.scanner import scan_files
from doc_triager.triage import build_classify_prompt

app = typer.Typer()


@app.command()
def run(
    source: str | None = typer.Option(
        None, "--source", "-s", help="Source directory path (config file fallback)"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output base directory path (config file fallback)"
    ),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Classify only, do not move files"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Max number of files to process"
    ),
    extensions: str | None = typer.Option(
        None, "--extensions", help="Target extensions (comma-separated)"
    ),
) -> None:
    """Triage documents in the source directory."""
    config_path = Path(config) if config else Path("config.toml")
    try:
        cfg = load_config(config_path)
        cfg = resolve_config(cfg, source=source, output=output)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    log_level = "DEBUG" if verbose else cfg.logging.level
    setup_logging(level=log_level, log_file=cfg.logging.file)

    logger = logging.getLogger("doc_triager")
    logger.info("Input: %s", cfg.input.directory)
    logger.info("Output: %s", cfg.output.directory)
    logger.info("Dry run: %s", dry_run)
    logger.info("LLM: %s/%s", cfg.llm.provider, cfg.llm.model)

    target_ext = (
        [f".{e.strip('.')}" for e in extensions.split(",")] if extensions else None
    )
    files = scan_files(
        Path(cfg.input.directory),
        exclude_patterns=cfg.input.exclude_patterns,
        target_extensions=target_ext,
    )

    effective_limit = limit if limit is not None else cfg.input.max_files or None
    if effective_limit is not None:
        files = files[:effective_limit]

    logger.info("対象ファイル数: %d", len(files))

    # DB初期化
    init_database(Path(cfg.database.path))

    debug_dir = (
        Path(cfg.text_extraction.debug_dir) if cfg.text_extraction.debug_dir else None
    )

    process_files(
        files=files,
        cfg=cfg,
        dry_run=dry_run,
        debug_dir=debug_dir,
    )


@app.command()
def status(
    triage: str | None = typer.Option(None, "--triage", help="Filter by triage"),
) -> None:
    """Show processing status summary."""
    typer.echo("Status summary")


@app.command()
def reclassify(
    threshold: float = typer.Option(
        0.5, "--threshold", help="New confidence threshold"
    ),
) -> None:
    """Re-classify unknown documents with a new threshold."""
    typer.echo(f"Reclassify with threshold: {threshold}")


@app.command()
def export(
    format: str = typer.Option("json", "--format", help="Export format (json/csv)"),
) -> None:
    """Export triage results from DB."""
    typer.echo(f"Export as {format}")


@app.command(name="preview-cmd")
def preview_cmd(
    file: str = typer.Argument(..., help="対象ファイルパス"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Preview the CLI command and prompt that would be used for a file."""
    config_path = Path(config) if config else Path("config.toml")
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    file_path = Path(file)
    if not file_path.exists():
        typer.echo(f"Error: ファイルが見つかりません: {file_path}", err=True)
        raise typer.Exit(code=1)

    mode = cfg.llm.mode
    provider = cfg.llm.provider
    model = cfg.llm.model

    filename = file_path.name
    file_extension = file_path.suffix

    is_file_direct = mode == "cli" and provider == "claude"

    if mode == "api":
        typer.echo(f"モード: API ({provider})")
        typer.echo(f"モデル: {model}")
        typer.echo("")
        typer.echo("APIモードではCLIコマンドは使用しません。")
        typer.echo("")
        prompt = build_classify_prompt(
            filename=filename,
            file_extension=file_extension,
            text="<テキスト抽出結果がここに入ります>",
            truncated=False,
        )
        typer.echo("プロンプト:")
        for line in prompt.splitlines():
            typer.echo(f"  {line}")
    elif is_file_direct:
        typer.echo("モード: ファイル直接（CLI claude）")
        cmd = build_claude_cmd(model=model or None, file_path=file_path)
        typer.echo("コマンド:")
        typer.echo(f"  {' '.join(cmd)}")
        typer.echo("")
        prompt = build_classify_prompt(
            filename=filename,
            file_extension=file_extension,
            file_path=file_path,
        )
        typer.echo("プロンプト (stdin):")
        for line in prompt.splitlines():
            typer.echo(f"  {line}")
    else:
        typer.echo(f"モード: テキスト抽出（CLI {provider}）")
        typer.echo(f"モデル: {model}")
        typer.echo("")
        typer.echo(
            "ファイルからテキストを抽出した後、CLIにプロンプトとして送信します。"
        )
        typer.echo("")
        prompt = build_classify_prompt(
            filename=filename,
            file_extension=file_extension,
            text="<テキスト抽出結果がここに入ります>",
            truncated=False,
        )
        typer.echo("プロンプト (stdin):")
        for line in prompt.splitlines():
            typer.echo(f"  {line}")


if __name__ == "__main__":
    app()
