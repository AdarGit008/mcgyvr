"""Work the configured verifier wrote is reviewed by the next-best unit instead.

The case: ``verifier.unit`` names the dearest rung, the work
climbs to it, and the rung that wrote the accepted change is the one named to
review it. A model does not review its own output, so nothing was asked and
the change was accepted ``unverified`` — while the rung below, which could
have reviewed it, sat unasked. The promises, none of which names a machine:

* **A stand-in reviews.** When the unit ``verifier.unit`` names serves the
  model that wrote the change, the next-best unit that did not write it
  reviews instead: the nearest usable rung below the configured verifier on
  the climb, then the nearest above it. An approval is ``verified``, and the
  judgement — the result file's detail and the journal's correction — names
  the stand-in and says why it stood in.
* **The independence rule is not bent.** A rung serving the builder's model,
  under any unit name or spelling, never stands in.
* **A stand-in never costs more than the review the operator chose.** A local
  rung may always stand in; a hosted one only for a hosted ``verifier.unit``,
  and only from below it.
* **No stand-in, no review, said plainly.** The work is accepted
  ``unverified`` with a note that the reviewer wrote the change and no other
  unit was available; nothing is asked.
* **Nothing else moves.** A configured verifier that did not write the change
  reviews it, as before.

Every machine here is invented, and the one thing substituted is a model.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.decision import BoolAnswer, Decision, Noul, ScoreAnswer
from mcgyvr.escalate import Assurance
from mcgyvr.local_pool import Protocol, Rung, source_map
from mcgyvr.route import Try, Verdict
from mcgyvr.runner import Completion, StopReason
from mcgyvr.verify import NoReviewer, Reviewer, reviewers_for
from tests import livejournal as lj

TARGET = "src/pkg/value.py"
BASE = "VALUE = 0\n"

KEY = "ZETA_TEST_KEY"

#: The case's shape: two hosted rungs, the dearer one named to review.
HOSTED_PAIR = f"""\
units:
  flash:
    address: https://flash.example.invalid
    model: zeta-flash
    rig: cloud-a
    api_key_env: {KEY}
    window: 32768
  pro:
    address: https://pro.example.invalid
    model: zeta-pro
    rig: cloud-b
    api_key_env: {KEY}
    window: 32768
ladder:
- flash
- pro
verifier:
  unit: pro
"""

#: Three keyless rungs, cheapest first, three different models.
THREE_LOCAL = """\
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
    window: 32768
  middle:
    address: http://localhost:18002
    model: kappa-coder:14b
    rig: bench-b
    width: 1
    window: 32768
  big:
    address: http://localhost:18003
    model: zeta-coder:32b
    rig: bench-c
    width: 1
    window: 32768
ladder:
- small
- middle
- big
"""

#: A rung between the two that serves the builder's model under another unit
#: name and another spelling of the model.
WITH_A_TWIN = """\
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
    window: 32768
  twin:
    address: http://localhost:18003
    model: registry.example/Acme-Coder:7b:latest
    rig: bench-c
    width: 1
    window: 32768
  big:
    address: http://localhost:18002
    model: zeta-coder:32b
    rig: bench-b
    width: 1
    window: 32768
ladder:
- small
- twin
- big
"""

ONE_RUNG = """\
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
    window: 32768
ladder:
- small
"""

#: A keyless rung, then a hosted one serving another model.
LOCAL_THEN_HOSTED = f"""\
units:
  small:
    address: http://localhost:18001
    model: acme-coder:7b
    rig: bench-a
    width: 1
    window: 32768
  hosted:
    address: https://api.example.invalid
    model: zeta-large
    rig: cloud
    api_key_env: {KEY}
    window: 32768
ladder:
- small
- hosted
"""

#: Two hosted rungs, the cheaper one named to review.
HOSTED_BELOW_A_DEARER_ONE = HOSTED_PAIR.replace("unit: pro", "unit: flash")

CONTRACT = f"""
id: value
task_type: code
task: Set VALUE to 1.
target: {TARGET}
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q \\"VALUE = 1\\" {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
  attempts: 1
scope:
  allow: ["src/**"]
"""

ACCEPTED = "```python\nVALUE = 1\n```\n"
REJECTED = "```python\nVALUE = 2\n```\n"


@pytest.fixture(autouse=True)
def _hosted_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted rungs are offered, and no session or home leaks in."""
    monkeypatch.setenv(KEY, "invented")
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text(BASE, encoding="utf-8")
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "base")):
        subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            env={**os.environ, **lj.IDENTITY},
        )
    return root


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="m",
        source="s",
        protocol=Protocol.OPENAI,
        max_output_tokens=512,
        latency_s=0.0,
    )


def _builders(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer the builders' dispatches from a script, in draw order."""
    scripted = list(replies)
    sent: list[str] = []

    def fake(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(rung)
        if not scripted:
            raise AssertionError(f"an unscripted worker dispatch to {rung!r}")
        return _completion(scripted.pop(0))

    lj.patch_dispatch(monkeypatch, fake)
    return sent


def _no_prose_review(monkeypatch: pytest.MonkeyPatch) -> None:
    import mcgyvr.verify as verify

    def fake(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        raise AssertionError(f"a prose review was asked of {rung!r}")

    monkeypatch.setattr(verify, "dispatch", fake)


def _typed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Approve every typed question; record which rung was asked."""
    import mcgyvr.decision as decision

    asked: list[str] = []

    def fake(source_map, rung, state, questions, **kwargs):  # type: ignore[no-untyped-def]
        asked.append(rung)
        answers: dict[str, Any] = {}
        for name, question in questions.items():
            answers[name] = (
                BoolAnswer(True, 0.9, 0.8)
                if isinstance(question, Noul)
                else ScoreAnswer(level=0.0, probabilities={"low": 1.0}, confidence=0.8)
            )
        return Decision(answers=answers)

    monkeypatch.setattr(decision, "classify_rung", fake)
    return asked


def _chosen(text: str, builder: str) -> Reviewer | NoReviewer:
    config = parse_config(text)
    return reviewers_for(config, source_map(config))(builder)


def _attempt_on(repo: Path, text: str, rung: str) -> Any:
    """One attempt on ``rung`` the way ``mcgyvr direct`` builds it."""
    from mcgyvr.drive import worker_attempt
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    config = parse_config(text)
    pool = source_map(config)
    offered = pool.get(rung)
    assert offered is not None, f"{rung!r} is not offered"
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(
            config,
            pool,
            load_contract(CONTRACT),
            sandbox,
            reviewers=reviewers_for(config, pool),
        )
        return attempt(Try(rung=Rung(name=rung, model=offered.model), attempt=1, of=1))


# --- who stands in -----------------------------------------------------------


def test_work_built_by_the_verifier_unit_is_reviewed_by_the_rung_below_it() -> None:
    chosen = _chosen(HOSTED_PAIR, "pro")

    assert isinstance(chosen, Reviewer), chosen
    assert chosen.unit == "flash"
    assert chosen.model == "zeta-flash"
    assert "`verifier.unit` 'pro'" in chosen.label, chosen.label
    assert "wrote this change" in chosen.label, chosen.label


def test_the_nearest_rung_below_the_verifier_stands_in_before_any_above_it() -> None:
    from mcgyvr.verify import stand_in_rung

    config = parse_config(THREE_LOCAL + "verifier:\n  unit: middle\n")
    assert stand_in_rung(config, source_map(config), "middle", "middle") == "small"


def test_with_nothing_below_the_verifier_the_nearest_rung_above_stands_in() -> None:
    from mcgyvr.verify import stand_in_rung

    config = parse_config(THREE_LOCAL + "verifier:\n  unit: small\n")
    assert stand_in_rung(config, source_map(config), "small", "small") == "middle"


def test_a_rung_serving_the_builders_model_never_stands_in() -> None:
    from mcgyvr.verify import stand_in_rung

    config = parse_config(WITH_A_TWIN + "verifier:\n  unit: small\n")
    assert stand_in_rung(config, source_map(config), "small", "small") == "big"

    only_the_twin = WITH_A_TWIN.replace("- big\n", "") + "verifier:\n  unit: small\n"
    chosen = _chosen(only_the_twin, "small")
    assert isinstance(chosen, NoReviewer), chosen


def test_a_verifier_unit_serving_the_builders_model_is_stood_in_for() -> None:
    """One model under two unit names is one model: the twin wrote it too."""
    chosen = _chosen(WITH_A_TWIN + "verifier:\n  unit: twin\n", "small")

    assert isinstance(chosen, Reviewer), chosen
    assert chosen.unit == "big"
    assert "`verifier.unit` 'twin'" in chosen.label, chosen.label


def test_a_hosted_rung_never_stands_in_for_a_local_verifier() -> None:
    chosen = _chosen(LOCAL_THEN_HOSTED + "verifier:\n  unit: small\n", "small")
    assert isinstance(chosen, NoReviewer), chosen


def test_a_hosted_rung_dearer_than_a_hosted_verifier_never_stands_in() -> None:
    chosen = _chosen(HOSTED_BELOW_A_DEARER_ONE, "flash")
    assert isinstance(chosen, NoReviewer), chosen


def test_with_no_other_unit_the_reason_says_the_reviewer_wrote_the_change() -> None:
    chosen = _chosen(ONE_RUNG + "verifier:\n  unit: small\n", "small")

    assert isinstance(chosen, NoReviewer), chosen
    assert "`verifier.unit` 'small'" in chosen.reason, chosen.reason
    assert "wrote this change" in chosen.reason, chosen.reason
    assert "no other unit" in chosen.reason, chosen.reason


def test_a_verifier_that_did_not_write_the_change_reviews_it_as_before() -> None:
    chosen = _chosen(HOSTED_PAIR, "flash")

    assert isinstance(chosen, Reviewer), chosen
    assert chosen.unit == "pro"
    assert chosen.model == "zeta-pro"
    assert chosen.label == "pro", "a configured reviewer was called a stand-in"


# --- the driver ---------------------------------------------------------------


def test_the_stand_ins_approval_is_verified_and_says_who_reviewed_and_why(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _builders(monkeypatch, ACCEPTED)
    _no_prose_review(monkeypatch)
    typed = _typed(monkeypatch)

    judgement = _attempt_on(repo, HOSTED_PAIR, "pro")

    assert judgement.verdict is Verdict.PASSED, judgement.detail
    assert judgement.assurance is Assurance.VERIFIED, judgement.detail
    assert set(typed) == {"flash"}, f"asked on {typed}"
    assert "verified by flash" in judgement.detail, judgement.detail
    assert "`verifier.unit` 'pro'" in judgement.detail, judgement.detail
    assert "wrote this change" in judgement.detail, judgement.detail


def test_with_no_stand_in_the_work_is_unverified_and_nothing_is_asked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _builders(monkeypatch, ACCEPTED)
    _no_prose_review(monkeypatch)
    typed = _typed(monkeypatch)

    judgement = _attempt_on(repo, ONE_RUNG + "verifier:\n  unit: small\n", "small")

    assert judgement.verdict is Verdict.PASSED, judgement.detail
    assert judgement.assurance is Assurance.UNVERIFIED
    assert "wrote this change" in judgement.detail, judgement.detail
    assert "no other unit" in judgement.detail, judgement.detail
    assert typed == [], "a model was asked with no independent reviewer"


# --- what a caller sees ---------------------------------------------------------


def test_the_result_and_the_journal_name_the_stand_in_after_a_climb(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """flash is rejected, pro is accepted, and flash reviews pro's work."""
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(HOSTED_PAIR, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "value.yaml", CONTRACT)
    result = tmp_path / "result.json"
    journal = tmp_path / "journal"
    built_on = _builders(monkeypatch, REJECTED, ACCEPTED)
    _no_prose_review(monkeypatch)
    typed = _typed(monkeypatch)

    code = lj.main(
        lj.run_args(
            contract,
            repo,
            config,
            "--result",
            str(result),
            "--record",
            str(journal),
            "--session",
            "agent-a",
        )
    )

    assert code == 0
    assert built_on == ["flash", "pro"], built_on
    assert set(typed) == {"flash"}, f"asked on {typed}"
    written = json.loads(result.read_text(encoding="utf-8"))
    assert written["assurance"] == "verified", written
    # The judgement's words are the run's own `detail`, as they are the
    # accepted attempt's: where the work landed is `delivery`'s (#183).
    assert "verified by flash" in written["detail"], written["detail"]
    assert written["delivery"].startswith("not committed"), written["delivery"]
    accepted = written["attempts"][-1]
    assert accepted["rung"] == "pro", accepted
    assert "verified by flash" in accepted["detail"], accepted["detail"]
    assert "`verifier.unit` 'pro'" in accepted["detail"], accepted["detail"]

    lines = [
        json.loads(line)
        for line in (journal / "agent-a.jsonl").read_text("utf-8").splitlines()
    ]
    said = [
        row["detail"]
        for row in lines
        if row.get("attempt_id", "").endswith(":pro:1") and "detail" in row
    ]
    assert any(
        "verified by flash" in detail and "`verifier.unit` 'pro'" in detail
        for detail in said
    ), said
