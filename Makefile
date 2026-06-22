.PHONY: install dev lint test typecheck check build check-release-metadata clean

install:
	uv sync

dev:
	uv sync --extra dev

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

lint-fix:
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck:
	uv run mypy src

# Lint + typecheck (atalho pre-PR)
check: lint typecheck

# Empacota o wheel (uv build)
build:
	uv build

# Valida consistencia de versao entre pyproject.toml, server.json e CHANGELOG.md
check-release-metadata:
	@uv run python scripts/check_release_metadata.py

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=src --cov-report=term-missing --cov-report=html

run:
	uv run mcp-juridico-brasil

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov dist build
