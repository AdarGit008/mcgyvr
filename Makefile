# mcgyvr task entrypoints — the single documented way in.
#   make setup     install dependencies (frozen against uv.lock)
#   make test      run the test suite
#   make lint      ruff check + format check
#   make typecheck mypy (strict)
#   make docs      regenerate the generated docs (config reference)
#   make check     everything CI runs
# uv provides the interpreter and a reproducible, locked dependency set.
.PHONY: setup test lint typecheck docs docs-check check

setup:  ## install dependencies (frozen — resolved from uv.lock)
	uv sync --frozen

test: setup  ## run the test suite
	uv run --no-sync pytest

lint: setup  ## lint and format check
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .

typecheck: setup  ## strict type checking
	uv run --no-sync mypy

docs: setup  ## regenerate the generated docs (config reference)
	uv run --no-sync python -m mcgyvr.docgen

docs-check: setup  ## fail if a committed generated doc has drifted
	uv run --no-sync python -m mcgyvr.docgen --check

check: lint typecheck test  ## everything CI runs
