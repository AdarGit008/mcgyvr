"""A model-written `code` contract states its output cap, or it is never sent.

`code` is the work mcgyvr's harness
runs, and a reply in a harness is bounded by a number somebody wrote. Every
unit carries one from setup, and every `code` contract states one:
``limits.max_output_tokens``, what the work is worth.

A contract that states none is not invented a number. It still loads, so
``mcgyvr contract`` calls it valid and says what it is missing, but
``mcgyvr run`` refuses it before any model is called: the dispatch fails loud,
naming the field, and no rung of the ladder is sent anything or climbed to.
The automatic sizing that used to fill the gap (a floor for the task type,
twice the target, and a reasoning allowance) is gone with it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.local_pool import source_map
from tests import livejournal as lj

#: Two units with room to spare, so nothing but the missing cap can refuse.
LADDER = """\
units:
  local_cheap:
    address: http://rig-a.invalid:8080
    model: cheap-coder
    rig: rig-a
    width: 1
    window: 32768
  local_dear:
    address: http://rig-a.invalid:8081
    model: dear-coder
    rig: rig-a
    width: 1
    window: 32768
ladder:
- local_cheap
- local_dear
"""

UNCAPPED = """
id: uncapped
task_type: code
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
scope:
  allow: ["src/**"]
"""

CAPPED = UNCAPPED + "limits:\n  max_output_tokens: 512\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
    for args in (("init", "-q"), ("add", "-A"), (*identity, "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def _sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int | None]]:
    """Record every rung a request reaches, and its cap; answer with a file."""
    from mcgyvr import drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    seen: list[tuple[str, int | None]] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        seen.append((rung, request.max_output_tokens))
        return Completion(
            text="```python\nVALUE = 1\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="cheap-coder",
            source=rung,
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return seen


def test_it_loads_with_no_cap_invented_for_it() -> None:
    contract = load_contract(UNCAPPED)
    assert contract.limits.max_output_tokens is None


def test_mcgyvr_contract_calls_it_valid_and_says_run_refuses_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = lj.make_contract(tmp_path / "uncapped.yaml", UNCAPPED)

    assert lj.main(["contract", str(path)]) == 0
    out = capsys.readouterr().out
    assert "valid" in out, out
    assert "`mcgyvr run` refuses it" in out, out
    assert "limits.max_output_tokens" in out, out


def test_the_dispatch_refuses_it_by_name_before_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import OutputCapUnstatedError, dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(UNCAPPED)

    with pytest.raises(OutputCapUnstatedError) as refused:
        dispatch_prompt(pool, "local_cheap", build_prompt(contract), contract)

    assert sent == []
    said = str(refused.value)
    assert "'uncapped'" in said, said
    assert "limits.max_output_tokens" in said, said


def test_a_stated_cap_is_sent_as_stated(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(CAPPED)

    dispatch_prompt(pool, "local_cheap", build_prompt(contract), contract)

    assert sent == [("local_cheap", 512)]


def test_a_run_fails_before_any_model_is_called_and_does_not_climb(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.drive import worker_attempt
    from mcgyvr.escalate import Halted, Outcome, escalate
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    sent = _sent(monkeypatch)
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(UNCAPPED)

    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )

    assert isinstance(outcome, Halted), outcome
    assert outcome.outcome is Outcome.ERROR
    assert sent == [], "no model is called for a contract that states no cap"
    (only,) = outcome.history
    assert only.raised
    assert "OutputCapUnstatedError" in only.detail, only.detail
    assert "limits.max_output_tokens" in only.detail, only.detail
    assert (outcome.attempts_spent, outcome.escalations) == (0, 0)
