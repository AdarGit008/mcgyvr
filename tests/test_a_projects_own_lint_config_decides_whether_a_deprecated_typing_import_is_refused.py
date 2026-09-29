"""A project's own lint config decides whether a deprecated typing import is refused.

``from typing import List`` and ``List[int]`` are correct code in an old
spelling. A repository that states no ruff configuration is linted by the
product's shipped default selection, and under that default the gate reports
the old spelling and does not refuse the change for it.

A repository that states its own ruff configuration (``[tool.ruff]`` in
``pyproject.toml``, ``ruff.toml`` or ``.ruff.toml``) is judged by it, and the
product does not soften what it asks:

* where it selects the rules that flag the old spelling (the ``UP`` family, or
  ``UP006`` and ``UP035`` by name), the change is refused under those codes;
* where it selects the import-sorting rules, an import block it finds unsorted
  is refused, even when the import in it is a deprecated ``typing`` one;
* where it selects none of these, the lint rung has nothing to refuse the
  change for.

A repair runs the same linter under the same configuration, and fixes only
what that configuration selects. Where it also selects unused-import removal
(``F``), a repair rewrites ``List[int]`` to ``list[int]``, drops the import
that is then unused, and the gate accepts. Under the ``UP`` rules alone a
repair rewrites the annotation and leaves ``from typing import List`` in
place, so the change stays refused under UP035: that is the project's own
selection, and the last test here pins it as a fact that already holds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest

from mcgyvr.contract import loads as load_contract
from mcgyvr.gate import Gate, GateResult
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.typecheck import STYLE
from mcgyvr.repair import repair

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the rules in question are ruff's; without it the lint rung does not run",
)

TARGET = "src/pkg/rows.py"

#: Formatted, import-sorted and correct: the only thing a linter can say about
#: it is the deprecated spelling, on line 1 (UP035) and line 4 (UP006).
OLD_SPELLING = (
    "from typing import List\n"
    "\n"
    "\n"
    "def total(rows: List[int]) -> int:\n"
    '    """Add the rows."""\n'
    "    return sum(rows)\n"
)

#: The same kind of import with one blank line after it, which the
#: import-sorting rules report as an unformatted import block on line 1.
OLD_SPELLING_TIGHT = (
    "from typing import Mapping\n"
    "\n"
    "def widths(rows: Mapping) -> int:\n"
    "    return len(rows)\n"
)

#: The codes the old spelling is reported under.
OLD_SPELLING_CODES = {"UP006", "UP035"}

PROJECT = '[project]\nname = "rows"\nversion = "0"\n'

CONTRACT = f"""
id: add-rows
task_type: function_implementation
task: Add the rows.
target: {TARGET}
stop_conditions:
  - The rows are not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def _repo(tmp_path: Path, config: dict[str, str]) -> Path:
    """A git repository whose base commit holds ``config`` and one module."""
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    for name, text in config.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _gated(repo: Path, source: str) -> GateResult:
    """The gate's verdict on a change that writes ``source`` to the target."""
    (repo / TARGET).write_text(source, encoding="utf-8")
    return Gate().run(ChangeSet.detect(repo, "HEAD"))


def _codes(findings: Iterable[Finding]) -> set[str]:
    return {f.code for f in findings if f.code}


@needs_ruff
@pytest.mark.parametrize(
    "config",
    [
        pytest.param(
            {"pyproject.toml": PROJECT + '\n[tool.ruff.lint]\nselect = ["UP"]\n'},
            id="pyproject-selects-the-family",
        ),
        pytest.param(
            {
                "pyproject.toml": PROJECT,
                "ruff.toml": '[lint]\nselect = ["UP006", "UP035"]\n',
            },
            id="ruff-toml-selects-the-two-codes",
        ),
        pytest.param(
            {
                "pyproject.toml": PROJECT,
                ".ruff.toml": '[lint]\nselect = ["F", "I", "UP"]\n',
            },
            id="dot-ruff-toml-selects-the-family-among-others",
        ),
    ],
)
def test_a_config_that_selects_the_rules_refuses_the_old_spelling_under_them(
    tmp_path: Path, config: dict[str, str]
) -> None:
    result = _gated(_repo(tmp_path, config), OLD_SPELLING)

    assert not result.accepted, (
        f"the project's own configuration selects the rules that flag the old "
        f"spelling, and the change was accepted: {result.observations}"
    )
    refused = {f.code for f in result.findings if f.check == "lint"}
    assert refused >= OLD_SPELLING_CODES, (
        f"refused, but not under the codes the project selected: {result.findings}"
    )
    assert not OLD_SPELLING_CODES & _codes(result.observations), (
        f"the same code was both refused and noted: {result.observations}"
    )


@needs_ruff
def test_a_config_that_selects_import_sorting_refuses_the_block_the_old_spelling_is_in(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path, {"pyproject.toml": PROJECT, "ruff.toml": '[lint]\nselect = ["I"]\n'}
    )

    result = _gated(repo, OLD_SPELLING_TIGHT)

    assert not result.accepted, (
        f"the project's own configuration selects import sorting and the block "
        f"is unformatted, and the change was accepted: {result.observations}"
    )
    assert "I001" in {f.code for f in result.findings if f.check == "lint"}, (
        f"refused, but not for the import block: {result.findings}"
    )


@needs_ruff
def test_a_config_that_does_not_select_the_rules_does_not_refuse_the_old_spelling(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path, {"pyproject.toml": PROJECT + '\n[tool.ruff.lint]\nselect = ["F"]\n'}
    )

    result = _gated(repo, OLD_SPELLING)

    assert result.accepted, (
        f"the project's own configuration does not select the rules that flag "
        f"the old spelling, and the change was refused: {result.findings}"
    )
    assert not OLD_SPELLING_CODES & (
        _codes(result.findings) | _codes(result.observations)
    ), f"a rule the project did not select was applied: {result}"


@needs_ruff
def test_under_the_shipped_default_the_old_spelling_is_reported_not_refused(
    tmp_path: Path,
) -> None:
    result = _gated(_repo(tmp_path, {"pyproject.toml": PROJECT}), OLD_SPELLING)

    assert result.accepted, (
        f"under the shipped default the old spelling is a note, and the change "
        f"was refused: {result.findings}"
    )
    noted = {f.code for f in result.observations if f.check == STYLE}
    assert noted >= OLD_SPELLING_CODES, (
        f"under the shipped default the old spelling was not reported: "
        f"{result.observations}"
    )


def _repaired_and_regated(repo: Path) -> GateResult:
    """Refused first, then repaired in place, then judged again."""
    first = _gated(repo, OLD_SPELLING)
    assert not first.accepted, (
        f"the premise: the project's own configuration refuses the old "
        f"spelling, and the change was accepted: {first.observations}"
    )
    outcome = repair(repo=repo, contract=load_contract(CONTRACT))
    assert outcome.repaired == (TARGET,), outcome
    return Gate().run(ChangeSet.detect(repo, "HEAD"))


@needs_ruff
def test_a_repair_clears_the_old_spelling_where_the_config_also_removes_unused_imports(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {"pyproject.toml": PROJECT + '\n[tool.ruff.lint]\nselect = ["F", "UP"]\n'},
    )

    again = _repaired_and_regated(repo)

    assert again.accepted, (
        f"the repair ran under the same configuration the gate judged by, which "
        f"also removes an unused import, and left the change refused: "
        f"{again.findings}"
    )


@needs_ruff
def test_under_the_up_rules_alone_a_repair_leaves_the_import_and_it_stays_refused(
    tmp_path: Path,
) -> None:
    """A pinned fact, not a promise this change made: it holds already.

    The project's configuration selects no rule that removes an unused import,
    so the repair rewrites the annotation and the import it no longer needs
    stays, refused under UP035 as the project asked.
    """
    repo = _repo(
        tmp_path, {"pyproject.toml": PROJECT + '\n[tool.ruff.lint]\nselect = ["UP"]\n'}
    )

    again = _repaired_and_regated(repo)

    assert not again.accepted, f"the old import was cleared: {again.observations}"
    assert {f.code for f in again.findings if f.check == "lint"} == {"UP035"}, (
        f"expected the annotation rewritten and the import left: {again.findings}"
    )
    assert "from typing import List" in (repo / TARGET).read_text(encoding="utf-8")
