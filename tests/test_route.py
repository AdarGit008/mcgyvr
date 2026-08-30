"""#24's acceptance is three statements, and two of them are about what routing
refuses to do.

*Family exhaustion is distinguishable from every other failure* is held by
:class:`~mcgyvr.route.Exhausted` being its own type carrying an
:class:`~mcgyvr.route.Exhaustion` reason, and by the three reasons being reached
independently — a family whose attempts were spent, one whose rungs all declined
without spending any, and one with no rung at all are three different facts
about an install and are asserted as three.

*No path crosses families inside this component* is the one a test can only hold
negatively, so it is held twice: once behaviourally, by climbing a ladder that
has rungs in a dearer family and asserting they are never tried however the
climb ends, and once structurally, by asserting a plan's steps are all of the
plan's own family for every family the catalog declares.

*Attempt budgets are policy in config, not constants in code* is held by driving
one contract against two configs that differ only in a rung's ``attempts`` and
asserting the number of attempts changes with it — a test that asserted the
default of 1 alone would pass just as well against a hard-coded 1.

*Fan-out chooses where a climb starts and never reorders the ladder* is the
fourth statement, added with ``ladder.fanout``, and it is held from all three
sides: a full cheapest rung is still taken under ``none``, the free peer is
taken under ``full``, the cheapest rung with a slot to spare is taken under
``idle``, an idle ladder gives the same rung under every mode, and a plan's
order is asserted to be price order whatever the mode and whatever is busy.

``idle`` and ``full`` are held apart rather than assumed different, because the
two agree on every ladder of equal widths and a suite that only ever ran one of
those would let either rule stand in for the other. The case that separates
them is a cheap narrow rung beside a dear wide one: ``idle`` takes the first
rung that will admit work and ``full`` takes the roomiest, so they name
different rungs there and the same rung everywhere else. What crosses *families*
under ``idle`` is not this module's — :func:`mcgyvr.escalate.escalate` chooses
which family a climb enters — so the ladders here are single-family and the
assertions are about which rung of one plan a climb starts on.

Two of those need machines of *different widths* to be worth anything. "Busy"
means no free slot and not merely fewer jobs — a four-wide rig running two
dispatches can take this contract and a single-slot rig running one cannot — so
the ladders here declare unequal ``max_parallel`` and the tests fill slots
rather than counting them. And the walk from the start rung is upward only: a
rung skipped for being full is not returned to when a dearer one fails, because
that is answering a failure with a weaker model.

Load is made real with :meth:`~mcgyvr.capacity.Capacity.hold` rather than with a
stub, because the number under test is the one a real dispatch moves; filling
more than one slot of a source takes more than one thread, which is what
:func:`occupied` is for.

Nothing here dispatches. The attempt function is a recorder, which is the whole
reason :func:`~mcgyvr.route.climb` takes one: every rule in the module is about
sequencing and budgets, and a test that needed a model to check a budget would
be testing the model.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.catalog import catalog
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV, Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deterministic import ToolStep
from mcgyvr.pool import Endpoint, Rung, SourceMap, source_map
from mcgyvr.route import (
    Accepted,
    Attempted,
    Exhausted,
    Exhaustion,
    Fanout,
    Plan,
    Result,
    RouteError,
    Step,
    Try,
    Verdict,
    attempts_for,
    by_family,
    climb,
    family_of,
    plan,
)

MIXED = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
  spare:
    base_url: http://192.168.1.20:8000
    api: openai
    max_parallel: 1
  vendor:
    base_url: https://api.example.com/v1
    api: openai
    max_parallel: 4
    api_key_env: EXAMPLE_API_KEY
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
    - name: local_qwen-14b
      source: spare
      model: qwen2.5-coder:14b
    - name: api_big
      source: vendor
      model: vendor-large
"""

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

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

SHARED = """
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
    - name: local_qwen-14b
      source: workstation
      model: qwen2.5-coder:14b
"""

WIDTHS = """
version: 1
sources:
  wide:
    base_url: http://wide.example.net:11434
    api: ollama
    max_parallel: 4
  narrow:
    base_url: http://narrow.example.net:11434
    api: ollama
    max_parallel: 1
ladder:
  tiers:
    - name: local_wide
      source: wide
      model: qwen3-coder:30b
    - name: local_narrow
      source: narrow
      model: qwen3-coder:30b
"""

# Three rungs of three different widths, which is the only arrangement on which
# the three fan-out modes can give three different answers. Fill the cheapest
# rung's single slot and ``none`` still takes it, ``idle`` takes the next
# cheapest — the first that will admit work — and ``full`` takes the roomiest,
# which is the dearest rung on this ladder. On any ladder of equal widths
# ``idle`` and ``full`` agree everywhere, so a suite without this shape would
# let either rule stand in for the other.
UNEVEN = """
version: 1
sources:
  small:
    base_url: http://small.example.net:11434
    api: ollama
    max_parallel: 1
  medium:
    base_url: http://medium.example.net:11434
    api: ollama
    max_parallel: 1
  large:
    base_url: http://large.example.net:11434
    api: ollama
    max_parallel: 4
ladder:
  tiers:
    - name: local_7b
      source: small
      model: qwen2.5-coder:7b
    - name: local_14b
      source: medium
      model: qwen2.5-coder:14b
    - name: local_32b
      source: large
      model: qwen2.5-coder:32b
"""

TRIPLE = """
version: 1
sources:
  small:
    base_url: http://small.example.net:11434
    api: ollama
    max_parallel: 2
  medium:
    base_url: http://medium.example.net:11434
    api: ollama
    max_parallel: 2
  large:
    base_url: http://large.example.net:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_7b
      source: small
      model: qwen2.5-coder:7b
    - name: local_14b
      source: medium
      model: qwen2.5-coder:14b
    - name: local_32b
      source: large
      model: qwen2.5-coder:32b
"""

DETERMINISTIC_CONTRACT = """
id: tidy
task_type: format
task: Reformat the package.
target: src/pkg/fetch.py
scope:
  allow: ["src/**"]
"""

# A deterministic type whose floor binds no program: ADR-0025 holds eslint at
# `recommended`, which has no import-order rule, so nothing sorts imports in
# js/ts. This is the contract that still reaches the empty-plan path now that
# the floor binds tools for the types that have them.
UNBOUND_DETERMINISTIC_CONTRACT = """
id: tidy-imports
task_type: import_sort
task: Sort the imports.
target: src/pkg/fetch.ts
scope:
  allow: ["src/**"]
"""

# How long a slot-holding thread waits to be let go. Nothing asserts on it: it
# only decides how long a broken implementation takes to say so.
HOLD_TIMEOUT_S = 5.0

LOCAL = catalog().family("local")
API = catalog().family("api")
DETERMINISTIC = catalog().family("deterministic")


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential for the api source, assembled rather than written literally."""
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


@pytest.fixture
def lock_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Slot files are host-wide by design (#185); tests must not share them."""
    monkeypatch.setattr(
        "mcgyvr.capacity._default_lock_dir", lambda: tmp_path / "capacity-locks"
    )


def mapped(text: str) -> tuple[Config, SourceMap]:
    config = parse(text)
    return config, source_map(config)


def with_fanout(text: str, mode: str) -> str:
    """The same config with ``ladder.fanout`` set, and nothing else moved.

    One substituted line, so that no assertion about a mode can be quietly
    explained by a config that also drifted somewhere else.
    """
    return text.replace("ladder:\n", f"ladder:\n  fanout: {mode}\n")


def with_attempts(text: str, rung: str, attempts: int) -> str:
    """The same config with one rung's attempts policy set."""
    lines: list[str] = []
    for line in text.splitlines():
        lines.append(line)
        if line.strip() == f"- name: {rung}":
            lines.append(f"      attempts: {attempts}")
    return "\n".join(lines)


def contract(text: str = CONTRACT) -> Contract:
    return load_contract(text)


class Recorder:
    """An attempt function that answers from a script and records what it saw.

    The script is consumed one verdict per call, and running past its end is
    itself a failure: a climb that tried more rungs than the test scripted has
    broken the budget the test is about, and a silent default would hide it.

    A passing verdict carries a marker naming the rung and the attempt number
    that produced it. It travels as the result's ``detail``, which
    :func:`~mcgyvr.route.climb` copies into the :class:`~mcgyvr.route.Attempted`
    row it appends — so a test can still say *which* attempt on *which* rung the
    accepted climb came from, which is the only reason the marker exists. It
    used to ride on a ``Result.value``; that channel is gone, because content
    that travels beside a verdict without being bound to it is how un-gated
    bytes reach a repository.
    """

    def __init__(self, *verdicts: Verdict) -> None:
        self._verdicts = list(verdicts)
        self.seen: list[Try] = []

    def __call__(self, attempt: Try) -> Result:
        self.seen.append(attempt)
        if not self._verdicts:
            raise AssertionError(
                f"climb made an unscripted attempt on {attempt.rung.name!r}"
            )
        verdict = self._verdicts.pop(0)
        if verdict is Verdict.PASSED:
            return Result.passed(f"{attempt.rung.name}#{attempt.attempt}")
        if verdict is Verdict.DECLINED:
            return Result.declined("not work this rung does")
        return Result.failed("the gate rejected it")

    @property
    def rungs(self) -> list[str]:
        return [t.rung.name for t in self.seen]


class DownProbe:
    """A :class:`~mcgyvr.pool.SourceProbe` that says the named sources are down.

    The structural type is the whole of #22's surface as the pool sees it, so a
    test can supply one without a network — which is what lets "skipped because
    unreachable" be told apart from "skipped because unconfigured" here.
    """

    def __init__(self, down: set[str]) -> None:
        self._down = down

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        return {
            e.source: f"{e.source} did not answer"
            for e in endpoints
            if e.source in self._down
        }


@contextmanager
def occupied(capacity: Capacity, pool: SourceMap, *rungs: str) -> Iterator[None]:
    """Hold one slot of each rung named, for the body of the block.

    A rung named twice has two of its slots held, which is the only way a
    *width* can be made to matter: the arrangement worth testing is a wide rig
    carrying work and still able to take more, beside a narrow rig carrying
    less and unable to take any. One thread per slot rather than a nested stack
    on this one, because :meth:`~mcgyvr.capacity.Capacity.hold` refuses a thread
    that already holds the source — a caller queueing against itself is a
    deadlock it names rather than performs.
    """
    held = threading.Semaphore(0)
    release = threading.Event()

    def occupy(rung: str) -> None:
        with capacity.hold(pool.bind(rung)):
            held.release()
            release.wait(HOLD_TIMEOUT_S)

    threads = [threading.Thread(target=occupy, args=(rung,)) for rung in rungs]
    for thread in threads:
        thread.start()
    try:
        for _ in rungs:
            assert held.acquire(timeout=HOLD_TIMEOUT_S), "a slot never filled"
        yield
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=HOLD_TIMEOUT_S)


def accepted(result: Accepted | Exhausted) -> Accepted:
    assert isinstance(result, Accepted), f"expected an accepted climb, got {result}"
    return result


def exhausted(result: Accepted | Exhausted) -> Exhausted:
    assert isinstance(result, Exhausted), f"expected an exhausted family, got {result}"
    return result


# --- the family view of a ladder ------------------------------------------


def test_a_rung_is_api_exactly_when_its_source_needs_a_credential() -> None:
    config, _ = mapped(MIXED)

    assert family_of(config, "local_qwen-7b") == LOCAL
    assert family_of(config, "local_qwen-14b") == LOCAL
    assert family_of(config, "api_big") == API


def test_the_family_rule_is_the_catalogs_and_is_not_restated_here() -> None:
    """The rule lives in one place; this asserts routing asks rather than knows.

    A second copy of "api when it declares a key" would be the kind of drift
    that only shows up when one of the two is edited, so the check is that the
    catalog's own answer and routing's agree for every rung of a config.
    """
    config, _ = mapped(MIXED)
    known = catalog()

    for tier in config.ladder.tiers:
        assert family_of(config, tier.name) == known.family_of(
            config.sources[tier.source]
        )


def test_an_unknown_rung_is_a_bug_and_says_what_the_ladder_offers() -> None:
    config, _ = mapped(KEYLESS)

    with pytest.raises(RouteError) as excinfo:
        family_of(config, "local_qwen-70b")

    assert "local_qwen-7b" in str(excinfo.value)


def test_every_declared_family_is_a_key_even_with_no_rungs(key: None) -> None:
    """An empty family is an answer, not an absence."""
    config, pool = mapped(MIXED)

    grouped = by_family(config, pool)

    assert [f.name for f in grouped] == ["deterministic", "local", "api"]
    assert grouped[DETERMINISTIC] == ()
    assert [r.name for r in grouped[LOCAL]] == ["local_qwen-7b", "local_qwen-14b"]
    assert [r.name for r in grouped[API]] == ["api_big"]


def test_a_keyless_install_has_an_empty_api_family() -> None:
    config, pool = mapped(KEYLESS)

    grouped = by_family(config, pool)

    assert grouped[API] == ()
    assert len(grouped[LOCAL]) == 1


def test_a_rung_whose_source_is_unusable_is_not_routed_to() -> None:
    """The api rung is configured here, but $EXAMPLE_API_KEY is unset.

    The pool has already decided it cannot be offered and recorded why. Routing
    must not reach for it anyway: the reason it was skipped is exactly the
    reason a dispatch to it would fail.
    """
    config, pool = mapped(MIXED)

    assert [s.name for s in pool.skipped] == ["api_big"]
    assert by_family(config, pool)[API] == ()


# --- budgets are policy ----------------------------------------------------


def test_the_rungs_configured_attempts_is_what_gets_spent() -> None:
    """Two configs differing only in one number produce two different climbs."""
    once, once_pool = mapped(KEYLESS)
    twice, twice_pool = mapped(with_attempts(KEYLESS, "local_qwen-7b", 2))

    one = exhausted(climb(plan(once, once_pool, contract()), Recorder(Verdict.FAILED)))
    two = exhausted(
        climb(
            plan(twice, twice_pool, contract()),
            Recorder(Verdict.FAILED, Verdict.FAILED),
        )
    )

    assert one.attempts_spent == 1
    assert two.attempts_spent == 2


def test_the_default_is_to_escalate_rather_than_retry(key: None) -> None:
    """Unset, a rung gets one attempt — the whole of the escalate-not-retry rule."""
    config, pool = mapped(MIXED)

    steps = plan(config, pool, contract()).steps

    assert [step.attempts for step in steps] == [1, 1]


def test_a_contract_may_lower_a_rungs_budget_and_so_may_the_config() -> None:
    """The lower of the two applies, whichever one it is."""
    generous, generous_pool = mapped(with_attempts(KEYLESS, "local_qwen-7b", 4))
    strict, strict_pool = mapped(KEYLESS)

    capped = contract(CONTRACT.replace("attempts: 5", "attempts: 2"))
    uncapped = contract()

    assert plan(generous, generous_pool, capped).steps[0].attempts == 2
    assert plan(generous, generous_pool, uncapped).steps[0].attempts == 4
    assert plan(strict, strict_pool, uncapped).steps[0].attempts == 1


def test_the_deterministic_family_gets_exactly_one_attempt_whatever_is_asked() -> None:
    """A tool fails identically on retry, so no policy may buy a second go."""
    generous = contract(CONTRACT.replace("attempts: 5", "attempts: 9"))

    assert attempts_for(DETERMINISTIC, 7, generous) == 1
    assert attempts_for(LOCAL, 7, generous) == 7
    assert attempts_for(API, 7, generous) == 7


# --- planning --------------------------------------------------------------


def test_a_plan_is_the_contracts_floor_family_cheapest_rung_first(key: None) -> None:
    config, pool = mapped(MIXED)

    made = plan(config, pool, contract())

    assert made.family == LOCAL  # function_implementation starts on local
    assert made.rungs == ("local_qwen-7b", "local_qwen-14b")
    assert made.budget == 2


def test_a_plan_never_contains_a_rung_of_another_family(key: None) -> None:
    """The structural half of "no path crosses families", over every family."""
    config, pool = mapped(MIXED)

    for family in catalog().families:
        made = plan(config, pool, contract(), family=family)
        assert made.family == family
        for step in made.steps:
            # A deterministic step is a program and carries no rung, so it has no
            # family to cross; `Plan.rungs` is the property that already draws
            # that line, and reading it here keeps this test about rungs.
            assert isinstance(step, Step)
            assert family_of(config, step.rung.name) == family


def test_the_deterministic_family_plans_the_tool_that_does_the_work() -> None:
    """The floor binds a program, so a `format` contract plans one.

    This test used to assert the opposite — that the family planned nothing and
    said so structurally — and it was an accurate description of a hole. X07
    measured the hole rather than reading the comment: 4 of 4 deterministic task
    types planned nothing to run on their own floor, so every one of them was a
    model call for work `ruff` does for free. The reason string it asserted is
    still reachable, and the test below is what reaches it.
    """
    config, pool = mapped(KEYLESS)

    made = plan(config, pool, contract(DETERMINISTIC_CONTRACT))

    assert made.family == DETERMINISTIC
    assert made
    assert made.rungs == (), "a program has no rung, and none should be invented"
    assert [step.tool.program for step in made.steps if isinstance(step, ToolStep)] == [
        "ruff"
    ]


def test_a_deterministic_type_with_no_program_for_its_target_still_says_why() -> None:
    """The structural reason survives, narrowed to the case that now reaches it.

    ADR-0025 holds eslint at `recommended`, which has no import-order rule, so
    there is no js/ts import sorter to bind. That is a missing *program for a
    type*, not a missing source for a rung, and the words have to send an
    operator to the right file.
    """
    config, pool = mapped(KEYLESS)

    made = plan(config, pool, contract(UNBOUND_DETERMINISTIC_CONTRACT))

    assert made.family == DETERMINISTIC
    assert not made
    assert "tools, not a model on a source" in made.reason
    assert "no tool is bound" in made.reason


def test_an_empty_family_with_skipped_rungs_points_at_the_skip() -> None:
    """A missing credential is a different problem from an unbound family."""
    config, pool = mapped(MIXED)  # $EXAMPLE_API_KEY is unset in this env

    made = plan(config, pool, contract(), family=API)

    assert not made
    assert "api_big" in made.reason
    assert "EXAMPLE_API_KEY" in made.reason


def test_an_empty_family_quotes_its_own_skipped_rungs_and_not_anothers() -> None:
    """Another family's broken source is not why this family is empty.

    Both families are empty here for unrelated reasons: the local sources are
    unreachable and the api source has no credential. An explanation that
    offered the wrong one would send someone to fix a source that was never in
    the family they asked about.
    """
    config = parse(MIXED)  # $EXAMPLE_API_KEY is unset, so api_big is skipped
    pool = source_map(config, probe=DownProbe({"workstation", "spare"}))

    local = plan(config, pool, contract(), family=LOCAL)
    api = plan(config, pool, contract(), family=API)

    assert "did not answer" in local.reason
    assert "EXAMPLE_API_KEY" not in local.reason
    assert "EXAMPLE_API_KEY" in api.reason
    assert "did not answer" not in api.reason


def test_an_unbound_family_names_what_binding_one_would_take() -> None:
    config, pool = mapped(KEYLESS)

    made = plan(config, pool, contract(), family=API)

    assert "api_key_env" in made.reason


def test_a_family_from_another_catalog_is_refused_rather_than_planned() -> None:
    config, pool = mapped(KEYLESS)
    invented = replace(LOCAL, name="gpu_cluster")

    with pytest.raises(RouteError):
        plan(config, pool, contract(), family=invented)


# --- climbing --------------------------------------------------------------


def test_a_passing_rung_ends_the_climb_and_the_dearer_rung_is_never_tried(
    key: None,
) -> None:
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.PASSED)

    result = accepted(climb(plan(config, pool, contract()), attempts))

    assert result.rung == "local_qwen-7b"
    assert result.history[-1] == Attempted(
        rung="local_qwen-7b",
        attempt=1,
        verdict=Verdict.PASSED,
        detail="local_qwen-7b#1",
    )
    assert attempts.rungs == ["local_qwen-7b"]


def test_a_failed_rung_escalates_to_the_next_rung_of_the_same_family(
    key: None,
) -> None:
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.FAILED, Verdict.PASSED)

    result = accepted(climb(plan(config, pool, contract()), attempts))

    assert result.rung == "local_qwen-14b"
    assert attempts.rungs == ["local_qwen-7b", "local_qwen-14b"]


def test_a_spent_family_is_named_exhausted_and_lists_what_it_tried(key: None) -> None:
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    result = exhausted(climb(plan(config, pool, contract()), attempts))

    assert result.reason is Exhaustion.RUNGS_SPENT
    assert result.family == LOCAL
    assert result.attempts_spent == 2
    assert [a.rung for a in result.history] == ["local_qwen-7b", "local_qwen-14b"]
    assert "local_qwen-14b" in result.detail


def test_exhaustion_never_reaches_for_the_dearer_family(key: None) -> None:
    """The behavioural half of "no path crosses families".

    The ladder has a usable api rung, the local family is spent, and the climb
    ends anyway — because deciding to spend an API token is #43's decision, made
    with rules this module cannot see.
    """
    config, pool = mapped(MIXED)
    assert "api_big" in [r.name for r in pool.rungs]
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    result = exhausted(climb(plan(config, pool, contract()), attempts))

    assert "api_big" not in attempts.rungs
    assert all(a.rung != "api_big" for a in result.history)


def test_a_decline_moves_on_without_spending_an_attempt() -> None:
    """#81's rule: a rung that steps aside is not a rung that failed."""
    config, pool = mapped(with_attempts(KEYLESS, "local_qwen-7b", 3))
    attempts = Recorder(Verdict.DECLINED)

    result = exhausted(climb(plan(config, pool, contract()), attempts))

    assert result.reason is Exhaustion.ALL_DECLINED
    assert result.attempts_spent == 0
    # Budgeted three, asked once: the decline answered for the whole rung.
    assert attempts.rungs == ["local_qwen-7b"]
    assert "no attempt was spent" in result.detail


def test_a_decline_beside_a_failure_is_a_spent_family_not_a_declined_one(
    key: None,
) -> None:
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.DECLINED, Verdict.FAILED)

    result = exhausted(climb(plan(config, pool, contract()), attempts))

    assert result.reason is Exhaustion.RUNGS_SPENT
    assert result.attempts_spent == 1
    assert [a.verdict for a in result.history] == [Verdict.DECLINED, Verdict.FAILED]


def test_an_empty_plan_is_exhausted_with_no_rung_and_carries_the_reason() -> None:
    config, pool = mapped(KEYLESS)
    made = plan(config, pool, contract(UNBOUND_DETERMINISTIC_CONTRACT))
    attempts = Recorder()

    result = exhausted(climb(made, attempts))

    assert result.reason is Exhaustion.NO_RUNG
    assert result.history == ()
    assert result.detail == made.reason
    assert attempts.seen == []


def test_a_retry_on_one_rung_is_numbered_and_stops_at_the_budget() -> None:
    config, pool = mapped(with_attempts(KEYLESS, "local_qwen-7b", 3))
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED)

    result = exhausted(climb(plan(config, pool, contract()), attempts))

    assert [t.attempt for t in attempts.seen] == [1, 2, 3]
    assert {t.of for t in attempts.seen} == {3}
    assert result.attempts_spent == 3


def test_a_withheld_attempt_ends_the_climb_without_blaming_the_family(
    key: None,
) -> None:
    """A caller's ceiling stopped it, so the family says nothing about itself.

    ``WITHHELD`` is distinct from ``RUNGS_SPENT`` for that reason: a family that
    was not allowed to finish must not read like one that was tried and could
    not, or every task cut short by a budget would look like a ladder that is
    not up to the work.
    """
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.FAILED)

    result = exhausted(
        climb(
            plan(config, pool, contract()),
            attempts,
            permit=lambda step, number: step.rung.name == "local_qwen-7b",
        )
    )

    assert result.reason is Exhaustion.WITHHELD
    assert attempts.rungs == ["local_qwen-7b"]
    assert "local_qwen-14b" in result.detail
    assert result.attempts_spent == 1


def test_a_permit_that_funds_everything_changes_nothing(key: None) -> None:
    """The parameter is a question, not a policy: answering yes is the default."""
    config, pool = mapped(MIXED)

    without = exhausted(
        climb(plan(config, pool, contract()), Recorder(Verdict.FAILED, Verdict.FAILED))
    )
    with_permit = exhausted(
        climb(
            plan(config, pool, contract()),
            Recorder(Verdict.FAILED, Verdict.FAILED),
            permit=lambda step, number: True,
        )
    )

    assert without.reason is with_permit.reason is Exhaustion.RUNGS_SPENT
    assert [a.rung for a in without.history] == [a.rung for a in with_permit.history]


def test_a_permit_is_asked_before_the_attempt_is_made_not_after(key: None) -> None:
    """A guard consulted afterwards is a guard that has already spent."""
    config, pool = mapped(KEYLESS)
    attempts = Recorder()  # any call at all is an unscripted attempt

    result = exhausted(
        climb(plan(config, pool, contract()), attempts, permit=lambda step, n: False)
    )

    assert result.reason is Exhaustion.WITHHELD
    assert attempts.seen == []
    assert result.history == ()


def test_an_attempt_that_raises_is_not_swallowed_into_an_exhaustion() -> None:
    """A verdict is a judgement; an exception is the absence of one."""
    config, pool = mapped(KEYLESS)

    def explode(attempt: Try) -> Result:
        raise RuntimeError("the socket died")

    with pytest.raises(RuntimeError):
        climb(plan(config, pool, contract()), explode)


# --- capacity threads all the way through ----------------------------------


def test_every_rung_tried_is_handed_the_capacity_to_dispatch_under(key: None) -> None:
    """The gap #23 left: ``dispatch`` is unbounded by default, so a walk that
    bounded only its first rung would be enforcing a source's limit on some of
    its own dispatches, which is the same as not enforcing it."""
    config, pool = mapped(MIXED)
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert len(attempts.seen) == 2
    assert all(t.capacity is capacity for t in attempts.seen)


def test_a_climb_with_no_capacity_says_so_rather_than_inventing_one() -> None:
    config, pool = mapped(KEYLESS)
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts)

    assert attempts.seen[0].capacity is None


# --- fan-out decides which rung is first, never what order they are in ------


def test_a_plan_carries_the_configured_fanout_mode() -> None:
    """``climb`` has no config, so the mode has to travel on the plan."""
    default, default_pool = mapped(KEYLESS)
    spread, spread_pool = mapped(with_fanout(KEYLESS, "full"))

    assert plan(default, default_pool, contract()).fanout is Fanout.NONE
    assert plan(spread, spread_pool, contract()).fanout is Fanout.FULL


def test_a_fanout_mode_nobody_declared_is_refused_rather_than_defaulted() -> None:
    """The schema refuses one at parse; reaching here means a hand-built config,
    and routing it as ``none`` would answer "spread this batch" by not doing."""
    config, pool = mapped(KEYLESS)
    sideways = replace(config, ladder=replace(config.ladder, fanout="sideways"))

    with pytest.raises(RouteError, match="sideways"):
        plan(sideways, pool, contract())


def test_load_never_reorders_a_plan_under_any_mode(lock_dir: None) -> None:
    """Price order is what a ladder means, and no mode may rewrite it — a plan
    that put a busy rung last would be deciding that load outranks price."""
    for mode in ("none", "idle", "full"):
        config, pool = mapped(with_fanout(MIXED, mode))
        capacity = Capacity.of(config)

        with capacity.hold(pool.bind("local_qwen-7b")):
            made = plan(config, pool, contract(), capacity=capacity)

        assert made.rungs == ("local_qwen-7b", "local_qwen-14b"), mode


def test_the_default_takes_the_cheapest_rung_however_busy_it_is(
    lock_dir: None,
) -> None:
    """``none`` is today's behaviour and this is what keeps it byte for byte."""
    config, pool = mapped(MIXED)
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with capacity.hold(pool.bind("local_qwen-7b")):
        climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


def test_full_fanout_starts_on_the_free_peer_when_the_cheapest_rung_is_full(
    lock_dir: None,
) -> None:
    """The gap the knob exists for: a batch queues on one rung while a peer of
    the same family sits idle, and widening ``max_parallel`` cannot fix it.

    "Busy" is *no free slot*, which is why both of the cheapest rung's slots are
    held here and not just one. A rung with work on it and a slot to spare is
    still the cheapest place this contract can run right now, and moving off it
    would be paying for a dearer rung to avoid a queue that does not exist.
    """
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with occupied(capacity, pool, "local_qwen-7b", "local_qwen-7b"):
        landed = accepted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_qwen-14b"]
    assert landed.rung == "local_qwen-14b"


def test_full_fanout_on_an_idle_ladder_of_equal_rungs_is_the_default(
    lock_dir: None,
) -> None:
    """Three equally wide rungs, nothing running: every rung has the same number
    of free slots, the tie goes to price, and the knob has changed nothing."""
    config, pool = mapped(with_fanout(TRIPLE, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_7b"]


def test_full_fanout_on_an_idle_ladder_still_takes_the_cheapest_rung(
    lock_dir: None,
) -> None:
    """Turning the knob on changes nothing until something is actually busy.

    Here the cheapest rung is also the widest, so it wins on free slots outright
    rather than on the tie-break. That is the knob spreading work as asked: with
    nothing running, the rung with the most room is where a batch should start,
    and on this ladder it is also the cheapest.
    """
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


def test_idle_keeps_the_cheapest_rung_while_it_still_has_a_slot_to_spare(
    lock_dir: None,
) -> None:
    """ "Busy" is *no free slot*, and a rung with work on it is not that.

    One of ``local_qwen-7b``'s two slots is held, so the cheapest rung can still
    take this contract now — and moving off it would be reaching for a dearer
    rung to avoid a queue that does not exist. ``idle`` is a mode about which
    rung a *saturated* ladder offers, not about which rung is quietest.
    """
    config, pool = mapped(with_fanout(MIXED, "idle"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with capacity.hold(pool.bind("local_qwen-7b")):
        climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


def test_idle_starts_on_the_cheapest_rung_that_has_a_free_slot(
    lock_dir: None,
) -> None:
    """The half of ``idle`` that is #24's: choosing among the rungs of one family.

    Both of the cheapest rung's slots are held, so it will admit nothing, and
    the next cheapest is where this contract can actually run. Before this was
    wired the mode was a switch attached to nothing here — entering a family
    whose cheapest rung was full still picked that full rung, and
    ``docs/config-reference.md`` told operators otherwise.

    The busy rung is passed over rather than tried: it reaches no verdict and
    is in no history, which is what keeps a queue from funding an escalation.
    """
    config, pool = mapped(with_fanout(MIXED, "idle"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with occupied(capacity, pool, "local_qwen-7b", "local_qwen-7b"):
        landed = accepted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_qwen-14b"]
    assert landed.rung == "local_qwen-14b"
    assert [a.rung for a in landed.history] == ["local_qwen-14b"], "busy is no verdict"


def test_the_three_modes_give_three_different_answers_on_one_busy_ladder(
    lock_dir: None,
) -> None:
    """``idle`` is not ``full`` with a threshold, and this is where that shows.

    One ladder, one held slot, three modes, three rungs. The cheapest rung is
    full, so ``none`` queues on it, ``idle`` takes the next cheapest — the first
    rung that will admit this dispatch now — and ``full`` takes the roomiest,
    which here is the dearest rung on the ladder. All three are right for the
    question their own mode asks; what they must not be is the same answer,
    because ``idle``'s rule is "the first that admits work" and ``full``'s is
    "the one with the most room", and those coincide on every ladder of equal
    widths. Asserting them side by side is what stops one implementation from
    quietly serving both.
    """
    landed: dict[str, list[str]] = {}
    for mode in ("none", "idle", "full"):
        config, pool = mapped(with_fanout(UNEVEN, mode))
        capacity = Capacity.of(config)
        attempts = Recorder(Verdict.PASSED)

        with occupied(capacity, pool, "local_7b"):
            climb(plan(config, pool, contract()), attempts, capacity=capacity)

        landed[mode] = attempts.rungs

    assert landed["none"] == ["local_7b"], "the cheapest rung, queued on"
    assert landed["idle"] == ["local_14b"], "the cheapest rung with a free slot"
    assert landed["full"] == ["local_32b"], "the roomiest rung, which is dearest"


def test_idle_queues_on_the_cheapest_rung_when_no_rung_has_a_free_slot(
    lock_dir: None,
) -> None:
    """With nothing free inside the family, ``idle`` is ``none``, exactly.

    There is nowhere cheaper to wait than the cheapest rung, and choosing a
    dearer full rung would buy a queue instead of a slot. The rung this mode
    would spill to when every rung of *this* family is full is in another
    family, which is :attr:`mcgyvr.escalate.Ascent.next_free_rung`'s to name and
    :func:`mcgyvr.escalate.escalate`'s to enter — nothing here may reach for it.
    """
    config, pool = mapped(with_fanout(WIDTHS, "idle"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with occupied(
        capacity,
        pool,
        "local_wide",
        "local_wide",
        "local_wide",
        "local_wide",
        "local_narrow",
    ):
        climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_wide"], "the cheapest rung, queued on"


def test_idle_without_a_capacity_keeps_price_order() -> None:
    """No capacity is no load, and inventing one is not routing — as for ``full``."""
    config, pool = mapped(with_fanout(MIXED, "idle"))
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts)

    assert attempts.rungs == ["local_qwen-7b"]


def test_idle_stops_at_a_rung_whose_load_cannot_be_read_rather_than_stepping_over(
    lock_dir: None,
) -> None:
    """An unknown belongs on the cheap side, at this seam and at the other one.

    This capacity bounds the cheapest rung's source and no other, which is a
    capacity and a pool built from different configs. The cheapest rung is full
    and the dearer one cannot be read at all — and "cheapest free" is only
    knowable if every cheaper rung could be priced, so the answer is price
    order. Reading the unreadable rung as free instead would move the climb onto
    a dearer rung on the strength of not knowing; it is the same rule
    :attr:`mcgyvr.escalate.Ascent.next_free_rung` applies by answering ``None``.

    The width is stated to match what the config declares, because
    :meth:`~mcgyvr.capacity.Capacity.hold` refuses an endpoint that disagrees
    with the capacity bounding it — the fact under test is a *missing* source,
    not a contradicted one.
    """
    config, pool = mapped(with_fanout(MIXED, "idle"))
    capacity = Capacity({"workstation": 2})
    attempts = Recorder(Verdict.PASSED)

    with occupied(capacity, pool, "local_qwen-7b", "local_qwen-7b"):
        climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


def test_full_fanout_without_a_capacity_keeps_price_order() -> None:
    """There is no load to read without one, and inventing one is not routing."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts)

    assert attempts.rungs == ["local_qwen-7b"]


def test_a_rung_skipped_for_being_full_is_not_walked_back_down_to(
    lock_dir: None,
) -> None:
    """A rung passed over is passed over for the whole climb, not deferred.

    This replaces a test that asserted the opposite — that a climb starting on
    ``local_qwen-14b`` walked back to ``local_qwen-7b`` and spent two attempts
    doing it. That was the defect written down as the specification: the cheaper
    rung was skipped because it had no free slot, and reaching it *after* the
    dearer rung has failed answers a failure with a weaker model. It also costs
    a move — :func:`mcgyvr.escalate.permit` charges an escalation per new rung —
    so at ``max_escalations: 1`` the run spends its only escalation going
    downhill.

    The family is spent when the climb runs out of rungs *above* where it
    started, and the untried rung is named as untried rather than counted as a
    failure.
    """
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    with occupied(capacity, pool, "local_qwen-7b", "local_qwen-7b"):
        spent = exhausted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_qwen-14b"]
    assert spent.reason is Exhaustion.RUNGS_SPENT
    assert spent.attempts_spent == 1
    assert "local_qwen-7b" in spent.detail
    assert "Not tried" in spent.detail


def test_full_fanout_prefers_a_free_slot_over_a_smaller_number_of_jobs(
    lock_dir: None,
) -> None:
    """Least loaded is not the same question as has a slot free, and only the
    second one is answerable without knowing how wide a machine is.

    A four-wide rig with two dispatches on it is doing twice the work of a
    single-slot rig that is full, and it is the only one of the two that can
    take this contract now. Choosing by absolute load sends the climb to the
    saturated rung, where :meth:`~mcgyvr.capacity.Capacity.hold` blocks it while
    two slots stand free next door — the funnel the knob exists to end, reached
    by the knob itself. It is the same rule
    :attr:`mcgyvr.escalate.Ascent.next_free_rung` states as ``load < width``.
    """
    config, pool = mapped(with_fanout(WIDTHS, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with occupied(capacity, pool, "local_wide", "local_wide", "local_narrow"):
        landed = accepted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_wide"], "two free slots beat one busy one"
    assert landed.rung == "local_wide"


def test_full_fanout_climbs_upward_from_its_start_and_never_back_down(
    lock_dir: None,
) -> None:
    """Fan-out chooses where a climb *begins*; from there the ladder is a ladder.

    Three rungs, with the cheapest and the dearest each carrying a dispatch, so
    the free-slot choice starts in the middle. When that rung fails the climb
    may only go up. Re-choosing by load at every step instead would order the
    whole walk by load and send a failed 14b down to 7b — a weaker model tried
    after a stronger one has already failed, which inverts the one thing a
    ladder asserts, and which ``docs/config-reference.md`` calls actively
    harmful. It is not free, either: :func:`mcgyvr.escalate.permit` charges an
    escalation per new rung, so a task at ``max_escalations: 1`` would spend its
    only move going downhill and never reach 32b at all.

    The rungs cheaper than the start are not revisited, because they were
    skipped for being busy rather than for failing, and a climb that came back
    to them would be descending too.
    """
    config, pool = mapped(with_fanout(TRIPLE, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED)

    with occupied(capacity, pool, "local_7b", "local_32b"):
        spent = exhausted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_14b", "local_32b"], "upward only"
    assert spent.reason is Exhaustion.RUNGS_SPENT
    assert spent.attempts_spent == 2


def test_two_plans_of_the_same_inputs_are_the_same_plan(lock_dir: None) -> None:
    """A plan is a value, and a caller may compare two of them.

    What a rung runs on is not part of what a plan *is*: two plans built from
    one config, one pool and one contract describe the same route whether or
    not they were handed the same :class:`~mcgyvr.route.Machine` objects, and
    :class:`mcgyvr.escalate.Ascent` says the same thing one level up about the
    capacity an ascent was handed. A :class:`~mcgyvr.route.Machine` compared by
    identity — which is the only way it can be compared, since it deliberately
    names nothing — silently makes every plan unequal to every other.
    """
    config, pool = mapped(MIXED)
    capacity = Capacity.of(config)

    first = plan(config, pool, contract(), capacity=capacity)
    second = plan(config, pool, contract(), capacity=capacity)

    assert first == second
    assert first.steps[0].machine is not second.steps[0].machine


def test_a_raising_attempt_stops_counting_against_the_rung_it_raised_on(
    lock_dir: None,
) -> None:
    """A count that leaked would make a machine look busy to every later climb
    in the process — and it would show as a batch avoiding a rung that is free."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)

    def explode(step: Try) -> Result:
        raise RuntimeError("the socket died mid-dispatch")

    with pytest.raises(RuntimeError):
        climb(plan(config, pool, contract()), explode, capacity=capacity)

    after = Recorder(Verdict.PASSED)
    climb(plan(config, pool, contract()), after, capacity=capacity)

    assert after.rungs == ["local_qwen-7b"]


def test_a_busy_rung_is_passed_over_and_never_recorded_as_having_failed(
    lock_dir: None,
) -> None:
    """Busy is a queue, not a verdict. Escalation is funded by failures, so a
    rung that was skipped for a free peer must leave no mark that reads as one."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with occupied(capacity, pool, "local_qwen-7b", "local_qwen-7b"):
        landed = accepted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert [entry.rung for entry in landed.history] == ["local_qwen-14b"]
    assert all(entry.verdict is Verdict.PASSED for entry in landed.history)


def test_two_rungs_on_one_machine_are_one_queue() -> None:
    """Load is a property of the box. Two names for one machine that counted
    separately would let a fan-out spread a batch across a box it never left."""
    config, pool = mapped(SHARED)

    made = plan(config, pool, contract())

    assert made.rungs == ("local_qwen-7b", "local_qwen-14b")
    assert made.climbable[0].machine is made.climbable[1].machine


def test_a_plan_can_be_asked_how_busy_a_rung_is_without_naming_the_machine(
    lock_dir: None,
) -> None:
    """#20 at this seam: the plan carries the question, never the box's name."""
    config, pool = mapped(MIXED)
    capacity = Capacity.of(config)

    made = plan(config, pool, contract())
    machine = made.climbable[0].machine
    assert machine is not None

    rendered = repr(made)
    for where in ("workstation", "spare", "localhost", "192.168.1.20"):
        assert where not in rendered
    assert machine.load(capacity) == 0
    with capacity.hold(pool.bind("local_qwen-7b")):
        assert machine.load(capacity) == 1


def test_a_step_bound_to_no_machine_is_taken_in_price_order(lock_dir: None) -> None:
    """A hand-built plan names no machine, so there is no load to order by, and
    ordering by the ones that could be read would order by nothing at all."""
    config, pool = mapped(MIXED)
    capacity = Capacity.of(config)
    made = plan(config, pool, contract())
    bare = Plan(
        family=LOCAL,
        steps=tuple(Step(step.rung, step.attempts) for step in made.climbable),
        fanout=Fanout.FULL,
    )
    attempts = Recorder(Verdict.PASSED)

    with capacity.hold(pool.bind("local_qwen-7b")):
        climb(bare, attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


# --- the shapes callers depend on -----------------------------------------


def test_a_plan_reports_its_budget_before_anything_is_spent() -> None:
    rung = Rung(name="local_qwen-7b", model="qwen2.5-coder:7b")

    made = Plan(family=LOCAL, steps=(Step(rung, 2), Step(rung, 3)))

    assert made.budget == 5
    assert len(made) == 2
    assert bool(made) is True


def test_a_result_is_built_through_a_named_verdict() -> None:
    assert Result.passed("x").verdict is Verdict.PASSED
    assert Result.passed("x").detail == "x"
    assert Result.failed("why").verdict is Verdict.FAILED
    assert Result.declined("why").detail == "why"


def test_a_declined_history_entry_is_kept_rather_than_dropped() -> None:
    """A family that was never tried must not read like one that was."""
    entry = Attempted(rung="r", attempt=1, verdict=Verdict.DECLINED)

    assert entry.verdict is Verdict.DECLINED


# --- the decision is readable without running anything ---------------------


def test_the_pool_command_shows_the_family_and_budget_of_every_rung(
    tmp_path: Path,
    key: None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routing that cannot be read cannot be checked.

    ``mcgyvr pool`` already answered "what can run"; a rung's family is how dear
    it is to ask and its budget is how many times it will be asked, and both are
    decided before anything is spent. Printing them keeps the two numbers a
    reader can act on next to the ladder they belong to — and a family is a cost
    class, not a location, so this says nothing about which machine answers.
    """
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(with_attempts(MIXED, "local_qwen-14b", 3), encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(path))

    assert main(["pool"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert any(
        "local_qwen-7b" in line and "local" in line and "1 attempt" in line
        for line in lines
    )
    assert any("local_qwen-14b" in line and "3 attempts" in line for line in lines)
    assert any("api_big" in line and "api" in line for line in lines)
