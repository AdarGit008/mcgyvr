"""hostos puts mcgyvr's data and caches where each system keeps them.

Linux keeps today's XDG places; macOS its ``~/Library`` folders; Windows
``%LOCALAPPDATA%``. A ``$XDG_STATE_HOME`` or ``$XDG_CACHE_HOME`` the user set
wins on every system. The config folder stays ``~/.mcgyvr`` everywhere, the
data folder, the index cache and the weights follow, and the shell whose rc
file setup offers to extend is named the same way on every system.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcgyvr import hostos
from mcgyvr.cli.commands.setup import _offer_path_append, _shell_rc
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
    found = hostos.user_dirs()
    assert found == hostos.UserDirs(
        home=home, data=_place(data, home), cache=_place(cached, home)
    )
    assert roots.data_home() == found.data
    assert cache.cache_dir() == found.cache / "index"
    assert roots.home() == home / ".mcgyvr"


@pytest.mark.parametrize("system", sorted(NATIVE))
def test_the_xdg_variables_the_user_set_win_on_every_system(
    system: str, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", "~/my-cache")
    found = hostos.user_dirs()
    assert found.data == tmp_path / "state" / "mcgyvr"
    assert found.cache == home / "my-cache" / "mcgyvr"


def test_a_relative_xdg_state_home_is_passed_over(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "linux")
    monkeypatch.setenv("XDG_STATE_HOME", "relative/state")
    assert hostos.user_dirs().data == home / ".local" / "state" / "mcgyvr"


@pytest.mark.parametrize("local", [None, "relative\\Local"])
def test_windows_without_a_usable_localappdata_uses_the_profiles_own(
    local: str | None, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    if local is None:
        monkeypatch.delenv("LOCALAPPDATA")
    else:
        monkeypatch.setenv("LOCALAPPDATA", local)
    assert hostos.user_dirs().data == home / "AppData" / "Local" / "mcgyvr"


def test_a_relative_data_folder_is_refused_naming_the_systems_default(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_DATA", "relative")
    as_system(monkeypatch, "linux")
    with pytest.raises(
        roots.FolderError, match=re.escape("to use ~/.local/state/mcgyvr") + "$"
    ):
        roots.data_home()
    as_system(monkeypatch, "darwin")
    native = home / "Library" / "Application Support" / "mcgyvr"
    with pytest.raises(roots.FolderError, match=re.escape(f"to use {native}") + "$"):
        roots.data_home()


@pytest.mark.parametrize("system", sorted(NATIVE))
def test_the_weights_sit_in_the_systems_cache_whatever_xdg_says(
    system: str, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    native = hostos.user_dirs().cache / "weights"
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "elsewhere"))
    assert rigscan.default_weights_dir() == str(native)
    assert fetcher.weights_dir() == str(native)


@pytest.mark.parametrize(
    ("shell", "named"),
    [
        ("/bin/bash", ".bashrc"),
        ("/usr/bin/zsh", ".zshrc"),
        ("/bin/dash", ".profile"),
        ("sh", ".profile"),
        ("/usr/bin/fish", ".config/fish/config.fish"),
        ("pwsh", "Documents/PowerShell/Microsoft.PowerShell_profile.ps1"),
        ("powershell", "Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1"),
    ],
)
def test_a_shell_names_its_startup_file(shell: str, named: str, tmp_path: Path) -> None:
    assert hostos.shell_rc_file(shell, tmp_path) == tmp_path / named


def test_no_shell_named_is_zsh_on_macos_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for system, rc in (("linux", None), ("windows", None), ("darwin", ".zshrc")):
        as_system(monkeypatch, system)
        assert hostos.shell_rc_file(None, tmp_path) == (rc and tmp_path / rc)
    as_system(monkeypatch, "linux")
    assert hostos.shell_rc_file("/bin/tcsh", tmp_path) is None


def test_a_windows_shell_drops_its_exe_and_posix_keeps_the_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    assert hostos.shell_rc_file("bash.exe", tmp_path) == tmp_path / ".bashrc"
    as_system(monkeypatch, "linux")
    assert hostos.shell_rc_file("bash.exe", tmp_path) is None


def test_setup_offers_no_posix_path_line_to_a_powershell_profile(
    tmp_path: Path,
) -> None:
    def never(_question: str) -> str:
        raise AssertionError("nothing should be asked")

    assert _shell_rc("pwsh", tmp_path) is None
    assert _offer_path_append(prompt=never, shell="pwsh", home=tmp_path) is None
    assert not (tmp_path / "Documents").exists()
