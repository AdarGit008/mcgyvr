"""Under ``triage: jev`` a climb starts on the smallest unit jev says can do the job.

Before anything is spent, the unit bound to the ``jev`` role is asked one typed
``Choice``: the state is the contract and the ladder, each unit with what the
install states about it, and the options are exactly the ladder's rungs. The
climb starts on the rung it picks; the rungs below are skipped, never spent,
and escalation goes on upward from there as it always has.

* **The default asks nobody.** ``triage: none`` is the climb exactly as it was:
  jev is not asked even when one is bound, and nothing is recorded.
* **Fan-out reads what triage left.** ``idle`` may still enter on a free rung
  above the pick, and never on one below it, however free.
* **Triage never fails a contract.** No jev unit, one that cannot be reached,
  or a reply that cannot be read: the climb starts on its first rung and the
  record says why.
* **The decision is kept.** The rung, every rung's probability, the confidence
  and the model asked land on the outcome and in the run's result file.
* **It can be decided ahead of time.** ``triage_ahead`` asks about a set of
  contracts once, outside any run; a contract that stores the pick as its
  ``start_rung`` starts there on every run and jev is not asked again. A stored
  rung the ladder cannot start on is refused, never quietly replaced.

The model is the only thing substituted: :func:`mcgyvr.decision._post_json` for
jev, and the attempt function or :data:`mcgyvr.drive.dispatch` for the climb.
Every host is invented.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.capacity import Capacity
from mcgyvr.contract import dumps, loads
from mcgyvr.escalate import Assurance, Delivered, Halted, Judgement, ascent, escalate
from mcgyvr.result import RunResult
from mcgyvr.route import RouteError, Try, Verdict
from mcgyvr.triage import triage_ahead
from tests import livejournal as lj
from tests.drives import CONTRACT, contract, mapped

LADDER = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 1
    window: 32768
    output_tokens: 4096
  local_qwen-14b:
    address: http://192.168.1.20:8000
    model: qwen2.5-coder:14b
    rig: spare
    width: 1
    window: 65536
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    rig: vendor
    width: 4
    window: 200000
    api_key_env: EXAMPLE_API_KEY
  judge:
    address: http://localhost:18002
    model: example-judge:1b
    rig: workstation
    width: 1
ladder:
- local_qwen-7b
- local_qwen-14b
- api_big
max_escalations: 2
"""

JEV = "jev:\n  unit: judge\n"
TRIAGED = LADDER + JEV + "triage: jev\n"
RUNGS = ("local_qwen-7b", "local_qwen-14b", "api_big")


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


@pytest.fixture(autouse=True)
def locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Slot files are host-wide by design; tests must not share them."""
    monkeypatch.setattr(
        "mcgyvr.capacity._default_lock_dir", lambda: tmp_path / "capacity-locks"
    )


def picking(monkeypatch: pytest.MonkeyPatch, label: str) -> list[dict[str, Any]]:
    """Answer jev's question with `label` far likelier than the others.

    Returns the payloads of the triage question, so a test can read the prompt
    jev was given. Any other typed question, such as a reviewer's verdict, is
    answered the way a unit that serves no probabilities answers it.
    """
    sent: list[dict[str, Any]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        if 'Question "start"' not in payload["messages"][0]["content"]:
            raise decision.DecisionError("the endpoint answered without logprobs")
        sent.append(payload)
        others = [
            {"token": other, "logprob": -4.0} for other in "ABC" if other != label
        ]
        top = [{"token": label, "logprob": -0.05}, *others]
        return {
            "choices": [
                {
                    "index": 0,
                    "logprobs": {"content": [{"token": label, "top_logprobs": top}]},
                    "finish_reason": "length",
                }
            ]
        }

    monkeypatch.setattr(decision, "_post_json", post)
    return sent


def never_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("jev was asked")

    monkeypatch.setattr(decision, "_post_json", post)


class Recorder:
    """An attempt that answers from a script and records the rungs it was sent."""

    def __init__(self, *verdicts: Verdict) -> None:
        self._verdicts = list(verdicts)
        self.rungs: list[str] = []

    def __call__(self, this: Try) -> Judgement:
        self.rungs.append(this.rung.name)
        if not self._verdicts:
            raise AssertionError(f"an unscripted attempt on {this.rung.name!r}")
        if self._verdicts.pop(0) is Verdict.PASSED:
            return Judgement(verdict=Verdict.PASSED, assurance=Assurance.UNVERIFIED)
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")


class Dispatching(Recorder):
    """An attempt that really takes a slot on the rung it was sent to.

    ``timeout=0`` turns a dispatch at a full rung into a failure rather than
    a wait, so the rung recorded is the rung the work could actually go to.
    """

    def __init__(self, pool: Any, *verdicts: Verdict) -> None:
        super().__init__(*verdicts)
        self._pool = pool

    def __call__(self, this: Try) -> Judgement:
        assert this.capacity is not None
        with this.capacity.hold(self._pool.bind(this.rung.name), timeout=0):
            return super().__call__(this)


# --- the default is the climb as it was ---------------------------------------


def test_without_triage_jev_is_never_asked_and_the_climb_starts_on_the_first_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    never_asked(monkeypatch)
    config, pool = mapped(LADDER + JEV)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED)

    result = escalate(config, pool, contract(), attempts)

    assert config.get("triage") == "none"
    assert attempts.rungs == list(RUNGS)
    assert result.triage is None


# --- what jev is asked ---------------------------------------------------------


def test_jev_is_asked_one_choice_over_the_ladder_given_the_contract_and_its_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED)
    job = contract()

    escalate(config, pool, job, Recorder(Verdict.PASSED))

    assert len(sent) == 1, "one question, asked once"
    payload = sent[0]
    assert payload["max_tokens"] == 1
    assert payload["model"] == "example-judge:1b"
    prompt = payload["messages"][0]["content"]
    lines = prompt.splitlines()
    state = json.loads(lines[lines.index("State:") + 1])
    assert state["contract"] == job.as_dict()
    assert state["ladder"] == [
        {
            "unit": "local_qwen-7b",
            "model": "qwen2.5-coder:7b",
            "family": "local",
            "window": 32768,
            "reply_room": 4096,
        },
        {
            "unit": "local_qwen-14b",
            "model": "qwen2.5-coder:14b",
            "family": "local",
            "window": 65536,
        },
        {
            "unit": "api_big",
            "model": "vendor-large",
            "family": "api",
            "window": 200000,
        },
    ]
    assert "smallest unit that can do this job" in prompt
    assert "A: local_qwen-7b (qwen2.5-coder:7b)" in lines
    assert "B: local_qwen-14b (qwen2.5-coder:14b)" in lines
    assert "C: api_big (vendor-large)" in lines


# --- where the climb starts ----------------------------------------------------


def test_the_climb_starts_on_the_rung_jev_picks_and_the_rungs_below_are_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    result = escalate(config, pool, contract(), attempts)

    assert isinstance(result, Halted)
    assert attempts.rungs == ["local_qwen-14b", "api_big"], "7b is never tried"
    assert result.attempts_spent == 2
    assert result.escalations == 1, "escalation goes on upward from the pick"


def test_a_pass_on_the_triaged_rung_is_no_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED)

    result = escalate(config, pool, contract(), Recorder(Verdict.PASSED))

    assert isinstance(result, Delivered)
    assert result.rung == "local_qwen-14b"
    assert result.escalations == 0
    assert result.attempts_spent == 1


def test_a_triaged_start_in_a_dearer_family_makes_that_family_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picking(monkeypatch, "C")
    config, pool = mapped(TRIAGED)
    attempts = Recorder(Verdict.PASSED)

    result = escalate(config, pool, contract(), attempts)

    assert isinstance(result, Delivered)
    assert attempts.rungs == ["api_big"]
    assert [family.name for family in result.entered] == ["api"]


# --- triage and fan-out --------------------------------------------------------


def test_idle_fanout_on_a_free_ladder_starts_on_the_triaged_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED + "fanout: idle\n")
    capacity = Capacity.of(config)
    attempts = Dispatching(pool, Verdict.PASSED)

    result = escalate(config, pool, contract(), attempts, capacity=capacity)

    assert isinstance(result, Delivered)
    assert attempts.rungs == ["local_qwen-14b"]


def test_idle_fanout_moves_a_full_triaged_start_up_and_never_below_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pick is full and the rung below it is free: the work goes up.

    Without triage ``idle`` would take the free rung below; with it, that rung
    is not on the climb at all, so the first free rung at or above the pick is
    the priced one.
    """
    picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED + "fanout: idle\n")
    capacity = Capacity.of(config)
    attempts = Dispatching(pool, Verdict.PASSED)

    with capacity.hold(pool.bind("local_qwen-14b"), rung="local_qwen-14b"):
        untriaged = ascent(config, pool, contract(), capacity=capacity)
        assert untriaged.next_free_rung == "local_qwen-7b", "7b is free"

        result = escalate(config, pool, contract(), attempts, capacity=capacity)

    assert isinstance(result, Delivered)
    assert attempts.rungs == ["api_big"]
    assert capacity.load("api_big") == 0, "the entry's claim was given back"


# --- triage never fails a contract ---------------------------------------------


def test_with_no_jev_unit_bound_the_climb_starts_on_the_first_rung_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    never_asked(monkeypatch)
    config, pool = mapped(LADDER + "triage: jev\n")
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.FAILED)

    result = escalate(config, pool, contract(), attempts)

    assert attempts.rungs == list(RUNGS)
    assert result.triage is not None
    assert result.triage.rung is None
    assert "no unit is bound to the jev role" in result.triage.fallback


def _unreachable(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise ConnectionRefusedError("connection refused")


def _unreadable(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"choices": [{"index": 0, "message": {"content": "B"}}]}


@pytest.mark.parametrize(
    ("post", "named"),
    [(_unreachable, "ConnectionRefusedError"), (_unreadable, "DecisionError")],
    ids=["unreachable", "unreadable"],
)
def test_a_jev_that_cannot_be_asked_or_read_falls_back_to_the_first_rung(
    monkeypatch: pytest.MonkeyPatch, post: Any, named: str
) -> None:
    monkeypatch.setattr(decision, "_post_json", post)
    config, pool = mapped(TRIAGED)
    attempts = Recorder(Verdict.PASSED)

    result = escalate(config, pool, contract(), attempts)

    assert isinstance(result, Delivered), "triage never fails the contract"
    assert attempts.rungs == ["local_qwen-7b"]
    assert result.triage is not None
    assert result.triage.rung is None
    assert named in result.triage.fallback
    assert result.triage.probabilities == {}


# --- the record ----------------------------------------------------------------


def test_the_triage_decision_is_carried_on_the_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED)

    result = escalate(config, pool, contract(), Recorder(Verdict.PASSED))

    triaged = result.triage
    assert triaged is not None
    assert triaged.rung == "local_qwen-14b"
    assert tuple(triaged.probabilities) == RUNGS
    assert max(triaged.probabilities, key=triaged.probabilities.__getitem__) == (
        "local_qwen-14b"
    )
    assert sum(triaged.probabilities.values()) == pytest.approx(1.0)
    assert triaged.confidence is not None and 0.0 < triaged.confidence <= 1.0
    assert triaged.model == "example-judge:1b"
    assert triaged.fallback == ""


def test_a_result_file_without_triage_has_no_triage_key() -> None:
    report = RunResult(contract="c", task_type="code", target="t", session="o", run="r")

    assert "triage" not in report.as_json()


TARGET = "src/pkg/fetch.py"
BASE = "def fetch(url):\n    return url\n"
CHANGED = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"
MODEL_CONTRACT = f"""
id: retry
task_type: code
task: Give the fetch helper a retry budget named RETRY.
target: {TARGET}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
demonstration: ["sh -c 'grep -q RETRY {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
        },
    )


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: str,
    contract_text: str = MODEL_CONTRACT,
) -> tuple[int, list[str], Path]:
    """`mcgyvr run` one contract on a real repository with the model scripted.

    Returns the exit code, the rungs dispatched to, and the result file's path.
    """
    from mcgyvr.cli import main
    from tests.drives import _completion

    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / TARGET).write_text(BASE, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    contract_path = tmp_path / "retry.yaml"
    contract_path.write_text(contract_text, encoding="utf-8")
    config_path = tmp_path / "mcgyvr.yaml"
    config_path.write_text(config, encoding="utf-8")
    result_path = tmp_path / "result.json"
    dispatched: list[str] = []

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        dispatched.append(rung)
        return _completion(f"```python\n{CHANGED}```\n")

    lj.patch_dispatch(monkeypatch, fake_dispatch)
    code = main(
        [
            "run",
            str(contract_path),
            "--repo",
            str(repo),
            "--config",
            str(config_path),
            "--sandbox",
            "tempdir",
            "--result",
            str(result_path),
        ]
    )
    return code, dispatched, result_path


def test_the_triage_decision_is_written_into_the_runs_result_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    picking(monkeypatch, "B")

    code, dispatched, result_path = _run(tmp_path, monkeypatch, TRIAGED)

    assert code == 0
    assert dispatched == ["local_qwen-14b"]
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert written["rung"] == "local_qwen-14b"
    assert [a["rung"] for a in written["attempts"]] == ["local_qwen-14b"]
    triaged = written["triage"]
    assert triaged["rung"] == "local_qwen-14b"
    assert triaged["source"] == "jev"
    assert set(triaged["probabilities"]) == set(RUNGS)
    assert 0.0 < triaged["confidence"] <= 1.0
    assert triaged["model"] == "example-judge:1b"
    assert triaged["fallback"] == ""


# --- triage decided ahead of time ------------------------------------------------


def test_triage_ahead_returns_one_record_per_contract_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked whatever the config's `triage` says: this is the ahead-of-time pass."""
    sent = picking(monkeypatch, "B")
    config, pool = mapped(LADDER + JEV)
    first = contract()
    second = contract(CONTRACT.replace("id: fetch-retry", "id: fetch-timeout"))

    records = triage_ahead(config, pool, [first, second])

    assert len(sent) == 2, "one question per contract"
    assert set(records) == {"fetch-retry", "fetch-timeout"}
    for record in records.values():
        assert record.rung == "local_qwen-14b"
        assert record.source == "jev"
        assert tuple(record.probabilities) == RUNGS
        assert record.confidence is not None and record.confidence > 0.0


def test_a_rung_triaged_ahead_is_stored_on_the_contract_and_honoured_without_jev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    picking(monkeypatch, "B")
    config, pool = mapped(TRIAGED)
    record = triage_ahead(config, pool, [contract()])["fetch-retry"]
    assert record.rung is not None
    frozen = loads(dumps(replace(contract(), start_rung=record.rung)))
    never_asked(monkeypatch)
    attempts = Recorder(Verdict.FAILED, Verdict.FAILED)

    result = escalate(config, pool, frozen, attempts)

    assert frozen.start_rung == "local_qwen-14b"
    assert attempts.rungs == ["local_qwen-14b", "api_big"]
    assert result.triage is not None
    assert result.triage.rung == "local_qwen-14b"
    assert result.triage.source == "contract"


def test_a_stated_start_rung_is_honoured_with_triage_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    never_asked(monkeypatch)
    config, pool = mapped(LADDER + JEV)
    attempts = Recorder(Verdict.PASSED)

    result = escalate(
        config, pool, contract(CONTRACT + "start_rung: api_big\n"), attempts
    )

    assert isinstance(result, Delivered)
    assert attempts.rungs == ["api_big"]


def test_a_start_rung_the_ladder_does_not_list_is_refused_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    never_asked(monkeypatch)
    config, pool = mapped(TRIAGED)
    attempts = Recorder()

    with pytest.raises(RouteError, match=r"'local_qwen-32b'.*does not list"):
        escalate(
            config, pool, contract(CONTRACT + "start_rung: local_qwen-32b\n"), attempts
        )

    assert attempts.rungs == [], "nothing was dispatched"


def test_a_start_rung_whose_unit_is_not_available_is_refused_saying_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    never_asked(monkeypatch)
    monkeypatch.delenv("EXAMPLE_API_KEY")
    config, pool = mapped(TRIAGED)

    with pytest.raises(RouteError, match=r"'api_big'.*not available"):
        escalate(config, pool, contract(CONTRACT + "start_rung: api_big\n"), Recorder())


def test_a_run_whose_stored_start_rung_is_off_the_ladder_is_refused_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    never_asked(monkeypatch)

    code, dispatched, result_path = _run(
        tmp_path,
        monkeypatch,
        TRIAGED,
        MODEL_CONTRACT + "start_rung: local_qwen-32b\n",
    )

    assert code == 1
    assert dispatched == []
    assert "does not list" in capsys.readouterr().err
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert "local_qwen-32b" in written["detail"]
