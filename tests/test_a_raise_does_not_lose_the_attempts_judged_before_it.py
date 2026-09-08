"""An attempt that raises does not take the attempts judged before it with it.

``route.climb`` keeps the history of one family's climb in a local list and
lets a raising attempt propagate. ``escalate`` caught it and appended the
raising attempt alone — the two judged attempts before it on the same rung,
whose journal rows had been written and whose findings the replanner needs,
were in a list that died with the exception. ``attempts_spent`` still
counted them, so the result file said two attempts were spent and listed
one, and the rows of the two stayed ``uncorrected`` forever.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.escalate import Judgement, Outcome, RetryNotes, escalate, required_policy
from mcgyvr.route import Try, Verdict, family_of
from mcgyvr.telemetry import fold
from tests import livejournal as lj
from tests.test_escalate import KEYLESS, contract, halted, mapped

LADDER_WITH_THREE_ATTEMPTS = lj.LADDER + "      attempts: 3\n"
CONTRACT_WITH_THREE_ATTEMPTS = lj.MODEL_CONTRACT.replace(
    "  max_output_tokens: 256\n", "  max_output_tokens: 256\n  attempts: 3\n"
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_the_history_keeps_the_judged_attempts_before_the_raise() -> None:
    config, pool = mapped(
        KEYLESS.replace(
            "model: qwen2.5-coder:7b\n", "model: qwen2.5-coder:7b\n      attempts: 3\n"
        )
    )
    task = contract()

    def flaky(this: Try) -> Judgement:
        if this.attempt < 3:
            return Judgement(
                verdict=Verdict.FAILED,
                policy=required_policy(task, family_of(config, this.rung.name)),
                detail=f"rejected on attempt {this.attempt}",
                retry=RetryNotes(
                    checks=("acceptance",), lines=(f"finding {this.attempt}",)
                ),
                draw=0,
                draws=2,
            )
        raise RuntimeError("the socket died on attempt 3")

    result = halted(escalate(config, pool, task, flaky))

    assert result.outcome is Outcome.ERROR
    assert result.attempts_spent == 2
    assert [(a.attempt, a.verdict, a.raised) for a in result.history] == [
        (1, Verdict.FAILED, False),
        (2, Verdict.FAILED, False),
        (3, Verdict.FAILED, True),
    ]
    assert result.history[0].findings == ("finding 1",)
    assert result.history[1].draws == 2


def test_every_row_before_the_raise_is_corrected_and_listed(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.drive as drive
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, RunnerError, StopReason

    answers: list[str | None] = [lj.BAD_REPLY, lj.BAD_REPLY, None]

    def dies_on_the_third(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        reply = answers.pop(0)
        if reply is None:
            raise RunnerError("connection refused")
        return Completion(
            text=reply,
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", dies_on_the_third)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(
        LADDER_WITH_THREE_ATTEMPTS + f"journal:\n  dir: {journal}\n", encoding="utf-8"
    )
    contract = lj.make_contract(tmp_path / "impl.yaml", CONTRACT_WITH_THREE_ATTEMPTS)

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    assert answers == [], "all three dispatches were made"
    rows = sorted(fold(path=journal / "claude-s1.jsonl"), key=lambda r: r["attempt_id"])
    assert [r["outcome"] for r in rows] == ["failed", "failed", "error"], rows
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "error"
    assert [a["verdict"] for a in result["attempts"]] == ["failed", "failed", "error"]
    assert result["attempts"][0]["findings"], result["attempts"][0]
