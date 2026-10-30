"""The shipped programs run in a real shell of the system the tests run on.

The fake shells of :mod:`tests.remote_rigs` hold the plumbing; these hold the
real thing, each on its own system (the ``platforms`` workflow runs them on
macOS and Windows): a POSIX shell decodes the ``echo <base64> | base64 -d |
python3 -I -B -`` line and runs it, and Windows runs the PowerShell launcher
under cmd.exe (OpenSSH's default shell) and under PowerShell, finds a Python,
and hands the program its arguments and its feed. The reader run this way reads
an empty invented machine (``MCGYVR_TEST_MACHINE_ROOT``, with no tool on PATH
but the shell's own), never the machine the tests run on.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib
from tests.machinereader import ROOT_VARIABLE

ECHO_ARGS = (
    b"import json, sys\n"
    b"print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}))\n"
)

posix = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("python3") is None
    or shutil.which("base64") is None,
    reason="a POSIX shell with base64 and python3",
)
windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows' own shells")


@posix
def test_a_posix_shell_runs_the_shipped_line() -> None:
    sent = gatelib.ship(gatelib.LINUX, ECHO_ARGS, ("up", "line=a b"))
    done = subprocess.run(
        ["/bin/sh", "-c", sent.command], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"argv": ["up", "line=a b"], "stdin": ""}


@posix
def test_a_posix_shell_runs_the_reader_over_an_invented_machine(tmp_path: Path) -> None:
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("base64", "python3"):
        found = shutil.which(name)
        assert found is not None
        (tools / name).symlink_to(found)
    (tmp_path / "root").mkdir()
    done = subprocess.run(
        ["/bin/sh", "-c", gatelib.cards_read_command()],
        capture_output=True,
        text=True,
        timeout=180,
        env={"PATH": str(tools), ROOT_VARIABLE: str(tmp_path / "root"), "LC_ALL": "C"},
        check=False,
    )
    if "needs Python 3.9" in done.stderr:
        pytest.skip("this machine's python3 is older than the shipped floor")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["host"]["os"] == "linux"  # a test root's


def _windows_shells(command: str) -> list[list[str]]:
    return [
        ["cmd.exe", "/d", "/c", command],
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
    ]


@windows
def test_windows_shells_answer_the_probe() -> None:
    for argv in _windows_shells(gatelib.PROBE_WINDOWS):
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        assert done.stdout.strip() == gatelib.WINDOWS_PLATFORM, (argv[0], done.stderr)


@windows
def test_windows_shells_run_the_launcher_with_arguments_and_feed() -> None:
    args = ("mcgyvr-fetch", "C:\\Users\\Jane Doe\\w x.gguf", "Bob\u2019s $(x)")
    sent = gatelib.ship(gatelib.WINDOWS, ECHO_ARGS, args, feed=b'{"job": 1}')
    for argv in _windows_shells(sent.command):
        done = subprocess.run(
            argv, input=sent.stdin, capture_output=True, text=True, check=False
        )
        assert done.returncode == 0, (argv[0], done.stderr)
        said = json.loads(done.stdout)
        assert said == {"argv": list(args), "stdin": '{"job": 1}'}, argv[0]


@windows
def test_windows_runs_the_shipped_reader_over_an_invented_machine(
    tmp_path: Path,
) -> None:
    sent = gatelib.scan_read(gatelib.WINDOWS, cards=True)
    # PATH holds the Python found and PowerShell, and no card tool: the
    # reader reads the empty invented machine, not this one.
    system = os.environ.get("SYSTEMROOT", "C:\\Windows")
    shells = [os.path.join(system, "System32", "WindowsPowerShell", "v1.0")]
    python = os.path.dirname(sys.executable)
    env = {
        **{k: v for k, v in os.environ.items() if k.upper() != "PATH"},
        "PATH": os.pathsep.join([python, *shells]),
        ROOT_VARIABLE: str(tmp_path),
    }
    done = subprocess.run(
        ["cmd.exe", "/d", "/c", sent.command],
        input=sent.stdin,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["host"]["os"] == "linux"  # a test root's
