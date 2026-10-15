"""A ``chat`` run does not print the note that the sandbox is HEAD.

A run on a dirty tree says the sandbox is built from HEAD and names the
uncommitted paths it leaves out, so a contract whose commands need them is not
judged on a tree the user cannot see (e2e run 1, F11). A ``chat`` contract
with no target, no sources and no command reads nothing off the tree: the note
told it to commit files it never looks at (e2e run 3, T4). So such a run says
nothing about it, on stderr or in the result file's ``notes``.

The note stays wherever the tree is read: an ``agent`` run reads its sources
off HEAD, and a ``chat`` contract that names sources reads them there too.

Runs go through ``mcgyvr.cli.main`` with ``drive.dispatch`` scripted; the
session is staged on this host (``sandbox.sessions: tempdir``, the default),
so nothing here needs Docker.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

NOTE = "the sandbox is built from"

CHAT = """\
id: sky
task_type: chat
task: Why is the sky blue?
"""

CHAT_WITH_SOURCES = """\
id: sky-report
task_type: chat
task: What does the report say about the sky?
sources: ["src/report.txt"]
"""

AGENT = """\
id: brief
task_type: agent
task: Summarise the report.
sources: ["src/report.txt"]
"""

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def dirty(tmp_path: Path) -> Path:
    """A committed repository with an edit and a file nobody committed."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "report.txt").write_text("The sky is blue.\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    (root / "src" / "report.txt").write_text("The sky is grey.\n", encoding="utf-8")
    (root / "notes.txt").write_text("draft\n", encoding="utf-8")
    return root


def _scripted(monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    import mcgyvr.drive as drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Completion:
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

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)


def _run(
    tmp_path: Path,
    document: str,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[dict[str, Any], str]:
    """Run ``document`` on ``repo``; the result file and everything printed."""
    from mcgyvr.cli import main

    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    for name in (
        "CLAUDE_CODE_SESSION_ID",
        "PI_SESSION_FILE",
        "CLAUDE_CONFIG_DIR",
        "MCGYVR_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(home))
    _scripted(monkeypatch, "Rayleigh scattering.")

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(
        "units:\n"
        "  local_qwen-7b:\n"
        "    address: http://localhost:11434\n"
        "    model: qwen2.5-coder:7b\n"
        "    rig: workstation\n"
        "ladder:\n"
        "- local_qwen-7b\n"
        "journal:\n"
        f"  dir: {tmp_path / 'journal'}\n",
        encoding="utf-8",
    )
    contract = tmp_path / "contract.yaml"
    contract.write_text(document, encoding="utf-8")
    result_file = tmp_path / "result.json"
    main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--orchestrator",
            "t",
            "--result",
            str(result_file),
        ]
    )
    printed = capsys.readouterr()
    result = json.loads(result_file.read_text(encoding="utf-8"))
    return result, printed.out + printed.err


def test_a_chat_run_on_a_dirty_tree_says_nothing_about_head(
    tmp_path: Path,
    dirty: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result, said = _run(tmp_path, CHAT, dirty, monkeypatch, capsys)

    assert result["outcome"] == "accepted", said
    assert NOTE not in said, said
    assert not any(NOTE in note for note in result["notes"]), result["notes"]


def test_a_chat_run_that_reads_sources_still_says_the_sandbox_is_head(
    tmp_path: Path,
    dirty: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result, said = _run(tmp_path, CHAT_WITH_SOURCES, dirty, monkeypatch, capsys)

    assert NOTE in said, said
    assert any(NOTE in note for note in result["notes"]), result["notes"]


def test_an_agent_run_on_a_dirty_tree_still_says_the_sandbox_is_head(
    tmp_path: Path,
    dirty: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result, said = _run(tmp_path, AGENT, dirty, monkeypatch, capsys)

    assert NOTE in said, said
    assert any(NOTE in note for note in result["notes"]), result["notes"]
