"""A failure note names a repo file by its repo-relative path and no other host path.

A failure record travels: the climb hands it to the next rung, and the hub
carries it to another user's rig as prompt data. What a check printed is full
of the machine it ran on — pytest's ``rootdir:``, a traceback's ``File "…"``,
an interpreter's site-packages, the throwaway ``HOME`` a command was given — and
none of that is the repository's. So two things hold, at two layers:

* the gate knows the workspace a command ran in (:attr:`Sandbox.roots`, every
  spelling of it a command can print: the host directory, its resolved form, the
  container's ``/workspace``), and the acceptance rung turns a path under it into
  the repo-relative one it is, so the note still says *which file*;
* :class:`mcgyvr.notes.FailureNote` guarantees, however it is built — from a
  finding, an undecided rung, a refusal, an unreadable reply, or a record read
  back from JSON — that no absolute path is left in ``message``, ``command`` or
  ``path``: anything that is not repo-relative is replaced by
  :data:`mcgyvr.redact.REDACTED`, or, for ``path``, dropped.

The invariant is checked here with a pattern of its own rather than with the
module's, so a gap in one is not hidden by the same gap in the other. Every
path below is invented.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import GateResult, InconclusiveRung
from mcgyvr.notes import FailureNote, FailureNotes, NoteKind
from mcgyvr.redact import REDACTED
from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.docker import DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import DockerResult
from mcgyvr.sandbox.tempdir import TempDirSandbox

#: An absolute path, or a home-relative one, where a path can begin: at the start
#: of the text or after a space, a quote, a bracket, `=`, `:` or `,`. A URL's
#: `//` does not count — its host is not a path on anyone's machine.
_HOST_PATH = re.compile(r"(?:^|[\s'\"(\[{=:,<])(?:/|~/)(?=[\w.~-])", re.MULTILINE)


def _host_paths(record: FailureNotes) -> list[str]:
    """Every field of every note that still holds a host path."""
    held = []
    for note in record.as_json()["notes"]:
        for name in ("message", "command", "path"):
            value = note[name]
            if isinstance(value, str) and _HOST_PATH.search(value):
                held.append(f"{name}: {value!r}")
    return held


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _record(gate: GateResult) -> FailureNotes:
    record = FailureNotes.of_gate(gate, rung="local_a", family="local", attempt=1)
    assert record is not None, f"the gate accepted the change: {gate}"
    return record


def _failing(script: str) -> tuple[str, ...]:
    return ("sh", "-c", f"{script}\nexit 1")


# --- the gate: a path under the workspace is the repo-relative one ------------


def test_a_workspace_path_in_an_acceptance_failure_is_repo_relative(
    repo: Path,
) -> None:
    """pytest's ``rootdir:`` and a traceback's file, as the sandbox printed them."""
    script = (
        'echo "rootdir: $(pwd)"\n'
        'echo "  File \\"$(pwd)/pkg/mod.py\\", line 3, in total"\n'
        "echo \"frame = <frame at 0x7f, file '$(pwd -P)/pkg/mod.py', line 5>\"\n"
        'echo "$(pwd)/pkg/mod.py:7: AssertionError"'
    )
    with TempDirSandbox(repo) as sandbox:
        workspace = str(sandbox.workspace)
        report = Acceptance(sandbox, (_failing(script),)).run()

    (finding,) = report.findings
    assert workspace not in finding.message
    assert "rootdir: .\n" in finding.message
    assert '  File "pkg/mod.py", line 3, in total' in finding.message
    assert "file 'pkg/mod.py', line 5>" in finding.message
    assert "\npkg/mod.py:7: AssertionError" in finding.message

    record = _record(GateResult(findings=report.findings))
    (note,) = record.notes
    assert "pkg/mod.py:7: AssertionError" in note.message
    assert _host_paths(record) == []


def test_a_container_path_in_an_acceptance_failure_is_repo_relative(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In docker mode a command prints the container's `/workspace`, not the host's."""

    def answer(args: Sequence[str], timeout: float | None) -> _ExecResult:
        said = (
            "rootdir: /workspace\n"
            "/workspace/pkg/mod.py:7: AssertionError\n"
            "/usr/lib/python3.12/site-packages/_pytest/python.py:194: in call\n"
        )
        return _ExecResult(1, said, "", False)

    def daemon(args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        return DockerResult(0, "", "")

    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(docker_module, "_docker_exec", answer)
    with DockerSandbox(
        repo, image="img:latest", runner=daemon, system="Linux"
    ) as sandbox:
        assert "/workspace" in sandbox.roots
        report = Acceptance(sandbox, (("pytest", "-q"),)).run()

    (finding,) = report.findings
    assert "rootdir: .\n" in finding.message
    assert "\npkg/mod.py:7: AssertionError" in finding.message

    record = _record(GateResult(findings=report.findings))
    (note,) = record.notes
    assert f"{REDACTED}:194: in call" in note.message
    assert _host_paths(record) == []


def test_a_path_outside_the_workspace_is_redacted(repo: Path) -> None:
    """Site-packages, the command's own HOME, another directory that merely
    starts with the workspace's name: none of them is the repository's."""
    script = (
        'echo "  File \\"/opt/elsewhere/lib/site-packages/thing.py\\", line 9"\n'
        'echo "cache at $HOME/.cache/tool"\n'
        'echo "copied to $(pwd)-other/pkg/mod.py"\n'
        'echo "see ~/notes.txt and --basetemp=/tmp/sandbox-x/run"'
    )
    with TempDirSandbox(repo) as sandbox:
        workspace = str(sandbox.workspace)
        report = Acceptance(sandbox, (_failing(script),)).run()

    record = _record(GateResult(findings=report.findings))
    (note,) = record.notes
    assert workspace not in note.message
    assert "/opt/elsewhere" not in note.message
    assert "/tmp/sandbox-x" not in note.message
    assert "notes.txt" not in note.message
    assert f'  File "{REDACTED}", line 9' in note.message
    assert f"--basetemp={REDACTED}" in note.message
    assert _host_paths(record) == []


# --- the record: no host path, however a note is built ------------------------


def test_a_findings_message_command_and_path_carry_no_host_path() -> None:
    gate = GateResult(
        findings=(
            Finding(
                check="typecheck",
                path="/tmp/sandbox-x/task/pkg/mod.py",
                line=3,
                code="return-value",
                message="/tmp/sandbox-x/task/pkg/mod.py:3: error: bad return",
                command="/opt/elsewhere/bin/mypy --config-file /tmp/sandbox-x/m.ini",
                exit_code=1,
            ),
            Finding(
                check="structure",
                path="../outside/mod.py",
                message="climbs out of the repository",
            ),
        )
    )

    record = _record(gate)

    typed, climbing = record.notes
    assert typed.path is None
    assert typed.message == f"{REDACTED}:3: error: bad return"
    assert typed.command == f"{REDACTED} --config-file {REDACTED}"
    assert climbing.path is None
    assert _host_paths(record) == []


def test_an_undecided_rung_a_refusal_and_an_unreadable_reply_carry_no_host_path() -> (
    None
):
    undecided = _record(
        GateResult(
            inconclusive=(
                InconclusiveRung(
                    adapter="python",
                    rung="lint",
                    tool="ruff",
                    exit_code=2,
                    detail="cannot read /tmp/sandbox-x/task/ruff.toml",
                ),
            )
        )
    )
    refused = FailureNotes.of_refusal(
        "the change breaks /opt/elsewhere/app/main.py",
        GateResult(),
        rung="local_a",
        family="local",
        attempt=1,
    )
    unreadable = FailureNotes.unreadable(
        "the reply could not be read: no block in ~/replies/one.txt",
        rung="local_a",
        family="local",
        attempt=1,
    )

    for record in (undecided, refused, unreadable):
        (note,) = record.notes
        assert REDACTED in note.message, note.message
        assert _host_paths(record) == []
    assert refused.notes[0].kind is NoteKind.REFUSAL
    assert unreadable.notes[0].kind is NoteKind.UNREADABLE


def test_a_record_read_back_from_json_carries_no_host_path() -> None:
    """The record is the boundary: one written elsewhere is held to it on reading."""
    written: dict[str, Any] = {
        "schema": "mcgyvr.failure_notes/1",
        "rung": "local_a",
        "family": "local",
        "attempt": 1,
        "checks": ["acceptance"],
        "notes": [
            {
                "check": "acceptance",
                "kind": "finding",
                "message": "rootdir: /tmp/sandbox-x/task",
                "path": "/tmp/sandbox-x/task/pkg/mod.py",
                "line": None,
                "code": "failed",
                "command": "/opt/elsewhere/bin/pytest -q",
                "exit_code": 1,
                "test_id": None,
                "symbol": None,
            }
        ],
    }

    record = FailureNotes.from_json(written)

    (note,) = record.notes
    assert note.message == f"rootdir: {REDACTED}"
    assert note.command == f"{REDACTED} -q"
    assert note.path is None
    assert _host_paths(record) == []


def test_a_url_keeps_its_host_and_path_and_loses_only_its_userinfo() -> None:
    note = FailureNote(
        check="acceptance",
        kind=NoteKind.FINDING,
        message=(
            "fetch https://user:hunter2@example.invalid/a/b.txt failed; "
            "see http://example.invalid/docs/x.html and pkg/mod.py"
        ),
    )

    assert note.message == (
        f"fetch https://{REDACTED}@example.invalid/a/b.txt failed; "
        "see http://example.invalid/docs/x.html and pkg/mod.py"
    )
