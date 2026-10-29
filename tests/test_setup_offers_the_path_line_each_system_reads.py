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

import os
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
    shell: str, profile: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    asked: list[str] = []

    rc = _offer_path_append(prompt=_yes(asked), shell=shell, home=tmp_path)

    assert rc == tmp_path / profile
    assert rc.read_text(encoding="utf-8") == _PATH_POWERSHELL + "\n"
    assert len(asked) == 1 and "PowerShell profile" in asked[0], asked


def test_a_profile_already_naming_the_folder_is_not_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
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
        setup_command,
        "_powershell_exe",
        lambda name: installed if name == "pwsh" else None,
    )
    assert _login_shell() == shell


def test_windows_runs_powershell_by_full_path_never_by_bare_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pwsh.exe or powershell.exe left in the working folder is never the
    # one run: Windows PowerShell is the system one, PowerShell 7 the one in a
    # PATH folder named in full or under Program Files.
    as_system(monkeypatch, "windows")
    work = tmp_path / "work"
    work.mkdir()
    (work / "pwsh.exe").write_text("planted", encoding="utf-8")
    (work / "powershell.exe").write_text("planted", encoding="utf-8")
    monkeypatch.chdir(work)
    system_root = tmp_path / "Windows"
    system_ps = system_root / "System32" / "WindowsPowerShell" / "v1.0"
    system_ps.mkdir(parents=True)
    (system_ps / "powershell.exe").write_text("", encoding="utf-8")
    programs = tmp_path / "Program Files"
    monkeypatch.setenv("SYSTEMROOT", str(system_root))
    monkeypatch.setenv("ProgramFiles", str(programs))
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", "relative"]))

    assert setup_command._powershell_exe("powershell") == str(
        system_ps / "powershell.exe"
    )
    assert setup_command._powershell_exe("pwsh") is None

    seven = programs / "PowerShell" / "7"
    seven.mkdir(parents=True)
    (seven / "pwsh.exe").write_text("", encoding="utf-8")
    assert setup_command._powershell_exe("pwsh") == str(seven / "pwsh.exe")

    named = tmp_path / "tools"
    named.mkdir()
    (named / "pwsh.exe").write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", os.pathsep.join([".", str(named)]))
    assert setup_command._powershell_exe("pwsh.exe") == str(named / "pwsh.exe")


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
    as_system(monkeypatch, "windows")
    # A Documents folder moved to a synced folder moves the profile with it:
    # PowerShell's own $PROFILE is the file it reads at start-up.
    moved = tmp_path / "Synced" / "Documents" / "PowerShell" / "profile.ps1"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        setup_command, "_ask_powershell", lambda shell: ("RemoteSigned", moved)
    )

    rc = _offer_path_append(prompt=_yes([]), shell="pwsh")

    assert rc == moved
    assert moved.read_text(encoding="utf-8") == _PATH_POWERSHELL + "\n"
    assert not (tmp_path / PWSH_PROFILE).exists()


def test_a_powershell_that_does_not_answer_falls_back_to_the_documents_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(setup_command, "_ask_powershell", lambda shell: (None, None))

    rc = _offer_path_append(prompt=_yes([]), shell="pwsh")

    assert rc == tmp_path / PWSH_PROFILE


@pytest.mark.parametrize("policy", ["Restricted", "AllSigned"])
def test_a_policy_that_runs_no_profile_writes_none_and_names_uv(
    policy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    as_system(monkeypatch, "windows")
    # A profile that never runs puts nothing on PATH and makes PowerShell
    # print an error at every start; uv's own command needs no policy change.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        setup_command, "_ask_powershell", lambda shell: (policy, tmp_path / "p.ps1")
    )
    asked: list[str] = []

    assert _offer_path_append(prompt=_yes(asked), shell="pwsh") is None

    assert asked == []
    assert not (tmp_path / "p.ps1").exists()
    assert not (tmp_path / PWSH_PROFILE).exists()
    out = capsys.readouterr().out
    assert policy in out and "uv tool update-shell" in out


def test_asking_powershell_reads_its_policy_and_one_ps1_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []
    kwargs: list[dict[str, object]] = []
    (tmp_path / "Documents" / "PowerShell").mkdir(parents=True)
    answer = tmp_path / "Documents" / "PowerShell" / "profile.ps1"
    program = str(tmp_path / "pwsh")
    monkeypatch.setattr(setup_command, "_powershell_exe", lambda shell: program)

    class Done:
        returncode = 0
        stdout = f"RemoteSigned\r\n{answer}\r\n"

    def run(argv: list[str], **given: object) -> Done:
        seen.append(argv)
        kwargs.append(given)
        return Done()

    monkeypatch.setattr(subprocess, "run", run)
    assert setup_command._ask_powershell("pwsh") == ("RemoteSigned", answer)
    assert seen[0][0] == program and "-NoProfile" in seen[0]
    assert "UTF8" in seen[0][-1] and kwargs[0]["encoding"] == "utf-8"
    assert kwargs[0]["stdin"] == subprocess.DEVNULL

    # Not a .ps1, relative, or under a folder that does not exist: the policy
    # stands, the path does not, and no folder is made for it.
    for wrong in (
        "relative.ps1",
        str(tmp_path / "x.txt"),
        str(tmp_path / "a" / "b" / "c.ps1"),
    ):
        Done.stdout = f"Restricted\n{wrong}\n"
        assert setup_command._ask_powershell("pwsh") == ("Restricted", None)
    assert not (tmp_path / "a").exists()

    def gone(argv: list[str], **_kwargs: object) -> Done:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", gone)
    assert setup_command._ask_powershell("pwsh") == (None, None)
    monkeypatch.setattr(setup_command, "_powershell_exe", lambda shell: None)
    assert setup_command._ask_powershell("pwsh") == (None, None)


def test_a_comment_mentioning_the_folder_is_not_a_path_line(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("# add .local/bin to the path some day\n", encoding="utf-8")
    asked: list[str] = []
    assert _offer_path_append(prompt=_yes(asked), shell="bash", home=tmp_path) == rc
    assert asked


@pytest.mark.parametrize("system", ["linux", "darwin"])
def test_powershell_off_windows_is_left_as_it_is(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The PowerShell line names Windows' folder and separator.
    as_system(monkeypatch, system)
    asked: list[str] = []
    assert _offer_path_append(prompt=_yes(asked), shell="pwsh", home=tmp_path) is None
    assert asked == []
    assert not (tmp_path / "Documents").exists()


@pytest.mark.skipif(
    shutil.which("pwsh") is None, reason="PowerShell (pwsh) is not installed"
)
def test_a_real_powershell_names_its_policy_and_an_absolute_profile() -> None:
    policy, profile = setup_command._ask_powershell("pwsh")
    assert policy
    assert profile is None or (profile.is_absolute() and profile.suffix == ".ps1")
