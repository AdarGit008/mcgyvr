"""A folder variable that names no usable folder is refused in one line.

Promise: when the variable that moves mcgyvr's config folder names no usable
folder, a command refuses with one line, never a traceback. A value that names
no folder at all (not an absolute path, or a home that cannot be expanded) is
refused by the variable's name; a folder that is there and cannot be searched
is refused by the path that could not be used; ``fleet lock``'s guard also
refuses one that loops back on itself where Python raises on the loop (3.12),
and other readers see it as holding no live.json.
Every reader of the pointer naming the live fleet refuses it as it refuses a
pointer that cannot be read, so a run, a probe or the door's first gate says
why it cannot tell which fleet is live. The version line still prints, and
says why the config cannot be read.

Nothing is reached: every command here refuses before it would read a machine.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.fleet import roots
from tests._helpers import by_path

REPO = Path(__file__).resolve().parent.parent
GATE_1 = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "01-round.py"
#: Values that name no folder: one is not absolute, one cannot be expanded.
UNUSABLE = ("relative/folder", "~<user>/x")
#: What the installed ``mcgyvr`` command runs.
ENTRY = "from mcgyvr.cli import main; raise SystemExit(main())"
#: Commands that each reach the config folder before anything else.
COMMANDS = (
    ("config",),
    ("fleet", "use", "any"),
    ("fleet", "tag", "any"),
    ("fleet", "probe"),
    ("fleet", "alerts"),
)


@pytest.fixture
def unusable(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    value = str(request.param)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCGYVR_HOME", value)
    return value


@pytest.mark.parametrize("unusable", UNUSABLE, indirect=True)
@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_a_command_refuses_it_in_one_line_naming_the_variable(
    command: tuple[str, ...], unusable: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(list(command)) == 1

    said = capsys.readouterr().err
    assert said.startswith("error: $MCGYVR_HOME="), said
    assert said.count("\n") == 1, said


@pytest.mark.parametrize("unusable", UNUSABLE, indirect=True)
def test_the_live_pointer_is_refused_as_one_that_cannot_be_read(
    unusable: str,
) -> None:
    with pytest.raises(roots.LiveFleetError, match="MCGYVR_HOME"):
        roots.live_fleet()


@pytest.mark.parametrize("unusable", UNUSABLE, indirect=True)
def test_the_first_gate_refuses_a_live_serve_by_the_variables_name(
    unusable: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RUN_HOST", "served.invalid")
    monkeypatch.setenv("RUN_SERVE_EXPECTED", "u1")
    gate = by_path("gate_01_round", GATE_1)

    with pytest.raises(SystemExit):
        gate.refuse_unless_the_fleet_lock_names("up", "live")

    said = capsys.readouterr().err
    assert "gate 1: $MCGYVR_HOME=" in said, said


@pytest.mark.parametrize("unusable", UNUSABLE, indirect=True)
def test_the_version_line_still_prints_and_says_why(
    unusable: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])

    assert exited.value.code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("mcgyvr "), lines
    assert lines[1].startswith("config: ") and "MCGYVR_HOME" in lines[1], lines


def test_the_installed_command_prints_no_traceback(tmp_path: Path) -> None:
    shell = {**os.environ, "HOME": str(tmp_path), "MCGYVR_HOME": UNUSABLE[0]}
    done = subprocess.run(
        [sys.executable, "-c", ENTRY, "config"],
        cwd=tmp_path,
        env=shell,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert done.returncode == 1, (done.stdout, done.stderr)
    assert "Traceback" not in done.stderr, done.stderr
    assert done.stderr.startswith("error: $MCGYVR_HOME="), done.stderr


@pytest.fixture
def unsearchable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A config folder named by an absolute path inside a folder nobody may search."""
    locked = tmp_path / "locked"
    folder = locked / "settings"
    folder.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCGYVR_HOME", str(folder))
    locked.chmod(0)
    try:
        if os.access(folder, os.F_OK):
            pytest.skip("this user searches a folder whatever its mode says")
        yield folder
    finally:
        locked.chmod(0o755)


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_a_command_refuses_a_folder_it_cannot_search_in_one_line_naming_it(
    command: tuple[str, ...], unsearchable: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(list(command)) == 1

    said = capsys.readouterr().err
    assert said.startswith("error: "), said
    assert str(unsearchable) in said, said
    assert said.count("\n") == 1, said


def test_a_pointer_in_a_folder_it_cannot_search_is_refused_as_one_that_cannot_be_read(
    unsearchable: Path,
) -> None:
    with pytest.raises(roots.LiveFleetError, match="cannot be read") as refused:
        roots.live_fleet()

    assert str(unsearchable / "live.json") in str(refused.value)


def test_the_first_gate_refuses_a_folder_it_cannot_search_by_its_path(
    unsearchable: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RUN_HOST", "served.invalid")
    monkeypatch.setenv("RUN_SERVE_EXPECTED", "u1")
    gate = by_path("gate_01_round", GATE_1)

    with pytest.raises(SystemExit):
        gate.refuse_unless_the_fleet_lock_names("up", "live")

    said = capsys.readouterr().err
    assert "gate 1: " in said and str(unsearchable) in said, said
    assert "Traceback" not in said, said


def test_the_version_line_says_a_folder_it_cannot_search_cannot_be_read(
    unsearchable: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])

    assert exited.value.code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].startswith("config: unreadable ("), lines
    assert str(unsearchable) in lines[1], lines


def test_a_config_folder_that_loops_back_on_itself_is_refused_in_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """On Python 3.12 a link to itself never resolves; on later Pythons it
    resolves and the folder is seen as holding no live.json."""
    loop = tmp_path / "settings"
    loop.symlink_to(loop)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCGYVR_HOME", str(loop))
    dev = tmp_path / "dev"
    lock = ["fleet", "lock", "--fleet", "f.yaml", "--evidence", "e.json"]

    assert cli.main([*lock, "--root", str(dev)]) == 1

    said = capsys.readouterr().err
    assert said.startswith("error: "), said
    assert str(loop) in said, said
    assert said.count("\n") == 1, said
