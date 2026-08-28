"""D02 — a decomposition is a plan, and a plan that nothing runs is a list.

``decompose`` emits contracts and stops. Nothing orders them, nothing notices that
one of them needs another to have happened first, and nothing decides what to do when
one fails — ``propose`` is an unbound parameter and there is no driver behind it. So
today a multi-step change is handed to the operator as a pile of YAML whose only
ordering is the one the proposer happened to emit, and the first contract to fail
takes its dependants down with it silently, by writing against a file the step before
it never created.

Three statements, and they are the three decisions a driver makes.

*Order.* Asserted with the contracts handed in **reverse** of their dependency order,
because a driver that simply iterates its input satisfies any test whose fixture is
already sorted — and a proposer's emission order is not a topological sort, it is the
order a model thought of things. The dependency has to be read from the contract for
the run to be right.

*Refusal.* A contract whose dependency failed is not run at all, and this is asserted
on the dependant never having been attempted rather than on it having failed. The
distinction is spend: attempting it burns a rung's worth of tokens to produce a
guaranteed rejection against a tree that is missing the thing it was told to use, and
the rejection then looks like a worker failure in every record downstream.

*Re-planning.* After a wave with failures, what runs next must be informed by them.
Asserted two ways, because either alone is passed by the wrong thing: the failed
contract's id and the reason it failed must reach the re-planner — otherwise it
re-plans blind and re-emits the step that just failed — and the identical contract
must not be attempted a second time in the next wave, which is what a retry loop
dressed as a wave loop would do. What the re-planner is handed is inspected as
whatever it received, not as a prescribed signature: the requirement is that the
failure is named to it, not how.

Where a contract states its dependency is the port's to decide — the schema has no
field for it today, which is why that resolution is a RED failure of its own with its
own sentence. What must not drift is that the statement lives on the contract, so a
plan can be ordered before a token is spent, the way ``route.plan()`` already is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.red_port.conftest import required

DRIVER = "run a set of contracts in dependency order and re-plan the work that failed"
DECLARE = "record in a contract which other contracts must complete before it runs"

CONTRACT = """
id: {id}
task_type: docstring
task: Document the {id} helper.
target: src/pkg/fetch.py
stop_conditions:
  - The helper's behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

REASON = "acceptance command exited 1: two checks failed"

# The field a contract states its dependency in. A placeholder like every other
# name here — what matters is that the statement is on the contract.
DEPENDS_ON = "depends_on"


@dataclass
class Outcome:
    """What an attempt reports back — spelled several ways, since the driver is "
    "unwritten."""

    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok

    @property
    def completed(self) -> bool:
        return self.ok

    @property
    def accepted(self) -> bool:
        return self.ok


@dataclass
class Run:
    """A recording attempt function: which contracts were run, in which order."""

    verdicts: dict[str, bool] = field(default_factory=dict)
    attempted: list[str] = field(default_factory=list)

    def __call__(self, *args: Any, **kwargs: Any) -> Outcome:
        contract = next(a for a in (*args, *kwargs.values()) if hasattr(a, "id"))
        self.attempted.append(contract.id)
        ok = self.verdicts.get(contract.id, True)
        return Outcome(ok, "" if ok else REASON)


def _driver() -> Any:
    return required(
        DRIVER, lambda: __import__("mcgyvr.waves", fromlist=["run_waves"]).run_waves
    )


def _declaring(task_id: str, depends_on: tuple[str, ...] = ()) -> Any:
    """A contract that says, on its own face, which contracts must finish before it."""

    def build() -> Any:
        from mcgyvr.contract import ContractError, loads

        text = CONTRACT.format(id=task_id)
        if depends_on:
            text += f"{DEPENDS_ON}:\n" + "".join(f"  - {dep}\n" for dep in depends_on)
        try:
            made = loads(text)
        except ContractError as refused:
            raise AttributeError(
                f"a contract cannot state a dependency: {refused}"
            ) from refused
        declared = tuple(getattr(made, DEPENDS_ON))
        if declared != depends_on:
            raise AttributeError(f"declared {depends_on} and carried {declared}")
        return made

    return required(DECLARE, build)


def test_a_contract_runs_after_the_one_it_depends_on() -> None:
    """Handed in the wrong order, run in the right one.

    Reversed on purpose: with the contracts already sorted, a driver that ignored
    ``depends_on`` entirely would pass this test and fail the first real plan.
    """
    first = _declaring("write-fetch")
    second = _declaring("document-fetch", depends_on=("write-fetch",))
    run = Run()

    _driver()(contracts=(second, first), attempt=run)

    assert run.attempted == ["write-fetch", "document-fetch"], (
        f"contracts ran in {run.attempted}, not in the order their dependencies require"
    )


def test_a_contract_whose_dependency_failed_is_never_attempted() -> None:
    """Not attempted-and-failed: not attempted.

    Its input does not exist, so the attempt can only produce a rejection — one that
    costs a rung's tokens and then reads, everywhere downstream, as the worker's
    fault rather than as the plan's.
    """
    blocker = _declaring("write-fetch")
    dependant = _declaring("document-fetch", depends_on=("write-fetch",))
    run = Run(verdicts={"write-fetch": False})

    _driver()(contracts=(blocker, dependant), attempt=run)

    assert "document-fetch" not in run.attempted, (
        "a contract was run although the work it depends on never landed: "
        f"{run.attempted}"
    )
    assert run.attempted == ["write-fetch"], f"unexpected work was run: {run.attempted}"


def test_a_failed_wave_is_re_planned_with_the_failures_named() -> None:
    """The next wave is informed by the last one, and is not the last one again.

    The re-planner is handed whatever the driver hands it and this test reads all of
    it: the requirement is that the failed contract and the reason it failed are in
    there. Then the plan it returns is what runs — the failed contract itself is
    asserted not to come round a second time, which is the difference between
    re-planning and retrying.
    """
    failing = _declaring("write-fetch")
    passing = _declaring("document-host")
    replanned = _declaring("write-fetch-simpler")
    run = Run(verdicts={"write-fetch": False})
    handed: list[str] = []

    def replan(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        handed.append(repr((args, kwargs)))
        return (replanned,)

    _driver()(contracts=(failing, passing), attempt=run, replan=replan, max_waves=2)

    assert handed, "a wave failed and nothing was re-planned"
    said = handed[0]
    assert "write-fetch" in said, (
        f"the re-planner was not told which contract failed: {said}"
    )
    assert REASON in said, f"the re-planner was not told why it failed: {said}"
    assert "write-fetch-simpler" in run.attempted, "the re-planned work was never run"
    assert run.attempted.count("write-fetch") == 1, (
        f"the failed contract was retried unchanged rather than re-planned: "
        f"{run.attempted}"
    )
