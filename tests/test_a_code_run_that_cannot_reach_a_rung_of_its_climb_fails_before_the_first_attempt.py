"""A `code` run a rung of its climb cannot be sent to fails before anything is spent.

Every request is sent its unit's maximum, so a unit that states neither its
window nor its reply room has no maximum to send, and a `code` dispatch to it
fails loud. Checked only when a rung is reached, a run whose dearer rung is such
a unit would spend every attempt on the cheaper rungs first and then fail on
the escalation — paying for work it could never finish. So before the first
attempt, with the first prompt, every rung of the climb is checked; a rung that
cannot be sent to ends the run there, naming that rung, with nothing
dispatched.

The check at each attempt stays as well: a retry's prompt carries the last
attempt's notes and can grow past what the first one left room for
(``tests/test_every_generating_request_is_sent_its_units_maximum.py``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.local_pool import source_map

#: A cheap unit with a wide window, and a dearer hosted one that states its
#: reply room, or states nothing and so has no maximum to send.
LADDER = """\
units:
  local_cheap:
    address: http://rig-a.invalid:8080
    model: cheap-coder
    rig: rig-a
    width: 1
    window: 32768
  api_dear:
    address: http://api.invalid/v1
    model: dear-coder
    width: 1
{room}ladder:
- local_cheap
- api_dear
"""

CONTRACT = """
id: climb
task_type: code
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
scope:
  allow: ["src/**"]
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
    for args in (("init", "-q"), ("add", "-A"), (*identity, "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def _sent(monkeypatch: pytest.MonkeyPatch, text: str) -> list[str]:
    """Record every rung a request reaches, answering each with ``text``."""
    from mcgyvr import drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    seen: list[str] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        seen.append(rung)
        return Completion(
            text=text,
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


def _run(repo: Path, room: str) -> Any:
    from mcgyvr.drive import worker_attempt
    from mcgyvr.escalate import escalate
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    config = parse_config(LADDER.format(room=room))
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        return escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )


def test_a_rung_up_the_climb_with_no_ceiling_ends_the_run_unspent(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.escalate import Halted, Outcome

    # A reply the gate rejects: without the check the cheap rung would spend
    # its attempts on it before the climb reached the rung it cannot use.
    sent = _sent(monkeypatch, "```python\nOTHER = 1\n```")

    outcome = _run(repo, room="")

    assert isinstance(outcome, Halted), outcome
    assert outcome.outcome is Outcome.ERROR
    assert sent == [], f"nothing is dispatched for a climb that cannot finish: {sent}"
    (only,) = outcome.history
    assert only.raised
    assert "UnitCeilingUnknownError" in only.detail, only.detail
    assert "'api_dear'" in only.detail, only.detail
    assert "units.api_dear.output_tokens" in only.detail, only.detail
    assert "before the first attempt" in only.detail, only.detail
    assert (outcome.attempts_spent, outcome.escalations) == (0, 0)


def test_a_climb_whose_every_rung_states_a_ceiling_runs(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.escalate import Delivered

    sent = _sent(monkeypatch, "```python\nVALUE = 1\n```")

    outcome = _run(repo, room="    output_tokens: 4096\n")

    assert isinstance(outcome, Delivered), outcome
    assert sent == ["local_cheap"]
