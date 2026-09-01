"""ADR-0034 at the commit point: a rung that did not run is not a rung that passed.

:func:`mcgyvr.deliver.deliver` runs the gate for itself, over the bytes on disk,
inside the repository lock and immediately before staging. That re-run is the
module's stated floor — *"Nothing a caller says can make un-judged bytes into a
commit"* — and it read one field of the gate's answer. ``_judged`` returned
:attr:`~mcgyvr.gate.GateResult.findings` and dropped the rest, while
:attr:`~mcgyvr.gate.GateResult.accepted` is ``not findings and not
inconclusive``. The second half is the half ADR-0034 added; delivery was
deciding on the half that predates it.

What that costs is neither hypothetical nor a race. A repository whose
``pyproject.toml`` ruff cannot load — a key from another ruff, a half-finished
edit, a version skew — makes every ruff invocation exit **2 with an empty
stdout**. ADR-0034 measured precisely that, and it is why an adapter raises
:class:`~mcgyvr.gate.adapter.ToolFailedError` on an exit code it does not report
under: an empty finding list must never also mean *we could not tell*. The gate
does the right thing with it — an :class:`~mcgyvr.gate.runner.InconclusiveRung`
for lint, another for format, and no findings. Delivery's ``if findings:`` guard
then passes and the change is committed with lint and format never applied, and
with nothing on the returned :class:`~mcgyvr.deliver.Delivery` saying so. The
false pass is silent in both directions: the commit looks gated and the answer
looks clean.

**Which path makes it the whole bar.** ``mcgyvr run --commit`` on the ladder
carries an :class:`~mcgyvr.deliver.Accepted`, but ``pending.resume`` with a bare
``str`` — and any caller that hands delivery the bytes rather than a binding —
reaches this seam with no sandbox verdict behind it at all. There, delivery's
gate run is the only gate the bytes ever see, so a rung that did not run is not
a degraded second opinion; it is the acceptance bar missing.

**Nothing here is substituted.** The linter that cannot run is the project's own
ruff, failing the way ADR-0034 measured it fail, against a config file this test
writes into the repository being delivered into. A stand-in adapter raising
``ToolFailedError`` would have proved the same refusal fires, and would also have
proved it against a gate whose lint rung the test wrote — which is the one thing
the reproduction must not assume.

**The controls carry the weight the reproduction cannot.** A fix that refused
every delivery satisfies "it did not commit" perfectly, so
:func:`test_a_repository_whose_linter_runs_still_delivers` runs the identical
delivery over a config ruff reads and requires the commit. And
:func:`test_an_absent_tool_is_still_not_a_refusal` holds ADR-0034's fourth
clause, which is the one this fix could most easily break by accident: a tool
that is *missing* leaves a hole an operator can see, is recorded in
``environment_issues``, and must keep delivering — the keyless install (#44) is
the case that clause exists to preserve, and "reject on anything the environment
complains about" would take it away.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import deliver

CONTRACT = """
id: fetch-strip
task_type: function_implementation
task: Strip the URL before returning it.
target: src/pkg/fetch.py
stop_conditions:
  - The trimming rule is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

TARGET = "src/pkg/fetch.py"

#: The base, and the change. Deliberately dull: one added line that lints and
#: formats clean, so that every refusal below is about a rung that could not
#: run rather than about anything the change did.
BEFORE = "def fetch(url):\n    return url\n"
AFTER = "def fetch(url):\n    return url.strip()\n"

#: A `pyproject.toml` ruff refuses to load. `unknown field` is what ruff answers
#: with, on **exit 2 and an empty stdout** for every one of the four invocations
#: the adapters make — the measurement ADR-0034 turns on, re-measured here by
#: `test_the_premise_is_a_ruff_that_exits_2` rather than assumed.
UNREADABLE_CONFIG = "[tool.ruff]\nnot-a-real-ruff-key = 3\n"

#: The same file with nothing ruff objects to. The control's only difference.
READABLE_CONFIG = "[tool.ruff]\nline-length = 88\n"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def make_repo(where: Path, config: str) -> Path:
    (where / "src" / "pkg").mkdir(parents=True)
    (where / TARGET).write_text(BEFORE, encoding="utf-8")
    (where / "pyproject.toml").write_text(config, encoding="utf-8")
    git(where.parent, "init", "-q", str(where))
    git(where, "config", "user.email", "test@example.invalid")
    git(where, "config", "user.name", "test")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


def contract() -> Contract:
    return loads(CONTRACT)


needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the reproduction is a real ruff exiting 2; there is nothing to fake here",
)


@needs_ruff
def test_the_premise_is_a_ruff_that_exits_2(tmp_path: Path) -> None:
    """The measurement the rest of this file stands on, taken rather than assumed.

    ADR-0034's table is dated 2026-08-16 and the record says so on purpose:
    "the fix is only correct for as long as that table is". If a later ruff
    answers an unloadable config with exit 1, or with a diagnostic on stdout,
    every test below would keep passing for the wrong reason — the change would
    be refused by a *finding* rather than by an inconclusive rung, and the field
    this fix is about would never be read. This is the assertion that fails
    first when that day comes.
    """
    repo = make_repo(tmp_path / "repo", UNREADABLE_CONFIG)

    done = subprocess.run(
        ["ruff", "check", "--output-format=json", "--force-exclude", "--", TARGET],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert done.returncode == 2, (
        f"ruff answered an unloadable config with {done.returncode}, not 2; "
        f"ADR-0034's measured table has moved and this file's premise with it"
    )
    assert not done.stdout.strip(), (
        f"ruff wrote {done.stdout!r} on its failure. The whole defect is that an "
        f"empty stdout reads as zero diagnostics, so a failure that says something "
        f"would be caught by the JSON reader instead."
    )


@needs_ruff
def test_a_linter_that_could_not_run_does_not_get_a_commit(tmp_path: Path) -> None:
    """The reproduction: un-judged bytes reached a commit through delivery's own gate.

    The content is a bare ``str``, which is the shape that carries no verdict at
    all — ``pending.resume``'s, and the shape delivery's docstring says is
    "judged ... either way". With ruff unable to load the repository's config,
    lint and format both come back inconclusive and neither comes back as a
    finding, so the only thing standing between these bytes and a commit is
    whether delivery reads the field ADR-0034 added.

    Asserted as "did not commit" rather than as a reason, because the reason is
    :func:`test_the_refusal_names_what_could_not_be_judged`'s and a commit that
    happened cannot be un-happened by a good sentence.
    """
    repo = make_repo(tmp_path / "repo", UNREADABLE_CONFIG)
    base = git(repo, "rev-parse", "HEAD").strip()

    delivery = deliver(repo=repo, contract=contract(), content=AFTER, base=base)

    assert not delivery.committed, (
        "delivery committed a change whose lint and format rungs never ran. "
        "`GateResult.accepted` is `not findings and not inconclusive`, and this "
        "seam read only the first half (ADR-0034)."
    )
    assert git(repo, "rev-parse", "HEAD").strip() == base, (
        "a commit is on the branch, so the refusal — if there was one — did not "
        "happen before staging"
    )


@needs_ruff
def test_the_refusal_names_what_could_not_be_judged(tmp_path: Path) -> None:
    """A refusal an operator can act on names the rung, the tool and the exit code.

    "Rejected" would be the wrong word and an unusable one. Nothing is claimed
    about the change here — ADR-0034 clause 3 is explicit that no finding is
    invented — and the operator's next move is to fix a config file, which they
    can only do if the refusal says which tool would not load it. That is what
    :class:`~mcgyvr.gate.runner.InconclusiveRung` carries, and it is asserted
    structurally as well as in the sentence: a run manifest has to be able to
    answer *which rung* per row, and a caller re-deriving that by parsing prose
    is the coupling the structured field exists to prevent.
    """
    repo = make_repo(tmp_path / "repo", UNREADABLE_CONFIG)
    base = git(repo, "rev-parse", "HEAD").strip()

    delivery = deliver(repo=repo, contract=contract(), content=AFTER, base=base)

    assert not delivery.committed, delivery.reason
    assert "ruff" in delivery.reason, delivery.reason
    assert "lint" in delivery.reason, delivery.reason
    assert "2" in delivery.reason, delivery.reason
    assert not delivery.findings, (
        f"the refusal invented findings: {delivery.findings}. ADR-0034 clause 3 "
        f"— the change is not rejected, it simply did not pass a bar that never "
        f"ran — and a caller reporting these to a worker would ask it to fix "
        f"nothing it did."
    )
    assert {rung.rung for rung in delivery.inconclusive} == {"lint", "format"}, (
        f"the Delivery does not carry which rungs could not run: "
        f"{delivery.inconclusive}. Both ruff rungs faulted, and ADR-0034 clause "
        f"6 keeps every rung being attempted after one faults."
    )
    assert all(rung.tool == "ruff" for rung in delivery.inconclusive)
    assert all(rung.exit_code == 2 for rung in delivery.inconclusive)


@needs_ruff
def test_a_repository_whose_linter_runs_still_delivers(tmp_path: Path) -> None:
    """The control: this is a fix, not a refusal.

    Identical delivery, identical bytes, one line of TOML different. A change
    over which every rung ran and found nothing is exactly what delivery exists
    to commit, and a fix that read ``accepted`` as "refuse when anything is off"
    would leave this failing while every assertion above still passed.
    """
    repo = make_repo(tmp_path / "repo", READABLE_CONFIG)
    base = git(repo, "rev-parse", "HEAD").strip()

    delivery = deliver(repo=repo, contract=contract(), content=AFTER, base=base)

    assert delivery.committed, f"the accepted change was not delivered: {delivery}"
    assert not delivery.inconclusive, delivery.inconclusive
    assert git(repo, "show", f"{delivery.commit}:{TARGET}") == AFTER


def test_an_absent_tool_is_still_not_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0034 clause 4, which this fix must not quietly repeal.

    A tool that is *absent* leaves a legible hole: it is recorded in
    ``environment_issues``, it does not reject, and the verdict is still
    reached. ``README.md`` promises a keyless install "runs local-only ... with
    the gate as the acceptance bar" (#44), and a machine without ruff is an
    ordinary machine. The two cases look alike from a distance and mean opposite
    things, which is the whole distinction ADR-0034 was opened to draw — so the
    narrowest way to get this fix wrong is to reject on both.

    ``require_tool`` is what the adapter asks "is this machine's ruff there", so
    that is the one thing replaced, and it is replaced with the answer the
    function itself gives on a machine that has none. Emptying ``PATH`` would be
    the more literal spelling and a worse test: delivery's own ``git``
    subprocesses go through the same ``PATH``, so the run would fail for a
    reason that has nothing to do with the linter.
    """
    from mcgyvr.gate.adapter import ToolUnavailableError

    repo = make_repo(tmp_path / "repo", READABLE_CONFIG)
    base = git(repo, "rev-parse", "HEAD").strip()

    def not_installed(tool: str) -> str:
        raise ToolUnavailableError(tool)

    monkeypatch.setattr("mcgyvr.gate.adapters.python.require_tool", not_installed)

    delivery = deliver(repo=repo, contract=contract(), content=AFTER, base=base)

    assert delivery.committed, (
        f"a machine with no ruff could not deliver: {delivery.reason}. An absent "
        f"tool is an environment issue, never an inconclusive rung (ADR-0034 "
        f"clause 4), and the keyless install is what that clause preserves."
    )
    assert not delivery.inconclusive
