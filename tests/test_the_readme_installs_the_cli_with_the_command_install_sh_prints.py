"""The README installs the CLI with the one command ``install.sh`` prints.

``install.sh``'s ``CLI_INSTALL`` is the single place the command that gets the
``mcgyvr`` CLI is written. The README says it twice: as the first line of its
install section, and in the ``cli:`` line of the ``install.sh`` output it
shows. While mcgyvr was not on PyPI the two disagreed (the README led with
``uv tool install mcgyvr`` and a "until the PyPI package is published"
fallback; the script printed a git URL). mcgyvr 0.3.0 is on PyPI, so both
name the plain package, and this holds them to the script.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"
INSTALL_SH = REPO / "skills" / "mcgyvr" / "install.sh"


def _cli_install() -> str:
    match = re.search(
        r'^CLI_INSTALL="(.*)"$', INSTALL_SH.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match is not None, "install.sh must define CLI_INSTALL"
    return match.group(1)


def _install_section() -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index("## Install\n")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_install_sh_installs_the_published_package() -> None:
    assert _cli_install() == "uv tool install mcgyvr"


def test_the_readme_first_install_command_is_install_sh_s() -> None:
    section = _install_section()
    first_block = re.search(r"```sh\n(.*?)```", section, re.DOTALL)
    assert first_block is not None, "the install section opens with a sh block"
    first_line = first_block.group(1).splitlines()[0]
    assert first_line == _cli_install(), first_line


def test_the_readme_shows_the_cli_line_install_sh_prints() -> None:
    cli_lines = [ln for ln in _install_section().splitlines() if ln.startswith("cli: ")]
    assert cli_lines == [f"cli: {_cli_install()}"], cli_lines


def test_the_readme_has_no_until_published_fallback() -> None:
    section = _install_section()
    assert "until the pypi package is published" not in section.lower()
    assert "releases/download" not in section
