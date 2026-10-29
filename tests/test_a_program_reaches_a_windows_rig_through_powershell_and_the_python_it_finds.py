"""A program reaches a Windows rig through PowerShell and the Python it finds there.

Windows' OpenSSH runs a command in cmd.exe unless PowerShell is set as its
shell, and neither has ``base64 -d`` nor bash. So every shipped program goes by
one constant ``powershell -NoProfile -NonInteractive -EncodedCommand`` line,
which reads the same under either shell and stays far under cmd.exe's 8191
characters however many units it starts. What changes from one shipment to the
next (the program, its arguments, what it reads on its own stdin) travels on
stdin, never inside a script, so no path or argument can be read as PowerShell,
whatever quotes it holds. The script finds a Python 3.9 or newer (each ``py
-3``, then each ``python``), writes the program with WriteAllBytes, runs it
with ``-I -B`` and the arguments, and removes it. The read-only channel admits
the Windows reader, header read and listing built from this checkout, and
nothing else.
"""

from __future__ import annotations

import base64
import json
import random
import subprocess
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib, native
from tests.remote_rigs import FakeShell

ECHO_ARGS = (
    b"import json, sys\n"
    b"print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read(),"
    b" 'flags': [sys.flags.isolated, sys.dont_write_bytecode]}))\n"
)
#: cmd.exe's longest command line
#: (https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/command-line-string-limitation).
CMD_MAX = 8191
#: Every character PowerShell reads as a single quote: ASCII and U+2018-U+201B.
QUOTES = "'\u2018\u2019\u201a\u201b"


def _script(command: str) -> str:
    assert command.startswith(gatelib.POWERSHELL)
    encoded = command[len(gatelib.POWERSHELL) :]
    return base64.b64decode(encoded, validate=True).decode("utf-16-le")


def test_one_constant_command_runs_every_program() -> None:
    one = gatelib.ship(gatelib.WINDOWS, b"print(1)\n", ("--cards",))
    other = gatelib.ship(gatelib.WINDOWS, ECHO_ARGS, ("a", "b c"), feed=b"x")
    assert one.command == other.command == gatelib.WINDOWS_SHIP
    script = _script(gatelib.WINDOWS_SHIP)
    for step in (
        "[IO.File]::WriteAllBytes($file, $program)",
        "@(@('py', '-3'), @('python'))",
        "-CommandType Application -All",
        "sys.exit(sys.version_info < (3, 9))",
        "@('-I', '-B')",
        "Remove-Item -LiteralPath $file",
        "exit $code",
    ):
        assert step in script
    assert len(gatelib.WINDOWS_SHIP) < CMD_MAX
    assert len(gatelib.WINDOWS_DISCOVER) < CMD_MAX


def test_many_units_still_fit_one_cmd_line() -> None:
    unit = native.NativeUnit(
        name="m",
        container="mcgyvr-box1-m-8080",
        program="llama-server",
        argv=("--model", "C:\\Users\\Jane Doe\\w\\m.gguf", "--port", "8080") * 6,
        env={"CUDA_VISIBLE_DEVICES": "0"},
        port=8080,
        cards=(0,),
        depends_on=(),
        asleep=False,
    )
    units = native.units_text([unit] * 8)
    sent = gatelib.ship(gatelib.WINDOWS, b"print(1)\n", ("up", units))
    assert len(sent.command) < CMD_MAX
    posix = gatelib.ship(gatelib.DARWIN, b"x" * 200_000, ("up", units), on_stdin=True)
    assert len(posix.command) < 32 * 1024  # the program is on stdin
    assert posix.stdin is not None and posix.stdin.endswith("\n")


def test_the_program_runs_with_its_arguments_and_its_own_stdin(tmp_path: Path) -> None:
    feed = b'{"token": "s3cret"}'
    args = (
        "mcgyvr-fetch",
        "C:\\Users\\Jane Doe\\w x.gguf",
        'say "hi"',
        f"Bob{QUOTES}s; $(calc) `n",
        "trailing\\",
    )
    sent = gatelib.ship(gatelib.WINDOWS, ECHO_ARGS, args, feed=feed)
    # Neither the feed (a job holding a token) nor an argument is in the
    # command a process list shows.
    assert "s3cret" not in sent.command and "calc" not in _script(sent.command)
    done = FakeShell("windows", tmp_path)("rig", sent.command, input=sent.stdin)
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)
    assert said == {"argv": list(args), "stdin": feed.decode(), "flags": [1, True]}
    assert not list((tmp_path / "AppData" / "Local" / "mcgyvr" / "tmp").iterdir())


def test_a_posix_line_carries_no_feed() -> None:
    with pytest.raises(ValueError, match="no feed"):
        gatelib.ship(gatelib.LINUX, b"print(1)\n", feed=b"job")


def test_a_posix_line_quotes_an_argument_that_is_not_one_plain_token() -> None:
    sent = gatelib.ship(gatelib.DARWIN, b"print(1)\n", ("up", "line=a b"))
    assert sent.command.endswith(" | base64 -d | python3 -I -B - up 'line=a b'")
    assert sent.stdin is None


@pytest.mark.parametrize("quote", list(QUOTES))
def test_the_read_only_channel_admits_the_windows_reads_built_here(quote: str) -> None:
    path = f"C:\\models\\Jane{quote}s $(calc) m.gguf"
    scan = gatelib.scan_read(gatelib.WINDOWS)
    header = gatelib.header_read(gatelib.WINDOWS, path)
    listing = gatelib.windows_discover(f"C:\\models\\Jane{quote}s; $(calc)")
    assert gatelib._read_only_command(scan.command, scan.stdin)
    assert gatelib._read_only_command(header.command, header.stdin)
    assert gatelib._read_only_command(listing.command, listing.stdin)
    assert gatelib._read_only_command(gatelib.PROBE_WINDOWS)
    # Nothing of the path or the folder is in a script.
    assert "calc" not in _script(header.command) + _script(listing.command)


def test_the_read_only_channel_refuses_any_other_windows_program() -> None:
    scan = gatelib.scan_read(gatelib.WINDOWS)
    cards = gatelib.scan_read(gatelib.WINDOWS, cards=True)
    other = gatelib.ship(gatelib.WINDOWS, b"import os; os.remove('x')\n")
    two = gatelib.ship(gatelib.WINDOWS, gatelib._header_source(), ("a", "b"))
    fed = gatelib.ship(gatelib.WINDOWS, gatelib._header_source(), ("a",), feed=b"x")
    assert scan.stdin is not None
    first = scan.stdin[0]
    tampered = ("A" if first != "A" else "B") + scan.stdin[1:]
    assert not gatelib._read_only_command(scan.command, tampered)
    assert not gatelib._read_only_command(scan.command, None)
    assert not gatelib._read_only_command(scan.command, scan.stdin + "ZmVlZA==\n")
    # `--cards` goes under the door, as on POSIX.
    assert not gatelib._read_only_command(cards.command, cards.stdin)
    assert not gatelib._read_only_command(other.command, other.stdin)
    assert not gatelib._read_only_command(two.command, two.stdin)
    assert not gatelib._read_only_command(fed.command, fed.stdin)
    assert not gatelib._read_only_command(gatelib.powershell("Remove-Item C:\\x"))
    assert not gatelib._read_only_command(gatelib.WINDOWS_DISCOVER, "\n")
    # A POSIX line with a stdin is no read either.
    assert not gatelib._read_only_command(gatelib.scan_read_command(), "x")


def test_the_windows_reader_is_the_reader_the_posix_line_ships() -> None:
    windows = gatelib.scan_read(gatelib.WINDOWS)
    posix = gatelib.scan_read_command()
    assert windows.stdin is not None
    assert windows.stdin.split("\n")[0] == posix.split(" ")[1]


def test_the_windows_listing_finds_gguf_files_in_the_folder_sent(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.gguf").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"")
    sent = gatelib.windows_discover(str(tmp_path))
    assert "$_.Extension -eq '.gguf'" in _script(sent.command)
    done = FakeShell("windows", tmp_path)("rig", sent.command, input=sent.stdin)
    assert done.stdout.split() == [str(tmp_path / "a.gguf")]
    with pytest.raises(ValueError):
        gatelib.windows_discover("")


def test_a_cmd_shell_does_not_run_the_posix_line(tmp_path: Path) -> None:
    done = FakeShell("windows", tmp_path)("rig", gatelib.scan_read_command())
    assert isinstance(done, subprocess.CompletedProcess)
    assert done.returncode != 0


def test_the_arguments_split_back_as_windows_splits_a_command_line() -> None:
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
