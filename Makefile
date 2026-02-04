.PHONY: install test lint format check run dry-run clean build publish help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

test: ## Run all tests
	uv run pytest tests/ -v

lint: ## Run linter
	uv run ruff check src/ tests/

format: ## Format code
	uv run ruff format src/ tests/

format-check: ## Check formatting without changes
	uv run ruff format --check src/ tests/

lint-md: ## Lint markdown files
	npx markdownlint-cli2 "docs/**/*.md" "*.md"

check: lint format-check lint-md test ## Run all checks (lint + format + markdown + test)

run: ## Run doc-triager
	uv run doc-triager run

dry-run: ## Run doc-triager in dry-run mode
	uv run doc-triager run --dry-run

clean: ## Remove build artifacts and caches
	rm -rf dist/ build/ *.egg-info/ .pytest_cache/ .ruff_cache/
	find src tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build: clean ## Build distribution packages
	uv build

publish: build ## Publish to PyPI
	uv publish
