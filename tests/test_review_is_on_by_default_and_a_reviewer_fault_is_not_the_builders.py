"""Model work is reviewed unless the config says not to, and a review is honest.

The promises, none of which names a machine:

* **Review is on by default.** A config that does not mention ``verifier``
  reviews model work; only ``verifier.enabled: false`` switches it off. A
  config that names ``verifier.unit`` keeps reviewing on that unit.
* **With no unit named, the reviewer picks itself.** It is the next dearer
  local rung of the climb whose model is not the builder's — never a hosted
  one, which reviews only when ``verifier.unit`` names it. Where no rung qualifies the
  work is still accepted, stamped ``unverified`` where a caller sees it, not
  silently.
* **The typed verdict is the default.** It is read from a reviewer that serves
  next-token probabilities; one that does not is asked in prose instead.
* **The typed checks of the gate run on the reviewer, and never reject.**
* **A reviewer's fault is never the builder's.** A reviewer that could not be
  asked, gave no verdict, stopped at its output cap or turned out to be the
  builder leaves the gate's acceptance standing, labelled ``unverified``.
* **One model under two spellings is one model.** A weights file and the name
  it carries, a Windows path, a registry prefix: none of them makes a model
  independent of itself.

Every machine here is invented, and the one thing substituted is a model.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import Family
from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.decision import BoolAnswer, Decision, DecisionError, Noul, ScoreAnswer
from mcgyvr.escalate import Assurance, Opinion, Review, judge
from mcgyvr.gate import GateResult
from mcgyvr.pool import Protocol, Rung, source_map
from mcgyvr.route import Try, Verdict
from mcgyvr.runner import Completion, StopReason, TransportError

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/value.py"
BASE = "VALUE = 0\n"

#: Two keyless rungs on two invented hosts, cheapest first, two different
#: models. The smallest ladder on which a reviewer can be picked at all.
TWO_RUNGS = """\
profile: dev
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
  big:
    address: http://localhost:18002
    model: zeta-coder:32b
    rig: bench-b
    width: 1
ladder:
- small
- big
"""

#: The same ladder with a rung between the two that serves the builder's model
#: under another unit name and another spelling of the model.
WITH_A_TWIN = """\
profile: dev
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
  twin:
    address: http://localhost:18003
    model: registry.example/Acme-Coder:7b:latest
    rig: bench-c
    width: 1
  big:
    address: http://localhost:18002
    model: zeta-coder:32b
    rig: bench-b
    width: 1
ladder:
- small
- twin
- big
"""

ONE_RUNG = """\
profile: dev
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
ladder:
- small
"""

CONTRACT = f"""
id: value
task_type: function_implementation
task: Set VALUE to 1.
target: {TARGET}
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q \\"VALUE = 1\\" {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

ACCEPTED = "```python\nVALUE = 1\n```\n"

LOCAL = Family(name="local", rank=1, doc="a model on the operator's own machine")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text(BASE, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _completion(
    text: str, stop: StopReason = StopReason.COMPLETE, raw: str = "stop"
) -> Completion:
    return Completion(
        text=text,
        stop_reason=stop,
        raw_stop_reason=raw,
        model="m",
        source="s",
        protocol=Protocol.OPENAI,
        max_output_tokens=512,
        latency_s=0.0,
    )


def _worker_replies(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer the builder's dispatches from a script."""
    import mcgyvr.drive as drive

    scripted = list(replies)
    sent: list[str] = []

    def fake(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(rung)
        if not scripted:
            raise AssertionError(f"an unscripted worker dispatch to {rung!r}")
        return _completion(scripted.pop(0))

    monkeypatch.setattr(drive, "dispatch", fake)
    return sent


def _prose_reviews(
    monkeypatch: pytest.MonkeyPatch, *replies: Completion
) -> list[tuple[str, str]]:
    """Answer the reviewer's prose dispatches to a rung; record (rung, prompt)."""
    import mcgyvr.verify as verify

    scripted = list(replies)
    asked: list[tuple[str, str]] = []

    def fake(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        asked.append((rung, request.prompt))
        if not scripted:
            raise AssertionError(f"an unscripted review dispatch to {rung!r}")
        return scripted.pop(0)

    monkeypatch.setattr(verify, "dispatch", fake)
    return asked


def _typed(
    monkeypatch: pytest.MonkeyPatch,
    *,
    verdict: bool = True,
    jev_yes: bool = True,
    raises: Exception | None = None,
) -> list[tuple[str, tuple[str, ...]]]:
    """Answer the reviewer's typed questions; record (rung, question names).

    Patched at :func:`mcgyvr.decision.classify_rung`, which the reviewer's
    typed half reaches through :func:`~mcgyvr.decision.classify_for` when no
    ``jev.unit`` is bound.
    """
    import mcgyvr.decision as decision

    asked: list[tuple[str, tuple[str, ...]]] = []

    def fake(source_map, rung, state, questions, **kwargs):  # type: ignore[no-untyped-def]
        asked.append((rung, tuple(questions)))
        if raises is not None:
            raise raises
        answers: dict[str, Any] = {}
        for name, question in questions.items():
            if name == "verdict":
                answers[name] = BoolAnswer(verdict, 0.9 if verdict else 0.1, 0.8)
            elif isinstance(question, Noul):
                answers[name] = BoolAnswer(jev_yes, 0.9 if jev_yes else 0.1, 0.8)
            else:
                answers[name] = ScoreAnswer(
                    level=0.0 if jev_yes else 2.0,
                    probabilities={"low": 1.0} if jev_yes else {"high": 1.0},
                    confidence=0.8,
                )
        return Decision(answers=answers)

    monkeypatch.setattr(decision, "classify_rung", fake)
    return asked


def _attempt_on(repo: Path, text: str, rung: str, model: str) -> Any:
    """One attempt on ``rung`` the way ``mcgyvr run`` builds it."""
    from mcgyvr.drive import worker_attempt
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from mcgyvr.verify import reviewers_for

    config = parse_config(text)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(
            config, pool, contract, sandbox, reviewers=reviewers_for(config, pool)
        )
        return attempt(Try(rung=Rung(name=rung, model=model), attempt=1, of=1))


# --- the config ------------------------------------------------------------


def test_a_config_that_does_not_mention_review_reviews() -> None:
    assert parse_config(TWO_RUNGS).data["verifier"]["enabled"] is True


def test_review_enabled_with_no_unit_loads_instead_of_being_refused() -> None:
    config = parse_config(TWO_RUNGS + "verifier:\n  enabled: true\n")
    assert config.data["verifier"]["unit"] is None


def test_review_switched_off_asks_no_reviewer_and_says_why() -> None:
    from mcgyvr.verify import NoReviewer, reviewers_for

    config = parse_config(TWO_RUNGS + "verifier:\n  enabled: false\n")
    chosen = reviewers_for(config, source_map(config))("small")
    assert isinstance(chosen, NoReviewer)
    assert "verifier.enabled: false" in chosen.reason


def test_a_named_unit_with_no_model_reviews_with_the_units_own_model() -> None:
    config = parse_config(TWO_RUNGS + "verifier:\n  unit: big\n")
    assert source_map(config).role_model("verifier") == "zeta-coder:32b"


# --- which rung reviews ----------------------------------------------------


def test_the_reviewer_is_the_next_dearer_rung_with_another_model() -> None:
    from mcgyvr.verify import reviewer_rung

    config = parse_config(TWO_RUNGS)
    pool = source_map(config)
    assert reviewer_rung(config, pool, "small") == "big"
    assert reviewer_rung(config, pool, "big") is None, "nothing is dearer"


def test_a_dearer_rung_serving_the_builders_model_is_passed_over() -> None:
    from mcgyvr.verify import reviewer_rung

    config = parse_config(WITH_A_TWIN)
    assert reviewer_rung(config, source_map(config), "small") == "big"


def test_one_model_under_two_spellings_is_one_model() -> None:
    from mcgyvr.verify import model_identity

    name = model_identity("acme-coder-7b")
    assert model_identity("/weights/acme-coder-7b.gguf") == name
    assert model_identity("C:\\weights\\acme-coder-7b.gguf") == name
    assert model_identity("/weights/acme-coder-7b-00001-of-00002.gguf") == name
    assert model_identity("acme-coder-7b.v2") != name, "a version is not a file"


# --- what a review costs the builder --------------------------------------


def test_a_reviewer_with_no_verdict_leaves_the_gates_acceptance_unverified() -> None:
    contract = load_contract(CONTRACT)
    verdict = judge(
        contract, LOCAL, GateResult(), verifier=lambda: Review.unusable("no token")
    )
    assert verdict.verdict is Verdict.PASSED, "a reviewer fault failed the builder"
    assert verdict.assurance is Assurance.UNVERIFIED
    assert verdict.reviewer_failed is True
    assert "no token" in verdict.detail


def test_an_absent_reviewer_says_why_in_the_judgement() -> None:
    contract = load_contract(CONTRACT)
    verdict = judge(contract, LOCAL, GateResult(), absent="nothing is dearer")
    assert verdict.assurance is Assurance.UNVERIFIED
    assert "nothing is dearer" in verdict.detail


def test_a_review_stopped_at_its_cap_is_not_an_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.verify import reviewers_for, verify

    config = parse_config(TWO_RUNGS)
    pool = source_map(config)
    _prose_reviews(
        monkeypatch,
        _completion(
            "APPROVE — and then the reasons ran", StopReason.TRUNCATED, "length"
        ),
    )
    chosen = reviewers_for(config, pool)("small")
    review = verify(
        load_contract(CONTRACT),
        family=LOCAL,
        gate=GateResult(),
        change="VALUE = 1\n",
        builder="acme-coder:7b",
        reviewer=chosen.model,  # type: ignore[union-attr]
        ask=chosen.ask,  # type: ignore[union-attr]
    )
    assert review.opinion is Opinion.UNUSABLE


# --- typed first, prose where the reviewer has no probabilities -------------


def _never(prompt: str) -> str:
    raise AssertionError("the prose reviewer was asked")


def test_a_reviewer_without_probabilities_is_asked_in_prose() -> None:
    from mcgyvr.verify import verify

    def decide(state: Any) -> Decision:
        raise DecisionError("the endpoint answered without logprobs content")

    review = verify(
        load_contract(CONTRACT),
        family=LOCAL,
        gate=GateResult(),
        change="VALUE = 1\n",
        builder="acme-coder:7b",
        reviewer="zeta-coder:32b",
        ask=lambda prompt: "APPROVE — the value is set.",
        decide=decide,
    )
    assert review.opinion is Opinion.AGREED


def test_an_unreachable_reviewer_is_not_asked_twice() -> None:
    from mcgyvr.verify import verify

    def decide(state: Any) -> Decision:
        raise TransportError("could not reach the reviewer")

    review = verify(
        load_contract(CONTRACT),
        family=LOCAL,
        gate=GateResult(),
        change="VALUE = 1\n",
        builder="acme-coder:7b",
        reviewer="zeta-coder:32b",
        ask=_never,
        decide=decide,
    )
    assert review.opinion is Opinion.UNUSABLE


# --- the driver -------------------------------------------------------------


def test_the_driver_reviews_on_the_picked_rung_with_a_typed_verdict(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    _prose_reviews(monkeypatch)  # any prose dispatch fails the test
    typed = _typed(monkeypatch, verdict=True)

    judgement = _attempt_on(repo, TWO_RUNGS, "small", "acme-coder:7b")

    assert judgement.verdict is Verdict.PASSED
    assert judgement.assurance is Assurance.VERIFIED, judgement.detail
    assert typed, "no typed question was asked"
    assert {rung for rung, _ in typed} == {"big"}, f"asked on {typed}"
    names = {name for _, asked in typed for name in asked}
    assert "verdict" in names, "the verdict was not asked as a typed question"
    assert "satisfies_task" in names, "the gate's typed checks were not wired"


def test_the_gates_typed_checks_never_reject(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    _prose_reviews(monkeypatch)
    _typed(monkeypatch, verdict=True, jev_yes=False)

    judgement = _attempt_on(repo, TWO_RUNGS, "small", "acme-coder:7b")

    assert judgement.verdict is Verdict.PASSED, judgement.detail
    assert judgement.assurance is Assurance.VERIFIED


def test_the_driver_falls_back_to_prose_on_the_picked_rung(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    prose = _prose_reviews(monkeypatch, _completion("APPROVE — VALUE is 1."))
    typed = _typed(monkeypatch, raises=DecisionError("no top_logprobs"))

    judgement = _attempt_on(repo, TWO_RUNGS, "small", "acme-coder:7b")

    assert judgement.assurance is Assurance.VERIFIED, judgement.detail
    assert [rung for rung, _ in prose] == ["big"]
    # The gate's typed checks and the verdict share one refused request.
    assert len(typed) == 1, f"a unit with no probabilities was asked {typed}"


def test_the_top_rung_is_accepted_unverified_and_says_why(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    _prose_reviews(monkeypatch)
    typed = _typed(monkeypatch)

    judgement = _attempt_on(repo, TWO_RUNGS, "big", "zeta-coder:32b")

    assert judgement.verdict is Verdict.PASSED
    assert judgement.assurance is Assurance.UNVERIFIED
    assert "independent" in judgement.detail, judgement.detail
    assert typed == [], "a model was asked with no independent reviewer"


def test_a_named_reviewer_that_is_the_builder_does_not_fail_the_builder(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    _prose_reviews(monkeypatch)
    typed = _typed(monkeypatch)

    judgement = _attempt_on(
        repo, TWO_RUNGS + "verifier:\n  unit: small\n", "small", "acme-coder:7b"
    )

    assert judgement.verdict is Verdict.PASSED, judgement.detail
    assert judgement.assurance is Assurance.UNVERIFIED
    assert judgement.reviewer_failed is True
    assert typed == [], "a self-review was spent"


# --- what a caller sees -----------------------------------------------------


@pytest.mark.parametrize("extra", ["", "verifier:\n  enabled: false\n"])
def test_an_unverified_acceptance_is_said_on_stderr_and_in_the_result(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: str,
) -> None:
    import json

    from mcgyvr.cli import main

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(ONE_RUNG + extra, encoding="utf-8")
    contract = tmp_path / "value.yaml"
    contract.write_text(CONTRACT, encoding="utf-8")
    result = tmp_path / "result.json"
    _worker_replies(monkeypatch, ACCEPTED)
    _prose_reviews(monkeypatch)
    _typed(monkeypatch)

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--result",
            str(result),
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    assert "(unverified)" in captured.out
    assert "UNVERIFIED" in captured.err, f"stderr was silent: {captured.err!r}"
    written = json.loads(result.read_text(encoding="utf-8"))
    assert written["assurance"] == "unverified"
    assert written["detail"], "the result does not say why the work is unverified"


# --- what a review costs, and what it tells the builder ----------------------


def _attempt_with(repo: Path, text: str, contract_text: str) -> Any:
    """One attempt on the cheapest rung with ``contract_text`` as the contract."""
    from mcgyvr.drive import worker_attempt
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from mcgyvr.verify import reviewers_for

    config = parse_config(text)
    pool = source_map(config)
    contract = load_contract(contract_text)
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(
            config, pool, contract, sandbox, reviewers=reviewers_for(config, pool)
        )
        return attempt(
            Try(rung=Rung(name="small", model="acme-coder:7b"), attempt=1, of=1)
        )


def _jev_asks(typed: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    return [rung for rung, names in typed if "satisfies_task" in names]


def test_a_draw_the_gate_rejects_costs_the_reviewer_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    prose = _prose_reviews(monkeypatch)
    typed = _typed(monkeypatch)

    failing = CONTRACT.replace("sys.exit(0)", "sys.exit(1)")
    judgement = _attempt_with(repo, TWO_RUNGS, failing)

    assert judgement.verdict is Verdict.FAILED, judgement.detail
    assert typed == [], f"a rejected draw spent reviewer requests: {typed}"
    assert prose == []


def test_the_typed_checks_are_asked_of_the_winning_draw_only(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED, ACCEPTED)
    _prose_reviews(monkeypatch)
    typed = _typed(monkeypatch)

    two_draws = TWO_RUNGS + "breadth:\n  draws: 2\n  temperature: 0.7\n"
    judgement = _attempt_with(repo, two_draws, CONTRACT)

    assert judgement.assurance is Assurance.VERIFIED, judgement.detail
    assert _jev_asks(typed) == ["big"], f"typed checks asked per draw: {typed}"


def test_a_reviewer_that_answered_an_http_error_is_not_asked_again_in_prose() -> None:
    from mcgyvr.runner import BackendError
    from mcgyvr.verify import verify

    def decide(state: Any) -> Decision:
        raise BackendError("HTTP 503 from the reviewer: the model is loading")

    asked: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return "APPROVE — the value is set."

    review = verify(
        load_contract(CONTRACT),
        family=LOCAL,
        gate=GateResult(),
        change="VALUE = 1\n",
        builder="acme-coder:7b",
        reviewer="zeta-coder:32b",
        ask=ask,
        decide=decide,
    )
    assert review.opinion is Opinion.UNUSABLE
    assert asked == [], "a backend that just errored was asked a second time"


def test_a_reviewer_without_probabilities_is_refused_once_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.verify import Reviewer, reviewers_for

    typed = _typed(monkeypatch, raises=DecisionError("no top_logprobs"))
    config = parse_config(TWO_RUNGS)
    chosen = reviewers_for(config, source_map(config))("small")
    assert isinstance(chosen, Reviewer) and chosen.decide is not None

    for _ in range(3):
        with pytest.raises(DecisionError):
            chosen.decide({"change": "VALUE = 1\n"})
    assert len(typed) == 1, "a unit with no probabilities was asked again"


def test_an_http_error_does_not_switch_the_typed_verdict_off_for_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.runner import BackendError
    from mcgyvr.verify import Reviewer, reviewers_for

    typed = _typed(monkeypatch, raises=BackendError("HTTP 503"))
    config = parse_config(TWO_RUNGS)
    chosen = reviewers_for(config, source_map(config))("small")
    assert isinstance(chosen, Reviewer) and chosen.decide is not None

    for _ in range(2):
        with pytest.raises(BackendError):
            chosen.decide({"change": "VALUE = 1\n"})
    assert len(typed) == 2, "one HTTP error switched the typed verdict off"


def test_a_typed_refusal_tells_the_retry_what_the_reviewer_found(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker_replies(monkeypatch, ACCEPTED)
    prose = _prose_reviews(monkeypatch)
    _typed(monkeypatch, verdict=False, jev_yes=False)

    judgement = _attempt_with(repo, TWO_RUNGS, CONTRACT)

    assert judgement.verdict is Verdict.FAILED, judgement.detail
    assert judgement.retry is not None
    lines = "\n".join(judgement.retry.lines)
    assert "satisfies_task" in lines, f"the retry was told only: {lines!r}"
    assert prose == [], "a refusal was paid for twice"


def test_a_picked_reviewer_on_a_sleeping_card_is_woken(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.decision as decision
    import mcgyvr.drive as drive
    from mcgyvr.runner import RefusedConnectionError

    awake: set[str] = set()

    class Waker:
        def dispatching(self, rung, send):  # type: ignore[no-untyped-def]
            try:
                return send()
            except RefusedConnectionError:
                awake.add(rung)
                return send()

    monkeypatch.setattr(drive, "wake_for_config", lambda config: Waker())

    def sleepy(source_map, rung, state, questions, **kwargs):  # type: ignore[no-untyped-def]
        if rung not in awake:
            raise RefusedConnectionError(f"nothing listens for {rung!r}")
        answers: dict[str, Any] = {}
        for name, question in questions.items():
            answers[name] = (
                BoolAnswer(True, 0.9, 0.8)
                if isinstance(question, Noul)
                else ScoreAnswer(level=0.0, probabilities={"low": 1.0}, confidence=0.8)
            )
        return Decision(answers=answers)

    monkeypatch.setattr(decision, "classify_rung", sleepy)
    _worker_replies(monkeypatch, ACCEPTED)
    _prose_reviews(monkeypatch)

    judgement = _attempt_with(repo, TWO_RUNGS, CONTRACT)

    assert awake == {"big"}, "the reviewer's card was never woken"
    assert judgement.assurance is Assurance.VERIFIED, judgement.detail


# --- an automatic reviewer is a local one ------------------------------------

#: A keyless rung, then a hosted one serving another model. The hosted rung is
#: dearer and independent, and it is still never picked by itself: asking it
#: spends money nobody chose to spend on review.
LOCAL_THEN_HOSTED = """\
profile: dev
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
  hosted:
    address: https://api.example.invalid
    model: zeta-large
    rig: cloud
    api_key_env: ZETA_TEST_KEY
ladder:
- small
- hosted
"""


def test_a_hosted_rung_is_never_picked_as_the_reviewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.verify import NoReviewer, reviewer_rung, reviewers_for

    monkeypatch.setenv("ZETA_TEST_KEY", "invented")
    config = parse_config(LOCAL_THEN_HOSTED)
    pool = source_map(config)
    assert pool.get("hosted") is not None, "the hosted rung is not offered"

    assert reviewer_rung(config, pool, "small") is None
    chosen = reviewers_for(config, pool)("small")
    assert isinstance(chosen, NoReviewer)
    assert "local" in chosen.reason, chosen.reason


def test_with_no_local_reviewer_the_work_is_unverified_and_nothing_is_asked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZETA_TEST_KEY", "invented")
    _worker_replies(monkeypatch, ACCEPTED)
    prose = _prose_reviews(monkeypatch)
    typed = _typed(monkeypatch)

    judgement = _attempt_with(repo, LOCAL_THEN_HOSTED, CONTRACT)

    assert judgement.verdict is Verdict.PASSED, judgement.detail
    assert judgement.assurance is Assurance.UNVERIFIED
    assert "local" in judgement.detail, judgement.detail
    assert typed == [] and prose == [], "a hosted rung was asked to review"


def test_a_hosted_unit_named_as_the_verifier_still_reviews(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.verify import Reviewer, reviewers_for

    monkeypatch.setenv("ZETA_TEST_KEY", "invented")
    named = LOCAL_THEN_HOSTED + "verifier:\n  unit: hosted\n"
    config = parse_config(named)
    chosen = reviewers_for(config, source_map(config))("small")
    assert isinstance(chosen, Reviewer)
    assert chosen.model == "zeta-large"


def test_init_warns_of_review_spend_only_for_a_named_hosted_reviewer() -> None:
    from types import SimpleNamespace

    from mcgyvr.initialize import ApiUnit, _limits

    hosted = ApiUnit(
        model="zeta-large",
        address="https://api.example.invalid",
        api_key_env="ZETA_TEST_KEY",
    )
    said = " ".join(
        _limits(
            SimpleNamespace(notes=(), docker=True),  # type: ignore[arg-type]
            SimpleNamespace(notes=()),  # type: ignore[arg-type]
            (hosted,),
        )
    )
    assert "may be asked to review" not in said, said
    assert "local" in said and "verifier.unit" in said, said
