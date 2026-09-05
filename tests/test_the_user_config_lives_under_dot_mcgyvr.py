"""The user-level config is ``~/.mcgyvr/config/mcgyvr.yaml`` (owner, 2026-09-05).

Three places are searched, in order: ``$MCGYVR_CONFIG``, ``./mcgyvr.yaml``,
then the user's own directory. The last of these was the XDG config dir; the
owner asked for ``~/.mcgyvr/config/`` and that is now the only user-level
location — ``$XDG_CONFIG_HOME`` is not consulted, so setting it moves nothing.
``mcgyvr init`` with no path writes to that same file, and every ``--config``
help line names it, so the third answer to "where is my config" is printed
beside the first two rather than left to be discovered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.config import (
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    ConfigMissingError,
    config_path,
    load,
)
from mcgyvr.initialize import InitResult
from tests import livejournal as lj

USER_CONFIG = Path(".mcgyvr") / "config" / CONFIG_FILENAME


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME of our own, no override, a cwd with no config in it."""
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


def test_the_user_level_config_is_under_dot_mcgyvr(home: Path) -> None:
    assert config_path() == home / USER_CONFIG


def test_xdg_config_home_moves_nothing(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg = tmp_path / "xdg" / "mcgyvr"
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    assert config_path() == home / USER_CONFIG


def test_the_working_directory_still_wins_over_the_user_dir(
    home: Path, tmp_path: Path
) -> None:
    local = Path.cwd() / CONFIG_FILENAME
    local.write_text("version: 1\n", encoding="utf-8")
    (home / USER_CONFIG).parent.mkdir(parents=True)
    (home / USER_CONFIG).write_text("version: 1\n", encoding="utf-8")
    assert config_path() == local


def test_the_override_still_wins_over_everything(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "elsewhere.yaml"))
    assert config_path() == tmp_path / "elsewhere.yaml"


def test_a_missing_config_is_reported_at_the_dot_mcgyvr_path(home: Path) -> None:
    with pytest.raises(ConfigMissingError, match=r"\.mcgyvr/config/mcgyvr\.yaml"):
        load()


def test_init_with_no_path_writes_under_dot_mcgyvr(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []

    def fake_initialize(path: Path, **_: object) -> InitResult:
        seen.append(path)
        return InitResult(path=path, created=True, written=True)

    monkeypatch.setattr(cli, "initialize", fake_initialize)
    code = lj.main(["init"])
    assert code == 0
    assert seen == [home / USER_CONFIG]


@pytest.mark.parametrize("command", ["config", "pool", "emit", "run", "init"])
def test_every_config_help_line_names_the_user_dir(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lj.main([command, "--help"]) == 0
    out = capsys.readouterr().out
    assert "~/.mcgyvr/config/mcgyvr.yaml" in out, out
