"""Every command that loads a config answers the person who pointed it.

``load`` grew a remedy that depends on *who chose the path*: telling someone who
has just set ``$MCGYVR_CONFIG`` to a path with a typo in it to "set
``$MCGYVR_CONFIG``" is advice to do again what did not work. That was proved
once, against the loader, and then shipped with four of the five commands that
load a config still getting the circular sentence — because each resolved the
path itself and handed it over as if a flag had named it. A test that calls the
loader directly cannot see that: no command calls it the way that test did. So
these drive the commands.

There are three situations here, not two, and the third is why "name one that
is there" is not the whole answer. ``mcgyvr init`` writes to
``$MCGYVR_CONFIG`` — its own help says so — so ``export
MCGYVR_CONFIG=~/mcgyvr.yaml`` followed by a command on a fresh install is a
documented setup one step from finished, and the remedy is to run ``init``, not
to rename the variable. A ``--config`` typo is the other thing entirely: the
file the caller typed is not there, and nothing but a different path fixes it.
And a default location nobody named is the bare install, where "run ``mcgyvr
init``, or set ``$MCGYVR_CONFIG``" is exactly right, because neither has
happened yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import CONFIG_PATH_ENV
from tests import livejournal as lj

#: Every command that loads a config, as ``(argv without a path, flag)``. The
#: flag form takes the path; the bare form makes the command resolve it, which
#: is the shape that shipped the circular advice.
COMMANDS: list[tuple[str, list[str], list[str]]] = [
    ("config", ["config"], ["config", "{path}"]),
    ("pool", ["pool"], ["pool", "{path}"]),
    ("catalog", ["catalog", "--against"], ["catalog", "--against", "{path}"]),
    # `emit` also requires the window the run serves, which is not a config
    # question: the run declares it (test_dod_one_context_number.py).
    (
        "emit",
        ["emit", "--ctx-per-slot", "4096"],
        ["emit", "--ctx-per-slot", "4096", "--config", "{path}"],
    ),
]


@pytest.fixture
def nowhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cwd with no config in it, a HOME with none either, and no override."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    monkeypatch.chdir(work)
    return tmp_path / "absent" / "mcgyvr.yaml"


@pytest.mark.parametrize(("name", "bare", "flagged"), COMMANDS, ids=lambda v: str(v))
def test_a_command_pointed_by_the_environment_is_not_told_to_point_again(
    name: str,
    bare: list[str],
    flagged: list[str],
    nowhere: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``$MCGYVR_CONFIG`` at a path that is not there wants ``init``, not itself."""
    monkeypatch.setenv(CONFIG_PATH_ENV, str(nowhere))

    code = lj.main(bare)

    err = capsys.readouterr().err
    assert code != 0, err
    assert str(nowhere) in err, err
    assert CONFIG_PATH_ENV not in err, err
    assert "mcgyvr init" in err, err


@pytest.mark.parametrize(("name", "bare", "flagged"), COMMANDS, ids=lambda v: str(v))
def test_a_command_pointed_by_a_flag_at_a_missing_config_is_told_to_name_one(
    name: str,
    bare: list[str],
    flagged: list[str],
    nowhere: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A path typed on the command line is a typo, and only a path fixes it."""
    code = lj.main([part.format(path=nowhere) for part in flagged])

    err = capsys.readouterr().err
    assert code != 0, err
    assert str(nowhere) in err, err
    assert CONFIG_PATH_ENV not in err, err


@pytest.mark.parametrize(("name", "bare", "flagged"), COMMANDS, ids=lambda v: str(v))
def test_a_command_with_no_config_anywhere_is_told_how_to_get_one(
    name: str,
    bare: list[str],
    flagged: list[str],
    nowhere: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nobody named a path, so both remedies are still open and both are said."""
    code = lj.main(bare)

    err = capsys.readouterr().err
    assert code != 0, err
    assert "mcgyvr init" in err, err
    assert CONFIG_PATH_ENV in err, err
