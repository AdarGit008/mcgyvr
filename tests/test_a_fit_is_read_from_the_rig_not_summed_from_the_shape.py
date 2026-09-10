"""Whether a unit fits is a reading of the rig against what its unit id needs.

RED. ``mcgyvr.fleet.transition`` does not exist. The intent is
``records/plans/fleet-identity.md``, "the fits verdict".

Owner's ruling: what fits is decided from what the hardware reports free, not
from a sum over the units a shape says are there. A foreign process held 3,374
MiB of srv1's card with nothing of ours running
(``src/mcgyvr/serving/gate-scripts/data-10-scan.py``); a sum never sees it. The
reading has three corrections the evidence forces:

* a sleeper's residual is on the card and its wake is not (Q15: 228 MiB asleep,
  3,790 awake), so a residual is subtracted and a wake is a need;
* a mapped unit's blob sits in page cache, which ``MemAvailable`` counts as
  free, so a running mapped unit claims ``max(read, need)``;
* any swap-out while reading means the machine is already paging (Q7 paged
  1.15 GiB on a pair the arithmetic cleared), and that refuses.
"""

from __future__ import annotations

import importlib
from typing import Any

from tests.red_port.conftest import required


def _transition() -> Any:
    return required(
        "decide a fit from a live reading of the rig and the needs of the units",
        lambda: importlib.import_module("mcgyvr.fleet.transition"),
    )


def reading(**overrides: Any) -> dict[str, Any]:
    """srv2 with the 3B awake, one sleeper, and nothing foreign."""
    read: dict[str, Any] = {
        "total_mib": 12288,
        "reserve_bound_mib": 380,
        "foreign_mib": 0,
        "staying_mib": [3790],
        "residual_mib": [234],
        "mem_available_mib": 20000,
        "ram_floor_mib": 2048,
        "running_mapped": [],
        "swap_out_delta_pages": 0,
    }
    read.update(overrides)
    return read


def need(card: float, ram: float = 0.0) -> dict[str, Any]:
    return {"unit_id": "unt-" + "7" * 64, "card_need_mib": card, "ram_need_mib": ram}


def test_card_room_is_total_less_reserve_foreign_staying_and_residuals() -> None:
    """12288 - 380 - 0 - 3790 - 234 = 7884 MiB."""
    transition = _transition()
    assert transition.fits(reading(), [need(7544)]).ok
    assert not transition.fits(reading(), [need(7900)]).ok
    assert not transition.fits(reading(foreign_mib=3374), [need(7544)]).ok


def test_a_running_mapped_unit_claims_its_need_when_the_cache_reads_less() -> None:
    """20000 - max(2000, 6523) - 2048 = 11429 MiB of RAM."""
    transition = _transition()
    squeezed = reading(running_mapped=[{"read_mib": 2000, "need_mib": 6523}])
    assert transition.fits(squeezed, [need(0, 11000)]).ok
    assert not transition.fits(squeezed, [need(0, 11500)]).ok, (
        "the page cache read 2,000 MiB of a 6,523 MiB blob the unit still needs"
    )


def test_any_swap_out_while_reading_refuses() -> None:
    transition = _transition()
    verdict = transition.fits(reading(swap_out_delta_pages=1), [need(100, 100)])
    assert not verdict.ok
    assert "swap" in verdict.why
