"""CLI entry point for doc-triager."""

import logging
from pathlib import Path

import typer

from doc_triager.config import load_config, resolve_config
from doc_triager.database import init_database
from doc_triager.logging_config import setup_logging
from doc_triager.pipeline import process_files
from doc_triager.scanner import scan_files

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


if __name__ == "__main__":
    app()
