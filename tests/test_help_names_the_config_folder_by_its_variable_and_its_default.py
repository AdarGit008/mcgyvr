"""Help names the config folder by its variable and its default.

Promise: every help line that names a place in mcgyvr's config folder names
the folder by the variable that moves it and says which folder is only the
default, so a user who moved the folder is never sent to one mcgyvr does not
read. The one line that names the default on its own is the lock's guard,
which refuses a root under either folder.

Nothing is reached: only help is printed.
"""

from __future__ import annotations

import pytest

from mcgyvr import cli
from mcgyvr.fleet import roots

#: Commands whose help names a place in the config folder.
HELPS = (
    ("config",),
    ("pool",),
    ("emit",),
    ("run",),
    ("fleet",),
    ("fleet", "alerts"),
)
#: The variable as help names it.
VARIABLE = f"${roots.HOME_ENV}"


def _help(command: tuple[str, ...], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exited:
        cli.main([*command, "--help"])
    assert exited.value.code == 0
    return " ".join(capsys.readouterr().out.split())


def test_the_names_help_shows_carry_the_variable_and_the_default() -> None:
    for shown in (roots.FLEETS_SHOWN, roots.LIVE_FILE_SHOWN):
        assert shown.startswith(f"{VARIABLE}/"), shown
        assert f"default {roots.HOME_DIR}/" in shown, shown


@pytest.mark.parametrize("command", HELPS, ids=" ".join)
def test_a_help_naming_the_config_folder_names_it_by_its_variable(
    command: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    said = _help(command, capsys)

    assert VARIABLE in said, said
    bare = said.replace(roots.FLEETS_SHOWN, "").replace(roots.LIVE_FILE_SHOWN, "")
    assert roots.HOME_DIR not in bare, said


def test_the_lock_guard_names_the_moved_folder_and_its_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    said = _help(("fleet", "lock"), capsys)

    assert f"config folder ({VARIABLE}, else {roots.HOME_DIR})" in said, said
    assert f"or under {roots.HOME_DIR} is refused" in said, said
