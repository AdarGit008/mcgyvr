"""Breadth above one at ``breadth.temperature: 0.0`` is refused when the config loads.

Draw 0 is greedy and the draws after it sample at ``breadth.temperature``, so
a temperature of zero makes every draw the greedy one: N dispatches, N
byte-identical replies, N gate runs, and nothing the first draw did not
already say. A config that asks for that is not wrong in any field — the
breadth is a legal count and the temperature a legal number — it is wrong in
the pair, which is what :func:`~mcgyvr.config._cross_validate_fleet` exists
to refuse, the way it refuses an ``attempts`` entry for a unit nobody
declared.

The check is over the *effective* breadth of every unit: ``breadth.draws``
where a unit has no entry of its own, and its ``draws`` entry where it has, so
a single unit widened by name is refused as surely as the whole ladder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, load, parse
from tests import livejournal as lj

IDENTICAL = "identical draws"


def test_two_draws_at_temperature_zero_are_refused() -> None:
    with pytest.raises(ConfigSchemaError, match=IDENTICAL) as refused:
        parse(lj.LADDER + "breadth:\n  draws: 2\n  temperature: 0.0\n")
    assert "breadth.temperature" in str(refused.value)


def test_a_units_own_draws_above_one_at_temperature_zero_are_refused() -> None:
    with pytest.raises(ConfigSchemaError, match=IDENTICAL) as refused:
        parse(lj.LADDER + "breadth:\n  temperature: 0\ndraws:\n  local_qwen-7b: 2\n")
    assert "local_qwen-7b" in str(refused.value), "the unit widened is named"


def test_one_draw_at_temperature_zero_is_the_greedy_install_and_loads() -> None:
    config = parse(lj.LADDER + "breadth:\n  temperature: 0.0\n")
    assert config.get("breadth.draws") == 1
    assert config.get("breadth.temperature") == 0.0


def test_two_draws_at_the_default_temperature_load() -> None:
    config = parse(lj.LADDER + "breadth:\n  draws: 2\n")
    assert config.get("breadth.temperature") == 0.7


def test_the_refusal_reaches_a_setup_read_from_disk(tmp_path: Path) -> None:
    setup = lj.make_config(tmp_path / "setup")
    lj.append_policy(setup, "breadth:\n  draws: 3\n  temperature: 0.0\n")
    with pytest.raises(ConfigSchemaError, match=IDENTICAL):
        load(setup)
