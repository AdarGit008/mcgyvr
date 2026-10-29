"""hostos names the startup file each shell reads, and setup extends only a POSIX one.

bash, zsh, sh/dash and fish read their rc files under the home, PowerShell
its profile; no shell named is zsh on macOS and nothing elsewhere. Setup's
PATH offer writes a POSIX export line, so a PowerShell profile is left alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import hostos
from mcgyvr.cli.commands.setup import _offer_path_append, _shell_rc
from tests.hostos_fakes import as_system


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
