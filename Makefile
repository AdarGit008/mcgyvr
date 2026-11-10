# mcgyvr task entrypoints — the single documented way in.
#   make setup     install dependencies (frozen against uv.lock)
#   make test      run the test suite
#   make lint      ruff check + format check
#   make typecheck mypy (strict)
#   make docs      regenerate the generated docs (config reference, /mcgyvr, /mcgyvr-direct, /mcgyvr-use)
#   make check     everything CI runs
#   make release   the local half of a release (build, checks, notes); prints the tag command
# uv provides the interpreter and a reproducible, locked dependency set.
.PHONY: setup test lint typecheck docs docs-check check release

setup:  ## install dependencies (frozen — resolved from uv.lock)
	# The project itself is rebuilt every time: its version is read from git
	# (hatch-vcs), and an editable install that was not rebuilt reports the
	# commit it was last built at, not HEAD — `mcgyvr --version` on a checkout
	# would name the wrong code.
	uv sync --frozen --reinstall-package mcgyvr

test: setup  ## run the test suite
	uv run --no-sync pytest

lint: setup  ## lint and format check
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .

typecheck: setup  ## strict type checking
	uv run --no-sync mypy

docs: setup  ## render+check+delete the config reference; regenerate /mcgyvr, /mcgyvr-direct, /mcgyvr-use
	uv run --no-sync python -m mcgyvr.docgen

docs-check: setup  ## fail if the reference does not render or the committed skill drifted
	uv run --no-sync python -m mcgyvr.docgen --check

check: setup  ## everything CI runs — one build, then lint, typecheck, docs-check and test
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .
	uv run --no-sync mypy
	uv run --no-sync python -m mcgyvr.docgen --check
	uv run --no-sync pytest

# The local half of a release: what the tag's run of .github/workflows/release.yml checks, run here
# first, publishing nothing. One build into $(RELEASE_DIR) (cleared by uv first), the wheel is the
# version, the version has CHANGELOG notes (printed), `twine check`; then the tag command is printed
# for a human to run — pushing the tag is the release. The version is RELEASE_VERSION, or the newest
# CHANGELOG section. Before the tag exists the build is stamped with that version
# (SETUPTOOLS_SCM_PRETEND_VERSION); when the tag already names HEAD the version is read from it, as
# the tag's run reads it. Refused: a tree that differs from HEAD (the tag names HEAD, not the tree)
# and a version already tagged on another commit.
RELEASE_DIR ?= build/release
RELEASE_PY ?= uv run --no-project --with packaging python
TWINE ?= uv run --no-project --with twine twine

release:  ## the local half of a release (build, version, notes, twine check); prints the tag command
	@set -e; \
	if [ -n "$$(git status --porcelain --untracked-files=no)" ]; then \
		echo "REFUSED — the tree differs from HEAD; commit first, the tag names HEAD" >&2; exit 1; fi; \
	version="$(RELEASE_VERSION)"; \
	if [ -z "$$version" ]; then \
		version=$$($(RELEASE_PY) scripts/release/changelog_notes.py --latest CHANGELOG.md); fi; \
	version="$${version#v}"; tag="v$$version"; \
	at=$$(git rev-parse -q --verify "refs/tags/$$tag^{commit}" || true); \
	if [ -n "$$at" ] && [ "$$at" != "$$(git rev-parse HEAD)" ]; then \
		echo "REFUSED — $$tag is already tagged at $$at; write the next version's CHANGELOG section" >&2; \
		exit 1; fi; \
	if [ -z "$$at" ]; then export SETUPTOOLS_SCM_PRETEND_VERSION="$$version"; fi; \
	uv build --clear --out-dir "$(RELEASE_DIR)"; \
	$(RELEASE_PY) scripts/release/wheel_is_tag.py "$$tag" "$(RELEASE_DIR)"/*.whl; \
	echo "--- notes for $$tag (CHANGELOG.md)"; \
	$(RELEASE_PY) scripts/release/changelog_notes.py "$$tag" CHANGELOG.md; \
	echo "---"; \
	$(TWINE) check "$(RELEASE_DIR)"/*; \
	echo "local half passed for $$tag: nothing was tagged, pushed or uploaded. To release:"; \
	if [ -z "$$at" ]; then echo "  git tag -a $$tag -m $$tag"; fi; \
	echo "  git push origin $$tag"
