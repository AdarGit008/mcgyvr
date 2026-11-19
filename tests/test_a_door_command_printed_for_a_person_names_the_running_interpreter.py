"""A door command printed for a person runs as printed.

The door is the module `mcgyvr.serving.run`, and only the interpreter running
mcgyvr is sure to import it: on a uv tool install no `python` is on PATH, and
where one is, it need not be the environment that holds mcgyvr. So every door
command mcgyvr tells a person to run starts with `sys.executable`, joined by
`gatelib.door_line`:

* **the live admission's clean and restore lines** (`fleet.admission.door_commands`);
* **the refusal of a native status read of another machine** (`serve status --host`);
* **the refusal of a card with several launch specs** (`wake._why_not_one`).

Each line is split back by the rule it was joined with (`shlex` on POSIX,
PowerShell's single quotes on Windows): its first word is the running
interpreter, the next two are `-m` and the door's module, and the door's own
parser takes the rest. The several-specs line is a template, with DIRECTION
and FILE named as such in the same sentence; the parser takes it once they are
filled in as that sentence says.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path, PureWindowsPath

import pytest

from mcgyvr.exits import Exit
from mcgyvr.serving import Card, run
from mcgyvr.serving.gatelib import DOOR_MODULE, door_line

#: A command in a printed line: the text between backticks.
QUOTED = re.compile(r"`([^`]*)`")
#: What PowerShell reads as a single quote: ' and U+2018, U+2019, U+201A, U+201B.
SINGLE = "'\u2018\u2019\u201a\u201b"
#: A word of a PowerShell line: in single quotes, a quote in it written twice,
#: or bare.
POWERSHELL_WORD = re.compile(
    f"[{SINGLE}]((?:[^{SINGLE}]|[{SINGLE}]{{2}})*)[{SINGLE}]" + r"|(\S+)"
)


@pytest.fixture
def interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """An interpreter whose path needs quoting and is not named `python`, on a
    POSIX machine, so the lines are shlex's on a Windows runner too."""
    path = str(tmp_path / "a tool env" / "bin" / "python3.12")
    monkeypatch.setattr(sys, "executable", path)
    monkeypatch.setattr(sys, "platform", "linux")
    return path


def door_words(text: str) -> list[list[str]]:
    """Every door command in `text`, split as a POSIX shell splits it."""
    commands = [shlex.split(quoted) for quoted in QUOTED.findall(text)]
    return [words for words in commands if words[1:3] == ["-m", DOOR_MODULE]]


def powershell_split(line: str) -> list[str]:
    assert line.startswith("& "), line
    return [
        re.sub(f"([{SINGLE}])\\1", r"\1", word[1]) if word[1] is not None else word[2]
        for word in POWERSHELL_WORD.finditer(line[2:])
    ]


def assert_runs(words: list[str], interpreter: str) -> None:
    """The words are a door command the door's own parser takes."""
    assert words[0] == interpreter, words
    assert "python" not in words, words
    assert words[1:3] == ["-m", DOOR_MODULE], words
    verb, *rest = words[3:]
    parse = {"serve": run._serve_parse, "read": run._read_parse}[verb]
    parse(rest)


def test_the_admission_lines_name_the_running_interpreter(interpreter: str) -> None:
    from mcgyvr.fleet.admission import door_commands
    from mcgyvr.fleet.admit import Plan

    fleet = {"units": {"first": {"unit_id": "unit-1"}}}
    plan = Plan(
        clean=[("box2", "mcgyvr-box2-stray")], restore=[("box1", "unit-1", "awake")]
    )
    lines = door_commands(fleet, "f", plan)
    commands = [words for line in lines for words in door_words(line)]

    assert [words[3:5] for words in commands] == [
        ["serve", "down"],
        ["serve", "up"],
        ["serve", "up"],
    ]
    for words in commands:
        assert_runs(words, interpreter)


def test_the_status_refusal_names_the_running_interpreter(
    interpreter: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.cli.commands.ladder import _native_status

    assert _native_status("box9") == Exit.REFUSED
    (words,) = door_words(capsys.readouterr().err)

    assert words[3:] == ["read", "--host", "box9"]
    assert_runs(words, interpreter)


def test_the_several_specs_refusal_names_the_running_interpreter(
    interpreter: str, tmp_path: Path
) -> None:
    from mcgyvr.wake import _why_not_one

    specs = (tmp_path / "compose.box1.a.yml", tmp_path / "compose.box1.b.yml")
    said = _why_not_one(Card("box1", None, specs=specs))
    (words,) = door_words(said)

    # A template: the sentence names what DIRECTION and FILE are, and where.
    assert words[3:] == ["serve", "DIRECTION", "--host", "box1", "--compose", "FILE"]
    assert "DIRECTION one of up, down, sleep and wake" in said, said
    assert f"FILE the current one's path in {tmp_path}." in said, said
    for direction in ("up", "down", "sleep", "wake"):
        for spec in specs:
            assert spec.name in said, said
            filled = [
                {"DIRECTION": direction, "FILE": str(tmp_path / spec.name)}.get(w, w)
                for w in words
            ]
            assert_runs(filled, interpreter)


def test_a_windows_line_is_powershells(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every character PowerShell reads as a single quote, in the user's folder.
    user = "it's \u2018a\u2019 \u201ab\u201b"
    folder = PureWindowsPath("C:/", "Users", user, "Scripts")
    path = str(folder / "python.exe")
    monkeypatch.setattr(sys, "executable", path)
    args = ("serve", "up", "--host", "box1", "--compose", "compose.box 1.yml")

    line = door_line(*args, windows=True)

    doubled = "".join(mark * 2 if mark in SINGLE else mark for mark in path)
    assert line.startswith(f"& '{doubled}' -m "), line
    assert powershell_split(line) == [path, "-m", DOOR_MODULE, *args]
    assert_runs(powershell_split(line), path)


def test_a_posix_line_is_shlexs(interpreter: str) -> None:
    args = ("read", "--host", "box 1")

    line = door_line(*args, windows=False)

    assert line == shlex.join([interpreter, "-m", DOOR_MODULE, *args])
    assert shlex.split(line) == [interpreter, "-m", DOOR_MODULE, *args]
