.PHONY: help test test-cov lint typecheck format check docs docs-build clean

PYTHON ?= .venv/bin/python

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

docs:  ## Serve docs locally on localhost:8000
	$(PYTHON) -m mkdocs serve

docs-build:  ## Build docs (strict)
	$(PYTHON) -m mkdocs build --strict

test:  ## Run tests
	$(PYTHON) -m pytest tests/ -x --tb=short -q

test-cov:  ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ --cov=parsimony_mcp --cov-report=term-missing --cov-fail-under=80

lint:  ## Run ruff linter
	$(PYTHON) -m ruff check parsimony_mcp tests

format:  ## Auto-format code
	$(PYTHON) -m ruff format parsimony_mcp tests
	$(PYTHON) -m ruff check --fix parsimony_mcp tests

typecheck:  ## Run mypy (strict)
	$(PYTHON) -m mypy parsimony_mcp

check: lint typecheck test  ## Run lint + typecheck + test

clean:  ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .mypy_cache .ruff_cache .pytest_cache htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
