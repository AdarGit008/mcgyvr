"""What an executor is handed to run, and what an ascent says it offers.

Four defects that all have the same shape: a value was read the way it was
convenient to read rather than the way the thing that produced it states itself.

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

import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deterministic import Routed, ToolStep, tool_steps
from mcgyvr.deterministic import route as floor_route
from mcgyvr.escalate import ascent
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import Step

# A keyless install with one local rung: the cheapest ladder a stranger has.
KEYLESS = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
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
