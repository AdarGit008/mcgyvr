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

*Fan-out breaks a tie and never reorders the ladder* is the fourth statement,
added with ``ladder.fanout``, and it is held from both sides: a busy cheapest
rung is still taken under ``none`` and under ``idle`` (which is another
module's mode), the free peer is taken under ``full``, an idle ladder gives the
same rung under every mode, and a plan's order is asserted to be price order
whatever the mode and whatever is busy. Load is made real with
:meth:`~mcgyvr.capacity.Capacity.hold` rather than with a stub, because the
number under test is the one a real dispatch moves.

Nothing here dispatches. The attempt function is a recorder, which is the whole
reason :func:`~mcgyvr.route.climb` takes one: every rule in the module is about
sequencing and budgets, and a test that needed a model to check a budget would
be testing the model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.catalog import catalog
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV, Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
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

DETERMINISTIC_CONTRACT = """
id: tidy
task_type: format
task: Reformat the package.
target: src/pkg/fetch.py
scope:
  allow: ["src/**"]
"""

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
    """

    def __init__(self, *verdicts: Verdict) -> None:
        self._verdicts = list(verdicts)
        self.seen: list[Try] = []

    def __call__(self, attempt: Try) -> Result[str]:
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


def accepted(result: Accepted[str] | Exhausted) -> Accepted[str]:
    assert isinstance(result, Accepted), f"expected an accepted climb, got {result}"
    return result


def exhausted(result: Accepted[str] | Exhausted) -> Exhausted:
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
            assert family_of(config, step.rung.name) == family


def test_the_deterministic_family_plans_nothing_and_says_why_structurally() -> None:
    """It is empty for a reason no config edit changes, and the words say so."""
    config, pool = mapped(KEYLESS)

    made = plan(config, pool, contract(DETERMINISTIC_CONTRACT))

    assert made.family == DETERMINISTIC
    assert not made
    assert "#81" in made.reason
    assert "tools, not a model on a source" in made.reason


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
    assert result.value == "local_qwen-7b#1"
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
    made = plan(config, pool, contract(DETERMINISTIC_CONTRACT))
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

    def explode(attempt: Try) -> Result[str]:
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


def test_full_fanout_starts_on_the_free_peer_when_the_cheapest_rung_is_busy(
    lock_dir: None,
) -> None:
    """The gap the knob exists for: a batch queues on one rung while a peer of
    the same family sits idle, and widening ``max_parallel`` cannot fix it."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with capacity.hold(pool.bind("local_qwen-7b")):
        landed = accepted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_qwen-14b"]
    assert landed.rung == "local_qwen-14b"


def test_full_fanout_on_an_idle_ladder_still_takes_the_cheapest_rung(
    lock_dir: None,
) -> None:
    """A tie goes to price, so turning the knob on changes nothing until
    something is actually busy."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


def test_idle_is_not_this_modules_mode_and_reads_as_the_default_here(
    lock_dir: None,
) -> None:
    """``idle`` may spill into a priced family, which crosses the boundary #24
    draws; it is :func:`mcgyvr.escalate.ascent`'s and is carried, not acted on."""
    config, pool = mapped(with_fanout(MIXED, "idle"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.PASSED)

    with capacity.hold(pool.bind("local_qwen-7b")):
        climb(plan(config, pool, contract()), attempts, capacity=capacity)

    assert attempts.rungs == ["local_qwen-7b"]


def test_full_fanout_without_a_capacity_keeps_price_order() -> None:
    """There is no load to read without one, and inventing one is not routing."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    attempts = Recorder(Verdict.PASSED)

    climb(plan(config, pool, contract()), attempts)

    assert attempts.rungs == ["local_qwen-7b"]


def test_full_fanout_still_walks_every_rung_when_the_first_one_fails(
    lock_dir: None,
) -> None:
    """Fan-out changes which rung is tried first, not how many may be tried."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    with capacity.hold(pool.bind("local_qwen-7b")):
        spent = exhausted(
            climb(plan(config, pool, contract()), attempts, capacity=capacity)
        )

    assert attempts.rungs == ["local_qwen-14b", "local_qwen-7b"]
    assert spent.reason is Exhaustion.RUNGS_SPENT
    assert spent.attempts_spent == 2


def test_a_raising_attempt_stops_counting_against_the_rung_it_raised_on(
    lock_dir: None,
) -> None:
    """A count that leaked would make a machine look busy to every later climb
    in the process — and it would show as a batch avoiding a rung that is free."""
    config, pool = mapped(with_fanout(MIXED, "full"))
    capacity = Capacity.of(config)

    def explode(step: Try) -> Result[str]:
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

    with capacity.hold(pool.bind("local_qwen-7b")):
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
    assert made.steps[0].machine is made.steps[1].machine


def test_a_plan_can_be_asked_how_busy_a_rung_is_without_naming_the_machine(
    lock_dir: None,
) -> None:
    """#20 at this seam: the plan carries the question, never the box's name."""
    config, pool = mapped(MIXED)
    capacity = Capacity.of(config)

    made = plan(config, pool, contract())
    machine = made.steps[0].machine
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
        steps=tuple(Step(step.rung, step.attempts) for step in made.steps),
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
    assert Result.passed("x").value == "x"
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
