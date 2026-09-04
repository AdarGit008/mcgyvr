"""What the live-journal tests share: a repo, a ladder, a contract, a script.

Every test of ``mcgyvr run``'s journal drives ``mcgyvr.cli.main`` — the real
entry point — with ``drive.dispatch`` scripted so no endpoint is reached and
everything between the flag and the row (config, route, sandbox, prompt, parse,
gate) is real. The helpers here are the ones
``tests/test_a_recorded_run_is_written_under_the_orchestrator_that_ran_it.py``
wrote for itself, lifted so that the tests of *who* ran, *where* the journal
went and *how* the work landed do not carry four private copies each.

The environment is the seam. ``mcgyvr run`` reads ``CLAUDE_CODE_SESSION_ID``
and ``PI_SESSION_FILE`` to name the session that typed it, and this test
process runs inside one of those sessions, so :func:`clean_env` empties both
and points ``HOME`` at a directory nobody else writes to — a test that forgot
would journal under the developer's real state dir as the developer's real
session.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

SESSION_VARS = ("CLAUDE_CODE_SESSION_ID", "PI_SESSION_FILE", "CLAUDE_CONFIG_DIR")

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
scope:
  allow: ["src/**"]
"""

#: A reply the gate accepts: the acceptance command finds ``VALUE``.
GOOD_REPLY = "```python\nVALUE = 1\n```"
#: A reply the gate rejects: syntactically fine, acceptance fails.
BAD_REPLY = "```python\nOTHER = 1\n```"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **IDENTITY},
    )
    return done.stdout


def make_repo(root: Path) -> Path:
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "messy.py").write_text("x = 0\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def make_config(path: Path, *, journal_dir: Path | None = None) -> Path:
    text = LADDER
    if journal_dir is not None:
        text += f"journal:\n  dir: {journal_dir}\n"
    path.write_text(text, encoding="utf-8")
    return path


def make_contract(path: Path, text: str = MODEL_CONTRACT) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def clean_env(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """No session in the environment, and a HOME nobody else writes to."""
    for name in SESSION_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(home))


def claude_transcript(home: Path, session_id: str) -> Path:
    """A Claude Code transcript where Claude Code keeps them, under ``home``."""
    project = home / ".claude" / "projects" / "-home-someone-somewhere"
    project.mkdir(parents=True, exist_ok=True)
    path = project / f"{session_id}.jsonl"
    path.write_text(json.dumps({"type": "user", "sessionId": session_id}) + "\n")
    return path


def pi_transcript(home: Path, session_id: str) -> Path:
    """A Pi transcript where Pi keeps them, under ``home``."""
    where = home / ".pi" / "agent" / "sessions" / "--home-someone--"
    where.mkdir(parents=True, exist_ok=True)
    path = where / f"2026-09-03T06-19-33-727Z_{session_id}.jsonl"
    path.write_text(json.dumps({"type": "session", "id": session_id}) + "\n")
    return path


def scripted(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
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


def main(argv: Sequence[str]) -> int:
    """``mcgyvr.cli.main``, with an argparse exit read as the code it carries."""
    from mcgyvr.cli import main as cli_main

    try:
        return cli_main(list(argv))
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2


def run_args(contract: Path, repo: Path, config: Path, *extra: str) -> list[str]:
    return [
        "run",
        str(contract),
        "--repo",
        str(repo),
        "--sandbox",
        "tempdir",
        "--config",
        str(config),
        *extra,
    ]


def result_path(stdout: str) -> Path:
    """The result file a run announced, from its ``result: <path>`` line."""
    lines = [line for line in stdout.splitlines() if line.startswith("result: ")]
    assert len(lines) == 1, stdout
    return Path(lines[0].removeprefix("result: ").strip())
