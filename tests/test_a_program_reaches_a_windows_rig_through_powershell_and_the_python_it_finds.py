"""A program reaches a Windows rig through PowerShell and the Python it finds there.

Windows' OpenSSH runs a command in cmd.exe unless PowerShell is set as its
shell, and neither has ``base64 -d`` nor bash. So a shipped program goes as one
``powershell -NoProfile -NonInteractive -EncodedCommand`` line, which reads the
same under either shell, with the program (and, apart, what it reads on its own
stdin) on stdin. The script finds a Python 3.9 or newer (``py -3``, then
``python``), writes the program with WriteAllBytes, runs it with ``-I -B`` and
the arguments the door quoted, and removes it. The program, its arguments and
its feed arrive as sent: the fake Windows shell does what the script says and
runs them here. The read-only channel admits the Windows reader and header read
built from this checkout, and nothing else.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib
from tests.remote_rigs import FakeShell

ECHO_ARGS = (
    b"import json, sys\n"
    b"print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read(),"
    b" 'flags': [sys.flags.isolated, sys.dont_write_bytecode]}))\n"
)


def _script(command: str) -> str:
    script = gatelib._from_powershell(command)
    assert script is not None
    return script


def test_the_command_reads_the_same_under_cmd_and_powershell() -> None:
    sent = gatelib.ship(gatelib.WINDOWS, b"print(1)\n", ("--cards",))
    head, encoded = sent.command.rsplit(" ", 1)
    assert head == "powershell -NoProfile -NonInteractive -EncodedCommand"
    # Base64 alone after the flags: nothing either shell would read or quote.
    assert base64.b64decode(encoded, validate=True)
    script = _script(sent.command)
    for step in (
        "[IO.File]::WriteAllBytes($file, $program)",
        "@(@('py', '-3'), @('python'))",
        "sys.exit(sys.version_info < (3, 9))",
        "@('-I', '-B')",
        "Remove-Item -LiteralPath $file",
        "exit $code",
    ):
        assert step in script
    assert sent.stdin == base64.b64encode(b"print(1)\n").decode() + "\n"


def test_the_program_runs_with_its_arguments_and_its_own_stdin(tmp_path: Path) -> None:
    feed = b'{"token": "s3cret"}'
    args = ("mcgyvr-fetch", "C:\\Users\\Jane Doe\\w x.gguf", 'say "hi"')
    sent = gatelib.ship(gatelib.WINDOWS, ECHO_ARGS, args, feed=feed)
    # The feed (a job holding a token) is not in the command a process list shows.
    assert "s3cret" not in sent.command
    done = FakeShell("windows", tmp_path)("rig", sent.command, input=sent.stdin)
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)
    assert said == {"argv": list(args), "stdin": feed.decode(), "flags": [1, True]}
    # The file it was written to is gone.
    assert not list((tmp_path / "AppData" / "Local" / "mcgyvr" / "tmp").iterdir())


def test_a_posix_line_carries_no_feed() -> None:
    with pytest.raises(ValueError, match="no feed"):
        gatelib.ship(gatelib.LINUX, b"print(1)\n", feed=b"job")


def test_a_posix_line_quotes_an_argument_that_is_not_one_plain_token() -> None:
    sent = gatelib.ship(gatelib.DARWIN, b"print(1)\n", ("up", "line=a b"))
    assert sent.command.endswith(" | base64 -d | python3 -I -B - up 'line=a b'")
    assert sent.stdin is None


def test_the_read_only_channel_admits_the_windows_reads_built_here() -> None:
    scan = gatelib.scan_read(gatelib.WINDOWS)
    header = gatelib.header_read(gatelib.WINDOWS, "C:\\models\\Jane's m.gguf")
    listing = gatelib.windows_discover("C:\\models\\Jane's")
    assert gatelib._read_only_command(scan.command, scan.stdin)
    assert gatelib._read_only_command(header.command, header.stdin)
    assert gatelib._read_only_command(listing)
    assert gatelib._read_only_command(gatelib.PROBE_WINDOWS)


def test_the_read_only_channel_refuses_any_other_windows_program() -> None:
    scan = gatelib.scan_read(gatelib.WINDOWS)
    cards = gatelib.scan_read(gatelib.WINDOWS, cards=True)
    other = gatelib.ship(gatelib.WINDOWS, b"import os; os.remove('x')\n")
    two = gatelib.ship(gatelib.WINDOWS, gatelib._header_source(), ("a", "b"))
    assert scan.stdin is not None
    tampered = scan.stdin.replace(
        scan.stdin[5], "A" if scan.stdin[5] != "A" else "B", 1
    )
    assert not gatelib._read_only_command(scan.command, tampered)
    assert not gatelib._read_only_command(scan.command, None)
    assert not gatelib._read_only_command(scan.command, scan.stdin + "ZmVlZA==\n")
    # `--cards` goes under the door, as on POSIX.
    assert not gatelib._read_only_command(cards.command, cards.stdin)
    assert not gatelib._read_only_command(other.command, other.stdin)
    assert not gatelib._read_only_command(two.command, two.stdin)
    assert not gatelib._read_only_command(gatelib.powershell("Remove-Item C:\\x"))
    # A POSIX line with a stdin is no read either.
    assert not gatelib._read_only_command(gatelib.scan_read_command(), "x")


def test_the_windows_reader_is_the_reader_the_posix_line_ships() -> None:
    windows = gatelib.scan_read(gatelib.WINDOWS)
    posix = gatelib.scan_read_command()
    assert windows.stdin is not None
    assert windows.stdin.split("\n")[0] == posix.split(" ")[1]


def test_the_windows_listing_finds_gguf_files_with_a_quoted_folder() -> None:
    script = _script(gatelib.windows_discover("C:\\it's here"))
    assert "-LiteralPath 'C:\\it''s here'" in script
    assert "$_.Extension -eq '.gguf'" in script
    with pytest.raises(ValueError):
        gatelib.windows_discover("")


def test_a_cmd_shell_does_not_run_the_posix_line(tmp_path: Path) -> None:
    done = FakeShell("windows", tmp_path)("rig", gatelib.scan_read_command())
    assert isinstance(done, subprocess.CompletedProcess)
    assert done.returncode != 0


def test_the_arguments_split_back_as_windows_splits_a_command_line() -> None:
    import random

    rng = random.Random(7)
    cases = [
        ["C:\\m\\a.gguf"],
        ["a b", "c"],
        ['say "hi"'],
        ["trailing\\"],
        ["", ""],
        *(
            ["".join(rng.choice('ab \\"\t') for _ in range(rng.randint(0, 7)))]
            for _ in range(500)
        ),
    ]
    for args in cases:
        assert gatelib.windows_split(subprocess.list2cmdline(args)) == args
