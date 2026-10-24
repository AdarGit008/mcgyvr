"""A reply that hands its target back unchanged fails, and the climb goes on.

The rest of the gate passes such a reply: the acceptance commands passed on the
base tree before the attempt, and nothing else in the tree moved. Delivery is the
first place that sees no change, and it refuses the change as identical to the base
— by then the climb has stopped on an attempt it took as accepted, so the rungs
above were never asked and the work is lost. The attempt is failed instead, where
the climb reads its verdict: the next rung is tried exactly as after any other
failure, and a ladder whose every rung hands the target back ends spent, never
accepted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.escalate import Delivered, Halted, Outcome, escalate
from mcgyvr.local_pool import source_map
from mcgyvr.route import Verdict
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests.drives import LADDER, a_git_repo

TARGET = "src/pkg/value.py"

#: What `a_git_repo` commits at the target.
BASE = "VALUE = 0\n"

CHANGED = "VALUE = 1\n"

#: The acceptance command already passes on the base, so only the no-change
#: check can tell a reply that did the work from one that did nothing.
CONTRACT = f"""
id: set-value
task_type: code
task: Set VALUE to 1.
target: {TARGET}
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE {TARGET}'"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/**"]
"""


def _answers(
    monkeypatch: pytest.MonkeyPatch, by_rung: dict[str, str]
) -> list[tuple[str, str]]:
    """Answer every dispatch with the file its rung returns; record rung and prompt."""
    from mcgyvr import drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    asked: list[tuple[str, str]] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        asked.append((rung, request.prompt))
        return Completion(
            text=f"```python\n{by_rung[rung]}```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model=rung,
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return asked


def _climb(repo: Path) -> Delivered | Halted:
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        return escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )


def test_an_unchanged_reply_fails_and_the_next_rung_is_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cheap rung hands the file back as it was; the rung above changes it.

    The change is delivered from the rung above, and every try of the cheap rung is
    on the record as failed, naming the check that failed it.
    """
    repo = a_git_repo(tmp_path)
    asked = _answers(monkeypatch, {"local_qwen-7b": BASE, "local_qwen-14b": CHANGED})

    outcome = _climb(repo)

    assert isinstance(outcome, Delivered), outcome
    assert outcome.rung == "local_qwen-14b"
    assert outcome.judgement.accepted is not None
    assert outcome.judgement.accepted.content == CHANGED
    assert asked[-1][0] == "local_qwen-14b"
    cheap = [step for step in outcome.history if step.rung == "local_qwen-7b"]
    assert cheap, "the cheap rung was never tried"
    for step in cheap:
        assert step.verdict is Verdict.FAILED
        assert any("unchanged [identical-to-base]" in line for line in step.findings)


def test_a_ladder_that_only_hands_the_target_back_ends_spent_never_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every rung returns the file as it was, the top one included."""
    repo = a_git_repo(tmp_path)
    asked = _answers(monkeypatch, {"local_qwen-7b": BASE, "local_qwen-14b": BASE})

    outcome = _climb(repo)

    assert isinstance(outcome, Halted), outcome
    assert outcome.outcome is Outcome.LADDER_SPENT
    assert "local_qwen-14b" in {rung for rung, _ in asked}, (
        "the top rung was never asked"
    )
    assert outcome.history
    assert all(step.verdict is Verdict.FAILED for step in outcome.history)


def test_the_retry_is_told_its_reply_changed_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second try on the same rung hears why the first one failed."""
    from mcgyvr.local_pool import Rung
    from mcgyvr.route import Try

    repo = a_git_repo(tmp_path)
    asked = _answers(monkeypatch, {"local_qwen-7b": BASE})
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    rung = Rung(name="local_qwen-7b", model="m")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox)
        first = attempt(Try(rung=rung, attempt=1, of=2))
        attempt(Try(rung=rung, attempt=2, of=2))

    assert first.verdict is Verdict.FAILED
    assert len(asked) == 2
    assert "identical-to-base" not in asked[0][1]
    assert "identical-to-base" in asked[1][1]


def test_the_run_reports_a_spent_ladder_and_leaves_the_repository_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Through `mcgyvr run --commit`: no delivery is attempted, nothing is committed."""
    from mcgyvr.cli import main

    repo = a_git_repo(tmp_path)
    _answers(monkeypatch, {"local_qwen-7b": BASE, "local_qwen-14b": BASE})
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(LADDER, encoding="utf-8")
    contract = tmp_path / "set-value.yaml"
    contract.write_text(CONTRACT, encoding="utf-8")
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    said = capsys.readouterr()
    assert code == 1
    assert f"set-value: {Outcome.LADDER_SPENT.value}" in said.err
    assert "identical to" not in said.out + said.err, (
        "delivery was reached for a change no rung made"
    )
    assert (repo / TARGET).read_text(encoding="utf-8") == BASE
    after = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert after == head
