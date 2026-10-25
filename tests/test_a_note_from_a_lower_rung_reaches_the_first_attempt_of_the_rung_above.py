"""What a rung was refused for reaches the rung above it, under `retry_notes: climb`.

Before records travelled, each rung kept its own note, so the first attempt on
a dearer rung started blind: it was sent the contract alone, and the cheaper
rung's gate run — the most specific evidence the climb had — was thrown away
at the escalation. The record now names its rung and attempt and the driver
keeps the climb's history, so the rung above is told what the rung below was
refused for, under a banner that says whose attempt that was.

Nothing is stubbed but the model: a real two-rung ladder, the real escalation,
the real driver, a real sandbox and the real gate. What is asserted is the
prompt each rung was sent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.escalate import Delivered, escalate
from mcgyvr.local_pool import source_map
from mcgyvr.sandbox.tempdir import TempDirSandbox

LADDER = """\
units:
  local_a:
    address: http://localhost:11434
    model: small-coder
    rig: workstation
    width: 1
    window: 32768
  local_b:
    address: http://localhost:11435
    model: large-coder
    rig: workstation
    width: 1
    window: 32768
ladder:
- local_a
- local_b
"""

CONTRACT = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

#: Fails the contract's demonstration, so rung `local_a`'s gate rejects it.
REJECTED = "```python\nOTHER = 1\n```"
#: Satisfies it.
ACCEPTED = "```python\nVALUE = 1\n```"

BANNER_A = "ATTEMPT 1 ON local_a WAS REJECTED BY THE GATE"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "messy.py").write_text("x = 0\n", encoding="utf-8")
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "base")):
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=t@t.io",
                "-c",
                "user.name=t",
                "-C",
                str(root),
                *args,
            ],
            check=True,
            capture_output=True,
        )
    return root


def _climb(
    repo: Path, monkeypatch: pytest.MonkeyPatch, policy: str = ""
) -> list[tuple[str, str]]:
    """Climb both rungs, rung `local_a` refused and `local_b` accepted.

    Returns each dispatch as (rung, prompt), in the order they were made.
    """
    import mcgyvr.drive as drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    replies = {"local_a": REJECTED, "local_b": ACCEPTED}
    sent: list[tuple[str, str]] = []

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        sent.append((rung, request.prompt))
        return Completion(
            text=replies[rung],
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="m",
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    config = parse_config(LADDER + policy)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )
    assert isinstance(outcome, Delivered), outcome
    assert outcome.rung == "local_b"
    return sent


def test_the_rung_above_is_told_what_the_rung_below_was_refused_for(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default, `climb`: local_b's first attempt carries local_a's record."""
    sent = _climb(repo, monkeypatch)

    assert [rung for rung, _ in sent] == ["local_a", "local_b"]
    first_a, first_b = (prompt for _, prompt in sent)
    assert "WAS REJECTED" not in first_a
    assert BANNER_A in first_b, (
        f"local_b's first attempt started blind: local_a's gate run did not "
        f"reach it.\nprompt: {first_b}"
    )
    assert "acceptance [demonstration-failed]" in first_b


def test_the_record_is_kept_where_the_climb_ends(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The accepted climb's history still holds local_a's record, named as its own."""
    import mcgyvr.drive as drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    replies = {"local_a": REJECTED, "local_b": ACCEPTED}

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        return Completion(
            text=replies[rung],
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="m",
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )

    first, second = outcome.history
    assert first.notes is not None
    assert (first.notes.rung, first.notes.family, first.notes.attempt) == (
        "local_a",
        "local",
        1,
    )
    assert first.findings == first.notes.findings
    assert second.notes is None, "an accepted attempt leaves no record"


@pytest.mark.parametrize("mode", ["rung", "none"])
def test_under_rung_or_none_the_rung_above_starts_blind(
    mode: str, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`rung` hands on only this rung's last record, `none` nothing at all."""
    sent = _climb(repo, monkeypatch, f"retry_notes: {mode}\n")

    _, first_b = sent[1]
    assert "WAS REJECTED" not in first_b, first_b
