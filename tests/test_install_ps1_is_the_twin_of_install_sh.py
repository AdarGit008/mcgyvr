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
from pathlib import Path

import pytest

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
    assert "skills\\mcgyvr\\install.ps1" in windows[2]
    assert "-ExecutionPolicy Bypass" in windows[2]


# --- run, where PowerShell is installed ------------------------------------

PWSH = shutil.which("pwsh")
needs_pwsh = pytest.mark.skipif(
    PWSH is None, reason="PowerShell (pwsh) is not installed"
)


def _run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert PWSH is not None
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(INSTALL_PS1), *args],
        cwd=SKILL_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _installed(home: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for name in _sh_list("SKILLS"):
        for harness in _sh_list("HARNESS_DIRS"):
            pairs.append(
                (
                    home / harness / name / "SKILL.md",
                    REPO / "skills" / name / "SKILL.md",
                )
            )
    return pairs


@needs_pwsh
def test_install_places_every_skill_in_both_harnesses_and_again_changes_nothing(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = _run(home)
    assert first.returncode == 0, first.stderr
    for landed, source in _installed(home):
        assert landed.read_bytes() == source.read_bytes(), landed
        assert str(landed) in first.stdout, first.stdout
        assert (landed.parent / _sh_value("RECORD")).is_file()
    before = sorted((p, p.read_bytes()) for p in home.rglob("*") if p.is_file())

    again = _run(home)

    assert again.returncode == 0, again.stderr
    assert sorted((p, p.read_bytes()) for p in home.rglob("*") if p.is_file()) == before


@needs_pwsh
def test_a_hand_edited_copy_is_refused_unless_forced(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run(home).returncode == 0
    landed, source = _installed(home)[0]
    landed.write_text("edited\n", encoding="utf-8")

    refused = _run(home)
    assert refused.returncode != 0
    assert "--force" in refused.stderr
    assert landed.read_text(encoding="utf-8") == "edited\n"

    forced = _run(home, "--force")
    assert forced.returncode == 0, forced.stderr
    assert landed.read_bytes() == source.read_bytes()


@needs_pwsh
def test_uninstall_removes_every_copy_and_twice_is_not_an_error(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run(home).returncode == 0
    first = _run(home, "--uninstall")
    assert first.returncode == 0, first.stderr
    for landed, _ in _installed(home):
        assert not landed.parent.exists()
    second = _run(home, "--uninstall")
    assert second.returncode == 0
    assert "Nothing to remove." in second.stdout


@needs_pwsh
def test_an_unknown_argument_is_refused_naming_the_setup_document(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, "--bogus")
    assert result.returncode == 2
    assert _sh_value("SETUP_DOC") in result.stderr
