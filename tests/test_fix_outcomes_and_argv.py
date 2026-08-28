"""What a driver reads off an outcome, and what an executor is handed to run.

Four defects that all have the same shape: a value was read the way it was
convenient to read rather than the way the thing that produced it states itself.

**B8, the rest of it.** :func:`~mcgyvr.waves.run_waves` was fixed to read a
stated ``ok`` before falling back to truthiness. Five of mcgyvr's terminal
outcomes state one. Six do not — :class:`~mcgyvr.deliver.Delivery` says
``committed``, :class:`~mcgyvr.pending.Resumed` says ``completed``,
:class:`~mcgyvr.cleanup.Cleanup`, :class:`~mcgyvr.gate.GateResult` and
:class:`~mcgyvr.consensus.Consensus` say ``accepted``,
:class:`~mcgyvr.repair.RepairOutcome` says ``changed`` — and each of them fell
through to truthiness, where every one of them is true. A refused delivery was
reported as a completion.

So the sweep below is over *every* terminal outcome type in the codebase rather
than over the ones a fix happened to be written against, and it asserts both
polarities of each. Sweeping is how the sixth was found: ``Consensus`` was not on
the list this work started from, and it is true for a different reason from the
other five — it defines ``__len__`` as *the number of draws*, so a best-of-three
whose winner the gate rejected is three, and three is true.

A fix that reads six more field names correctly and still guesses "landed" for
the seventh type someone adds has not fixed the defect, it has postponed it —
which is why three of the tests here are about the type nobody has written yet.

**N1, an argv that is not a command.** The floor's step now carries the whole
command line, and appends the contract's target with nothing between it and the
flags. ``ruff format -h.py`` prints help and exits 0 — the file is untouched and
an executor reads the exit code as a formatted file. The gate's own ruff
invocation has always passed ``--``; the planned one did not. Asserted by running
the three programs, because "this argv cannot be read as an option" is a claim
about an argument parser and not about a tuple.

**N5 and N6, one class over.** ``Ascent.__len__`` counts the families that offer
something to *climb* and ``Ascent.__bool__`` counted the plans that hold
*anything*, so an ascent whose only non-empty plan is the program-only floor was
true and empty at once. :class:`~mcgyvr.deterministic.Routed` carries the same
``ToolStep | Step`` union :class:`~mcgyvr.route.Plan` does and gained none of the
properties that tell the two apart.

Nothing here needs a model, a key or a network. The subprocess tests run the
project's own tools on a file in ``tmp_path``.
"""

from __future__ import annotations

import dataclasses
import importlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.cleanup import Cleanup
from mcgyvr.config import Config, parse
from mcgyvr.consensus import Consensus
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deliver import Delivery
from mcgyvr.deterministic import Routed, ToolStep, tool_steps
from mcgyvr.deterministic import route as floor_route
from mcgyvr.escalate import (
    Assurance,
    Delivered,
    Halted,
    Judgement,
    Outcome,
    ascent,
)
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import GateResult
from mcgyvr.pending import Resumed
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.repair import RepairOutcome
from mcgyvr.route import Accepted, Exhausted, Exhaustion, Step, Verdict
from mcgyvr.sandbox.base import CommandResult
from mcgyvr.waves import VERDICTS, run_waves

# A keyless install with one local rung: the cheapest ladder a stranger has.
KEYLESS = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

# The same ladder with its one rung unusable: no key, so no rung, so nothing to
# climb anywhere in the ascent — the shape N5 is about.
UNUSABLE = """
version: 1
sources:
  cloud:
    base_url: https://api.example.invalid
    api: openai
    api_key_env: MCGYVR_NO_SUCH_KEY_FOR_THIS_TEST
    max_parallel: 1
ladder:
  tiers:
    - name: api_big
      source: cloud
      model: big
"""

WORK = """
id: alpha
task_type: docstring
task: Document the alpha helper.
target: src/pkg/fetch.py
stop_conditions:
  - The helper's behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

FORMAT = """
id: tidy
task_type: format
task: Reformat the package.
target: src/pkg/fetch.py
scope:
  allow: ["src/**"]
"""

DETERMINISTIC = catalog().family("deterministic")


def mapped(text: str) -> tuple[Config, SourceMap]:
    return (config := parse(text)), source_map(config)


def work() -> Contract:
    return load_contract(WORK)


def formatting(target: str = "src/pkg/fetch.py", task_type: str = "format") -> Contract:
    """A deterministic contract on ``target``, scoped widely enough to hold it."""
    return load_contract(
        FORMAT.replace("target: src/pkg/fetch.py", f"target: {target}")
        .replace("task_type: format", f"task_type: {task_type}")
        .replace('allow: ["src/**"]', 'allow: ["**"]')
    )


# --- B8: every outcome type mcgyvr can hand a driver -----------------------

FINDING = Finding(
    check="lint", path="src/pkg/fetch.py", line=1, code="E501", message=""
)


def delivered() -> Delivered[str]:
    family = catalog().families[0]
    return Delivered(
        family=family,
        rung="local",
        value="ok",
        assurance=Assurance.DETERMINISTIC,
        judgement=Judgement(
            verdict=Verdict.PASSED, value="ok", assurance=Assurance.DETERMINISTIC
        ),
        entered=(family,),
        history=(),
        attempts_spent=1,
        escalations=0,
    )


def halted() -> Halted:
    return Halted(
        outcome=Outcome.LADDER_SPENT,
        entered=(),
        history=(),
        attempts_spent=3,
        escalations=1,
        detail="the ladder is spent: 3 attempt(s), and none landed.",
    )


def exhausted() -> Exhausted:
    return Exhausted(
        family=catalog().families[0],
        reason=Exhaustion.RUNGS_SPENT,
        history=(),
        detail="every rung in the family was tried and none accepted.",
    )


# Every terminal outcome type in mcgyvr, in both polarities where it has two.
# `Delivered` and `Accepted` have only one: they are the types that exist to say
# a change was accepted, and a false one of either is not a value the codebase
# can produce.
OUTCOMES: tuple[tuple[str, object, bool], ...] = (
    ("escalate.Delivered", delivered(), True),
    ("escalate.Halted", halted(), False),
    (
        "route.Accepted",
        Accepted(family=catalog().families[0], rung="local", value="ok", history=()),
        True,
    ),
    ("route.Exhausted", exhausted(), False),
    (
        "sandbox.CommandResult",
        CommandResult(command=("x",), exit_code=0, stdout="", stderr=""),
        True,
    ),
    (
        "sandbox.CommandResult-failed",
        CommandResult(command=("x",), exit_code=1, stdout="", stderr="boom"),
        False,
    ),
    (
        "deliver.Delivery",
        Delivery(committed=True, commit="abc1234", path="src/pkg/fetch.py"),
        True,
    ),
    (
        "deliver.Delivery-refused",
        Delivery(committed=False, reason="the working tree is dirty"),
        False,
    ),
    ("pending.Resumed", Resumed(completed=True, task="alpha"), True),
    (
        "pending.Resumed-still-pending",
        Resumed(completed=False, task="alpha", reason="the verifier is unreachable"),
        False,
    ),
    ("cleanup.Cleanup", Cleanup(content="x = 1\n", accepted=True, cleaned=True), True),
    (
        "cleanup.Cleanup-rejected",
        Cleanup(
            content="x=1\n",
            accepted=False,
            detail="the findings are not the formatter's",
        ),
        False,
    ),
    ("repair.RepairOutcome", RepairOutcome(repaired=("src/pkg/fetch.py",)), True),
    ("repair.RepairOutcome-unchanged", RepairOutcome(), False),
    ("gate.GateResult", GateResult(), True),
    ("gate.GateResult-rejected", GateResult(findings=(FINDING,)), False),
    (
        "consensus.Consensus",
        Consensus(content="x = 1\n", chosen=0, gates=(GateResult(),)),
        True,
    ),
    (
        "consensus.Consensus-rejected",
        Consensus(content="x=1\n", chosen=0, gates=(GateResult(findings=(FINDING,)),)),
        False,
    ),
)


@pytest.mark.parametrize(
    ("outcome", "landed"),
    [(outcome, landed) for _, outcome, landed in OUTCOMES],
    ids=[name for name, _, _ in OUTCOMES],
)
def test_every_terminal_outcome_is_read_the_way_it_states_itself(
    outcome: object, landed: bool
) -> None:
    """The whole sweep, because the fix that read three of them was called done.

    Each of these is what some binding of ``attempt`` actually returns, and each
    of them is truthy — none defines ``__bool__``, on purpose and by policy. A
    driver that reads the object rather than the verdict reports every one of the
    failures below as work that landed.
    """
    run = run_waves([work()], lambda _: outcome)

    assert (run.completed == ("alpha",)) is landed, (
        f"{type(outcome).__name__} states {landed} and was read as {not landed}: {run}"
    )
    assert run.ok is landed, f"the run's verdict does not match the outcome's: {run}"


def test_a_refused_delivery_names_the_reason_the_delivery_gave() -> None:
    """Not only that it failed: a re-planner told nothing re-emits what failed."""
    refused = Delivery(committed=False, reason="the working tree is dirty")

    run = run_waves([work()], lambda _: refused)

    assert run.failed == (("alpha", "the working tree is dirty"),), (
        f"a refused delivery was not reported with the reason it stated: {run}"
    )


def test_an_outcome_type_nothing_here_can_read_fails_loudly() -> None:
    """The bar this fix is held to: the *next* outcome type, not these six.

    A ``_landed`` that knows five field names is a list that goes stale the day
    someone adds a sixth type — and its stale answer is "landed", which is the
    most expensive wrong answer this module has: the dependants are released into
    the next wave and spend rungs against a tree their input was never written
    into. An outcome this module cannot read is a defect in this module, and it
    has to read as a failure that names itself rather than as a quiet pass.
    """

    @dataclasses.dataclass(frozen=True)
    class Executed:
        """A plausible future outcome, stating its verdict in its own word."""

        succeeded: bool = False
        reason: str = "the program exited 2"

    run = run_waves([work()], lambda _: Executed())

    assert run.completed == (), (
        f"an outcome type this module cannot read was reported as work that "
        f"landed: {run}"
    )
    assert run.failed and "Executed" in run.failed[0][1], (
        f"the failure does not name the type that could not be read: {run.failed}"
    )
    assert "ok" in run.failed[0][1], (
        f"the failure does not say what would make the type readable: "
        f"{run.failed[0][1]}"
    )


def test_an_object_with_no_verdict_and_no_truth_value_is_not_a_completion() -> None:
    """``object()`` is the degenerate case of the same thing, and it is truthy."""
    run = run_waves([work()], lambda _: object())

    assert run.completed == (), f"a bare object was read as work that landed: {run}"


def test_a_truth_value_that_counts_something_else_is_not_a_verdict() -> None:
    """The sixth misread type, found by sweeping rather than by being told.

    :class:`~mcgyvr.consensus.Consensus` defines ``__len__`` — the number of
    draws — and states its verdict in ``accepted``. So it is truthy for the same
    reason the others are, one step removed: not because nobody wrote a truth
    value, but because the one that is written counts draws and a rejected
    best-of-three is three draws. "It defines ``__len__``, so its truthiness was
    meant" is exactly the reasoning that fails here, which is why nothing that is
    not a builtin is read that way.
    """
    rejected = Consensus(
        content="x=1\n", chosen=0, gates=(GateResult(findings=(FINDING,)),)
    )

    assert len(rejected) == 1 and bool(rejected) is True, "the premise did not hold"

    run = run_waves([work()], lambda _: rejected)

    assert run.completed == (), (
        f"a best-of-N whose winner the gate rejected was reported as a "
        f"completion, on the count of its draws: {run}"
    )


def test_a_new_outcome_that_counts_its_own_work_is_not_read_as_landed() -> None:
    """The general case of the ``Consensus`` defect, for the type nobody wrote.

    :class:`~mcgyvr.consensus.Consensus` is the instance of this that already
    exists; this is the shape. An outcome that keeps a tuple of what it did and
    defines ``__len__`` over it is true whenever it did anything at all — and
    "it did several things and all of them were rejected" is the case that
    matters. The wider rule this replaced ("the type declares a truth value, so
    reading it is reading what it meant") accepts every one of these, which is
    the misreading arriving by a different door.
    """

    @dataclasses.dataclass(frozen=True)
    class Drew:
        """A plausible future outcome that counts draws and judges separately."""

        drafts: tuple[str, ...] = ("first", "second")
        approved: bool = False

        def __len__(self) -> int:
            return len(self.drafts)

    assert len(Drew()) == 2 and bool(Drew()) is True, "the premise did not hold"

    run = run_waves([work()], lambda _: Drew())

    assert run.completed == (), (
        f"an outcome true on the count of its own drafts was read as work that "
        f"landed: {run}"
    )
    assert run.failed and "Drew" in run.failed[0][1], (
        f"the failure does not name the type that could not be read: {run.failed}"
    )


def test_the_registry_names_a_field_each_of_those_types_actually_has() -> None:
    """A registry keyed by name can rot; this is what stops it rotting silently.

    Renaming ``Delivery.committed`` would leave the entry naming a field that is
    not there — which now reads as an unreadable outcome and so as a failure,
    the safe direction, but a wrong one. Better to hear about it here than in a
    run where every delivery is suddenly refused.
    """
    for qualified, stated in VERDICTS.items():
        module_name, _, class_name = qualified.rpartition(".")
        cls = getattr(importlib.import_module(module_name), class_name)
        names = {each.name for each in dataclasses.fields(cls)}
        assert stated in names or isinstance(getattr(cls, stated, None), property), (
            f"{qualified} does not state a verdict in {stated!r} any more"
        )


def test_the_sweep_covers_every_type_the_registry_knows_about() -> None:
    """The two lists are one list, and this is what keeps them one.

    A type registered without a case here would be read by nothing but the
    registry's own spelling, which is the assertion that cannot fail.
    """
    swept = {type(outcome).__name__ for _, outcome, _ in OUTCOMES}
    registered = {qualified.rpartition(".")[2] for qualified in VERDICTS}

    assert registered <= swept, (
        f"registered but never driven through run_waves: {registered - swept}"
    )


@pytest.mark.parametrize("outcome", [True, "some value", 1])
def test_a_bare_truth_value_is_still_read_as_one(outcome: object) -> None:
    """The documented fallback, kept: ``attempt`` is an unbound parameter.

    A driver handing back a bare ``bool`` is one this module still serves, and
    refusing what cannot be read must not refuse the values whose truth value
    *is* their verdict.
    """
    assert run_waves([work()], lambda _: outcome).completed == ("alpha",), (
        f"a bare truth value ({outcome!r}) was not read as work that landed"
    )


@pytest.mark.parametrize("outcome", [False, None, "", 0])
def test_a_bare_falsy_value_is_still_a_failure(outcome: object) -> None:
    assert [task for task, _ in run_waves([work()], lambda _: outcome).failed] == [
        "alpha"
    ], f"a falsy outcome ({outcome!r}) was not read as a failure"


def test_a_spent_family_reports_the_prose_and_not_its_own_enum() -> None:
    """``Exhausted.reason`` is a code and ``Exhausted.detail`` is the sentence.

    The re-planner this reaches is a model in the general case, and
    ``rungs_spent`` tells it nothing it can plan differently against. The code is
    machine-readable, which is a virtue in a field and not in a paragraph handed
    to a worker.
    """
    run = run_waves([work()], lambda _: exhausted())

    assert run.failed == (("alpha", exhausted().detail),), (
        f"the family's own prose did not reach the report: {run.failed}"
    )


def test_every_class_the_wave_modules_prose_names_exists() -> None:
    """A docstring that cites a class nobody wrote is a false statement.

    ``waves`` cited ``mcgyvr.route.Passed`` and ``mcgyvr.sandbox.base.Result`` as
    evidence for how outcomes state themselves. Neither has ever existed — they
    are ``route.Accepted`` and ``sandbox.base.CommandResult`` — so the paragraph
    that justified reading ``ok`` rested on two types it could not have read.

    The source is found through the imported module rather than at a path
    relative to the working directory, so this reads the file that is actually
    in use.
    """
    reference = re.compile(r":(?:class|meth|attr|func|mod|data|exc):`~?(mcgyvr[\w.]*)`")
    dangling: list[str] = []

    for module_name in ("waves", "route", "escalate", "deterministic"):
        module = importlib.import_module(f"mcgyvr.{module_name}")
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        for cited in sorted(set(reference.findall(source))):
            if not _resolves(cited):
                dangling.append(f"{module_name}.py cites {cited}")

    assert dangling == [], f"prose naming things that do not exist: {dangling}"


def _resolves(dotted: str) -> bool:
    """Whether ``dotted`` names something importable, module or attribute."""
    parts = dotted.split(".")
    for depth in range(len(parts), 0, -1):
        try:
            found: object = importlib.import_module(".".join(parts[:depth]))
        except ImportError:
            continue
        for attribute in parts[depth:]:
            try:
                found = getattr(found, attribute)
            except AttributeError:
                return False
        return True
    return False


# --- N5: an ascent that says it holds work and offers none -----------------


def test_an_ascent_with_nothing_to_climb_is_falsy() -> None:
    """``bool`` and ``len`` of one object, answering opposite ways.

    The floor holds a program, which is something to run and nothing to climb.
    ``len`` was moved onto that distinction and ``bool`` was left on plan
    truthiness, so a caller guarding with ``if route:`` entered an ascent whose
    ``runnable`` is empty — the same misreading, one level up, that B1 was.
    """
    config, pool = mapped(UNUSABLE)

    route = ascent(config, pool, formatting())

    assert len(route) == 0, "the premise did not hold: something is climbable"
    assert not route, (
        "bool(ascent) is True while len(ascent) is 0: a caller guarding on "
        "truthiness enters an ascent with nothing to climb"
    )


@pytest.mark.parametrize("ladder", [KEYLESS, UNUSABLE])
@pytest.mark.parametrize("task", [WORK, FORMAT])
def test_the_two_questions_an_ascent_is_asked_get_one_answer(
    ladder: str, task: str
) -> None:
    """Whatever the shape, ``bool`` is ``len`` — asked twice, not answered twice."""
    config, pool = mapped(ladder)

    route = ascent(config, pool, load_contract(task))

    assert bool(route) is (len(route) > 0), (
        f"bool={bool(route)} and len={len(route)} for {route.families}"
    )


def test_an_ascent_whose_floor_holds_a_program_still_climbs_the_rung_above() -> None:
    """The other half: falsy must mean *nothing to climb*, not *nothing here*."""
    config, pool = mapped(KEYLESS)

    route = ascent(config, pool, formatting())

    assert bool(route) is True, "a rung above the floor is something to climb"
    assert len(route) == 1
    assert [p.family.name for p in route.runnable] == ["local"]


# --- N6: the same union, one class over ------------------------------------


def test_a_route_that_planned_a_program_tells_a_caller_it_is_one() -> None:
    """``Routed`` carries ``ToolStep | Step`` and had no way to say which.

    Every reader of a :class:`~mcgyvr.route.Plan` gained ``climbable`` and
    ``programs`` when B1 was fixed; a reader of a ``Routed`` was left with
    ``steps`` and truthiness — the exact pair that sent ``escalate`` into a
    family whose only step ``climb`` refuses.
    """
    config, pool = mapped(KEYLESS)

    landed = floor_route(config, pool, formatting(), installed=frozenset({"ruff"}))

    assert landed.family == DETERMINISTIC
    assert landed.climbable == (), "a program was offered to the ladder as a rung"
    assert [step.argv[0] for step in landed.programs] == ["ruff"]
    assert landed.climb_budget == 0, (
        f"a program the ladder never climbs was counted in what it may spend: "
        f"{landed.climb_budget}"
    )
    assert bool(landed) is True, "the floor planned work; the route is not empty"


def test_a_route_that_degraded_onto_a_rung_reports_a_rung() -> None:
    """The complement, so that the properties cannot be constants."""
    config, pool = mapped(KEYLESS)

    landed = floor_route(config, pool, formatting(), installed=frozenset())

    assert landed.programs == (), "nothing was installed, so nothing runs on the floor"
    assert [step.rung.name for step in landed.climbable] == ["local_qwen-7b"]
    assert landed.climb_budget == 1
    assert all(isinstance(step, Step) for step in landed.steps)


# --- N1: an argv that cannot be read as an option --------------------------

DASHED = (
    ("-h.py", "format", ("ruff", "format")),
    ("-h.py", "import_sort", ("ruff", "check", "--select", "I", "--fix")),
    ("--config=pwn.py", "lint_fix", ("ruff", "check", "--fix")),
    ("-h.js", "format", ("prettier", "--write")),
    ("--config=pwn.js", "lint_fix", ("eslint", "--fix")),
)


@pytest.mark.parametrize(("target", "task_type", "command"), DASHED)
def test_the_target_is_separated_from_the_flags(
    target: str, task_type: str, command: tuple[str, ...]
) -> None:
    """Every program in the floor's table takes its path after ``--``.

    A target is a contract's field and a contract is not a trusted document: it
    is what a decomposer emitted, and ``target: -h.py`` is a legal string in one.
    Without the separator it is an option to every one of these three programs.
    """
    (step,) = tool_steps(formatting(target, task_type))

    assert step.argv == (*command, "--", target), (
        f"the target is not separated from the flags: {step.argv}"
    )


def test_an_in_process_step_gains_no_separator_it_has_no_command_for() -> None:
    """``rename_symbol`` runs in mcgyvr's own index: no program, so no argv."""
    (step,) = tool_steps(formatting("-h.py", "rename_symbol"))

    assert step.argv == (), f"a step with no program was given a command: {step.argv}"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="the floor's tool is absent")
def test_a_target_that_reads_as_a_flag_is_formatted_rather_than_obeyed(
    tmp_path: Path,
) -> None:
    """The claim is about an argument parser, so it is asserted against one.

    ``ruff format -h.py`` prints ruff's help, exits **0**, and formats nothing —
    an executor reading the exit code records a completed ``format`` contract
    over a file it never touched. This is the whole defect, run.
    """
    unformatted = 'x = {  "a":1 }\n'
    target = tmp_path / "-h.py"
    target.write_text(unformatted, encoding="utf-8")
    config, pool = mapped(KEYLESS)

    landed = floor_route(
        config, pool, formatting("-h.py"), installed=frozenset({"ruff"})
    )
    (step,) = [s for s in landed.steps if isinstance(s, ToolStep)]
    finished = subprocess.run(
        [shutil.which("ruff") or "ruff", *step.argv[1:]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert "Usage: ruff" not in finished.stdout, (
        "the planned command was read as `ruff format -h`: the step printed "
        "help, exited 0, and formatted nothing"
    )
    assert target.read_text(encoding="utf-8") == 'x = {"a": 1}\n', (
        f"the file the step names was not formatted: {target.read_text()!r}"
    )


@pytest.mark.skipif(
    not Path("node_modules/.bin/prettier").exists(), reason="prettier is not installed"
)
def test_the_javascript_formatter_reads_the_target_as_a_path_too(
    tmp_path: Path,
) -> None:
    """The same argument, in the other toolchain the floor's table binds."""
    target = tmp_path / "-h.js"
    target.write_text("const a =   1\n", encoding="utf-8")

    (step,) = tool_steps(formatting("-h.js"))
    finished = subprocess.run(
        [str(Path("node_modules/.bin/prettier").resolve()), *step.argv[1:]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert target.read_text(encoding="utf-8") == "const a = 1;\n"


def test_the_separator_is_not_confused_for_the_target(tmp_path: Path) -> None:
    """``--`` is the last thing before the path and never the path itself."""
    (step,) = tool_steps(formatting("src/pkg/fetch.py"))

    assert step.argv[-2:] == ("--", "src/pkg/fetch.py")
    assert step.argv.count("--") == 1, f"the separator was doubled: {step.argv}"
    assert Routed(family=DETERMINISTIC, steps=(step,)).programs == (step,)
