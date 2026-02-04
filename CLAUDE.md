# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a single test file / class / test
uv run pytest tests/test_config.py
uv run pytest tests/test_config.py::TestLoadConfig
uv run pytest tests/test_config.py::TestLoadConfig::test_load_valid_config

# Lint and format
uv run ruff check
uv run ruff format --check
uv run ruff format              # auto-fix

# Markdown lint
npx markdownlint-cli2 "docs/**/*.md"

# Run CLI
uv run doc-triager run --source <dir> --output <dir>
uv run doc-triager status
uv run doc-triager reclassify --threshold 0.5
uv run doc-triager export --format json
```

## Architecture

doc-triager is a batch CLI tool that classifies local documents as
**evergreen** (timeless value), **temporal** (time-sensitive), or **unknown** using LLM analysis.
It is project ① in a two-project pipeline;
its output (`evergreen/` folder + `triage.db`) feeds into doc-searcher (②).
doc-triager has no knowledge of project ②.

### Module layout (src/doc_triager/)

- **cli.py** — Typer-based CLI entry point. Commands: `run`, `status`, `reclassify`, `export`.
- **config.py** — TOML config loading into dataclass hierarchy.
  `load_config()` → `resolve_config()` (CLI overrides) → `resolve_api_key()` (.env > env var).

Remaining modules (database, scanner, extractor, triage, llm, mover, logging) are tracked in `docs/TASK.md`.

### Processing flow (run command)

1. Scan source directory recursively, filter by extension/exclude patterns
2. Compute SHA-256 checksum per file, skip if already processed (DB lookup)
3. Extract text via MarkItDown → Markdown
4. Send to LLM (litellm API / claude CLI / codex CLI) for classification with confidence score
5. Apply confidence threshold (default 0.7); below → `unknown`
6. Move file to `<output>/{evergreen,temporal,unknown}/` preserving hierarchy
7. Record result in SQLite

### Key dependencies

- **litellm** — Multi-provider LLM calls (OpenAI, Anthropic, Ollama)
  via unified `completion()` API. Chosen over LangChain per ADR-0002.
- **markitdown[all]** — Converts PDF, DOCX, PPTX, XLSX, HTML, images to Markdown.
- **python-dotenv** — `.env` file loading for API keys.
- **typer** — CLI framework.

### Configuration priority

1. CLI options (highest)
2. TOML config file
3. Dataclass defaults (lowest)

API key priority: `.env` file > OS environment variable.

## Conventions

- Python 3.13+. Use `str | None` union syntax, not `Optional[str]`.
- Config sections are `@dataclass` classes composed into a root `Config` dataclass.
- Error messages in Japanese.
- Documents written in the language of the target file.
- Requirements spec: `docs/REQUIREMENTS.md`. ADRs: `docs/adr/`.
