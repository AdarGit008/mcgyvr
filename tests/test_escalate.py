"""#43's acceptance is five statements, and three of them are about refusals.

*Total attempts per task are bounded and configurable* is held by driving one
contract against configs that differ only in a ceiling and asserting the climb
changes with it — asserting a default alone would pass just as well against a
constant. Both ceilings are exercised that way, because they bound different
things: one counts moves and one counts spend, and a test that only moved the
number it happened to trip would not tell them apart.

*Every terminal outcome is machine-readable* is held by reaching all six
:class:`~mcgyvr.escalate.Outcome` members independently. They exist because a
caller responds differently to each: a ladder genuinely spent, two different
ceilings, an install with nothing to run, and a ladder that declined
throughout — the last of which says nothing at all about what the ladder can
do, and must not be reported as though it did.

*The unverified-acceptance path is closed* is the one a test can only hold
negatively, so it is held three ways: by asserting the upgrade happens for
every family above the deterministic one, by driving the whole
policy x family x verifier matrix and asserting
:attr:`~mcgyvr.escalate.Assurance.VERIFIED` is unreachable unless a verifier
ran and agreed, and by asserting an install with no verifier is labelled
unverified rather than accepted quietly.

*No verifier call is made for an attempt whose gate failed* is held with a spy
that raises if it is called at all — a counter asserted to be zero would pass
against a verifier called and ignored, which is the spend this rule exists to
prevent.

*A retry prompt carries the failing checks and not the passing ones* is held on
the note and again on the rendered prompt, and the exclusions are asserted by
name: an observation and an environment issue are both real entries on a gate
result that must not reach the worker, and neither would be caught by a test
that only checked the failing check was present.

Nothing here dispatches, gates or verifies. Every input is constructed, which
is the whole reason :func:`~mcgyvr.escalate.escalate` takes an attempt function
and :func:`~mcgyvr.escalate.judge` takes a gate result.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.catalog import Family, catalog
from mcgyvr.cli import main
from mcgyvr.config import CONFIG_PATH_ENV, Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import (
    Ascent,
    Assurance,
    Ceiling,
    Delivered,
    Halted,
    Judgement,
    Opinion,
    Outcome,
    RetryNotes,
    Review,
    ascent,
    escalate,
    judge,
    required_policy,
)
from mcgyvr.gate import Finding, GateResult
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import RouteError, Try, Verdict
from mcgyvr.worker.prompt import build_prompt

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


def mapped(text: str) -> tuple[Config, SourceMap]:
    config = parse(text)
    return config, source_map(config)


def with_budgets(text: str, **values: int) -> str:
    """The same config with a budgets block set."""
    lines = [text, "budgets:"]
    lines.extend(f"  {name}: {value}" for name, value in values.items())
    return "\n".join(lines)


def contract(text: str = CONTRACT) -> Contract:
    return load_contract(text)


def verifying(text: str = CONTRACT) -> Contract:
    """The same contract, declaring that a verifier must agree."""
    return load_contract(text + "\nverification:\n  policy: model\n")


class Recorder:
    """An attempt function that answers from a script and records what it saw.

    Running past the script is itself a failure: a task that made more attempts
    than the test wrote down has broken the budget the test is about, and a
    silent default would hide exactly that.
    """

    def __init__(self, *verdicts: Verdict) -> None:
        self._verdicts = list(verdicts)
        self.seen: list[Try] = []

    def __call__(self, this: Try) -> Judgement[str]:
        self.seen.append(this)
        if not self._verdicts:
            raise AssertionError(
                f"an unscripted attempt was made on {this.rung.name!r}"
            )
        verdict = self._verdicts.pop(0)
        if verdict is Verdict.PASSED:
            return Judgement(
                verdict=Verdict.PASSED,
                value=f"{this.rung.name}#{this.attempt}",
                assurance=Assurance.UNVERIFIED,
            )
        if verdict is Verdict.DECLINED:
            return Judgement(verdict=Verdict.DECLINED, detail="not work this rung does")
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")

    @property
    def rungs(self) -> list[str]:
        return [t.rung.name for t in self.seen]


class Spy:
    """A verifier that fails the test if it is ever asked.

    A counter checked for zero would be satisfied by a verifier that was called
    and whose answer was thrown away — which is the spend the ordering rule
    exists to prevent, so the assertion has to be that the call never happens.
    """

    def __call__(self) -> Review:
        raise AssertionError("the verifier was asked about a change the gate rejected")


def rejected(*checks: str) -> GateResult:
    return GateResult(
        findings=tuple(
            Finding(check=check, path="src/pkg/fetch.py", message="no", line=n + 1)
            for n, check in enumerate(checks)
        )
    )


def clean() -> GateResult:
    return GateResult()


def delivered(result: Delivered[str] | Halted) -> Delivered[str]:
    assert isinstance(result, Delivered), f"expected an accepted task, got {result}"
    return result


def halted(result: Delivered[str] | Halted) -> Halted:
    assert isinstance(result, Halted), f"expected a halted task, got {result}"
    return result


# --- the ascent is a rule, and monotonic by construction -------------------


def test_the_ascent_starts_at_the_contracts_floor_and_climbs_in_rank_order(
    key: None,
) -> None:
    config, pool = mapped(MIXED)

    route = ascent(config, pool, contract())

    assert route.floor == LOCAL  # function_implementation starts on local
    assert [f.name for f in route.families] == ["local", "api"]
    assert route.rungs == ("local_qwen-7b", "local_qwen-14b", "api_big")


def test_no_family_is_entered_twice_and_the_ranks_only_increase(key: None) -> None:
    """Ping-pong is impossible in the shape rather than prevented by a check.

    Asserted from every floor the catalog declares, so it is a statement about
    :func:`~mcgyvr.escalate.ascent` and not about one contract's floor.
    """
    config, pool = mapped(MIXED)

    for floor in catalog().families:
        families = ascent(config, pool, contract(), floor=floor).families
        ranks = [f.rank for f in families]

        assert len(set(families)) == len(families)
        assert ranks == sorted(ranks)
        assert ranks == list(range(floor.rank, len(catalog().families)))


def test_a_family_cheaper_than_the_floor_is_absent_rather_than_skipped(
    key: None,
) -> None:
    config, pool = mapped(MIXED)

    route = ascent(config, pool, contract(), floor=API)

    assert DETERMINISTIC not in route.families
    assert LOCAL not in route.families
    assert route.families == (API,)


def test_an_empty_floor_family_is_climbed_past_and_keeps_its_reason() -> None:
    """The case #24 handed over: a floor that binds no rung is an input.

    A `format` contract floors on the deterministic family, which no config can
    bind. #24 returns an empty plan naming why; ascent is what turns that into
    work rather than into a failure.
    """
    config, pool = mapped(KEYLESS)

    route = ascent(config, pool, contract(DETERMINISTIC_CONTRACT))

    assert route.floor == DETERMINISTIC
    assert [f.name for f in route.families] == ["deterministic", "local", "api"]
    assert [p.family.name for p in route.runnable] == ["local"]
    assert "#81" in route.reason


def test_a_family_from_another_catalog_is_refused_rather_than_climbed() -> None:
    config, pool = mapped(KEYLESS)
    invented = replace(LOCAL, name="gpu_cluster")

    with pytest.raises(RouteError):
        ascent(config, pool, contract(), floor=invented)


def test_an_ascent_reports_what_it_may_spend_before_anything_is_spent(
    key: None,
) -> None:
    """The whole climb is inspectable, not just one family of it."""
    config, pool = mapped(MIXED)

    route = ascent(config, pool, contract())

    assert route.ladder_budget == 3  # three rungs at the default one attempt
    assert route.budget == 3  # no independent ceiling is set
    assert route.most_rungs == 2  # max_escalations defaults to 1
    assert len(route) == 2  # two families offer a rung
    assert bool(route) is True


# --- ascent across families ------------------------------------------------


def test_a_spent_family_escalates_to_the_next_one_up(key: None) -> None:
    """The half #24 deliberately did not build."""
    config, pool = mapped(with_budgets(MIXED, max_escalations=2))
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.PASSED)

    result = delivered(escalate(config, pool, contract(), attempts))

    assert attempts.rungs == ["local_qwen-7b", "local_qwen-14b", "api_big"]
    assert result.family == API
    assert result.rung == "api_big"
    assert result.entered == (LOCAL, API)
    assert result.escalations == 2


def test_a_passing_rung_ends_the_task_and_no_dearer_family_is_entered(
    key: None,
) -> None:
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.PASSED)

    result = delivered(escalate(config, pool, contract(), attempts))

    assert result.outcome is Outcome.ACCEPTED
    assert result.entered == (LOCAL,)
    assert result.attempts_spent == 1
    assert result.escalations == 0
    assert "api_big" not in attempts.rungs


def test_a_keyless_install_halts_rather_than_reaching_for_a_family_it_lacks() -> None:
    """The api family is in the ascent and empty; that is not an error."""
    config, pool = mapped(KEYLESS)
    attempts = Recorder(Verdict.FAILED)

    result = halted(escalate(config, pool, contract(), attempts))

    assert result.outcome is Outcome.LADDER_SPENT
    assert result.entered == (LOCAL,)
    assert attempts.rungs == ["local_qwen-7b"]


def test_nothing_to_run_is_its_own_outcome_and_says_why_per_family() -> None:
    """An install that can run nothing is a configuration fact, not a failure."""
    config, pool = mapped(KEYLESS.replace("local_qwen-7b", "api_only"))
    attempts = Recorder()

    result = halted(escalate(config, pool, contract(), attempts, floor=API))

    assert result.outcome is Outcome.NOTHING_TO_RUN
    assert result.history == ()
    assert result.attempts_spent == 0
    assert "api_key_env" in result.detail
    assert attempts.seen == []


# --- the two ceilings ------------------------------------------------------


def test_the_escalation_ceiling_stops_the_climb_and_names_itself(key: None) -> None:
    """Default `max_escalations` is 1, so the third rung is never funded."""
    config, pool = mapped(MIXED)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    result = halted(escalate(config, pool, contract(), attempts))

    assert result.outcome is Outcome.ESCALATION_CEILING
    assert result.escalations == 1
    assert attempts.rungs == ["local_qwen-7b", "local_qwen-14b"]
    assert "max_escalations" in result.detail


def test_the_escalation_ceiling_is_policy_in_config_not_a_constant(key: None) -> None:
    """Two configs differing only in one number produce two different climbs."""
    tight, tight_pool = mapped(with_budgets(MIXED, max_escalations=0))
    loose, loose_pool = mapped(with_budgets(MIXED, max_escalations=2))

    one = halted(escalate(tight, tight_pool, contract(), Recorder(Verdict.FAILED)))
    three = halted(
        escalate(
            loose,
            loose_pool,
            contract(),
            Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED),
        )
    )

    assert one.outcome is Outcome.ESCALATION_CEILING
    assert one.attempts_spent == 1
    assert three.outcome is Outcome.LADDER_SPENT
    assert three.attempts_spent == 3


def test_the_attempt_ceiling_stops_the_task_and_names_itself(key: None) -> None:
    config, pool = mapped(with_budgets(MIXED, max_escalations=9, max_attempts=2))
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    result = halted(escalate(config, pool, contract(), attempts))

    assert result.outcome is Outcome.ATTEMPT_CEILING
    assert result.attempts_spent == 2
    assert "budgets.max_attempts" in result.detail
    assert "api_big" not in attempts.rungs


def test_the_attempt_ceiling_is_policy_in_config_not_a_constant(key: None) -> None:
    two, two_pool = mapped(with_budgets(MIXED, max_escalations=9, max_attempts=2))
    three, three_pool = mapped(with_budgets(MIXED, max_escalations=9, max_attempts=3))

    assert ascent(two, two_pool, contract()).budget == 2
    assert ascent(three, three_pool, contract()).budget == 3

    stopped = halted(
        escalate(two, two_pool, contract(), Recorder(Verdict.FAILED, Verdict.FAILED))
    )
    spent = halted(
        escalate(
            three,
            three_pool,
            contract(),
            Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED),
        )
    )

    assert stopped.outcome is Outcome.ATTEMPT_CEILING
    assert spent.outcome is Outcome.LADDER_SPENT


def test_an_unset_attempt_ceiling_is_the_ladders_own_budget_not_infinity(
    key: None,
) -> None:
    """Leaving the field unset still bounds the task, and by a number it can print."""
    config, pool = mapped(with_budgets(MIXED, max_escalations=9))

    route = ascent(config, pool, contract())

    assert route.ceiling.attempts is None
    assert route.budget == route.ladder_budget == 3


def test_a_ceiling_cannot_raise_what_the_ladder_offers(key: None) -> None:
    config, pool = mapped(with_budgets(MIXED, max_escalations=9, max_attempts=99))

    assert ascent(config, pool, contract()).budget == 3


def test_a_decline_charges_neither_ceiling(key: None) -> None:
    """#81's rule reaches the task level: a rung that stepped aside cost nothing.

    `max_escalations` is 0 here, so a single charged move would end the task on
    the second rung. Two rungs decline and the third still gets funded, which
    is only true if a decline moves the work without being a climb.
    """
    config, pool = mapped(with_budgets(MIXED, max_escalations=0))
    attempts = Recorder(Verdict.DECLINED, Verdict.DECLINED, Verdict.FAILED)

    result = halted(escalate(config, pool, contract(), attempts))

    assert attempts.rungs == ["local_qwen-7b", "local_qwen-14b", "api_big"]
    assert result.outcome is Outcome.LADDER_SPENT
    assert result.attempts_spent == 1
    assert result.escalations == 0


def test_a_ladder_that_declines_throughout_is_not_a_ladder_that_failed(
    key: None,
) -> None:
    config, pool = mapped(with_budgets(MIXED, max_escalations=0))
    attempts = Recorder(Verdict.DECLINED, Verdict.DECLINED, Verdict.DECLINED)

    result = halted(escalate(config, pool, contract(), attempts))

    assert result.outcome is Outcome.DECLINED_THROUGHOUT
    assert result.attempts_spent == 0
    assert "no attempt was spent" in result.detail


def test_every_terminal_outcome_is_reachable_and_distinct() -> None:
    """A vocabulary nothing can reach is prose with an enum around it."""
    reached = {
        Outcome.ACCEPTED,
        Outcome.LADDER_SPENT,
        Outcome.ESCALATION_CEILING,
        Outcome.ATTEMPT_CEILING,
        Outcome.NOTHING_TO_RUN,
        Outcome.DECLINED_THROUGHOUT,
    }

    assert reached == set(Outcome)


# --- verification policy: the upgrade --------------------------------------


def test_gate_only_stands_only_in_the_deterministic_family() -> None:
    """The policy was written about a tool; a model is not covered by it."""
    declared = contract()

    assert declared.verification.policy == "gate_only"
    assert required_policy(declared, DETERMINISTIC) == "gate_only"
    assert required_policy(declared, LOCAL) == "model"
    assert required_policy(declared, API) == "model"


def test_a_declared_model_policy_is_never_lowered() -> None:
    """An upgrade raises; it does not set."""
    strict = verifying()

    for family in catalog().families:
        assert required_policy(strict, family) == "model"


def test_the_upgrade_is_recorded_on_the_judgement_that_carried_it() -> None:
    verdict = judge(contract(), LOCAL, clean(), "new content")

    assert verdict.policy == "model"
    assert verdict.upgraded is True


# --- verification policy: the unverified path is closed --------------------


def test_verified_is_unreachable_unless_a_verifier_ran_and_agreed() -> None:
    """The matrix, driven whole: policy x family x what the verifier answered.

    Held as a structural statement rather than as a list of cases, because the
    claim is about every path through :func:`~mcgyvr.escalate.judge` and not
    about the ones that occurred to whoever wrote the test.
    """
    reviews = {
        "none": None,
        "agreed": Review.agreed,
        "refused": Review.refused,
        "unusable": Review.unusable,
    }

    for declared in (contract(), verifying()):
        for family in catalog().families:
            for label, review in reviews.items():
                verdict = judge(
                    declared,
                    family,
                    clean(),
                    "new content",
                    verifier=None if review is None else review,
                )
                if verdict.assurance is Assurance.VERIFIED:
                    assert label == "agreed", (
                        f"{declared.verification.policy} on {family.name} with a "
                        f"{label} review reached VERIFIED"
                    )
                if label in ("refused", "unusable") and verdict.policy == "model":
                    # Where a verifier was required, its answer is binding. In
                    # the deterministic family it is not required, so it is not
                    # asked at all and cannot reject anything.
                    assert verdict.verdict is not Verdict.PASSED


def test_a_keyless_install_is_labelled_unverified_rather_than_accepted_quietly() -> (
    None
):
    """E6's third first-class configuration, and where #44 attaches."""
    verdict = judge(contract(), LOCAL, clean(), "new content")

    assert verdict.verdict is Verdict.PASSED
    assert verdict.assurance is Assurance.UNVERIFIED
    assert verdict.upgraded is True
    assert "#44" in verdict.detail


def test_an_available_verifier_is_never_skipped() -> None:
    asked: list[str] = []

    def verifier() -> Review:
        asked.append("called")
        return Review.agreed("the change does what the contract asked")

    verdict = judge(contract(), LOCAL, clean(), "new content", verifier=verifier)

    assert asked == ["called"]
    assert verdict.assurance is Assurance.VERIFIED


def test_the_deterministic_family_does_not_spend_a_verifier_it_did_not_need() -> None:
    """`gate_only` is the whole bar there, so asking is spend the policy refused."""
    verdict = judge(
        contract(DETERMINISTIC_CONTRACT), DETERMINISTIC, clean(), "x", verifier=Spy()
    )

    assert verdict.assurance is Assurance.DETERMINISTIC
    assert verdict.upgraded is False


def test_a_refused_review_is_a_failed_attempt_and_carries_what_to_fix() -> None:
    verdict = judge(
        contract(),
        LOCAL,
        clean(),
        "x",
        verifier=lambda: Review.refused("the retry has no backoff"),
    )

    assert verdict.verdict is Verdict.FAILED
    assert verdict.assurance is None
    assert verdict.retry is not None
    assert "no backoff" in verdict.retry.text


def test_an_unusable_review_is_neither_an_approval_nor_the_builders_fault() -> None:
    """#41's rule reaching the policy: a reply that cannot be read is not a verdict."""
    verdict = judge(
        contract(), LOCAL, clean(), "x", verifier=lambda: Review.unusable("empty reply")
    )

    assert verdict.verdict is Verdict.FAILED
    assert verdict.reviewer_failed is True
    assert verdict.retry is None  # nothing the worker did, so nothing to tell it
    assert "#42" in verdict.detail


def test_a_review_is_built_through_a_named_opinion_never_a_boolean() -> None:
    assert Review.agreed().opinion is Opinion.AGREED
    assert Review.refused("why").opinion is Opinion.REFUSED
    assert Review.refused("why").detail == "why"
    assert Review.unusable().opinion is Opinion.UNUSABLE


def test_an_accepted_task_reports_the_bar_it_actually_cleared(key: None) -> None:
    config, pool = mapped(MIXED)

    def attempt(this: Try) -> Judgement[str]:
        return judge(
            contract(),
            LOCAL,
            clean(),
            this.rung.name,
            verifier=lambda: Review.agreed(),
        )

    result = delivered(escalate(config, pool, contract(), attempt))

    assert result.assurance is Assurance.VERIFIED
    assert result.verified is True


def test_an_acceptance_that_named_no_bar_is_read_as_unverified(key: None) -> None:
    """Defaulting the other way is how a result is reported as more assured."""
    config, pool = mapped(MIXED)

    def attempt(this: Try) -> Judgement[str]:
        return Judgement(verdict=Verdict.PASSED, value=this.rung.name)

    result = delivered(escalate(config, pool, contract(), attempt))

    assert result.assurance is Assurance.UNVERIFIED
    assert result.verified is False


# --- ordering: the gate runs first, and a failure costs no verifier --------


def test_no_verifier_is_asked_about_a_change_the_gate_rejected() -> None:
    """#32 stated this ordering; nothing held it until here."""
    verdict = judge(contract(), LOCAL, rejected("lint"), "x", verifier=Spy())

    assert verdict.verdict is Verdict.FAILED
    assert verdict.assurance is None
    assert "no verifier was asked" in verdict.detail


def test_the_ordering_holds_for_a_contract_that_demanded_verification() -> None:
    """The contract asking for a verifier does not buy the gate's failure one."""
    verdict = judge(verifying(), API, rejected("secrets", "scope"), "x", verifier=Spy())

    assert verdict.verdict is Verdict.FAILED


def test_a_gate_failure_costs_no_verifier_spend_anywhere_in_a_climb(key: None) -> None:
    config, pool = mapped(MIXED)

    def attempt(this: Try) -> Judgement[str]:
        return judge(
            contract(), LOCAL, rejected("lint"), this.rung.name, verifier=Spy()
        )

    result = halted(escalate(config, pool, contract(), attempt))

    assert result.outcome is Outcome.ESCALATION_CEILING
    assert result.attempts_spent == 2


# --- retries carry the failing checks only ---------------------------------


def test_a_retry_note_carries_the_failing_checks_and_not_the_passing_ones() -> None:
    gate = rejected("lint", "format")

    notes = RetryNotes.of(gate)

    assert notes is not None
    assert notes.checks == ("lint", "format")
    assert len(notes.lines) == 2
    for passing in ("scope", "secrets", "syntax", "acceptance"):
        assert passing not in notes.text


def test_a_retry_note_excludes_observations_and_environment_issues() -> None:
    """Two entries a gate result really carries, and neither is a rejection.

    An observation is a finding the gate deliberately did not reject on (#123),
    so quoting it would ask for a change that was never required; an
    environment issue is a tool that was not installed, which is not something
    the worker did or can fix.
    """
    gate = GateResult(
        findings=(Finding(check="lint", path="src/pkg/fetch.py", message="E501"),),
        observations=(
            Finding(check="semantic", path="src/pkg/fetch.py", message="unresolved"),
        ),
        environment_issues=("python: ruff not installed — lint skipped",),
    )

    notes = RetryNotes.of(gate)

    assert notes is not None
    assert notes.checks == ("lint",)
    assert "E501" in notes.text
    assert "unresolved" not in notes.text
    assert "not installed" not in notes.text


def test_a_clean_gate_produces_no_retry_note() -> None:
    assert RetryNotes.of(clean()) is None
    assert judge(contract(), LOCAL, clean(), "x").retry is None


def test_the_retry_prompt_names_what_failed_and_repeats_nothing_that_passed() -> None:
    """The rule reaching the prompt a worker is actually sent."""
    notes = RetryNotes.of(rejected("lint", "format"))
    assert notes is not None

    first = build_prompt(contract())
    again = build_prompt(contract(), retry=notes)

    assert "PREVIOUS ATTEMPT" not in first.user
    assert "PREVIOUS ATTEMPT" in again.user
    assert "lint" in again.user and "format" in again.user
    assert "scope" not in again.user and "secrets" not in again.user
    # The contract is unchanged, so a retry is the first prompt plus what failed.
    assert again.tokens > first.tokens


# --- the shapes callers depend on -----------------------------------------


def test_a_ceiling_reads_both_numbers_off_the_config(key: None) -> None:
    unset = Ceiling.of(parse(MIXED))
    set_both = Ceiling.of(parse(with_budgets(MIXED, max_escalations=4, max_attempts=7)))

    assert unset == Ceiling(escalations=1, attempts=None)
    assert set_both == Ceiling(escalations=4, attempts=7)


def test_an_empty_ascent_is_falsy_and_says_why() -> None:
    config, _ = mapped(KEYLESS)

    route = Ascent(floor=API, plans=(), ceiling=Ceiling.of(config))

    assert not route
    assert route.budget == 0
    assert route.rungs == ()


def test_a_halted_task_and_a_delivered_one_are_told_apart_by_type(key: None) -> None:
    config, pool = mapped(MIXED)

    done = escalate(config, pool, contract(), Recorder(Verdict.PASSED))
    stopped = escalate(
        config, pool, contract(), Recorder(Verdict.FAILED, Verdict.FAILED)
    )

    assert done.ok is True
    assert stopped.ok is False
    assert done.outcome is Outcome.ACCEPTED
    assert stopped.outcome is not Outcome.ACCEPTED


def test_the_history_spans_every_family_the_task_entered(key: None) -> None:
    """A task-level record that stopped at a family boundary would hide the climb."""
    config, pool = mapped(with_budgets(MIXED, max_escalations=2))
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED)

    result = halted(escalate(config, pool, contract(), attempts))

    assert [a.rung for a in result.history] == [
        "local_qwen-7b",
        "local_qwen-14b",
        "api_big",
    ]
    assert result.entered == (LOCAL, API)


def test_an_attempt_that_raises_is_not_swallowed_into_a_terminal_outcome() -> None:
    """A judgement is something the attempt made; an exception is its absence."""
    config, pool = mapped(KEYLESS)

    def explode(this: Try) -> Judgement[str]:
        raise RuntimeError("the socket died")

    with pytest.raises(RuntimeError):
        escalate(config, pool, contract(), explode)


def test_capacity_reaches_every_rung_of_every_family(key: None) -> None:
    """The gap #23 closed one family at a time, held across the whole climb."""
    from mcgyvr.capacity import Capacity

    config, pool = mapped(with_budgets(MIXED, max_escalations=2))
    capacity = Capacity.of(config)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED)

    escalate(config, pool, contract(), attempts, capacity=capacity)

    assert len(attempts.seen) == 3
    assert all(t.capacity is capacity for t in attempts.seen)


# --- the decision is readable without running anything ---------------------


def test_the_pool_command_prints_the_ceilings_that_bound_a_task(
    tmp_path: Path,
    key: None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ladder printed without its ceilings reads as though it will all be tried."""
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(with_budgets(MIXED, max_attempts=2), encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(path))

    assert main(["pool"]) == 0

    out = capsys.readouterr().out
    assert "1 escalation(s)" in out
    assert "2 of these 3 rung(s)" in out
    assert "2 attempt(s)" in out
    assert "budgets.max_attempts" in out


def test_the_pool_command_says_where_an_unset_ceiling_comes_from(
    tmp_path: Path,
    key: None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(MIXED, encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(path))

    assert main(["pool"]) == 0

    out = capsys.readouterr().out
    assert "the ladder's own budget" in out
    assert "3 attempt(s)" in out


def test_a_family_is_a_cost_class_and_the_ascent_names_no_machine(key: None) -> None:
    """Nothing above the execution seam learns where work runs (#20)."""
    config, pool = mapped(MIXED)

    route = ascent(config, pool, contract())

    rendered = repr(route)
    elsewhere = ("localhost", "192.168.1.20", "api.example.com", "workstation")
    for where in elsewhere:
        assert where not in rendered


def test_a_family_is_the_catalogs_and_the_ascent_restates_nothing() -> None:
    """The one definition of the rule stays the one definition."""
    config, pool = mapped(KEYLESS)

    route = ascent(config, pool, contract())

    assert isinstance(route.floor, Family)
    assert route.families == tuple(
        f for f in catalog().families if f.rank >= LOCAL.rank
    )
