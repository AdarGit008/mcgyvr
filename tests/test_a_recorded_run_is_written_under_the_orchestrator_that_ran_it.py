"""A recorded run is written under the orchestrator that ran it, or not at all.

``drive.Recording`` has required an orchestrator id since it was written — "a
row that cannot say which orchestrator produced it is the hole the field exists
to close (§9)" — and ``mcgyvr run`` had no flag to construct one, so the
production caller recorded nothing and the constraint was satisfied only in the
sense that it had never been exercised. The brief (*Live journal (WP0)*) gave
the command two flags: ``--record DIR`` names the journal directory and
``--orchestrator ID`` names the writer, and the sink is ``DIR/<ID>.jsonl`` so a
directory with two files in it is two orchestrators without anyone opening one.
Neither is required any more — the config names the directory and the session
names the writer — but both still do what they did.

``--record`` without ``--orchestrator`` is refused when no session names the
writer either, before a sandbox is opened and before anything is dispatched.
The alternative — a default id derived from the process — is exactly the
single-orchestrator assumption §9 names. What *is* accepted is the session
that typed the command: ``CLAUDE_CODE_SESSION_ID`` or ``PI_SESSION_FILE``
name a writer as surely as the flag does, and better, because the row can then
be followed back to the conversation
(``tests/test_a_row_names_the_session_that_drove_it.py``).

The command is exercised through ``mcgyvr.cli.main``, the real entry point,
with ``drive.dispatch`` scripted so no endpoint is reached; everything between
the flag and the row — config, route, sandbox, prompt, parse, gate — is real.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.telemetry import fold

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

MODEL_CONTRACT = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
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
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture(autouse=True)
def _no_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """This test process runs inside a session; the tests here must not."""
    for name in ("CLAUDE_CODE_SESSION_ID", "PI_SESSION_FILE", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "messy.py").write_text("x = 0\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(LADDER, encoding="utf-8")
    return path


@pytest.fixture
def contract(tmp_path: Path) -> Path:
    path = tmp_path / "impl.yaml"
    path.write_text(MODEL_CONTRACT, encoding="utf-8")
    return path


def _scripted(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer each dispatch from a script; an unscripted dispatch is a failure."""
    import mcgyvr.drive as drive
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    sent: list[str] = []
    queue = list(replies)

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Completion:
        if not queue:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        sent.append(request.prompt)
        return Completion(
            text=queue.pop(0),
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OLLAMA,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


def _main(argv: Sequence[str]) -> int:
    """``mcgyvr.cli.main``, with an argparse exit read as the code it carries."""
    from mcgyvr.cli import main

    try:
        return main(list(argv))
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2


def test_record_with_an_orchestrator_writes_that_orchestrators_journal(
    repo: Path,
    config: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scripted(monkeypatch, "```python\nVALUE = 1\n```")
    journal = tmp_path / "journal"

    code = _main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(config),
            "--record",
            str(journal),
            "--orchestrator",
            "agent-a",
        ]
    )

    assert code == 0
    sink = journal / "agent-a.jsonl"
    assert sink.is_file(), (
        sorted(p.name for p in journal.glob("*"))
        if journal.exists()
        else "no journal dir"
    )
    (row,) = fold(path=sink)
    assert row["orchestrator"] == "agent-a"
    assert row["rung"] == "local_qwen-7b"
    assert row["ok"] is True
    # The writer, the run, then the work: a re-run of the same contract is a
    # second run and not a second copy of the first.
    assert re.fullmatch(
        r"agent-a:\d{8}T\d{6}\.\d{6}Z:impl:local_qwen-7b:1", row["attempt_id"]
    ), row["attempt_id"]


def test_record_without_an_orchestrator_or_a_session_is_refused_before_dispatch(
    repo: Path,
    config: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = _scripted(monkeypatch)  # nothing scripted: any dispatch is a failure
    journal = tmp_path / "journal"

    code = _main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(config),
            "--record",
            str(journal),
        ]
    )

    assert code != 0
    err = capsys.readouterr().err
    assert "--orchestrator" in err, err
    assert sent == [], "a refused run still dispatched"
    # Refused having written nothing: no journal, no blob, no directory.
    assert not journal.exists() or not any(journal.iterdir()), sorted(
        p.name for p in journal.iterdir()
    )
