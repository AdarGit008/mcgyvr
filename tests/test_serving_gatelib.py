"""gatelib holds the one rule: a rig is reached under the door, and only there.

``gatelib.ssh`` is the only place in src/ and tools/ that spawns an ssh, and
it refuses — exit 2, naming the door command — unless the calling process
descends from ``mcgyvr.serving.run`` and names the host the door was opened
for. "Descends from" is read off ``/proc``, which nothing can set, and matches
the door by the suffix of its file (a copy of the door in a fixture tree is the
door) or by the ``-m mcgyvr.serving.run`` pair.

No test here reaches a rig: where an ssh is admitted, the ``ssh`` on PATH is a
stub that prints what it was handed.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib

REPO = Path(__file__).resolve().parent.parent
DOOR = "python -m mcgyvr.serving.run --host H --campaign C --step PATH --model M"
SSH = "ssh"

#: A stand-in for the door: a file whose path ends in mcgyvr/serving/run.py,
#: as a copy of the door in a fixture tree would, which runs its arguments as
#: a child. What the child sees in /proc is exactly what a gate sees.
FAKE_DOOR = (
    "import subprocess, sys\n"
    "raise SystemExit(subprocess.run(sys.argv[1:]).returncode)\n"
)


def clean_env(*path_first: Path) -> dict[str, str]:
    """No RUN_* or DOCKER_* inherited; the venv's interpreter first on PATH."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RUN_", "DOCKER_"))}
    parts = [str(p) for p in path_first] + [str(Path(sys.executable).parent)]
    parts += (env.get("PATH") or os.defpath).split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts)
    return env


def executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def fake_door(tmp_path: Path) -> Path:
    return executable(tmp_path / "tree" / "mcgyvr" / "serving" / "run.py", FAKE_DOOR)


def ssh_stub(where: Path) -> Path:
    """An ``ssh`` that records its argv and stdin, and answers. Reaches nothing."""
    log = where / "ssh.log"
    return executable(
        where / SSH,
        "#!/usr/bin/env bash\n"
        f"printf 'argv=%s\\n' \"$*\" >> '{log}'\n"
        f"printf 'stdin=%s\\n' \"$(cat)\" >> '{log}'\n"
        "echo answered\n",
    )


def under(
    door: Path, argv: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(door), *argv],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# --------------------------------------------------------------------------
# under_door: read from /proc, matched by suffix or by the -m pair
# --------------------------------------------------------------------------


def test_the_test_process_is_not_under_the_door() -> None:
    assert gatelib.under_door() is False


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["python", "-m", "mcgyvr.serving.run", "--host", "srv1"], True),
        (["/usr/bin/python3", "/x/src/mcgyvr/serving/run.py"], True),
        (["python", "/tmp/fixture/mcgyvr/serving/run.py"], True),
        (["python", "-m", "mcgyvr.serving.gatelib"], False),
        (["python", "-m", "pytest", "mcgyvr.serving.run"], False),
        (["bash", "-c", "mcgyvr/serving/run.py"], True),
        ([], False),
    ],
)
def test_is_door_matches_the_file_suffix_or_the_module_pair(
    argv: list[str], expected: bool
) -> None:
    assert gatelib.is_door(argv) is expected


def test_a_copy_of_the_door_in_a_fixture_tree_is_the_door(tmp_path: Path) -> None:
    door = fake_door(tmp_path)
    code = "from mcgyvr.serving import gatelib; print(gatelib.under_door())"
    result = under(door, [sys.executable, "-c", code], clean_env())
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_a_grandchild_of_the_door_is_under_it_too(tmp_path: Path) -> None:
    door = fake_door(tmp_path)
    code = "from mcgyvr.serving import gatelib; print(gatelib.under_door())"
    result = under(
        door,
        ["bash", "-c", f"{sys.executable} -c '{code}'"],
        clean_env(),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


# --------------------------------------------------------------------------
# ssh: refused outside the door, refused to the wrong host, admitted otherwise
# --------------------------------------------------------------------------


def test_ssh_outside_the_door_exits_2_naming_the_door(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        gatelib.ssh("srv1", "true")
    assert raised.value.code == 2
    err = capsys.readouterr().err
    assert "srv1" in err
    assert DOOR in err, err
    assert "not started by the door" in err


def test_ssh_to_a_host_the_door_was_not_opened_for_names_both(tmp_path: Path) -> None:
    door = fake_door(tmp_path)
    code = "from mcgyvr.serving import gatelib; gatelib.ssh('srv1', 'true')"
    env = clean_env(ssh_stub(tmp_path / "stubs").parent)
    env["RUN_HOST"] = "srv2"
    result = under(door, [sys.executable, "-c", code], env)
    assert result.returncode == 2, result.stderr
    assert "srv1" in result.stderr and "srv2" in result.stderr, result.stderr
    assert DOOR in result.stderr
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "the stub was reached"


def test_ssh_under_the_door_has_no_host_without_run_host(tmp_path: Path) -> None:
    door = fake_door(tmp_path)
    code = "from mcgyvr.serving import gatelib; gatelib.ssh('srv1', 'true')"
    result = under(door, [sys.executable, "-c", code], clean_env())
    assert result.returncode == 2, result.stderr
    assert "RUN_HOST" in result.stderr


def test_ssh_under_the_door_pipes_input_with_batchmode_and_a_timeout(
    tmp_path: Path,
) -> None:
    door = fake_door(tmp_path)
    stub = ssh_stub(tmp_path / "stubs")
    env = clean_env(stub.parent)
    env["RUN_HOST"] = "srv1"
    code = (
        "from mcgyvr.serving import gatelib\n"
        "done = gatelib.ssh('srv1', 'bash -s', input='hello reader')\n"
        "print(done.returncode, done.stdout.strip())\n"
    )
    result = under(door, [sys.executable, "-c", code], env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0 answered"
    log = (stub.parent / "ssh.log").read_text(encoding="utf-8").splitlines()
    assert log == [
        "argv=-o BatchMode=yes -o ConnectTimeout=10 srv1 bash -s",
        "stdin=hello reader",
    ]


def test_ssh_or_refuse_keeps_its_shape_and_propagates_the_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        gatelib.ssh_or_refuse("srv1", "true", "a read")
    assert raised.value.code == 2
    assert DOOR in capsys.readouterr().err


# --------------------------------------------------------------------------
# export: a descriptor the door named, or a refusal — never a stderr fallback
# --------------------------------------------------------------------------


def test_export_without_a_door_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("RUN_EXPORT_FD", raising=False)
    with pytest.raises(SystemExit) as raised:
        gatelib.export("RUN_THING", "value")
    assert raised.value.code == 2
    err = capsys.readouterr().err
    assert "started outside mcgyvr.serving.run" in err
    assert "RUN_THING" in err
    assert "(no door)" not in err


def test_export_writes_key_value_to_the_named_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_fd, write_fd = os.pipe()
    try:
        monkeypatch.setenv("RUN_EXPORT_FD", str(write_fd))
        gatelib.export("RUN_THING", "value")
        os.close(write_fd)
        write_fd = -1
        assert os.read(read_fd, 1024) == b"RUN_THING=value\n"
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)


def test_importing_gatelib_does_nothing() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import mcgyvr.serving.gatelib"],
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""


def test_gatelib_no_longer_names_a_docker_cli() -> None:
    assert not hasattr(gatelib, "docker"), "callers use the literal `docker`"


# --------------------------------------------------------------------------
# the shims' plumbing: which host an ssh argv names, which binary is next
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "host"),
    [
        (["-o", "X", "user@srv1", "cmd"], "srv1"),
        (["-p", "22", "srv1"], "srv1"),
        (["-p22", "srv1"], "srv1"),
        (["-oBatchMode=yes", "-l", "me", "srv2", "true"], "srv2"),
        (["-tt", "-i", "key", "-F", "cfg", "srv2", "cmd"], "srv2"),
        (["-4", "srv1"], "srv1"),
        (["--", "srv1", "docker", "system", "dial-stdio"], "srv1"),
        (["-o", "X", "--", "user@srv2"], "srv2"),
        (["srv1"], "srv1"),
        (["-o", "X"], None),
        (["-p", "22"], None),
        (["--"], None),
        ([], None),
    ],
)
def test_ssh_target_is_the_first_non_option_argument(
    argv: list[str], host: str | None
) -> None:
    assert gatelib.ssh_target(argv) == host


def test_next_on_path_skips_the_directory_it_is_told_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = tmp_path / "own"
    other = tmp_path / "other"
    executable(own / "tool", "#!/bin/sh\n")
    executable(other / "tool", "#!/bin/sh\n")
    monkeypatch.setenv("PATH", os.pathsep.join([str(own), str(other)]))
    assert gatelib.next_on_path("tool", skip=own) == str(other / "tool")
    assert gatelib.next_on_path("tool", skip=other) == str(own / "tool")
    assert gatelib.next_on_path("absent", skip=own) is None
