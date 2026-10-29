"""``skills/mcgyvr/install.ps1`` is ``install.sh`` for Windows, and says the same.

The two scripts install the same skills into the same harness folders under
the user's home, keep the same digest record beside each copy, hold the CLI to
the same version floor and print the same lines. Their settings are compared
here, word for word, so neither drifts; the README installs with ``install.sh``
on Linux and macOS and ``install.ps1`` on Windows, three lines each.

Where PowerShell (``pwsh``) is installed, the script is also run against a
temporary home: it places every skill in both harnesses, is idempotent,
refuses a hand-edited copy, and uninstalls twice without an error.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import docgen
from tests._paths import REPO

SKILL_DIR = REPO / "skills" / "mcgyvr"
INSTALL_SH = SKILL_DIR / "install.sh"
INSTALL_PS1 = SKILL_DIR / "install.ps1"
README = REPO / "README.md"

#: install.sh's setting name -> install.ps1's.
SETTINGS = {
    "CLI_INSTALL": "CliInstall",
    "MIN_VERSION": "MinVersion",
    "REPO_URL": "RepoUrl",
    "SETUP_DOC": "SetupDoc",
    "RECORD": "Record",
    "DESCRIPTION_MAX": "DescriptionMax",
}
LISTS = {"SKILLS": "Skills", "HARNESS_DIRS": "HarnessDirs"}

#: Lines both scripts print, verbatim.
SAID = (
    "installed: ",
    "removed: ",
    "not installed: ",
    "Nothing to remove.",
    "setup: ",
    "cli: ",
    "Invoke them with /mcgyvr <prompt> or /mcgyvr-direct <files|dir>; "
    "neither loads itself.",
    "differs from the copy this script installed; something has edited it. "
    "Re-run with --force to overwrite it.",
    "no mcgyvr on PATH: the skills are installed, but there is nothing on this "
    "machine for them to drive. Get it with: ",
    "the oldest this skill is known to drive. Upgrade it with: ",
    "not an argument this understands",
)


def _sh_value(name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    found = re.search(rf'^{name}=("?)([^"\n]*)\1$', text, re.MULTILINE)
    assert found, name
    return found.group(2)


def _sh_list(name: str) -> list[str]:
    text = INSTALL_SH.read_text(encoding="utf-8")
    found = re.search(rf"^{name}=\((.*?)^\)", text, re.MULTILINE | re.DOTALL)
    assert found, name
    return re.findall(r'"([^"]+)"', found.group(1))


def _ps1_value(name: str) -> str:
    text = INSTALL_PS1.read_text(encoding="utf-8")
    found = re.search(rf'^\${name} = ("?)([^"\n]*)\1$', text, re.MULTILINE)
    assert found, name
    return found.group(2)


def _ps1_list(name: str) -> list[str]:
    text = INSTALL_PS1.read_text(encoding="utf-8")
    found = re.search(rf"^\${name} = @\((.*?)\)", text, re.MULTILINE | re.DOTALL)
    assert found, name
    return re.findall(r'"([^"]+)"', found.group(1))


def test_the_windows_installer_is_present() -> None:
    assert INSTALL_PS1.is_file()


@pytest.mark.parametrize(("sh", "ps1"), sorted(SETTINGS.items()))
def test_each_setting_is_the_same_in_both_scripts(sh: str, ps1: str) -> None:
    assert _ps1_value(ps1) == _sh_value(sh)


@pytest.mark.parametrize(("sh", "ps1"), sorted(LISTS.items()))
def test_the_skills_and_harness_folders_are_the_same(sh: str, ps1: str) -> None:
    assert _ps1_list(ps1) == _sh_list(sh)


@pytest.mark.parametrize("line", SAID)
def test_both_scripts_say_the_same_lines(line: str) -> None:
    assert line in INSTALL_SH.read_text(encoding="utf-8"), line
    assert line in INSTALL_PS1.read_text(encoding="utf-8"), line


def test_the_windows_installer_needs_no_elevation_and_no_profile() -> None:
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "#Requires -RunAsAdministrator" not in text
    assert "$PROFILE" not in text
    assert "Set-ExecutionPolicy" not in text


def _readme_install_blocks() -> list[list[str]]:
    text = README.read_text(encoding="utf-8")
    section = text[
        text.index("## Install") : text.index("\n## ", text.index("## Install") + 1)
    ]
    blocks = re.findall(r"```(?:sh|powershell)\n(.*?)```", section, re.DOTALL)
    return [block.strip("\n").splitlines() for block in blocks]


def test_the_readme_installs_in_three_lines_per_system() -> None:
    blocks = _readme_install_blocks()
    assert len(blocks) == 2, blocks
    posix, windows = blocks
    assert [len(posix), len(windows)] == [3, 3], blocks
    cli = _sh_value("CLI_INSTALL")
    assert posix[0].startswith(cli) and windows[0].startswith(cli)
    assert "skills/mcgyvr/install.sh" in posix[2]
    # The README's Windows line is SETUP.md's, word for word.
    assert windows[2] == docgen.INSTALL_PS1_COMMAND


def test_the_windows_installer_header_shows_the_same_command() -> None:
    assert docgen.INSTALL_PS1_COMMAND in INSTALL_PS1.read_text(encoding="utf-8")


def test_the_windows_installer_is_ascii_for_windows_powershell() -> None:
    # Windows PowerShell 5.1 reads a script with no BOM in the ANSI code page.
    INSTALL_PS1.read_text(encoding="utf-8").encode("ascii")


# --- run -------------------------------------------------------------------

#: The PowerShells installed here: PowerShell 7, and Windows PowerShell where
#: it exists (the one the README runs).
SHELLS = [found for found in map(shutil.which, ("pwsh", "powershell")) if found]
BASH = shutil.which("bash") if sys.platform != "win32" else None
needs_both = pytest.mark.skipif(
    not SHELLS or BASH is None, reason="needs PowerShell and bash on a POSIX system"
)


@pytest.fixture(params=SHELLS or [""])
def shell(request: pytest.FixtureRequest) -> str:
    if not request.param:
        pytest.skip("no PowerShell is installed")
    return str(request.param)


def _env(home: Path, path_first: Path | None = None) -> dict[str, str]:
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    if path_first is not None:
        env["PATH"] = str(path_first) + os.pathsep + env.get("PATH", "")
    return env


def _run(
    shell: str, home: Path, *args: str, path_first: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(INSTALL_PS1), *args],
        cwd=SKILL_DIR,
        env=_env(home, path_first),
        capture_output=True,
        text=True,
        timeout=180,
    )


def _run_sh(
    home: Path, *args: str, path_first: Path | None = None
) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(INSTALL_SH), *args],
        cwd=SKILL_DIR,
        env=_env(home, path_first),
        capture_output=True,
        text=True,
        timeout=180,
    )


def _installed(home: Path) -> list[tuple[Path, Path]]:
    return [
        (home / harness / name / "SKILL.md", REPO / "skills" / name / "SKILL.md")
        for name in _sh_list("SKILLS")
        for harness in _sh_list("HARNESS_DIRS")
    ]


def _harness_files(home: Path) -> list[tuple[Path, bytes]]:
    """Every file under the harness folders: PowerShell keeps caches of its
    own under the home on macOS, which are not the install's."""
    return sorted(
        (p, p.read_bytes())
        for harness in _sh_list("HARNESS_DIRS")
        for p in (home / harness).rglob("*")
        if p.is_file()
    )


def _home(tmp_path: Path, name: str = "home") -> Path:
    home = tmp_path / name
    home.mkdir()
    return home


def test_install_places_every_skill_in_both_harnesses_and_again_changes_nothing(
    shell: str, tmp_path: Path
) -> None:
    home = _home(tmp_path)
    first = _run(shell, home)
    assert first.returncode == 0, first.stderr
    for landed, source in _installed(home):
        assert landed.read_bytes() == source.read_bytes(), landed
        assert str(landed) in first.stdout, first.stdout
        assert (landed.parent / _sh_value("RECORD")).is_file()
    before = _harness_files(home)

    again = _run(shell, home)

    assert again.returncode == 0, again.stderr
    assert _harness_files(home) == before


def test_a_hand_edited_copy_is_refused_unless_forced(
    shell: str, tmp_path: Path
) -> None:
    home = _home(tmp_path)
    assert _run(shell, home).returncode == 0
    landed, source = _installed(home)[0]
    landed.write_text("edited\n", encoding="utf-8")

    refused = _run(shell, home)
    assert refused.returncode != 0
    assert "--force" in refused.stderr
    assert landed.read_text(encoding="utf-8") == "edited\n"

    forced = _run(shell, home, "--force")
    assert forced.returncode == 0, forced.stderr
    assert landed.read_bytes() == source.read_bytes()


def test_uninstall_removes_every_copy_and_twice_is_not_an_error(
    shell: str, tmp_path: Path
) -> None:
    home = _home(tmp_path)
    assert _run(shell, home).returncode == 0
    first = _run(shell, home, "--uninstall")
    assert first.returncode == 0, first.stderr
    for landed, _ in _installed(home):
        assert not landed.parent.exists()
    second = _run(shell, home, "--uninstall")
    assert second.returncode == 0
    assert "Nothing to remove." in second.stdout


def test_uninstalling_a_linked_skill_folder_removes_the_link_alone(
    shell: str, tmp_path: Path
) -> None:
    home = _home(tmp_path)
    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "SKILL.md").write_text("mine\n", encoding="utf-8")
    link = home / _sh_list("HARNESS_DIRS")[0] / _sh_list("SKILLS")[0]
    link.parent.mkdir(parents=True)
    try:
        os.symlink(kept, link, target_is_directory=True)
    except OSError:
        pytest.skip("this system makes no directory link here")

    assert _run(shell, home, "--uninstall").returncode == 0

    assert not os.path.lexists(link)
    assert (kept / "SKILL.md").read_text(encoding="utf-8") == "mine\n"


def test_an_unknown_argument_is_refused_naming_the_setup_document(
    shell: str, tmp_path: Path
) -> None:
    result = _run(shell, tmp_path, "--bogus")
    assert result.returncode == 2
    assert _sh_value("SETUP_DOC") in result.stderr


def _outside_record_survives(
    run: Callable[[Path], subprocess.CompletedProcess[str]], tmp_path: Path
) -> None:
    home = _home(tmp_path)
    assert run(home).returncode == 0
    landed, _ = _installed(home)[0]
    outside = landed.parent.parent / "outside.txt"
    outside.write_text("not the skill's\n", encoding="utf-8")
    record = landed.parent / _sh_value("RECORD")
    with record.open("a", encoding="utf-8") as stream:
        stream.write(f"{'0' * 64}  ../outside.txt\n")

    again = run(home)

    assert again.returncode == 0, again.stderr
    assert outside.read_text(encoding="utf-8") == "not the skill's\n"


def test_a_record_naming_a_file_outside_the_skill_removes_nothing_there_sh(
    tmp_path: Path,
) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash")

    def run(home: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [bash, str(INSTALL_SH)],
            cwd=SKILL_DIR,
            env=_env(home),
            capture_output=True,
            text=True,
            timeout=180,
        )

    _outside_record_survives(run, tmp_path)


def test_a_record_naming_a_file_outside_the_skill_removes_nothing_there_ps1(
    shell: str, tmp_path: Path
) -> None:
    _outside_record_survives(lambda home: _run(shell, home), tmp_path)


@needs_both
def test_both_scripts_write_the_same_record(shell: str, tmp_path: Path) -> None:
    by_sh, by_ps1 = _home(tmp_path, "sh"), _home(tmp_path, "ps1")
    assert _run_sh(by_sh).returncode == 0
    assert _run(shell, by_ps1).returncode == 0
    records = sorted(p.relative_to(by_sh) for p in by_sh.rglob(_sh_value("RECORD")))
    assert records
    for rel in records:
        assert (by_ps1 / rel).read_bytes() == (by_sh / rel).read_bytes(), rel


def _fake_mcgyvr(folder: Path, version: str) -> Path:
    """A `mcgyvr` that reports `version` and accepts every contract."""
    folder.mkdir()
    posix = folder / "mcgyvr"
    posix.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "mcgyvr {version}"; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    posix.chmod(0o755)
    (folder / "mcgyvr.cmd").write_text(
        f'@echo off\r\nif "%1"=="--version" echo mcgyvr {version}\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    return folder


@pytest.mark.parametrize(
    ("version", "warned"),
    [
        ("0.5.0", "is older than"),
        ("0.5.1.dev3+g1", None),
        ("0.5.1rc1", None),
        ("0.0.0+gdeadbee", "never installed"),
        ("9.0.0", None),
    ],
)
def test_the_version_floor_warns_as_install_sh_does(
    shell: str, version: str, warned: str | None, tmp_path: Path
) -> None:
    fake = _fake_mcgyvr(tmp_path / "bin", version)
    ran = _run(shell, _home(tmp_path), path_first=fake)
    assert ran.returncode == 0, ran.stderr
    if warned is None:
        assert "install.ps1: mcgyvr" not in ran.stderr, ran.stderr
    else:
        assert warned in ran.stderr, ran.stderr
    if BASH is not None:
        twin = _run_sh(_home(tmp_path, "sh-home"), path_first=fake)
        assert (warned is None) == ("install.sh: mcgyvr" not in twin.stderr), (
            twin.stderr
        )
