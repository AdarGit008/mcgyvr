"""A person's ``mcgyvr serve sleep`` puts a card down the way the manager does.

Two ways to put a card to sleep: vLLM's level 2, where the process stays, the
weights and KV cache leave the card and a wake reads them back without a
container start; and a stop, where the containers go and a wake starts them
again. The ladder manager uses level 2 wherever every unit of the card is vLLM
and the unit answers on its sleep route, and stops the card otherwise. A
person typing ``mcgyvr serve sleep`` gets the same: one path for both, after
the same drain. The card is marked resting, so a dispatch wakes it before it
sends, and ``serve wake`` reads the mark to take the route back.

Every host, model and number here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE
from tests import livejournal as lj
from tests.test_a_wake_on_a_shared_card_makes_room_first import (
    SHARED_HOST,
    home,
    ladder_text,
    write_spec,
)

__all__ = ["home"]


def doors(monkeypatch: pytest.MonkeyPatch, *, sleep_code: int = 0) -> list[str]:
    """The door, recorded by verb; ``sleep`` exits ``sleep_code``, the rest work."""
    import mcgyvr.wake as wake

    log: list[str] = []

    def spawn(argv: list[str], **_: Any) -> int:
        verb = argv[argv.index("serve") + 1]
        log.append(verb)
        return sleep_code if verb == "sleep" else 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def config_path(tmp_path: Path, *, engine: str = "vllm") -> Path:
    path = tmp_path / "c.yaml"
    path.write_text(
        ladder_text(write_spec(tmp_path), engine=engine)
        + f"journal:\n  dir: {tmp_path / 'j'}\n",
        encoding="utf-8",
    )
    return path


def serve(direction: str, path: Path) -> int:
    return lj.main(["serve", direction, "--host", SHARED_HOST, "--config", str(path)])


def test_a_vllm_card_a_person_sleeps_rests_at_level_2(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.wake import resting

    log = doors(monkeypatch)

    assert serve("sleep", config_path(tmp_path)) == 0
    assert log == ["sleep"], "the card was stopped where it could rest at level 2"
    assert resting(SHARED_HOST, 8001) and resting(SHARED_HOST, 8002), (
        "no resting mark, so a dispatch would hang on the sleeping process"
    )
    assert "level 2" in capsys.readouterr().out


def test_a_card_a_person_slept_at_level_2_is_woken_in_its_process(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.wake import resting

    log = doors(monkeypatch)
    path = config_path(tmp_path)

    assert serve("sleep", path) == 0
    assert serve("wake", path) == 0
    assert log == ["sleep", "wake"], "the wake started containers that were running"
    assert not resting(SHARED_HOST)


def test_a_vllm_card_with_no_sleep_route_is_stopped_instead(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.wake import resting

    log = doors(monkeypatch, sleep_code=NO_SLEEP_ROUTE)

    assert serve("sleep", config_path(tmp_path)) == 0
    assert log == ["sleep", "down"]
    assert not resting(SHARED_HOST), "a stopped card was marked resting"
    assert "stopped" in capsys.readouterr().out


def test_a_card_of_another_engine_is_stopped(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = doors(monkeypatch)

    assert serve("sleep", config_path(tmp_path, engine="llama.cpp")) == 0
    assert log == ["down"], "a sleep was asked of an engine that has none"


def test_the_help_says_a_vllm_card_rests_at_level_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lj.main(["serve", "--help"]) == 0
    said = " ".join(capsys.readouterr().out.split())

    assert "level 2" in said, said
    assert "takes the whole card down" not in said, said
