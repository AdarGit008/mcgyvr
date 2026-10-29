"""Where `/proc` cannot prove a process descends from the door, the door's proof does.

The door mints a one-time secret, hands it down in `RUN_DOOR_PROOF`, and keeps
its digest with its own pid and start time in a 0600 file while it lives. A
process holding the secret of a live door is under the door; one with no
secret, a wrong one, a door that ended, a proof file another user could read
or that is a link, or a pid whose start time moved is not. Linux keeps the
`/proc` walk, so there the proof alone admits nothing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib, run

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")


@pytest.fixture
def no_proc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gatelib, "PROC_SELF", tmp_path / "no" / "proc" / "self")


def test_a_process_handed_a_live_doors_proof_is_under_the_door(
    no_proc: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret, path = gatelib.mint_proof()
    monkeypatch.setenv(gatelib.PROOF_VAR, secret)
    assert gatelib.under_door() is True
    gatelib.drop_proof(path)
    assert gatelib.under_door() is False, "a door that ended still proved descent"


def test_no_proof_or_a_wrong_one_is_outside_the_door(
    no_proc: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gatelib.mint_proof()
    monkeypatch.delenv(gatelib.PROOF_VAR, raising=False)
    assert gatelib.under_door() is False
    monkeypatch.setenv(gatelib.PROOF_VAR, "0" * 64)
    assert gatelib.under_door() is False
    monkeypatch.setenv(gatelib.PROOF_VAR, "not-a-secret")
    assert gatelib.under_door() is False


def test_a_proof_whose_door_pid_was_reused_proves_nothing(
    no_proc: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret, path = gatelib.mint_proof()
    body = json.loads(path.read_text())
    path.write_text(json.dumps({**body, "start": "another start"}))
    monkeypatch.setenv(gatelib.PROOF_VAR, secret)
    assert gatelib.under_door() is False


@posix
def test_a_proof_file_others_may_read_or_a_link_proves_nothing(
    no_proc: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret, path = gatelib.mint_proof()
    monkeypatch.setenv(gatelib.PROOF_VAR, secret)
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)
    path.chmod(0o644)
    assert gatelib.under_door() is False
    path.chmod(0o600)
    elsewhere = tmp_path / "planted"
    path.rename(elsewhere)
    path.symlink_to(elsewhere)
    assert gatelib.under_door() is False


def test_the_proof_file_holds_only_the_digest_never_the_secret(no_proc: None) -> None:
    secret, path = gatelib.mint_proof()
    assert secret not in path.read_text()
    assert path.name not in secret


def test_on_linux_the_proc_walk_decides_and_a_proof_admits_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if not gatelib.PROC_SELF.exists():
        pytest.skip("no /proc here")
    monkeypatch.setattr(gatelib, "PROC_SELF", tmp_path / "gone")
    secret, _path = gatelib.mint_proof()
    monkeypatch.undo()
    monkeypatch.setenv(gatelib.PROOF_VAR, secret)
    assert gatelib.under_door() is False


def test_the_door_hands_its_proof_down_and_removes_it_when_it_ends(
    no_proc: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, Path]] = []

    def verb(argv: list[str]) -> int:
        env: dict[str, str] = {}
        run._door_env(env)
        seen.append(run._PROOF[0])
        assert env[gatelib.PROOF_VAR] == run._PROOF[0][0]
        assert env[gatelib.PYTHON_VAR] == sys.executable
        assert env["PATH"].startswith(str(run.BIN) + os.pathsep)
        monkeypatch.setenv(gatelib.PROOF_VAR, env[gatelib.PROOF_VAR])
        assert gatelib.under_door() is True
        return 0

    monkeypatch.setattr(run, "read", verb)
    assert run.main(["read"]) == 0
    ((_secret, path),) = seen
    assert not path.exists()
    assert run._PROOF == []
