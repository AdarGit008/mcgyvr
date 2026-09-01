"""The seam between the deterministic floor and the ladder that climbs past it.

Two defects live here and they are the same seam seen from two sides. X07 bound
the floor by making :func:`~mcgyvr.route.plan` return a
:class:`~mcgyvr.deterministic.ToolStep` for a type a program owns — and then
neither half of what reads a plan was taught what a program is.

*Downward*, :func:`~mcgyvr.escalate.escalate` skips a family on truthiness
(``if not each``), so a floor that used to be empty and skipped is now non-empty
and entered, and :func:`~mcgyvr.route.climb`'s refusal fires as a
:class:`~mcgyvr.route.RouteError` — which is not a ``RunnerError``, so the
mission loop does not catch it and aborts mid-flight with earlier contracts
already committed. Every ``starts_on: deterministic`` contract with a program
bound took that path; the ones that still worked were the ones with **no** tool,
which is the successful path and the failing path swapped over.

*Upward*, the step that was planned carried a program's *name* and nothing else
— no target, and one name (``ruff``) shared by three task types whose
invocations differ. A caller willing to run it could not have worked out what to
run, so "the floor is bound" was true of the plan and false of anything
downstream of it.

The two are tested together because fixing either alone leaves the seam broken
in the other direction, and because the budget defect only becomes observable
once the first is fixed: a program the ladder never climbs must not be counted
among the attempts the ladder may spend.

Nothing here needs a model. The one test that runs a program runs the
project's own ``ruff``, on a file in ``tmp_path``, because "this step is
executable" is a claim only an execution can hold.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deterministic import ToolStep, tool_steps
from mcgyvr.deterministic import route as floor_route
from mcgyvr.escalate import Assurance, Delivered, Judgement, ascent, escalate
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import Result, RouteError, Step, Try, Verdict, climb, plan

# A keyless install: one local rung above the floor, no credential anywhere.
# The cheapest ladder a stranger can have, and the one a deterministic tool is
# worth most on — every attempt it saves is an attempt a model would have made.
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

# A deterministic contract *with a program bound* — the path B1 broke. A `.py`
# target makes the gate's Python adapter own it, which binds `ruff`.
FORMAT = """
id: tidy
task_type: format
task: Reformat the package.
target: src/pkg/fetch.py
scope:
  allow: ["src/**"]
"""

IMPORT_SORT = FORMAT.replace("task_type: format", "task_type: import_sort").replace(
    "id: tidy", "id: tidy-imports"
)

LINT_FIX = FORMAT.replace("task_type: format", "task_type: lint_fix").replace(
    "id: tidy", "id: tidy-lint"
)

DETERMINISTIC = catalog().family("deterministic")
LOCAL = catalog().family("local")


def mapped(text: str = KEYLESS) -> tuple[Config, SourceMap]:
    config = parse(text)
    return config, source_map(config)


def contract(text: str = FORMAT) -> Contract:
    return load_contract(text)


def passes(this: Try) -> Judgement:
    """An attempt function that accepts on whatever rung it is handed.

    The verdict is the whole of what these tests need from an attempt: they are
    about which steps are offered and which are refused, never about what an
    attempt does with one. The rung and attempt number are stated in ``detail``
    so a failure report names where the climb actually landed.
    """
    return Judgement(
        verdict=Verdict.PASSED,
        detail=f"{this.rung.name}#{this.attempt}",
        assurance=Assurance.UNVERIFIED,
    )


def never_asked(this: Try) -> Result:
    """An attempt function that must never be reached.

    `climb` refuses a program before it funds anything, so an attempt made at
    all is the refusal having been skipped — which a counter of zero would not
    tell apart from a refusal that fired for the wrong reason.
    """
    raise AssertionError(f"a program plan was climbed onto {this.rung.name!r}")


def steps_of(made: object) -> tuple[ToolStep, ...]:
    """The program steps of a plan, which is what these tests are about."""
    return tuple(
        step for step in getattr(made, "steps", ()) if isinstance(step, ToolStep)
    )


# --- B1: a floor bound to a program must not abort the climb ---------------


def test_a_deterministic_contract_with_a_tool_bound_climbs_instead_of_raising() -> None:
    """The live regression: the port made the successful path the failing one.

    On `main` this contract planned an empty deterministic family, escalate
    stepped over it, and the work was delivered by the local rung. Since the
    floor was bound the plan is non-empty, `escalate`'s truthiness guard enters
    it, and `climb` refuses a program with a `RouteError` — which is not a
    `RunnerError`, so the mission loop does not catch it and the whole run ends
    after earlier contracts have already been committed.
    """
    config, pool = mapped()

    outcome = escalate(config, pool, contract(), passes)

    assert isinstance(outcome, Delivered), (
        f"a deterministic contract with a program bound did not reach a rung: {outcome}"
    )
    assert outcome.family == LOCAL
    assert outcome.rung == "local_qwen-7b"


def test_the_floor_is_not_reported_as_a_family_the_task_entered() -> None:
    """Skipping is not entering. A family whose step nothing climbed was not
    tried, and a record that said it was would make the ladder look busier
    than it is."""
    config, pool = mapped()

    outcome = escalate(config, pool, contract(), passes)

    assert DETERMINISTIC not in outcome.entered
    assert [f.name for f in outcome.entered] == ["local"]


def test_a_family_whose_only_step_is_a_program_is_not_runnable() -> None:
    """`Ascent.runnable` answers "which families offer something to climb".

    A program is something to *run* and nothing to *climb*, so a floor holding
    one must not be counted among the families the ladder can walk — that count
    is what a caller reads to decide there is work the ladder can do.
    """
    config, pool = mapped()

    route = ascent(config, pool, contract())

    assert [p.family.name for p in route.plans] == ["deterministic", "local", "api"]
    assert [p.family.name for p in route.runnable] == ["local"]
    assert len(route) == 1


def test_the_floors_program_is_not_counted_in_the_ladders_attempt_budget() -> None:
    """The latent defect B1's fix makes live.

    `Ascent.ladder_budget` is "the most attempts the configured rungs could
    spend between them", and it is what bounds the climb when no
    `budgets.max_attempts` is set. A program is not a configured rung and is
    never climbed, so counting its single attempt hands the climb one attempt
    of headroom the ladder does not have — the ceiling would stop one attempt
    later than the operator's ladder says it should.
    """
    config, pool = mapped()

    route = ascent(config, pool, contract())

    assert route.ladder_budget == 1, (
        f"the ladder offers one rung at one attempt, so its budget is 1; "
        f"{route.ladder_budget} counts the floor's program as an attempt the "
        f"ladder could spend"
    )
    assert route.budget == 1  # no independent ceiling is set, so the ladder's own


def test_climbing_a_plan_that_is_a_program_is_still_a_named_refusal() -> None:
    """The refusal stays — it is only `escalate` that must stop reaching it.

    A caller that hands a floor plan to `climb` has made a routing mistake, and
    silently skipping the step would report a family as tried when nothing ran.
    This passed before the fix too; it is here so the fix cannot be made by
    deleting the refusal.
    """
    config, pool = mapped()
    made = plan(config, pool, contract())

    with pytest.raises(RouteError) as excinfo:
        climb(made, never_asked)

    assert "program, not a rung" in str(excinfo.value)


# --- B2: the planned step must carry what an executor needs ----------------


def test_a_planned_step_names_the_whole_command_that_would_run_it() -> None:
    """A step that does not determine its own command cannot be executed.

    The step used to carry a program's name and the number of attempts. Neither
    says *what to run on what*: the target is the contract's and never reached
    the step, and the invocation is not the program name — `ruff` alone is not a
    command. So a caller holding this step had to re-derive both from the
    contract, which is the second table :mod:`mcgyvr.deterministic` exists to
    avoid.

    The `--` is the rest of the same claim and was missing until the pressure
    test tried a target beginning with a dash: a command whose last argument can
    be read as an option is a command that runs something else. It is asserted
    against the three programs, by execution, in
    ``tests/test_fix_outcomes_and_argv.py``.
    """
    config, pool = mapped()

    (step,) = steps_of(plan(config, pool, contract()))

    assert step.tool.program == "ruff"
    assert step.target == "src/pkg/fetch.py"
    assert step.argv == ("ruff", "format", "--", "src/pkg/fetch.py")


def test_three_types_share_one_program_and_are_three_different_commands() -> None:
    """`ruff` owns three of the four deterministic types, and does three things.

    The program name is the same for all three, so a step carrying only the
    name is the same step three times over — and running any one of those
    invocations for another's contract would produce a change the catalog's
    guarantee for that type does not describe.
    """
    typed = [contract(text) for text in (FORMAT, IMPORT_SORT, LINT_FIX)]
    commands = {each.task_type: tool_steps(each)[0].argv for each in typed}

    assert commands == {
        "format": ("ruff", "format", "--", "src/pkg/fetch.py"),
        "import_sort": (
            "ruff",
            "check",
            "--select",
            "I",
            "--fix",
            "--",
            "src/pkg/fetch.py",
        ),
        "lint_fix": ("ruff", "check", "--fix", "--", "src/pkg/fetch.py"),
    }
    assert len(set(commands.values())) == 3


def test_an_in_process_tool_has_no_command_rather_than_a_made_up_one() -> None:
    """`rename_symbol` is executed by mcgyvr's own index, not by a program.

    Its step must not carry an invented argv: there is no program to run, and a
    command line that named one would send a caller to a process that cannot
    exist. An empty command is the honest answer and is distinguishable from a
    program's.
    """
    renaming = contract(
        FORMAT.replace("task_type: format", "task_type: rename_symbol").replace(
            "id: tidy", "id: rename"
        )
    )

    (step,) = tool_steps(renaming)

    assert step.tool.program is None
    assert step.tool.command == ()
    assert step.argv == ()


# --- the two fixes composed ------------------------------------------------


@pytest.mark.skipif(shutil.which("ruff") is None, reason="the floor's tool is absent")
def test_the_step_the_floor_plans_actually_formats_the_target_when_run(
    tmp_path: Path,
) -> None:
    """The claim "this step is executable" is one only an execution can hold.

    The plan is built from the config and the contract with no knowledge of this
    directory, the step's own argv is handed to a subprocess unchanged, and the
    file it names comes back formatted. Nothing here re-derives a command from
    the task type, which is the whole point: what was planned is what ran.
    """
    config, pool = mapped()
    target = tmp_path / "src" / "pkg" / "fetch.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = {  'a':1 }\n", encoding="utf-8")

    landed = floor_route(config, pool, contract(), installed=frozenset({"ruff"}))
    (step,) = steps_of(landed)
    finished = subprocess.run(step.argv, cwd=tmp_path, capture_output=True, check=False)

    assert landed.family == DETERMINISTIC, "the floor was not honoured"
    assert finished.returncode == 0, finished.stderr.decode()
    assert target.read_text(encoding="utf-8") == 'x = {"a": 1}\n'


def test_without_the_tool_the_work_degrades_to_a_rung_and_is_delivered_there(
    tmp_path: Path,
) -> None:
    """The other half of the same contract's story, end to end.

    A machine with no `ruff` still gets its file formatted, dearly: the floor
    degrades onto the local rung with the cost recorded, and the same contract
    driven through `escalate` is delivered by that rung rather than aborting the
    run. Both halves are asserted because a degradation that named a family the
    climb cannot reach would read as a fallback and behave as a halt.
    """
    config, pool = mapped()

    landed = floor_route(config, pool, contract(), installed=frozenset())
    outcome = escalate(config, pool, contract(), passes)

    assert landed.family == LOCAL
    assert [d.landed for d in landed.degradations] == ["local"]
    assert "ruff is not installed" in str(landed.degradations[0])
    (step,) = landed.steps
    assert isinstance(step, Step), "the work degraded onto something with no rung"
    assert isinstance(outcome, Delivered)
    assert outcome.family == landed.family
    assert outcome.rung == step.rung.name
