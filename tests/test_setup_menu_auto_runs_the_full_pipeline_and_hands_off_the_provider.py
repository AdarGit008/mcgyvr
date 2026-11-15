"""The menu's `setup` auto path runs the full pipeline and hands off the provider.

The menu defaults to auto, which chains scan → recommend → emit → serve up →
sample → lock with no start or lock question — the two stages are the ones
auto answers for you — and then writes ``provider.env`` beside the staged
setup so a custom provider (Pi, Hermes, VLM, …) can `source` it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.cli.commands.setup import run_menu_setup
from mcgyvr.fleet.roots import data_home, live_file
from tests import setup_door as sd

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "


def _staged() -> Path:
    (staged,) = (data_home() / "setup").iterdir()
    return staged


def test_auto_runs_the_full_pipeline_and_exports_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(monkeypatch, sd.FakeRig(), {}, typed={USE_CASE: "m"})

    assert run_menu_setup(auto=True, stop=None) == 0

    # The inputs (use case, Jev) are still asked; the pipeline stages are not.
    assert all(
        "Start the serving" not in q and "Lock the fleet" not in q for q in asked
    )
    assert live_file().exists()

    staged = _staged()
    env = (staged / "provider.env").read_text(encoding="utf-8").splitlines()
    assert env == [
        f"export MCGYVR_ENDPOINT=http://{sd.RIG}:8080/v1",
        "export MCGYVR_API_KEY=",
        f"export MCGYVR_MODEL={sd.MODEL}",
    ]


def test_manual_config_stop_writes_the_config_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {}, typed={USE_CASE: "m"})

    assert run_menu_setup(auto=False, stop="config") == 0

    staged = _staged()
    assert (staged / "fleet.yaml").exists()
    assert not (staged / "provider.env").exists(), "config-only stop serves nothing"
    assert not list((staged).glob("*.yml")), "no launch spec is emitted at config-only"
