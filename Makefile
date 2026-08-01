# mcgyvr task entrypoints — the single documented way in.
#   make setup     install dependencies (frozen against uv.lock)
#   make test      run the test suite
#   make lint      ruff check + format check
#   make typecheck mypy (strict)
#   make docs      regenerate the config reference from the config schema
#   make check     everything CI runs
#   make baseline  score this repo against the vendored baseline
# uv provides the interpreter and a reproducible, locked dependency set.
.PHONY: setup test lint typecheck docs docs-check check baseline

setup:  ## install dependencies (frozen — resolved from uv.lock)
	uv sync --frozen

test: setup  ## run the test suite
	uv run --no-sync pytest

lint: setup  ## lint and format check
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .

typecheck: setup  ## strict type checking
	uv run --no-sync mypy

docs: setup  ## regenerate the config reference from the config schema
	uv run --no-sync python -m mcgyvr.docgen

docs-check: setup  ## fail if the committed config reference has drifted
	uv run --no-sync python -m mcgyvr.docgen --check

check: lint typecheck test  ## everything CI runs

baseline:  ## score this repo against the vendored baseline
	node tools/baseline/baseline.mjs check --repo .
