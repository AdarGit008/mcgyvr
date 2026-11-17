"""``mcgyvr serve sleep|wake --config X`` runs the door against X.

The door is its own process and reads its setup from ``MCGYVR_CONFIG``, else
from the live fleet. A person who names a setup with ``--config`` has it read
by the command, and the door it spawns is handed the same one, by an absolute
path, also where ``MCGYVR_CONFIG`` names another. Without ``--config`` the
door's environment is the process's own, as it always was.

Every host, model and number here is invented.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import CONFIG_PATH_ENV
from tests import livejournal as lj
from tests.doors import SHARED_HOST, a_clean_home, ladder_text, write_spec

__all__ = ["home"]


def doors(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """The door, recorded by verb with the kwargs it was spawned with."""
    import mcgyvr.wake as wake

    log: list[tuple[str, dict[str, Any]]] = []

    def spawn(argv: list[str], **kwargs: Any) -> int:
        log.append((argv[argv.index("serve") + 1], kwargs))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def a_setup(where: Path) -> Path:
    """One setup file of the shared host's ladder, its specs and journal beside it."""
    where.mkdir(parents=True, exist_ok=True)
    path = where / "c.yaml"
    text = ladder_text(write_spec(where))
    path.write_text(text + f"journal:\n  dir: {where / 'j'}\n", encoding="utf-8")
    return path


def serve(direction: str, *config: str) -> int:
    named = ["--config", *config] if config else []
    return lj.main(["serve", direction, "--host", SHARED_HOST, *named])


def door_config(kwargs: dict[str, Any]) -> str | None:
    env = kwargs.get("env")
    return None if env is None else env.get(CONFIG_PATH_ENV)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_clean_home(tmp_path, monkeypatch)


@pytest.mark.parametrize("direction", ["sleep", "wake"])
def test_the_door_reads_the_config_named_by_an_absolute_path(
    direction: str, tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = a_setup(tmp_path / "named")
    monkeypatch.chdir(tmp_path)
    log = doors(monkeypatch)

    assert serve(direction, "named/c.yaml") == 0
    assert log, "no door was run"
    for verb, kwargs in log:
        handed = door_config(kwargs)
        assert handed is not None, f"the door's {verb} was left to find its own setup"
        assert Path(handed).is_absolute(), handed
        assert Path(handed).resolve() == named.resolve(), handed
        assert kwargs["env"]["HOME"] == os.environ["HOME"], (
            "the door lost the rest of the environment"
        )


def test_the_config_named_wins_over_the_one_the_environment_names(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = a_setup(tmp_path / "named")
    other = a_setup(tmp_path / "other")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(other))
    log = doors(monkeypatch)

    assert serve("sleep", str(named)) == 0
    assert serve("wake", str(named)) == 0
    assert [door_config(kwargs) for _, kwargs in log] == [str(named)] * len(log)
    assert os.environ[CONFIG_PATH_ENV] == str(other), (
        "the command changed its own environment"
    )


def test_without_a_named_config_the_door_keeps_the_environment_it_had(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = a_setup(tmp_path / "env")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(setup))
    log = doors(monkeypatch)

    assert serve("sleep") == 0
    assert serve("wake") == 0
    assert [verb for verb, _ in log] == ["sleep", "wake"]
    assert [kwargs for _, kwargs in log] == [{}, {}], (
        "a door no setup was named for was handed an environment of its own"
    )


def test_a_named_config_is_not_handed_to_a_door_run_after_the_command(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = a_setup(tmp_path / "named")
    other = a_setup(tmp_path / "other")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(other))
    log = doors(monkeypatch)

    assert serve("sleep", str(named)) == 0
    assert serve("wake") == 0
    assert [(verb, door_config(kwargs)) for verb, kwargs in log] == [
        ("sleep", str(named)),
        ("wake", None),
    ]
