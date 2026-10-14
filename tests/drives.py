"""Driving a contract up the ladder: an attempt, a raise, a halt."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, parse
from mcgyvr.config import parse as parse_config
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import (
    Delivered,
    Halted,
    escalate,
)
from mcgyvr.local_pool import SourceMap, source_map
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


LADDER = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 2
    window: 32768
  local_qwen-14b:
    address: http://localhost:11434
    model: qwen2.5-coder:14b
    rig: workstation
    width: 2
    window: 32768
ladder:
- local_qwen-7b
- local_qwen-14b
"""


def _completion(text: str):  # type: ignore[no-untyped-def]
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _driven(monkeypatch: pytest.MonkeyPatch, *replies: str):  # type: ignore[no-untyped-def]
    """Answer each dispatch from a script, and record the prompts that were sent."""
    import mcgyvr.drive as drive

    sent: list[str] = []
    scripted = list(replies)

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(request.prompt)
        if not scripted:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        return _completion(scripted.pop(0))

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


KEYLESS = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 2
    window: 32768
ladder:
- local_qwen-7b
"""


CONTRACT = """
id: fetch-retry
task_type: code
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


def mapped(text: str) -> tuple[Config, SourceMap]:
    config = parse(text)
    return config, source_map(config)


def contract(text: str = CONTRACT) -> Contract:
    return load_contract(text)


def halted(result: Delivered | Halted) -> Halted:
    assert isinstance(result, Halted), f"expected a halted task, got {result}"
    return result


CLIMBED_LADDER = """
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    rig: fast-rig
    width: 1
    window: 32768
  local_smart:
    address: http://smart-box.example:8001
    model: qwen2.5-coder-7b
    rig: smart-rig
    width: 1
    window: 32768
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    rig: vendor
    width: 1
    api_key_env: EXAMPLE_API_KEY
    window: 32768
  api_bigger:
    address: https://big.example.com/v1
    model: vendor-largest
    rig: vendor-big
    width: 4
    api_key_env: EXAMPLE_API_KEY
    window: 32768
ladder:
- local_fast
- local_smart
- api_big
- api_bigger
max_escalations: 3
{fanout}"""


#: Two units on an invented rig. The narrow one serves 4096 tokens, which the
#: contract's own ceiling (the schema's 4096) fits, so only the share can
#: refuse it; the wide one is there so "not climbed" can be asserted.
SHARE_LADDER = """\
units:
  local_narrow:
    address: http://rig-b.invalid:8080
    model: narrow-coder
    rig: rig-b
    width: 1
    window: 4096
  local_wide:
    address: http://rig-b.invalid:8081
    model: wide-coder
    rig: rig-b
    width: 1
    window: 32768
ladder:
- local_narrow
- local_wide
"""


#: The run's share: a quarter of any rung's window.
RUN_SHARE = "max_window_fraction: 0.25\n"


#: A reply of 1024 tokens alone is a quarter of the narrow window, so with any
#: prompt beside it the contract claims more than a quarter — and still fits.
SHARE_CONTRACT = """
id: greedy
task_type: code
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/**"]
"""


def _sharing(share: float) -> str:
    """The same contract, declaring its own share of the window."""
    return SHARE_CONTRACT.replace(
        "max_output_tokens: 1024\n",
        f"max_output_tokens: 1024\n  max_window_fraction: {share}\n",
    )


def a_git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
    for args in (("init", "-q"), ("add", "-A"), (*identity, "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def _sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every rung a request reaches; answer with a valid file."""
    from mcgyvr import drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    seen: list[str] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        seen.append(rung)
        return Completion(
            text="```python\nVALUE = 1\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="narrow-coder",
            source=rung,
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return seen


class _Waker:
    """A waker that records every rung it was asked to wake, then sends."""

    def __init__(self) -> None:
        self.woken: list[str] = []

    def dispatching(self, rung: str, send: Any) -> Any:
        self.woken.append(rung)
        return send()


def _run(
    share_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    policy: str,
    contract_text: str = SHARE_CONTRACT,
) -> tuple[Any, list[str], _Waker, Path]:
    from mcgyvr import drive
    from mcgyvr.drive import Recording, worker_attempt

    sent = _sent(monkeypatch)
    waker = _Waker()
    monkeypatch.setattr(drive, "wake_for_config", lambda config: waker)
    config = parse_config(SHARE_LADDER + policy)
    pool = source_map(config)
    contract = load_contract(contract_text)
    journal = tmp_path / "journal" / "orch.jsonl"
    journal.parent.mkdir()
    recording = Recording(path=journal, orchestrator="orch")
    with TempDirSandbox(share_repo) as sandbox:
        outcome = escalate(
            config,
            pool,
            contract,
            worker_attempt(config, pool, contract, sandbox, recording=recording),
        )
    return outcome, sent, waker, journal
