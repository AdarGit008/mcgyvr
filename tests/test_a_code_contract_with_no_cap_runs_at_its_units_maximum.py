"""A model-written `code` contract needs no output cap: it runs at its unit's maximum.

`code` used to have to state ``limits.max_output_tokens``, what the work was
worth: ``mcgyvr contract`` called a contract without one valid and
``mcgyvr run`` refused it before any model was called. The cap is not the
work's to state any more. Every request is sent the most its unit can give,
clamped to the room the window leaves the prompt, so a contract with no cap
runs, and one that states a cap is read and runs at the same number.
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


def _room(contract: Any) -> int:
    from mcgyvr.gate.preflight import unit_ceiling
    from mcgyvr.worker.prompt import build_prompt

    pool = source_map(parse_config(LADDER))
    room = unit_ceiling(pool.bind("local_cheap"), build_prompt(contract).measured)
    assert room.tokens is not None
    return room.tokens


def test_mcgyvr_contract_calls_it_valid_and_says_what_its_reply_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = lj.make_contract(tmp_path / "uncapped.yaml", UNCAPPED)

    assert lj.main(["contract", str(path)]) == 0
    out = capsys.readouterr().out
    assert "valid" in out, out
    assert "reply at its unit's maximum" in out, out
    assert "refuses" not in out, out


def test_the_dispatch_sends_it_the_room_its_unit_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(UNCAPPED)

    dispatch_prompt(pool, "local_cheap", build_prompt(contract), contract)

    assert sent == [("local_cheap", _room(contract))]


def test_a_stated_cap_is_not_what_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(CAPPED)

    dispatch_prompt(pool, "local_cheap", build_prompt(contract), contract)

    assert sent == [("local_cheap", _room(contract))]
    assert _room(contract) > 512


def test_a_run_reaches_a_model_at_its_units_maximum(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.drive import worker_attempt
    from mcgyvr.escalate import Outcome, escalate
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    sent = _sent(monkeypatch)
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(UNCAPPED)

    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )

    assert outcome.outcome is not Outcome.ERROR, outcome
    # The run's prompt carries the target's content too, so its room is the
    # window less that larger prompt: still the unit's, never a contract's.
    ((rung, cap), *_) = sent
    assert rung == "local_cheap"
    assert cap is not None and 512 < cap <= _room(contract)
