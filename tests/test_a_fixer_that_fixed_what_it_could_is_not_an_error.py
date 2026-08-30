"""``mcgyvr run`` read every non-zero exit as fatal, and a fixer's ordinary exit is 1.

:mod:`mcgyvr.deterministic` binds ``("python", "lint_fix")`` to ``ruff check
--fix``, and the catalog's guarantee for that type says what the binding is for:
*"Every autofix the project's linter applies is applied, and nothing else is. A
diagnostic the linter will not fix itself is explicitly out of scope for this
type rather than handed to a model under the same name."* A residue is therefore
not a failure of the contract — it is the contract's stated shape.

``ruff check --fix`` reports that residue by **exiting 1**. Measured against ruff
0.16.4 on a file with one fixable and one unfixable diagnostic: the fixable one
is removed, the file on disk is rewritten, and the process exits 1 saying
"1 fixed, 1 remaining". :func:`mcgyvr.cli._run` treated that as
``error: <ruff's diagnostic dump>`` and returned 1 before ``gate_workspace`` was
ever called. So a ``lint_fix`` contract whose autofixes landed *exactly as its
guarantee describes* was reported as an error, never gated, and never committed
— and the operator was shown a list of diagnostics that the type they asked for
explicitly does not fix, as though it were a crash.

``("python", "import_sort")`` is the same binding with ``--select I``, and has
the same exposure the moment an I-rule violation is unfixable.

**Where the line goes, and why not somewhere cheaper.** Three states, not two.
*Could not run* — 126/127, already separated by
:data:`~mcgyvr.gate.acceptance.DID_NOT_RUN` and already an environment issue,
which is what degrades a contract onto a dearer family instead of failing it.
*Ran and did the work its type's guarantee describes* — proceed, because the
gate is the thing that judges the result and refusing here means the result is
never judged at all. *Ran and failed* — fatal, because a tool that could not
load its config did not apply the guarantee to anything.

The test between the last two is the **exit code**, checked against the set of
codes under which that invocation is *reporting* rather than failing. That is
ADR-0034's clause 2 one layer out, and for the same measured reason: on a fatal
config error ruff writes an empty stdout, so nothing about the output separates
"clean" from "never ran". "Ignore the exit code and let the gate decide" would
have been the cheap fix and is the wrong one — it hands a change that no linter
ever touched to a gate whose own linter is broken in the same way.

The set differs by **task type**, because the guarantee is what says whether a
residue is expected. ``lint_fix`` and ``import_sort`` say it in as many words.
``format``'s guarantee is "byte-identical to what the project's own formatter
produces", which admits no residue at all — and, measured, neither formatter
exits non-zero except on failure (``ruff format`` answers an unparseable file
and an unloadable config alike with 2; so does ``prettier --write``).

Every measurement here is retaken by a test rather than quoted, because
ADR-0034's own table carries the warning: the fix is only correct for as long as
the table is.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import loads as load_contract
from mcgyvr.deterministic import tool_steps
from mcgyvr.drive import run_tool_step
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/messy.py"

#: One fixable diagnostic and one that is not, which is the ordinary state of a
#: file somebody asks a linter to tidy. ``import os`` is F401 and ruff removes
#: it; ``l`` is E741 and ruff will not rename a variable for you. The residue is
#: the whole point: a `lint_fix` contract over a file with nothing left over
#: exits 0 and would have passed against the defect.
RESIDUE = "import os\n\n\ndef f():\n    l = 1\n    return l\n"

#: ruff's default rule set does not carry E741, so the repository states its own
#: selection — which is also the honest arrangement: the tool step and the gate's
#: lint rung both read this file, so the bar the fixer applied and the bar the
#: gate applies are the same bar rather than two.
RUFF_CONFIG = '[tool.ruff.lint]\nselect = ["E", "F"]\n'

#: A `pyproject.toml` ruff refuses to load, which is the "ran and failed" case
#: and must stay fatal. The same shape ADR-0034 measured for the gate's own
#: invocations, here for the floor's.
BROKEN_CONFIG = "[tool.ruff]\nnot-a-real-ruff-key = 3\n"

LINT_FIX = """
id: tidy-lint
task_type: lint_fix
task: Apply the linter's own autofixes.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the floor under test is a real ruff; there is nothing to fake here",
)


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def make_repo(where: Path, source: str, config: str = RUFF_CONFIG) -> Path:
    (where / "src" / "pkg").mkdir(parents=True)
    (where / TARGET).write_text(source, encoding="utf-8")
    (where / "pyproject.toml").write_text(config, encoding="utf-8")
    _git(where, "init", "-q")
    _git(where, "add", "-A")
    _git(where, "commit", "-q", "-m", "base")
    return where


def written(tmp_path: Path, body: str, name: str = "c.yaml") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


# --- the measurements the rest of the file stands on -------------------------


@needs_ruff
def test_the_premise_is_a_fixer_that_fixed_things_and_exited_1(
    tmp_path: Path,
) -> None:
    """``ruff check --fix`` applies what it can and still exits 1. Both halves.

    Asserted together on purpose. "Exit 1" alone would be satisfied by a ruff
    that fixed nothing and merely complained, and a fix built on that reading
    would be letting a tool that did no work through to the gate. What makes the
    residue proceedable is that the tool *did* its type's guarantee — the file on
    disk is not the file it was handed — and both facts come out of one run.
    """
    repo = make_repo(tmp_path / "repo", RESIDUE)
    contract = load_contract(LINT_FIX)
    (step,) = tool_steps(contract)
    assert step.argv == ("ruff", "check", "--fix", "--", TARGET)

    with TempDirSandbox(repo) as sandbox:
        outcome = run_tool_step(step, sandbox)
        after = (sandbox.workspace / TARGET).read_text(encoding="utf-8")

    assert outcome.ran
    assert outcome.result is not None
    assert outcome.result.exit_code == 1, (
        f"ruff answered a remaining diagnostic with {outcome.result.exit_code}, "
        f"not 1. The premise of this whole file has moved."
    )
    assert "import os" not in after, (
        "ruff exited 1 without applying the autofix it was asked for, so this "
        "file's claim — that exit 1 means the guarantee was carried out — is not "
        "true of this ruff"
    )
    assert "l = 1" in after, (
        "ruff renamed the ambiguous variable, so there is no residue left and "
        "the case under test is not the case being run"
    )


@needs_ruff
def test_the_control_is_a_ruff_that_could_not_load_its_config(
    tmp_path: Path,
) -> None:
    """And the failing case is exit 2, which is what keeps the two apart.

    If a broken config produced the same exit code as a leftover diagnostic
    there would be no line to draw, and this file would be arguing for
    something unimplementable. It does not, and this is where that is checked
    rather than assumed.
    """
    repo = make_repo(tmp_path / "repo", RESIDUE, config=BROKEN_CONFIG)
    (step,) = tool_steps(load_contract(LINT_FIX))

    with TempDirSandbox(repo) as sandbox:
        outcome = run_tool_step(step, sandbox)

    assert outcome.ran, "a config error is ruff running and failing, not ruff absent"
    assert outcome.result is not None
    assert outcome.result.exit_code == 2, outcome.result.exit_code


# --- the reproduction --------------------------------------------------------


@needs_ruff
def test_a_lint_fix_that_left_a_diagnostic_is_gated_not_errored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The defect: work done exactly as the catalog describes, reported as an error.

    The change ruff makes here is one the gate accepts — the autofix deletes a
    line and adds none, so the diagnostic that remains is not on a worker-added
    line and the gate has nothing to attribute to the change. That is not a
    contrivance to make the test pass; it is why the defect is expensive. The
    contract was satisfiable, the tool satisfied it, and ``run`` returned 1
    with a dump of diagnostics the type it was given explicitly does not fix.

    Both halves are asserted. The exit code says the command did not fail, and
    the gate's own verdict line says the gate was *reached* — which is the
    actual claim, and the one that would survive a change to what the gate
    then decides.
    """
    from mcgyvr.cli import main

    repo = make_repo(tmp_path / "repo", RESIDUE)
    contract = written(tmp_path, LINT_FIX)

    code = main(["run", contract, "--repo", str(repo), "--sandbox", "tempdir"])

    out = capsys.readouterr()
    assert "tidy-lint: gate" in out.out, (
        f"the gate was never reached; `run` stopped at the tool step.\n"
        f"stdout: {out.out}\nstderr: {out.err}"
    )
    assert code == 0, (
        f"a lint_fix contract whose autofixes were applied exactly as its "
        f"catalog guarantee describes came back as a failure.\n"
        f"stdout: {out.out}\nstderr: {out.err}"
    )


@needs_ruff
def test_the_residue_is_reported_rather_than_swallowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proceeding is not the same as saying nothing happened.

    "Do not simply ignore exit codes" cuts both ways: a run that treats exit 1
    as silently equivalent to exit 0 tells the operator the linter had nothing
    to say, when in fact it has a list of things it will not fix and the
    operator may well want to see them. The diagnostic the type leaves out of
    scope is named on the way past.
    """
    from mcgyvr.cli import main

    repo = make_repo(tmp_path / "repo", RESIDUE)
    contract = written(tmp_path, LINT_FIX)

    main(["run", contract, "--repo", str(repo), "--sandbox", "tempdir"])

    out = capsys.readouterr().out
    assert "E741" in out, (
        f"the leftover diagnostic vanished. It is out of scope for `lint_fix`, "
        f"which is a reason not to fail on it and not a reason to hide it.\n"
        f"stdout: {out}"
    )


# --- the controls: a tool that genuinely failed is still fatal ---------------


@needs_ruff
def test_a_tool_that_ran_and_failed_is_still_fatal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control the whole fix turns on.

    Identical command, identical contract, one unloadable line of TOML. ruff
    exits 2 having applied nothing, so nothing about the guarantee was carried
    out and there is no result for a gate to judge — and the gate would be
    broken in exactly the same way, since it reads the same config. A fix that
    let every non-zero exit through to the gate satisfies every assertion above
    and fails here, which is the point of having it.
    """
    from mcgyvr.cli import main

    repo = make_repo(tmp_path / "repo", RESIDUE, config=BROKEN_CONFIG)
    contract = written(tmp_path, LINT_FIX)

    code = main(["run", contract, "--repo", str(repo), "--sandbox", "tempdir"])

    out = capsys.readouterr()
    assert code == 1, f"a ruff that could not load its config was not fatal: {out.out}"
    assert "error" in out.err, out.err
    assert "tidy-lint: gate" not in out.out, (
        "a change no linter applied anything to was carried to the gate, whose "
        "own lint rung reads the same broken config"
    )


@needs_ruff
def test_a_formatters_guarantee_admits_no_residue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``format`` is the other side of the line, and it is drawn by the guarantee.

    "The target is byte-identical to what the project's own formatter produces"
    has no room in it for a file the formatter declined to write. So ``format``
    reports under exit 0 and nothing else, and an unparseable target — which
    ``ruff format`` answers with 2 — is fatal rather than gated. Keeping this
    per task type rather than per program is what stops the fix from being "ruff
    exits 1, therefore 1 is fine": one program owns three of these types and the
    guarantee is what differs between them.
    """
    from mcgyvr.cli import main

    repo = make_repo(tmp_path / "repo", "def f(:\n    pass\n")
    contract = written(tmp_path, FORMAT)

    code = main(["run", contract, "--repo", str(repo), "--sandbox", "tempdir"])

    out = capsys.readouterr()
    assert code == 1, f"a formatter that produced nothing was not fatal: {out.out}"
    assert "tidy: gate" not in out.out, out.out


def test_a_missing_program_is_still_an_environment_issue(tmp_path: Path) -> None:
    """The third state, unchanged, and asserted here so it stays that way.

    126/127 is "the program is not on this machine", which
    :data:`~mcgyvr.gate.acceptance.DID_NOT_RUN` already separates and which
    degrades the contract onto a dearer family rather than failing it. A fix
    that reshaped the exit-code reading around the reporting/failing split could
    easily fold this in with the failures; it is a different question with a
    different answer, and nothing about this change touches it.
    """
    from dataclasses import replace

    from mcgyvr.deterministic import Tool

    repo = make_repo(tmp_path / "repo", RESIDUE)
    (planned,) = tool_steps(load_contract(LINT_FIX))
    step = replace(
        planned,
        tool=Tool(task_type="lint_fix", command=("mcgyvr-no-such-program-42",)),
    )

    with TempDirSandbox(repo) as sandbox:
        outcome = run_tool_step(step, sandbox)

    assert not outcome.ran
    assert "could not run" in outcome.environment_issue


@needs_ruff
def test_import_sort_carries_the_same_exposure_and_the_same_answer() -> None:
    """``import_sort`` is the same binding with ``--select I``, so it is the same rule.

    Asserted on the table rather than through a repository, because the
    behaviour under test is which exit codes each type reports under, and
    reaching that through an I-rule violation ruff happens to decline to fix
    would be testing ruff's fixability table instead of mcgyvr's. The
    reproduction above is the one that needs a real run; this is the claim that
    the answer does not stop at one task type.
    """
    from mcgyvr.deterministic import tool_for

    lint_fix = tool_for(load_contract(LINT_FIX))
    import_sort = tool_for(
        load_contract(LINT_FIX.replace("task_type: lint_fix", "task_type: import_sort"))
    )
    formatting = tool_for(load_contract(FORMAT))
    assert lint_fix is not None and import_sort is not None
    assert formatting is not None

    assert 1 in lint_fix.reporting
    assert 1 in import_sort.reporting, (
        "`ruff check --select I --fix` exits 1 whenever an I-rule violation is "
        "unfixable, exactly as the unselected form does"
    )
    assert 1 not in formatting.reporting
    assert all(2 not in tool.reporting for tool in (lint_fix, import_sort, formatting))
