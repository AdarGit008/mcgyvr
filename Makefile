# mcgyvr task entrypoints — the single documented way in.
#   make setup     install dependencies (frozen against uv.lock)
#   make test      run the test suite
#   make lint      ruff check + format check
#   make typecheck mypy (strict)
#   make docs      regenerate the generated docs (config reference, /mcgyvr skill)
#   make check     everything CI runs
#   make journal-index DIR=…   build DIR/index.sqlite over a live journal
#   make journal-review DIR=… [OUTCOME=…]   print prompt/reply/outcome triples
# uv provides the interpreter and a reproducible, locked dependency set.
.PHONY: setup test lint typecheck docs docs-check check journal-index journal-review

setup:  ## install dependencies (frozen — resolved from uv.lock)
	uv sync --frozen

test: setup  ## run the test suite
	uv run --no-sync pytest

lint: setup  ## lint and format check
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .

typecheck: setup  ## strict type checking
	uv run --no-sync mypy

docs: setup  ## render+check+delete the config reference; regenerate the /mcgyvr skill
	uv run --no-sync python -m mcgyvr.docgen

docs-check: setup  ## fail if the reference does not render or the committed skill drifted
	uv run --no-sync python -m mcgyvr.docgen --check

check: lint typecheck test  ## everything CI runs

DIR ?= $(HOME)/.local/state/mcgyvr/journal
journal-index: setup  ## build DIR/index.sqlite over the live journal (default: the schema's journal.dir)
	uv run --no-sync python tools/live/index.py $(DIR)

journal-review: setup  ## print prompt/reply/outcome triples from DIR; OUTCOME=word filters
	uv run --no-sync python tools/live/review.py $(DIR) $(if $(OUTCOME),--outcome $(OUTCOME),)
