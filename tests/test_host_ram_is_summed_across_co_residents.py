"""Two units on one host share its memory, and until now nothing added it up.

``hold_together`` sums what the units on a host ask of the **card**, because
each of them fitting alone is exactly how a 12 GB card is handed a compose file
asking for 13. Host RAM had no such sum: ``fit`` weighed each unit against the
same ``MemAvailable``, both passed, and the file emitted asked the host for
twice what it has. Owner's ruling, 2026-09-09: **RAM summed per host, VRAM per
card**, the sum taken after the loading modes are picked, with one host headroom
applied once, against the recorded scan and never a live read.

What each unit asks for is the arm its fit took — the law is F2.1 in
``records/plans/fleet-shape/formulas.md``, and it is the same split ``fit``
already makes:

* **mapped**, the engine's default: the *blob*, because every page of it goes
  through the page cache and the kernel may evict what it does not fit;
* **``--load-mode none``**: the *spilled experts*, which are allocated rather
  than cached, plus the runtime that spilling carries;
* **nothing to spill**: nothing at all. Host RAM does not constrain a unit whose
  weights are entirely the card's.

**Alternatives are not summed**, for the same reason they are not summed against
the card: two units on one port take turns, and adding figures for a contention
that cannot happen refuses a ladder either half of which runs perfectly well.
The worst case an operator can actually reach is the largest alternative at each
port, added across ports — which is the rule ``alternatives()`` already carries.

Two honest limits on all of this, stated here so a reader does not mistake the
sum for a measurement:

* **G2 in ``records/plans/fleet-shape/evidence_and_params.md``: nothing on this
  fleet has ever run two llama.cpp MoE units co-resident on one host**, so the
  sum is the declared law rather than a measured one.
* The case that can actually arrive is a host whose card figures are
  *declared* — srv2's vLLM pair states ``vram_gb`` in the config. Two
  geometry-sized units cannot reach this check, because ``_placement`` fills the
  card with experts and the VRAM sum refuses them first. That is why the specs
  below are scalar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, UnitError, hold_together, unit_for

WINDOW = 4096

#: srv1's measured idle ``MemAvailable``, 2026-09-09 — the figure both the
#: sweep and the recorded scan agree on.
AVAILABLE_GB = 14.19

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)


def rig(*, ram_gb: float = AVAILABLE_GB, vram_mib: int = 12288) -> Scan:
    return Scan.of(
        host="srv1",
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


def declared(name: str, *, ram_gb: float, disk_gb: float) -> ModelSpec:
    """A spec whose card figure an operator stated — the shape a co-resident
    pair really has on this fleet, and small enough on the card that the VRAM
    sum lets the question through to the memory one."""
    return ModelSpec(
        name=name,
        vram_gb=3.0,
        ram_gb=ram_gb,
        disk_gb=disk_gb,
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def pair(*, ram_gb: float, disk_gb: float, ports: tuple[int, int]) -> tuple[Unit, ...]:
    """Two units on one host, at the ports the caller names: two ports for
    co-residents, one port twice for alternatives."""
    scan = rig()
    return tuple(
        unit_for(
            scan,
            declared(name, ram_gb=ram_gb, disk_gb=disk_gb),
            engine="llama.cpp",
            port=port,
            ctx_per_slot=WINDOW,
        )
        for name, port in zip(("careful", "quick"), ports, strict=True)
    )


def test_two_spilling_co_residents_are_summed_against_the_host() -> None:
    """The refusal this whole check exists for. Each unit allocates 6.5 GiB of
    experts and each clears the 2.0 GiB refusal margin on its own against
    14.19 GiB available — 8.5 against 14.19, twice. Together they ask for 13.0
    with 2.0 held back, and the host has 14.19.

    This is the arm where being wrong is silent: the experts are allocated, the
    host swaps, and every request is still served — at 32% of the decode rate
    the same unit reaches with room (``ram-headroom-2026-09-09``). Nothing
    errors, so nothing but this sum catches it.
    """
    units = pair(ram_gb=6.5, disk_gb=14.0, ports=(8080, 8081))
    assert [unit.fit.load_mode for unit in units] == ["none", "none"]
    with pytest.raises(UnitError) as raised:
        hold_together(units, {"srv1": rig()})
    why = str(raised.value)
    assert "careful" in why and "quick" in why, why
    assert "13.00" in why, why
    assert "14.19" in why, why


def test_a_mapped_unit_asks_for_its_blob_and_an_unmapped_one_for_its_experts() -> None:
    """The two arms F2.1 names, and the reason the sum runs *after* the modes
    are picked rather than before: which figure a unit contributes is decided by
    the mode, so a sum taken first would be summing the wrong numbers.

    Mapped, the blob is what the host is asked to hold — 6.5 GiB apiece here,
    against experts of 1.0. The same two units judged on their experts would sum
    to 2.0 and pass; judged on their blobs they sum to 13.0 and do not.
    """
    units = pair(ram_gb=1.0, disk_gb=6.5, ports=(8080, 8081))
    assert [unit.fit.load_mode for unit in units] == [None, None]
    assert [unit.fit.ram_gb for unit in units] == [6.5, 6.5]
    with pytest.raises(UnitError):
        hold_together(units, {"srv1": rig()})


def test_a_pair_that_fits_with_the_headroom_is_not_refused() -> None:
    """One host headroom, applied once to the sum and not once per unit. 5.5 GiB
    of blob each is 11.0 with 2.0 held back against 14.19 available, and that
    fits — where a margin charged per unit would make it 15.0 and refuse a
    layout the host can hold.
    """
    hold_together(pair(ram_gb=1.0, disk_gb=5.5, ports=(8080, 8081)), {"srv1": rig()})


def test_alternatives_are_not_summed_because_only_one_is_ever_up() -> None:
    """The same two units that were refused as co-residents, on one port. They
    take turns — the second cannot bind until the first is gone — so adding
    their memory prices a contention that cannot happen, which is exactly the
    rule ``hold_together`` already applies to the card.
    """
    hold_together(pair(ram_gb=6.5, disk_gb=14.0, ports=(8080, 8080)), {"srv1": rig()})


def test_a_unit_that_spills_nothing_asks_the_host_for_nothing() -> None:
    """A model held entirely on the card reads its weights once and serves them
    from there; the pages it touched are clean the moment they are uploaded.
    Two of those on one host sum to zero, whatever their blobs weigh.
    """
    units = pair(ram_gb=0.0, disk_gb=14.0, ports=(8080, 8081))
    assert [unit.fit.ram_gb for unit in units] == [0.0, 0.0]
    hold_together(units, {"srv1": rig()})


def test_a_lone_unit_is_left_to_the_fit_that_already_admitted_it() -> None:
    """srv1 as it now stands, and the guard on the other half of 2026-09-09's
    finding: one Qwen3.6, 12.30 GiB of blob mapped into 14.19 GiB available,
    admitted by a mode gate that holds back 0.5. A host RAM sum charging the
    2.0 GiB refusal margin to that lone unit would refuse the very rung the
    measurement says to map. There is nothing to sum on a host with one unit.
    """
    scan = rig(vram_mib=6144)
    qwen = unit_for(
        scan,
        ModelSpec(
            name="Qwen3.6-35B-A3B-UD-IQ3_XXS",
            vram_gb=0.0,
            ram_gb=0.0,
            disk_gb=0.0,
            geometry=GEOMETRY["Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"],
            kv_cache_dtype_k="f16",
            kv_cache_dtype_v="f16",
        ),
        engine="llama.cpp",
        ctx_per_slot=WINDOW,
    )
    assert qwen.fit.load_mode is None
    assert qwen.fit.ram_gb == pytest.approx(12.304, abs=0.001)
    hold_together((qwen,), {"srv1": scan})
