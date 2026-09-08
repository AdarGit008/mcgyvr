"""The bench judges a worker by the product's floor, not by this repo's own.

``tools/bench/score.py:lint_config`` exists because a synthetic one-file
workspace carries no ruff configuration, so ruff falls back to everything it
knows — 826 rules on 0.16.4, TRY004 alone rejecting 75 of 257 checked-in
reference solutions. Its own docstring names the failure that made it: *"The
bench would have been applying a stricter bar than the product, which is the
exact inverse of what #113 asks for."*

That is the whole test of the choice, and it does not point at
``pyproject.toml``. When ``lint_config`` was written, this repository's
selection and the product's *were* the same list — ``src/mcgyvr/gate/adapters/
python.py:45`` says so, crediting ``lint_config`` as where the selection was
first measured. They stopped being the same on 2026-09-08, when
``DEFAULT_RUFF_SELECT`` narrowed pycodestyle from ``E`` to ``E4``/``E7``/``E9``
so that E501 — the one selected rule ``ruff format`` structurally cannot
satisfy, and 104 of 220 lint findings in the live journal — stopped rejecting a
docstring the formatter can never wrap. The bench kept deriving its bar from
``pyproject.toml`` and so kept selecting ``E``, which resurrected the exact
defect the docstring was written against: a worker reply the product would ship
scores as a lint rejection on the bench.

Reading ``pyproject.toml`` is the choice that fails here. It measures the
worker against *this repository's* house style, which nothing in a bench run is
about; a rule this project adds for its own prose would silently move every
published pass rate. The product floor is what a mcgyvr-managed repository that
declares nothing is actually gated by, which is exactly what a bench workspace
is.

The first test below is the load-bearing one: it runs the gate over a workspace
staged by the bench itself, so it asserts the configuration the bench *applies*
rather than the tuple it names. The tuple check follows only to catch a
restated copy — the drift that produced this file — and would pass on its own
against a bench whose applied bar was still wrong.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tomllib
import types
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.gate import Gate
from mcgyvr.gate.adapters.python import DEFAULT_RUFF_SELECT
from mcgyvr.gate.changeset import ChangeSet

REPO = Path(__file__).resolve().parent.parent

#: A file whose only fault is a docstring line past 88 columns. E501 under a
#: selection carrying the whole ``E`` family, clean under the product's floor,
#: and ``ruff format`` reports it already formatted under both — a formatter
#: rewraps code, never a string. The sentence is ordinary English on purpose:
#: ruff raises no E501 for an overlong run with no whitespace past the indent,
#: so a probe line of 110 ``x`` characters would have tested nothing.
UNWRAPPABLE = (
    "def add(a: int, b: int) -> int:\n"
    '    """Return the sum of a and b, in a sentence long enough that it runs'
    ' past the eighty-eight column limit."""\n'
    "    return a + b\n"
)

#: The same file with one unused import. F401 is in every selection under
#: discussion, so this is what distinguishes "the bench applies the product's
#: floor" from "the bench applies no lint bar at all" — the way a narrowed
#: select could pass the test above and still be a hole that looks like a pass.
UNUSED_IMPORT = "import json\n\n" + UNWRAPPABLE


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def score() -> Any:
    """``tools/bench/score.py``, which is a script rather than a package."""
    return _by_path("bench_score_floor", REPO / "tools" / "bench" / "score.py")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )


def _bench_workspace(score: Any, tmp_path: Path, solution: str) -> Path:
    """A workspace staged by the bench's own ``stage_config``, then committed.

    ``stage_config`` rather than a hand-written ``pyproject.toml``: the bar this
    asserts on has to be the one a scored candidate meets, and the point of that
    function is that there is one place the bar is written.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    score.stage_config(workspace)
    _git(workspace, "init", "-q")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "base")
    (workspace / "solution.py").write_text(solution, encoding="utf-8")
    return workspace


def _codes(workspace: Path) -> set[str]:
    result = Gate().run(ChangeSet.detect(workspace, "HEAD"))
    return {f.code for f in result.findings if f.code}


def test_the_bench_does_not_reject_a_line_the_formatter_cannot_wrap(
    score: Any, tmp_path: Path
) -> None:
    """The bench's applied bar, not the tuple it names.

    A worker reply the product would accept must not score as a lint rejection
    here, or the bench is measuring a bar nothing ships.
    """
    workspace = _bench_workspace(score, tmp_path, UNWRAPPABLE)
    assert "E501" not in _codes(workspace)


def test_the_bench_still_rejects_what_the_product_rejects(
    score: Any, tmp_path: Path
) -> None:
    """The other half: a floor, not an absence of one.

    Without this, a ``lint_config`` that selected nothing at all would pass the
    test above — which is #261's shape, the hole that looks like a pass.
    """
    workspace = _bench_workspace(score, tmp_path, UNUSED_IMPORT)
    assert "F401" in _codes(workspace)


def test_the_staged_selection_is_the_products_and_is_not_restated(
    score: Any, tmp_path: Path
) -> None:
    """Weaker than the two above, and kept for one reason: drift.

    ``lint_config`` and ``DEFAULT_RUFF_SELECT`` held the same nine families for
    three days and then quietly stopped. Asserting equality against the imported
    constant is what makes the next narrowing move both at once.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    score.stage_config(workspace)
    staged = tomllib.loads((workspace / "pyproject.toml").read_text(encoding="utf-8"))
    assert staged["tool"]["ruff"]["lint"]["select"] == list(DEFAULT_RUFF_SELECT)
