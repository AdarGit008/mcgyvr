"""The top rung is the dearest rung of the ladder this setup runs (I-30b).

`route.top_rung` names it once: the pool's usable rungs in climb order —
families cheapest first, the ladder's own order inside one — cut at the ceiling
`max_escalations` sets, as the ladder is reported to a hub. A relief rung is
the hub's, never a step of the ladder, and a rung that cannot be dispatched is
not on the pool. It is the rung `mcgyvr PROMPT` hands a refused proposal to.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import parse
from mcgyvr.local_pool import source_map
from mcgyvr.route import top_rung
from tests.relieftakes import mapped

LOCAL_ONLY = """\
units:
  cheap:
    address: http://cheap-box.example:8000
    model: coder-3b
    width: 1
  smart:
    address: http://smart-box.example:8001
    model: coder-7b
    width: 1
ladder:
- cheap
- smart
"""


@pytest.fixture(autouse=True)
def _keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "k-example")
    monkeypatch.setenv("HUB_KEY", "k-hub")


def test_the_api_rung_is_the_top_rung_above_a_local_one() -> None:
    config, pool = mapped(escalations=1)

    rung = top_rung(config, pool)

    assert rung is not None
    assert (rung.name, rung.model) == ("api_big", "vendor-large")


def test_the_ceiling_cuts_the_ladder_the_top_rung_is_taken_from() -> None:
    config, pool = mapped(escalations=0)

    rung = top_rung(config, pool)

    assert rung is not None
    assert rung.name == "local_fast"


def test_a_hub_lent_rung_is_never_the_top_rung() -> None:
    config, pool = mapped(escalations=5)

    assert pool.relief  # one is lent, above the ceiling
    rung = top_rung(config, pool)
    assert rung is not None
    assert rung.name == "api_big"


def test_inside_one_family_the_last_rung_the_ladder_lists_is_the_top() -> None:
    config = parse(LOCAL_ONLY)

    rung = top_rung(config, source_map(config))

    assert rung is not None
    assert rung.name == "smart"


def test_a_rung_that_cannot_be_dispatched_is_passed_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EXAMPLE_API_KEY")
    config, pool = mapped(escalations=1)

    rung = top_rung(config, pool)

    assert rung is not None
    assert rung.name == "local_fast"
