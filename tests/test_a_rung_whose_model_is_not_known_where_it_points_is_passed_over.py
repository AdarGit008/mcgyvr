"""A rung whose model is not known where it points is passed over, and said.

A rung that answers ``404`` with the code ``model_not_found`` was asked for a
model its address does not know: a hub that no longer has the model in its
pool, a provider that never had it, a name typed wrong. Nothing was asked of
a model, and the request is not pinned to that one, so the dispatch ends as
:class:`~mcgyvr.capacity.SlotUnavailableError`: the rung is asked once, no
attempt is spent, the cooldown does not learn it as failing, and the climb
tries the next rung at once. The same rule for every rung of the ladder,
with a key or without, whatever it points to.

A rung skipped so is skipped every time, and a mistyped name would be skipped
without a word. So each such dispatch writes one line to the run's log (its
standard error) naming the rung and the model it does not know.

A relief rung's ``404`` is unchanged: a stale rung, a full rung, with no
line. Any other ``404`` is still the rung's error.

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.escalate import Delivered, escalate
from mcgyvr.pool import source_map
from mcgyvr.route import Verdict
from mcgyvr.runner import (
    BackendError,
    ReliefUnavailableError,
    Request,
    RunnerError,
    UnknownModelError,
    dispatch,
)
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests.test_a_rung_whose_model_the_hub_cannot_place_is_passed_over import (
    CONTRACT,
    KEY,
    OTHER,
    POOLED,
    answer,
    answering,
    error,
    setup,
)

UNKNOWN = error(404, "model_not_found")
RUNG_ID = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"
RIDE = f"hitchhike-{RUNG_ID}"
LOCAL_MODEL = "qwen2.5-coder-3b"


def mixed(address: str) -> str:
    """A keyed rung, a keyless one and a relief rung, all at ``address``."""
    return f"""
units:
  pooled:
    address: {address}
    model: {POOLED}
    api_key_env: HUB_KEY
    width: 1
  local_fast:
    address: {address}
    model: {LOCAL_MODEL}
    width: 1
ladder: [local_fast, pooled]
fanout: idle
relief:
  {RIDE}:
    address: {address}
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: within
    busy_answers:
      - status: 503
        code: hitchhike_not_served_yet
      - status: 503
        code: hitchhike_host_away
      - status: 404
        code: model_not_found
"""


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", KEY)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
    for args in (("init", "-q"), ("add", "-A"), (*identity, "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def ask(address: str, rung: str, tmp_path: Path) -> tuple[Capacity, Any]:
    config = parse(mixed(address))
    capacity = Capacity.of(config, root=tmp_path / "slots")
    request = Request(prompt="hello", max_output_tokens=8)
    try:
        return capacity, dispatch(source_map(config), rung, request, capacity=capacity)
    except Exception as exc:
        return capacity, exc


def notes(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


@pytest.mark.parametrize(
    ("rung", "model"),
    [("pooled", POOLED), ("local_fast", LOCAL_MODEL)],
    ids=["keyed", "keyless"],
)
def test_a_model_the_address_does_not_know_is_a_full_rung_asked_once_and_said(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rung: str, model: str
) -> None:
    seen: list[str] = []
    with answering(*UNKNOWN, seen) as address:
        capacity, outcome = ask(address, rung, tmp_path)

    assert isinstance(outcome, UnknownModelError)
    assert isinstance(outcome, SlotUnavailableError)
    # Not a runner error, so the cooldown does not learn the rung as failing.
    assert not isinstance(outcome, RunnerError)
    assert seen == [model], "the rung was asked once and not again"
    assert capacity.load(rung) == 0, "the slot it held is given back"
    (said,) = notes(capsys)
    assert said.startswith("note: ")
    assert repr(rung) in said and repr(model) in said
    assert "does not know" in said
    assert KEY not in said and "hello" not in said
    assert repr(rung) in str(outcome) and repr(model) in str(outcome)


@pytest.mark.parametrize(
    "refusal",
    [error(404, "not_found"), (404, b"{}"), error(400, "model_not_found")],
    ids=["404-other", "404-no-code", "400"],
)
def test_any_other_answer_is_still_the_rungs_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], refusal: tuple[int, bytes]
) -> None:
    seen: list[str] = []
    with answering(*refusal, seen) as address:
        _, outcome = ask(address, "pooled", tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)
    assert notes(capsys) == []


def test_a_relief_rungs_404_is_a_stale_rung_as_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    with answering(*UNKNOWN, seen) as address:
        _, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, ReliefUnavailableError)
    assert not isinstance(outcome, UnknownModelError)
    assert notes(capsys) == []


def test_the_climb_tries_the_next_rung_at_once_and_the_log_says_why(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    asked_hub: list[str] = []
    asked_other: list[str] = []
    good = answer(OTHER, "```python\nVALUE = 1\n```")
    with (
        answering(*UNKNOWN, asked_hub) as hub,
        answering(*good, asked_other) as other,
    ):
        config = parse(setup(hub, other))
        pool = source_map(config)
        contract = load_contract(CONTRACT)
        with TempDirSandbox(repo) as sandbox:
            outcome = escalate(
                config, pool, contract, worker_attempt(config, pool, contract, sandbox)
            )

    assert isinstance(outcome, Delivered), outcome
    assert outcome.rung == "other"
    assert asked_hub == [POOLED], "the rung was asked once"
    assert asked_other == [OTHER]
    assert [(a.rung, a.verdict) for a in outcome.history] == [
        ("pooled", Verdict.DECLINED),
        ("other", Verdict.PASSED),
    ]
    assert (outcome.attempts_spent, outcome.escalations) == (1, 0)
    said = [line for line in notes(capsys) if "does not know" in line]
    assert len(said) == 1
    assert repr("pooled") in said[0] and repr(POOLED) in said[0]
