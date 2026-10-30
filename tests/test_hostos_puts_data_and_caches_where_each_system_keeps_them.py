"""hostos puts mcgyvr's data and caches where each system keeps them.

Linux keeps today's XDG places; macOS its ``~/Library`` folders; Windows
``%LOCALAPPDATA%``. A ``$XDG_STATE_HOME`` or ``$XDG_CACHE_HOME`` the user set
wins on every system. The config folder stays ``~/.mcgyvr`` everywhere; the
data folder, the index cache, the weights and the per-user temporary folders
follow. The home is looked up only when a folder is under it.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

from mcgyvr import hostos
from mcgyvr.fleet import roots
from mcgyvr.orchestrator import cache
from mcgyvr.serving import fetcher, rigscan
from tests.hostos_fakes import as_system

#: Each system's data and cache folders, under a home of ``~`` and a local
#: application-data folder of ``LOCAL``, with no XDG variable set.
NATIVE = {
    "linux": ("~/.local/state/mcgyvr", "~/.cache/mcgyvr"),
    "darwin": ("~/Library/Application Support/mcgyvr", "~/Library/Caches/mcgyvr"),
    "windows": ("LOCAL/mcgyvr", "LOCAL/mcgyvr/cache"),
}


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    for name in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "MCGYVR_DATA", "MCGYVR_WEIGHTS"):
        monkeypatch.delenv(name, raising=False)
    return folder


def _place(spelled: str, home: Path) -> Path:
    if spelled.startswith("~/"):
        return home / spelled[2:]
    return home.parent / "local" / spelled.removeprefix("LOCAL/")


@pytest.mark.parametrize("system", sorted(NATIVE))
def test_each_system_keeps_data_and_caches_in_its_own_place(
    system: str, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    data, cached = NATIVE[system]
    assert hostos.user_data_dir() == _place(data, home)
    assert hostos.user_cache_dir() == _place(cached, home)
    assert roots.data_home() == hostos.user_data_dir()
    assert cache.cache_dir() == hostos.user_cache_dir() / "index"
    assert roots.home() == home / ".mcgyvr"


@pytest.mark.parametrize("system", sorted(NATIVE))
def test_the_xdg_variables_the_user_set_win_on_every_system(
    system: str, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", "~/my-cache")
    assert hostos.user_data_dir() == tmp_path / "state" / "mcgyvr"
    assert hostos.user_cache_dir() == home / "my-cache" / "mcgyvr"


def test_a_relative_xdg_state_home_is_passed_over(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "linux")
    monkeypatch.setenv("XDG_STATE_HOME", "relative/state")
    assert hostos.user_data_dir() == home / ".local" / "state" / "mcgyvr"


@pytest.mark.parametrize("local", [None, "relative\\Local"])
def test_windows_without_a_usable_localappdata_uses_the_profiles_own(
    local: str | None, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    if local is None:
        monkeypatch.delenv("LOCALAPPDATA")
    else:
        monkeypatch.setenv("LOCALAPPDATA", local)
    assert hostos.user_data_dir() == home / "AppData" / "Local" / "mcgyvr"


@pytest.mark.skipif(sys.platform == "win32", reason="Linux's own folders")
def test_a_relative_data_folder_is_refused_naming_the_systems_default(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_DATA", "relative")
    as_system(monkeypatch, "linux")
    with pytest.raises(
        roots.FolderError, match=re.escape("to use ~/.local/state/mcgyvr") + "$"
    ):
        roots.data_home()
    state = home / ".local" / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    shown = re.escape(f"to use {state / 'mcgyvr'}") + "$"
    with pytest.raises(roots.FolderError, match=shown):
        roots.data_home()
    monkeypatch.delenv("XDG_STATE_HOME")
    as_system(monkeypatch, "darwin")
    native = home / "Library" / "Application Support" / "mcgyvr"
    with pytest.raises(roots.FolderError, match=re.escape(f"to use {native}") + "$"):
        roots.data_home()


@pytest.mark.parametrize("system", sorted(NATIVE))
def test_the_weights_sit_in_the_systems_cache_whatever_xdg_says(
    system: str, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    native = hostos.user_cache_dir() / "weights"
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "elsewhere"))
    assert Path(rigscan.default_weights_dir()) == native
    assert Path(fetcher.weights_dir()) == native


@pytest.mark.parametrize("system", sorted(NATIVE))
def test_a_folder_the_variables_name_needs_no_home(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    def no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", staticmethod(no_home))
    assert roots.data_home() == tmp_path / "state" / "mcgyvr"
    assert cache.cache_dir() == tmp_path / "cache" / "mcgyvr" / "index"


def test_per_user_temporary_folders_sit_in_the_system_temp_or_the_profile(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "shared-tmp"))
    for system in ("linux", "darwin"):
        as_system(monkeypatch, system)
        assert hostos.user_temp_root() == tmp_path / "shared-tmp"
    as_system(monkeypatch, "windows")
    monkeypatch.setenv("TEMP", "C:\\Temp")
    assert hostos.user_temp_root() == tmp_path / "local" / "mcgyvr" / "tmp"
