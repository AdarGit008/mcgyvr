"""§4, second item — ``UP035`` was demoted wholesale, and half of it is fatal.

:data:`~mcgyvr.gate.typecheck.STYLE_LINT_CODES` moves ruff's ``UP035`` off the
rejecting ``lint`` axis and onto ``style``, which
:class:`~mcgyvr.gate.GateResult` renders as an *observation*: real,
line-attributed, and outside the verdict. That was the right call for what the
demotion was argued for — ``from typing import List`` is correct code in the
wrong dialect, and spending a model call, a gate run and a rung of the ladder
on six characters is the exact cost the split exists to stop.

``UP035`` is not one rule. Ruff reports two unrelated faults under it:

``from typing import Mapping``
    Deprecated spelling. The module imports, the code runs, the annotation
    means what it says. Style, and it must stay demoted — reversing that is
    the defect this test's control exists to prevent.

``from collections import Mapping``
    Not a spelling. ``collections`` re-exported the abstract base classes as a
    compatibility shim through 3.9 and stopped in 3.10, so this line raises
    ``ImportError`` on every interpreter this project supports
    (``requires-python = ">=3.12"``). Nothing in the module runs. There is no
    dialect in which it is correct.

The gate accepts the second today and tells the reviewer, in
:func:`~mcgyvr.verify.gate_summary`'s own words, that "no check is asking for
them to be fixed".

**Why the message text cannot be the discriminator.** Ruff's own words for the
two lines above are byte-identical -- "Import from ``collections.abc``
instead: ``Mapping``" -- and so are the code, the severity and the rule name.
The two diagnostics differ in the filename and in nothing else, which is
pinned below. A rule that read the message would have to accept both or reject
both, which is the whole defect restated. What separates them is the module
the import names, and that is an AST fact about the worker's file.

The rule these are all measured against:

    Code that cannot be imported on the Python versions this project supports
    is a finding. A deprecated spelling of code that does import is an
    observation. One lint code carries both, so the axis is decided by what
    was imported and not by which code ruff printed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate import ChangeSet, Gate, GateResult
from mcgyvr.verify import gate_summary

# `Mapping` is spelled the same way in both halves on purpose: it is the one
# name that makes the pair differ in the imported-from module and in nothing
# else, so a test that passes on one and fails on the other cannot be passing
# on the imported name.
UNIMPORTABLE = """from collections import Mapping


def widths(rows: Mapping) -> int:
    return len(rows)
"""

DEPRECATED_SPELLING = """from typing import Mapping


def widths(rows: Mapping) -> int:
    return len(rows)
"""

# The demotion's own original example, kept as a second control: whatever
# separates the two halves must not disturb the case the split was argued for.
DEPRECATED_ALIAS = """from typing import List


def sizes(rows: List[int]) -> int:
    return len(rows)
"""


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository with one commit, and no ruff configuration.

    Real rather than mocked: the whole question is what a gate run over a real
    diff ends up saying, and the lint rung is a subprocess whose answer a fake
    would have to invent. No ``pyproject.toml`` either, so ruff resolves to its
    own defaults -- which is what a bare install of the tool reports, and the
    measurement :data:`~mcgyvr.gate.typecheck.STYLE_LINT_CODES` was calibrated
    against.
    """
    work = tmp_path / "work"
    (work / "src" / "pkg").mkdir(parents=True)
    (work / "src" / "pkg" / "fetch.py").write_text(
        "def fetch(url):\n    return url\n", encoding="utf-8"
    )
    git(work.parent, "init", "-q", str(work))
    git(work, "config", "user.email", "test@example.invalid")
    git(work, "config", "user.name", "test")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "base")
    return work


def worker_wrote(repo: Path, name: str, source: str) -> ChangeSet:
    """The change a worker left behind, as the gate sees it."""
    (repo / "src" / "pkg" / name).write_text(source, encoding="utf-8")
    return ChangeSet.detect(repo, git(repo, "rev-parse", "HEAD").strip())


def gated(repo: Path, name: str, source: str) -> GateResult:
    return Gate().run(worker_wrote(repo, name, source))


def test_an_import_that_cannot_resolve_fails_the_change(repo: Path) -> None:
    """``from collections import Mapping`` is an ``ImportError``, not a dialect.

    Asserted on the verdict rather than on the presence of a note, because the
    demotion's whole effect is that a note does not stop the change from
    landing. A worker that leaves this line behind has delivered a module that
    cannot be imported, and the gate exists to say so before a reviewer is
    spent on it.
    """
    result = gated(repo, "widths.py", UNIMPORTABLE)

    assert not result.accepted, (
        "`from collections import Mapping` raises ImportError on every Python "
        "this project supports, and the gate accepted the change: "
        f"observations={result.observations}"
    )
    assert any(f.path.endswith("widths.py") for f in result.findings), (
        f"the change was rejected, but nothing points at the import that "
        f"cannot resolve: {result.findings}"
    )


def test_the_reviewer_is_told_the_import_failed_rather_than_that_nobody_asked(
    repo: Path,
) -> None:
    """A finding that never reaches the gate summary is half a fix.

    :func:`~mcgyvr.verify.gate_summary` writes three channels for a reviewer
    that did not watch the run, and the observation channel says in as many
    words that "no check is asking for them to be fixed". An unimportable
    module described that way is worse than silence: the reviewer is told the
    item is optional.
    """
    summary = gate_summary(gated(repo, "widths.py", UNIMPORTABLE))

    failed, _, reported = summary.partition("Reported without rejecting.")

    assert "widths.py" in failed, (
        f"the unimportable import is not in the reviewer's Failed block: {summary}"
    )
    assert "widths.py" not in reported, (
        f"the reviewer is told no check is asking for an ImportError to be "
        f"fixed: {summary}"
    )


@pytest.mark.parametrize(
    ("name", "source"),
    [
        pytest.param("widths.py", DEPRECATED_SPELLING, id="typing-Mapping"),
        pytest.param("sizes.py", DEPRECATED_ALIAS, id="typing-List"),
    ],
)
def test_the_typing_half_of_up035_stays_demoted(
    repo: Path, name: str, source: str
) -> None:
    """The control. Re-promoting ``UP035`` wholesale is worse than the defect.

    Both halves, or neither is the point: a fix that rejected here would buy
    the ImportError back at the price of the thing the demotion was argued
    for, and the operator would pay an attempt for six characters again.
    """
    result = gated(repo, name, source)

    assert result.accepted, (
        f"a deprecated typing spelling is correct code in the wrong dialect "
        f"and it rejected the change: {result.findings}"
    )
    assert any(f.path.endswith(name) for f in result.observations), (
        f"the deprecated spelling was neither reported nor rejected, so the "
        f"gate stopped looking at the style half entirely: {result}"
    )


def test_the_verdict_does_not_depend_on_ruff_being_installed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator without ruff must still be told the module will not import.

    The demotion exists because a finding and an observation were the only two
    things a rung could say, and the gate's own answer to that was to make the
    style axis reach both the AST family and the linter — "so the verdict does
    not depend on which tools the operator happens to have". The unimportable
    half inherits that obligation. A fix that only narrowed the lint demotion
    would leave every install without ruff accepting an ImportError, which is
    the same defect with a smaller blast radius.

    PATH is emptied rather than ruff deleted: the gate resolves its tools
    through :func:`~mcgyvr.gate.adapter.require_tool`, so this is the machine
    the docstring is talking about, and the lint rung's absence shows up in
    ``environment_issues`` where it belongs. It is emptied *after* the change
    set is detected, because detecting one is git's job and a test that hid
    git would be measuring a different absence.
    """
    changed = worker_wrote(repo, "widths.py", UNIMPORTABLE)
    monkeypatch.setenv("PATH", str(repo / "no-tools-here"))

    result = Gate().run(changed)

    assert any("ruff" in issue for issue in result.environment_issues), (
        f"ruff was still reachable, so this ran on the wrong machine: "
        f"{result.environment_issues}"
    )
    assert not result.accepted, (
        f"with no linter on PATH the unimportable import was accepted, so the "
        f"verdict is the linter's and not the gate's: {result}"
    )
    assert any(f.path.endswith("widths.py") for f in result.findings), (
        f"rejected, but not for the import: {result.findings}"
    )


def test_ruffs_own_words_do_not_separate_the_two_halves(tmp_path: Path) -> None:
    """The premise behind choosing the AST over the message text.

    This asserts a fact about ruff rather than about mcgyvr, and it is here so
    that the fact is checked rather than remembered: the day ruff's two
    messages diverge, this fails and a reader learns that the cheaper
    discriminator has become available -- not that mcgyvr broke.
    """
    unimportable = tmp_path / "unimportable.py"
    deprecated = tmp_path / "deprecated.py"
    unimportable.write_text(UNIMPORTABLE, encoding="utf-8")
    deprecated.write_text(DEPRECATED_SPELLING, encoding="utf-8")

    fatal = _up035(unimportable)
    style = _up035(deprecated)

    assert fatal and style, (
        f"ruff reported no UP035 for one of the two: {fatal} {style}"
    )
    assert fatal == style, (
        f"ruff's UP035 diagnostics now differ in what a rule could read, so "
        f"the message is no longer the fragile discriminator this test "
        f"assumed: {fatal} vs {style}"
    )


def _up035(path: Path) -> list[tuple[object, ...]]:
    """Every UP035 ruff reports for ``path``, as much as a rule could read.

    Filename and end column are dropped: both are facts about where the line
    sits and how long it is, not about what is wrong with it. What is left is
    everything a lint-code-and-text rule could match on, the offered fix
    included -- and for these two inputs ruff offers the same fix as well.
    """
    done = subprocess.run(
        ["ruff", "check", "--output-format=json", "--isolated", "--", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode not in (0, 1):
        pytest.skip(f"ruff could not run: {done.stderr.strip()}")
    return [
        (
            diag["code"],
            diag["name"],
            diag["message"],
            diag["severity"],
            diag["url"],
            (diag.get("fix") or {}).get("message"),
            tuple(edit["content"] for edit in (diag.get("fix") or {}).get("edits", ())),
        )
        for diag in json.loads(done.stdout or "[]")
        if diag.get("code") == "UP035"
    ]
