"""Setup's PATH offer speaks the shell each system logs in with.

``uv tool install`` puts ``mcgyvr`` in ``~/.local/bin`` on every system
(``%USERPROFILE%\\.local\\bin`` on Windows). A POSIX shell's rc file gets the
export line, as before; with no ``$SHELL``, macOS gets ``~/.zshrc`` and Windows
gets a PowerShell profile (PowerShell 7's when ``pwsh`` is installed, else
Windows PowerShell's), which takes a PowerShell line instead of the export.
The profile is the one PowerShell itself names, since a Documents folder moved
elsewhere moves it; a profile that already puts ``.local\\bin`` on the path is
left alone.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr.cli.commands import setup as setup_command
from mcgyvr.cli.commands.setup import (
    _PATH_EXPORT,
    _PATH_POWERSHELL,
    _login_shell,
    _offer_path_append,
)
from tests.hostos_fakes import as_system

PWSH_PROFILE = Path("Documents") / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
WINPS_PROFILE = (
    Path("Documents") / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
)


def _yes(asked: list[str]) -> Callable[[str], str]:
    def prompt(question: str) -> str:
        asked.append(question)
        return "y"

    return prompt


def test_the_powershell_line_puts_the_uv_folder_first_on_the_path() -> None:
    assert _PATH_POWERSHELL == '$env:Path = "$HOME\\.local\\bin;$env:Path"'


@pytest.mark.parametrize(
    ("shell", "profile"), [("pwsh", PWSH_PROFILE), ("powershell", WINPS_PROFILE)]
)
def test_a_powershell_profile_gets_the_powershell_line(
    shell: str, profile: Path, tmp_path: Path
) -> None:
    asked: list[str] = []

    rc = _offer_path_append(prompt=_yes(asked), shell=shell, home=tmp_path)

    assert rc == tmp_path / profile
    assert rc.read_text(encoding="utf-8") == _PATH_POWERSHELL + "\n"
    assert len(asked) == 1 and "PowerShell profile" in asked[0], asked


def test_a_profile_already_naming_the_folder_is_not_asked_again(tmp_path: Path) -> None:
    rc = tmp_path / PWSH_PROFILE
    rc.parent.mkdir(parents=True)
    rc.write_text(_PATH_POWERSHELL + "\n", encoding="utf-8")
    asked: list[str] = []

    assert _offer_path_append(prompt=_yes(asked), shell="pwsh", home=tmp_path) is None
    assert asked == []


def test_a_posix_rc_still_gets_the_export_line(tmp_path: Path) -> None:
    rc = _offer_path_append(prompt=_yes([]), shell="/bin/zsh", home=tmp_path)
    assert rc == tmp_path / ".zshrc"
    assert rc.read_text(encoding="utf-8") == _PATH_EXPORT + "\n"


@pytest.mark.parametrize(
    ("installed", "shell"), [("C:/pwsh/pwsh.exe", "pwsh"), (None, "powershell")]
)
def test_windows_with_no_shell_named_logs_in_with_powershell(
    installed: str | None,
    shell: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    as_system(monkeypatch, "windows")
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: installed if name == "pwsh" else None,
    )
    assert _login_shell() == shell


def test_a_named_shell_wins_on_every_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/bash")
    for system in ("linux", "darwin", "windows"):
        as_system(monkeypatch, system)
        assert _login_shell() == "/usr/bin/bash"


def test_linux_and_macos_with_no_shell_named_leave_it_to_hostos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    for system in ("linux", "darwin"):
        as_system(monkeypatch, system)
        assert _login_shell() is None


def test_macos_with_no_shell_named_offers_zshrc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    as_system(monkeypatch, "darwin")
    rc = _offer_path_append(prompt=_yes([]), home=tmp_path)
    assert rc == tmp_path / ".zshrc"
    assert rc.read_text(encoding="utf-8") == _PATH_EXPORT + "\n"


def test_the_profile_powershell_names_is_the_one_extended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A Documents folder moved to a synced folder moves the profile with it:
    # PowerShell's own $PROFILE is the file it reads at start-up.
    moved = tmp_path / "Synced" / "Documents" / "PowerShell" / "profile.ps1"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(setup_command, "_ask_powershell_profile", lambda shell: moved)

    rc = _offer_path_append(prompt=_yes([]), shell="pwsh")

    assert rc == moved
    assert moved.read_text(encoding="utf-8") == _PATH_POWERSHELL + "\n"
    assert not (tmp_path / PWSH_PROFILE).exists()


def test_a_powershell_that_does_not_answer_falls_back_to_the_documents_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(setup_command, "_ask_powershell_profile", lambda shell: None)

    rc = _offer_path_append(prompt=_yes([]), shell="pwsh")

    assert rc == tmp_path / PWSH_PROFILE


def test_asking_powershell_for_its_profile_reads_one_absolute_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []
    answer = str(tmp_path / "profile.ps1")

    class Done:
        returncode = 0
        stdout = answer + "\r\n"

    def run(argv: list[str], **_kwargs: object) -> Done:
        seen.append(argv)
        return Done()

    monkeypatch.setattr(subprocess, "run", run)
    assert setup_command._ask_powershell_profile("pwsh") == Path(answer)
    assert seen and seen[0][0] == "pwsh" and "-NoProfile" in seen[0]

    Done.stdout = "relative.ps1\n"
    assert setup_command._ask_powershell_profile("pwsh") is None

    def gone(argv: list[str], **_kwargs: object) -> Done:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", gone)
    assert setup_command._ask_powershell_profile("pwsh") is None
