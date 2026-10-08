"""The rig-file folder follows the user's environment (``$MCGYVR_RIGS``).

Promise: the door's user mode holds each run to a rig file — the read-only
ssh scan ``mcgyvr scan --rig`` saves. That file sits in the rig-file folder,
``<config folder>/rigs`` by default. The user moves the folder by naming it in
the environment: ``$MCGYVR_RIGS``. With nothing named, it stays under the
config folder (``$MCGYVR_HOME``, else ``~/.mcgyvr``). A value that could name
a different folder from each working directory is refused by the variable's
name, never used; an empty value is no value; ``~`` is expanded. Every reader
and writer of a rig file goes through :func:`mcgyvr.serving.rigfile.path`, so
a value that names no usable folder is a :class:`mcgyvr.serving.rigfile.RigFileError`
— the same refusal a bad rig name already is — everywhere a rig file is read
or written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.fleet import roots
from mcgyvr.serving import rigfile


def _unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MCGYVR_RIGS", "MCGYVR_HOME"):
        monkeypatch.delenv(name, raising=False)


def test_with_nothing_named_the_rigs_folder_sits_under_the_config_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    assert roots.rigs_dir() == roots.home() / "rigs"


def test_the_rigs_folder_follows_the_folder_the_user_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "rigs-elsewhere"
    monkeypatch.setenv("MCGYVR_RIGS", str(moved))
    assert roots.rigs_dir() == moved


def test_a_rigs_folder_named_from_the_users_home_is_expanded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv("MCGYVR_RIGS", "~/rigs-elsewhere")
    assert roots.rigs_dir() == Path.home() / "rigs-elsewhere"


def test_an_empty_rigs_folder_is_no_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv("MCGYVR_RIGS", "")
    assert roots.rigs_dir() == roots.home() / "rigs"


@pytest.mark.parametrize("value", ["relative/rigs", "~<user>/x"])
def test_a_rigs_folder_that_names_no_folder_is_refused_by_its_variables_name(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    monkeypatch.setenv("MCGYVR_RIGS", value)
    with pytest.raises(roots.FolderError, match="MCGYVR_RIGS"):
        roots.rigs_dir()


def test_the_rig_file_path_is_under_the_named_rigs_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "rigs-elsewhere"
    monkeypatch.setenv("MCGYVR_RIGS", str(moved))
    assert rigfile.path("rig-a") == moved / "rig-a.json"


def test_a_bad_rigs_folder_is_a_rig_file_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every reader already turns RigFileError into a clean refusal."""
    _unset(monkeypatch)
    monkeypatch.setenv("MCGYVR_RIGS", "relative/rigs")
    with pytest.raises(rigfile.RigFileError, match="MCGYVR_RIGS"):
        rigfile.path("rig-a")


def test_read_and_write_use_the_named_rigs_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unset(monkeypatch)
    moved = tmp_path / "rigs-elsewhere"
    monkeypatch.setenv("MCGYVR_RIGS", str(moved))
    from tests import sample_fleet

    path = sample_fleet.rig_file()
    assert path == moved / f"{sample_fleet.RIG}.json"
    assert rigfile.read(sample_fleet.RIG) is not None
