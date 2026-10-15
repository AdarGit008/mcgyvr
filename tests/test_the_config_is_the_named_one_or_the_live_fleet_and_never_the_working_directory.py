"""The config is the one named, or the live fleet; never the working directory.

Owner, 2026-10-14: the config lookup drops the current-folder tier.
:func:`mcgyvr.config.config_path` resolves ``$MCGYVR_CONFIG`` (or a command's
``--config``), else the live fleet folder the config folder's ``live.json``
names. A ``fleet.yaml`` in the working directory no longer counts: a command
run there reads the live fleet, and with none live and nothing named, there is
no config, and the refusal says how to get one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.config import ConfigMissingError, config_path, load
from mcgyvr.fleet.roots import fleets_dir, live_file


def _setup(folder: Path, unit: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fleet.yaml").write_text(
        yaml.safe_dump(
            {
                "units": {unit: {"address": "http://127.0.0.1:9/v1", "model": "m"}},
            }
        ),
        encoding="utf-8",
    )
    (folder / "policy.yaml").write_text(
        yaml.safe_dump({"ladder": [unit]}), encoding="utf-8"
    )
    return folder


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a setup of its own."""
    here = _setup(tmp_path / "work", "cwd_unit")
    monkeypatch.chdir(here)
    return here


def test_a_setup_in_the_working_directory_is_not_the_config(work: Path) -> None:
    with pytest.raises(ConfigMissingError) as refused:
        load()
    said = str(refused.value)
    assert "MCGYVR_CONFIG" in said and str(live_file()) in said
    assert "mcgyvr setup" in said


def test_the_live_fleet_is_the_config_wherever_the_command_runs(work: Path) -> None:
    import json

    live = _setup(fleets_dir() / "flt@2026-10-14", "live_unit")
    live_file().write_text(json.dumps({"fleet": live.name}), encoding="utf-8")

    assert config_path() == live
    assert set(load().units) == {"live_unit"}


def test_the_named_config_wins(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = _setup(tmp_path / "named", "named_unit")
    monkeypatch.setenv("MCGYVR_CONFIG", str(named))

    assert config_path() == named
    assert set(load().units) == {"named_unit"}


def test_a_command_run_beside_a_setup_finds_no_config(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["config"]) != 0
    assert "no setup is named" in capsys.readouterr().err


def test_no_help_line_names_the_working_directory_as_a_config() -> None:
    assert "working directory" not in cli.CONFIG_DEFAULT_HELP
    assert "live.json" in cli.CONFIG_DEFAULT_HELP
