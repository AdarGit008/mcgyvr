"""A refusal names the reviewer that refused, as an approval names who approved (#183).

An approval's detail says ``verified by <reviewer>: …``, with the reviewer's
label — for a stand-in, ``<unit> (a fallback for `verifier.unit` …, whose
model … wrote this change)``, so it cannot be read as the configured
verifier's approval. A refusal said only ``the verifier refused the change:
…``: a stand-in's refusal read as the configured verifier's, the one unit that
was not asked. Now a refusal is ``refused by <reviewer>: …`` with the same
label the driver hands :func:`~mcgyvr.escalate.judge` (``Reviewer.label``),
for a stand-in and an ordinary reviewer alike; with no name to give it says
``the verifier``.
"""

from __future__ import annotations

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import Review, judge
from mcgyvr.gate import GateResult
from mcgyvr.local_pool import source_map
from mcgyvr.route import Verdict
from mcgyvr.verify import Reviewer, reviewers_for

KEY = "ZETA_TEST_KEY"

#: Two hosted rungs, the dearer one named to review: when it wrote the change,
#: the rung below it stands in.
HOSTED_PAIR = f"""\
profile: dev
units:
  flash:
    address: https://flash.example.invalid
    model: zeta-flash
    rig: cloud-a
    api_key_env: {KEY}
  pro:
    address: https://pro.example.invalid
    model: zeta-pro
    rig: cloud-b
    api_key_env: {KEY}
ladder:
- flash
- pro
verifier:
  unit: pro
"""

CONTRACT = """
id: value
task_type: code
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

WHY = "the retry has no backoff"


@pytest.fixture(autouse=True)
def _hosted_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted rungs are offered."""
    monkeypatch.setenv(KEY, "invented")


def _refused_by(reviewer: str) -> str:
    """The detail of a refusal judged with ``reviewer`` named."""
    contract = load_contract(CONTRACT)
    family = catalog().family("local")
    judgement = judge(
        contract,
        family,
        GateResult(),
        verifier=lambda: Review.refused(WHY),
        reviewer=reviewer,
    )
    assert judgement.verdict is Verdict.FAILED, judgement.detail
    return judgement.detail


def _reviewer(builder: str) -> Reviewer:
    config = parse_config(HOSTED_PAIR)
    chosen = reviewers_for(config, source_map(config))(builder)
    assert isinstance(chosen, Reviewer), chosen
    return chosen


def test_a_stand_ins_refusal_names_the_stand_in_and_why_it_stood_in() -> None:
    stand_in = _reviewer("pro")
    assert stand_in.unit == "flash", stand_in

    detail = _refused_by(stand_in.label)

    assert detail == f"refused by {stand_in.label}: {WHY}", detail
    assert "`verifier.unit` 'pro'" in detail, detail
    assert "wrote this change" in detail, detail


def test_an_ordinary_reviewers_refusal_names_the_reviewer() -> None:
    reviewer = _reviewer("flash")
    assert reviewer.label == "pro", reviewer

    assert _refused_by(reviewer.label) == f"refused by pro: {WHY}"


def test_a_refusal_with_no_reviewer_named_says_the_verifier() -> None:
    assert _refused_by("") == f"refused by the verifier: {WHY}"
