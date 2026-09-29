"""The config folder and the data folder follow the user's environment.

Promise: mcgyvr keeps its settings in one config folder, and names one data
folder for its own files; the user moves either one by naming it in the
environment: ``$MCGYVR_HOME`` for the config folder, ``$MCGYVR_DATA`` for the
data folder. Each moves alone. With nothing named, both sit under the user's
home folder, the data folder where the XDG base directory convention keeps
state. A value that could name a different folder from each working directory,
or that names no folder at all, is refused by the variable's name, never used;
an empty value is no value. Moving the config folder never unguards its
default: any mcgyvr command started without the variable still reads its
fleets there. A test never inherits either variable from the shell that ran
it.

What follows the config folder here: the live fleets, the pointer naming the
live one, and the user's own numbers. Only the data folder's place is settled
here: nothing is read or written through it yet.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr import cli, derived
from mcgyvr.fleet import roots

REPO = Path(__file__).resolve().parent.parent

#: The variables that move the two folders, and the convention's own.
MOVED = ("MCGYVR_HOME", "MCGYVR_DATA")
STATE = "XDG_STATE_HOME"


def _unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*MOVED, STATE):
        monkeypatch.delenv(name, raising=False)


def test_with_nothing_named_the_config_folder_is_the_default_under_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    assert roots.home() == Path.home() / ".mcgyvr"


def test_the_fleets_the_live_pointer_and_the_users_numbers_follow_the_named_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "settings"
    monkeypatch.setenv("MCGYVR_HOME", str(moved))

    assert roots.home() == moved
    assert roots.fleets_dir().parent == moved
    assert roots.live_file().parent == moved
    assert derived.overrides_path().parent == moved


def test_moving_the_config_folder_keeps_both_it_and_its_default_guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "settings"
    monkeypatch.setenv("MCGYVR_HOME", str(moved))

    assert roots.is_live(moved / "fleets" / "any")
    assert roots.is_live(Path.home() / ".mcgyvr" / "fleets" / "any")
    assert roots.is_live(moved)
    assert roots.is_live(Path.home() / ".mcgyvr")
    assert not roots.is_live(tmp_path / "elsewhere")
    assert not roots.is_live(tmp_path / f"{moved.name}-other")


@pytest.mark.parametrize("under", ["moved", "default"])
def test_a_lock_refused_under_a_guarded_folder_says_which_folders_are_guarded(
    under: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Refused under either folder, without calling it the live one."""
    _unset(monkeypatch)
    moved = tmp_path / "settings"
    monkeypatch.setenv("MCGYVR_HOME", str(moved))
    folder = moved if under == "moved" else Path.home() / ".mcgyvr"
    root = folder / "fleets" / "any"
    lock = ["fleet", "lock", "--fleet", "f.yaml", "--evidence", "e.json"]

    assert cli.main([*lock, "--root", str(root)]) == 1

    said = capsys.readouterr().err
    assert said.startswith(f"error: {root} "), said
    assert roots.HOME_DIR in said, said
    assert "is the live root" not in said, said


def test_the_default_stays_guarded_through_a_home_reached_by_a_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A home folder reached by a link guards the default by both its names."""
    _unset(monkeypatch)
    real = tmp_path / "real-home"
    real.mkdir()
    link = tmp_path / "link-home"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("HOME", str(link))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "settings"))

    assert roots.is_live(link / ".mcgyvr" / "fleets" / "any")
    assert roots.is_live(real / ".mcgyvr" / "fleets" / "any")


def test_a_config_folder_named_through_a_link_is_guarded_as_the_folder_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("MCGYVR_HOME", str(link))

    assert roots.is_live(real / "fleets" / "any")
    assert roots.is_live(link / "fleets" / "any")


def test_a_config_folder_named_from_the_users_home_is_expanded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv("MCGYVR_HOME", "~/settings")
    assert roots.home() == Path.home() / "settings"


def test_with_nothing_named_the_data_folder_is_the_default_under_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    assert roots.data_home() == Path.home() / ".local" / "state" / "mcgyvr"


def test_the_data_folder_follows_the_folder_the_user_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "data"
    monkeypatch.setenv("MCGYVR_DATA", str(moved))
    assert roots.data_home() == moved


def test_a_named_data_folder_wins_over_the_state_convention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(STATE, str(tmp_path / "state"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    assert roots.data_home() == tmp_path / "data"


def test_with_no_data_folder_named_it_sits_under_the_users_state_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(STATE, str(tmp_path / "state"))
    assert roots.data_home() == tmp_path / "state" / "mcgyvr"


@pytest.mark.parametrize("state", ["state", "~/state"])
def test_a_state_folder_that_is_not_absolute_is_ignored_as_the_convention_says(
    state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(STATE, state)
    assert roots.data_home() == Path.home() / ".local" / "state" / "mcgyvr"


def test_each_folder_moves_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    config, data = roots.home(), roots.data_home()

    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "settings"))
    assert roots.data_home() == data

    monkeypatch.delenv("MCGYVR_HOME")
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    assert roots.home() == config


@pytest.mark.parametrize("name", MOVED)
def test_an_empty_value_is_no_value(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _unset(monkeypatch)
    config, data = roots.home(), roots.data_home()
    monkeypatch.setenv(name, "")
    assert (roots.home(), roots.data_home()) == (config, data)


@pytest.mark.parametrize("value", ["relative/folder", "~<user>/x"])
@pytest.mark.parametrize("name", MOVED)
def test_a_value_that_names_no_folder_is_refused_by_its_variables_name(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(roots.FolderError, match=name):
        roots.home() if name == "MCGYVR_HOME" else roots.data_home()


def test_a_folder_refusal_is_caught_where_an_unresolvable_home_is() -> None:
    """Code that already survives a HOME it cannot resolve survives this too."""
    assert issubclass(roots.FolderError, RuntimeError)


def test_a_refused_config_folder_names_the_folder_unsetting_it_would_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv("MCGYVR_HOME", "relative/folder")
    with pytest.raises(roots.FolderError) as refused:
        roots.home()
    assert roots.HOME_DIR in str(refused.value)


def test_a_refused_data_folder_names_the_folder_unsetting_it_would_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(STATE, str(tmp_path / "state"))
    monkeypatch.setenv("MCGYVR_DATA", "relative/folder")
    with pytest.raises(roots.FolderError) as refused:
        roots.data_home()
    assert str(tmp_path / "state" / "mcgyvr") in str(refused.value)


#: The test the inner run holds: it passes only when the shared fixtures
#: cleared every variable that moves one of mcgyvr's folders.
INNER = f"""\
import os

def test_no_folder_variable_is_inherited():
    assert [n for n in {(*MOVED, STATE)!r} if n in os.environ] == []
"""


def test_a_test_never_inherits_either_folder_from_the_shell_that_ran_it(
    tmp_path: Path,
) -> None:
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "test_inner.py").write_text(INNER, encoding="utf-8")
    shell = dict(os.environ)
    for name in (*MOVED, STATE):
        shell[name] = str(tmp_path / "the-shells" / name)
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.conftest",
            "--basetemp",
            str(tmp_path / "basetemp"),
            "--rootdir",
            str(inner),
            str(inner / "test_inner.py"),
        ],
        cwd=REPO,
        env=shell,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
