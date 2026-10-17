"""``mcgyvr setup`` offers to append ``~/.local/bin`` to the login shell PATH.

Owner, 2026-10-17: after a successful interactive setup, the wizard offers to
append ``export PATH="$HOME/.local/bin:$PATH"`` to the login shell's rc file,
once the user says yes. The shell is read from ``$SHELL``: ``bash`` →
``~/.bashrc``, ``zsh`` → ``~/.zshrc``, ``sh``/``dash`` → ``~/.profile``,
``fish`` → ``~/.config/fish/config.fish``; an unknown shell is skipped. A file
that already carries a ``.local/bin`` PATH line is left alone.

The offer runs only in the interactive path and only after setup succeeds;
these tests exercise the seam directly, against a temporary home.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.cli.commands.setup import _offer_path_append, _shell_rc

EXPORT = 'export PATH="$HOME/.local/bin:$PATH"'


@pytest.mark.parametrize(
    ("shell", "name"),
    [
        ("/bin/bash", ".bashrc"),
        ("bash", ".bashrc"),
        ("/usr/bin/zsh", ".zshrc"),
        ("/bin/sh", ".profile"),
        ("/bin/dash", ".profile"),
        ("/usr/bin/fish", ".config/fish/config.fish"),
    ],
)
def test_the_shell_names_its_rc_file(tmp_path: Path, shell: str, name: str) -> None:
    assert _shell_rc(shell, tmp_path) == tmp_path / name


@pytest.mark.parametrize("shell", [None, "", "/bin/tcsh", "csh"])
def test_an_unknown_shell_names_no_rc_file(tmp_path: Path, shell: str | None) -> None:
    assert _shell_rc(shell, tmp_path) is None


def test_a_yes_appends_the_export_line(tmp_path: Path) -> None:
    asked: list[str] = []

    def prompt(question: str) -> str:
        asked.append(question)
        return "y"

    rc = _offer_path_append(prompt=prompt, shell="/bin/bash", home=tmp_path)

    assert rc == tmp_path / ".bashrc"
    assert (tmp_path / ".bashrc").read_text(encoding="utf-8") == EXPORT + "\n"
    assert asked == ["Add ~/.local/bin to your shell PATH in ~/.bashrc? [y/n] "]


def test_a_no_appends_nothing(tmp_path: Path) -> None:
    def prompt(question: str) -> str:
        return "n"

    assert _offer_path_append(prompt=prompt, shell="/bin/bash", home=tmp_path) is None
    assert not (tmp_path / ".bashrc").exists()


def test_an_already_present_line_is_skipped_without_prompting(tmp_path: Path) -> None:
    (tmp_path / ".bashrc").write_text(EXPORT + "\n", encoding="utf-8")
    asked: list[str] = []

    def prompt(question: str) -> str:
        asked.append(question)
        return "y"

    assert _offer_path_append(prompt=prompt, shell="/bin/bash", home=tmp_path) is None
    assert asked == [], "an idempotent file is never re-asked"


def test_an_unknown_shell_is_skipped_without_prompting(tmp_path: Path) -> None:
    asked: list[str] = []

    def prompt(question: str) -> str:
        asked.append(question)
        return "y"

    assert _offer_path_append(prompt=prompt, shell="/bin/tcsh", home=tmp_path) is None
    assert asked == []


def test_a_fish_shell_appends_to_its_config_file(tmp_path: Path) -> None:
    def prompt(question: str) -> str:
        return "y"

    rc = _offer_path_append(prompt=prompt, shell="/usr/bin/fish", home=tmp_path)

    assert rc == tmp_path / ".config" / "fish" / "config.fish"
    assert rc.read_text(encoding="utf-8") == EXPORT + "\n"


def test_an_existing_file_is_appended_not_overwritten(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("echo hi\n", encoding="utf-8")

    def prompt(question: str) -> str:
        return "y"

    _offer_path_append(prompt=prompt, shell="bash", home=tmp_path)

    assert rc.read_text(encoding="utf-8") == "echo hi\n" + EXPORT + "\n"
