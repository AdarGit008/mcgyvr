"""``install.sh`` installs the CLI from the published package.

``install.sh``'s ``CLI_INSTALL`` is the single place the command that gets the
``mcgyvr`` CLI is written.
"""

from __future__ import annotations

import re

from tests._paths import REPO

INSTALL_SH = REPO / "skills" / "mcgyvr" / "install.sh"


def _cli_install() -> str:
    match = re.search(
        r'^CLI_INSTALL="(.*)"$', INSTALL_SH.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match is not None, "install.sh must define CLI_INSTALL"
    return match.group(1)


def test_install_sh_installs_the_published_package() -> None:
    assert _cli_install() == "uv tool install mcgyvr"
