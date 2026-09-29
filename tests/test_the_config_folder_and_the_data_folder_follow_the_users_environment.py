"""The config folder and the data folder follow the user's environment.

Promise: mcgyvr keeps its settings in one config folder and its own files in
one data folder, and the user moves either one by naming it in the
environment: ``$MCGYVR_HOME`` for the config folder, ``$MCGYVR_DATA`` for the
data folder. Each moves alone. With nothing named, both sit under the user's
home folder, the data folder where the XDG base directory convention keeps
state. A value that could name a different folder from each working directory
is refused by the variable's name, never used; an empty value is no value. A
test never inherits either variable from the shell that ran it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr import derived
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
    assert roots.home() == Path(roots.HOME_DIR).expanduser()
    assert roots.home().is_relative_to(Path.home())


def test_every_setting_follows_the_config_folder_the_user_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "settings"
    monkeypatch.setenv("MCGYVR_HOME", str(moved))

    assert roots.home() == moved
    assert roots.fleets_dir().parent == moved
    assert roots.live_file().parent == moved
    assert derived.overrides_path().parent == moved
    assert roots.is_live(moved / "fleets" / "any")
    assert not roots.is_live(Path(roots.HOME_DIR).expanduser())


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
    assert roots.data_home() == Path(roots.DATA_DIR).expanduser()
    assert roots.data_home().is_relative_to(Path.home())


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
    assert roots.data_home() == tmp_path / "state" / roots.DATA_NAME


def test_a_state_folder_that_is_not_absolute_is_ignored_as_the_convention_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(STATE, "state")
    assert roots.data_home() == Path(roots.DATA_DIR).expanduser()


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


@pytest.mark.parametrize("name", MOVED)
def test_a_folder_that_is_not_absolute_is_refused_by_its_variables_name(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv(name, "relative/folder")
    with pytest.raises(roots.FolderError, match=name):
        roots.home() if name == "MCGYVR_HOME" else roots.data_home()


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
