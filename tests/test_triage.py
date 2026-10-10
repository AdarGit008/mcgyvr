"""The routing triage: typed questions name a task type and a semantic floor,
and the ladder climbs from that floor without ever being reordered.

The transport is stubbed everywhere here, the same way
``tests/test_decision.py`` stubs it — the properties under test are the
question shape, the floor clamping, and the invariant that the classifier only
names the entry point. :func:`mcgyvr.route.plan` and
:func:`mcgyvr.escalate.ascent` produce the same ladder order whatever the
classifier answers; a bad hint degrades to a normal climb.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import decision as decision_module
from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Score, ScoreAnswer
from mcgyvr.escalate import ascent
from mcgyvr.local_pool import Endpoint, Protocol, SourceMap, source_map
from mcgyvr.triage import (
    FLOOR_QUESTION,
    TASK_TYPE_QUESTION,
    Triage,
    TriageError,
    build_questions,
    floor_for,
    read_triage,
    triage,
)

LOCAL = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=2,
    credential_env=None,
)

TWO_FAMILIES = """\
units:
  local_qwen:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    rig: vendor
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_qwen
- api_big
"""

# Three rungs so that "no reordering" is observable inside a family as well as
# across it: the local family holds two rungs in the order the config wrote
# them, and the api family one. The whole ladder is family-grouped, so the
# suffix property below reads cleanly off ``Ascent.rungs`` too.
THREE_RUNG = """\
units:
  local_small:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
  local_big:
    address: http://localhost:11434
    model: qwen2.5-coder:14b
    rig: workstation
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    rig: vendor
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_small
- local_big
- api_big
"""

BUG_FIX = """\
id: fix-pager
task_type: bug_fix
task: The pager drops the last line of every file. Fix it.
target: src/pkg/pager.py
stop_conditions:
  - The defect cannot be reproduced from the demonstrating command.
acceptance: ["pytest -q"]
demonstration: ["pytest -q tests/test_pager.py::test_last_line"]
scope:
  allow: ["src/**/*.py"]
"""


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential for the api source, assembled rather than written literally."""
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


def mapped(text: str) -> tuple[Config, SourceMap]:
    config = parse(text)
    return config, source_map(config)


def contract(text: str = BUG_FIX) -> Contract:
    return load_contract(text)


def entry(token: str, logprob: float) -> dict[str, Any]:
    return {"token": token, "logprob": logprob}


def logprobs_document(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "logprobs": {
                    "content": [{"token": entries[0]["token"], "top_logprobs": entries}]
                },
                "finish_reason": "length",
            }
        ]
    }


def answered(task_type: str, level: float) -> Decision:
    """A decision whose two answers are already read, for the pure reader."""
    return Decision(
        answers={
            TASK_TYPE_QUESTION: ChoiceAnswer(
                choice=task_type, probabilities={task_type: 1.0}, confidence=1.0
            ),
            FLOOR_QUESTION: ScoreAnswer(level=level, probabilities={}, confidence=1.0),
        }
    )


# --- the questions ---------------------------------------------------------


def test_a_triage_asks_for_the_task_type_over_the_catalog() -> None:
    known = catalog()
    question = build_questions(known)[TASK_TYPE_QUESTION]
    assert isinstance(question, Choice)
    assert set(question.options) == set(known.names)


def test_a_triage_scores_the_floor_over_the_family_order() -> None:
    known = catalog()
    question = build_questions(known)[FLOOR_QUESTION]
    assert isinstance(question, Score)
    # One level per family, cheapest first, so the expected level *is* the
    # family's rank and the mapping is the family order, not a second table.
    assert question.levels == tuple(f.doc for f in known.families)


# --- the floor -------------------------------------------------------------


def test_a_hint_is_never_cheaper_than_the_types_own_floor() -> None:
    known = catalog()
    for task_type in known.task_types:
        for hinted in known.families:
            assert floor_for(task_type, hinted).rank >= task_type.starts_on.rank


def test_a_hint_cheaper_than_the_types_floor_degrades_to_a_normal_climb() -> None:
    known = catalog()
    bug_fix = known.require("bug_fix")
    assert floor_for(bug_fix, known.family("deterministic")) == known.family("local")


def test_a_hint_dearer_than_the_types_floor_raises_the_entry() -> None:
    known = catalog()
    bug_fix = known.require("bug_fix")
    assert floor_for(bug_fix, known.family("api")) == known.family("api")


# --- the reader ------------------------------------------------------------


def test_a_triage_reads_the_task_type_and_the_hinted_floor() -> None:
    known = catalog()
    result = read_triage(known, answered("bug_fix", 2.0))
    assert result.task_type.name == "bug_fix"
    assert result.floor.name == "api"


def test_a_triage_refuses_an_answer_that_is_not_the_typed_shape() -> None:
    known = catalog()
    wrong = Decision(
        answers={
            TASK_TYPE_QUESTION: ScoreAnswer(
                level=0.0, probabilities={}, confidence=1.0
            ),
            FLOOR_QUESTION: ScoreAnswer(level=0.0, probabilities={}, confidence=1.0),
        }
    )
    with pytest.raises(TriageError):
        read_triage(known, wrong)


# --- the network call ------------------------------------------------------


class Sent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []


def test_triage_sends_one_logprobs_request_per_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = Sent()

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.calls.append(payload)
        content = payload["messages"][0]["content"]
        if "Options:" in content:
            return logprobs_document([entry("A", 0.0)])
        return logprobs_document([entry("2", 0.0)])

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    result = triage(LOCAL, "qwen", {"task": "fix the pager"})

    assert len(sent.calls) == 2
    assert isinstance(result, Triage)
    # The first task type in the catalog, and a floor of the dearest family.
    assert result.task_type.name == "format"
    assert result.floor.name == "api"
    assert sent.calls[0]["max_tokens"] == 1
    assert sent.calls[0]["logprobs"] is True


# --- the invariant ---------------------------------------------------------


def test_the_climb_stays_a_suffix_whatever_the_classifier_names(
    key: None,
) -> None:
    """The classifier may only name the entry point, never reorder the ladder.

    For a fixed contract the normal ascent starts on the type's own floor. For
    every family the classifier could name as the floor, the resulting ascent
    is exactly a suffix of the normal one — the same plans in the same order,
    with only cheaper leading families dropped. A bad hint (cheaper than the
    type's floor) is clamped back to the normal climb.
    """
    config, pool = mapped(THREE_RUNG)
    c = contract(BUG_FIX)
    normal = ascent(config, pool, c)
    bug_fix = catalog().require("bug_fix")

    for hinted in catalog().families:
        floor = floor_for(bug_fix, hinted)
        raised = ascent(config, pool, c, floor=floor)
        assert raised.plans == normal.plans[len(normal.plans) - len(raised.plans) :]
        assert raised.rungs == normal.rungs[len(normal.rungs) - len(raised.rungs) :]


def test_a_bad_hint_degrades_to_the_normal_climb(key: None) -> None:
    """The cheaper-than-the-floor hint is the one that must not move anything."""
    config, pool = mapped(TWO_FAMILIES)
    c = contract(BUG_FIX)
    bug_fix = catalog().require("bug_fix")
    floor = floor_for(bug_fix, catalog().family("deterministic"))

    assert floor == catalog().family("local")
    assert ascent(config, pool, c, floor=floor).plans == ascent(config, pool, c).plans


def test_a_dearer_hint_raises_the_entry_and_never_reorders(key: None) -> None:
    """Raising the floor drops cheap families and keeps every surviving rung."""
    config, pool = mapped(THREE_RUNG)
    c = contract(BUG_FIX)
    floor = floor_for(catalog().require("bug_fix"), catalog().family("api"))

    raised = ascent(config, pool, c, floor=floor)
    assert raised.families == (catalog().family("api"),)
    assert raised.rungs == ("api_big",)
