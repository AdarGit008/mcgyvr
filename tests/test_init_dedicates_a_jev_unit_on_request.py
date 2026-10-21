"""`mcgyvr setup` dedicates a Jev unit on request.

An opt-in, in init's own non-interactive idiom (a flag, a printed account):
`--jev UNIT` names a written unit as the one every typed decision asks — it is
dedicated VRAM, never slept or woken. No default Jev model is picked in code:
the unit is always the operator's word, and a name init did not write is
refused naming the ones it did.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import load as load_config
from mcgyvr.initialize import InitError, initialize
from tests import livejournal as lj
from tests.inits import KEYLESS_RIG


def _unit_names(tmp_path: Path) -> tuple[str, ...]:
    first = tmp_path / "first"
    initialize(first, detection=KEYLESS_RIG)
    return tuple(load_config(first).units)


def test_jev_names_the_unit_every_typed_decision_asks(tmp_path: Path) -> None:
    (unit,) = _unit_names(tmp_path)
    where = tmp_path / "setup"
    result = initialize(where, detection=KEYLESS_RIG, jev=unit)
    config = load_config(where)
    assert config.get("jev.unit") == unit
    assert config.get("orchestrator.type") == "proposer"
    assert any("Jev" in line and unit in line for line in result.decisions)


def test_without_the_flag_the_jev_block_stays_unbound(tmp_path: Path) -> None:
    where = tmp_path / "setup"
    initialize(where, detection=KEYLESS_RIG)
    assert load_config(where).get("jev.unit") is None


def test_a_unit_init_did_not_write_is_refused_naming_the_ones_it_did(
    tmp_path: Path,
) -> None:
    (unit,) = _unit_names(tmp_path)
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=KEYLESS_RIG, jev="ghost")
    assert "ghost" in str(refused.value)
    assert unit in str(refused.value)


def test_the_flags_reach_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import cli

    seen: dict[str, object] = {}

    def fake_initialize(path: Path, **kwargs: object) -> object:
        seen.update(kwargs)
        return initialize(path, detection=KEYLESS_RIG, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cli.commands.setup, "initialize", fake_initialize)
    (unit,) = _unit_names(tmp_path)
    code = lj.main(
        [
            "setup",
            str(tmp_path / "setup"),
            "--jev",
            unit,
        ]
    )
    assert code == 0
    assert seen["jev"] == unit
