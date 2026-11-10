"""Setup and the ladder size a catalog record by the one catalog-slot law.

`mcgyvr recommend` prices a catalog record's cache with
`recommend._catalog_slot_bytes`: the context padded to whole cache cells, times
the per-token KV bytes, plus the recurrent (state-space) bytes of each
sequence. Setup and the ladder (`cli.sizing._catalog_specs`) size the same
record through that same function, for one user, so a hybrid or recurrent
model is no longer sized without its state and a context that is not a whole
number of cells is padded as llama.cpp pads it. The scan is an invented
machine.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from mcgyvr import recommend
from mcgyvr.cli import sizing
from mcgyvr.config import Config, Ladder, Unit
from mcgyvr.hubwire import CACHE_PAD_CELLS
from mcgyvr.knowledge import store as knowledge_store
from mcgyvr.knowledge.record import ModelRecord, Number
from mcgyvr.ladder_proposal import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Scan
from mcgyvr.serving import Unit as ServedUnit
from mcgyvr.serving import UnitError, units_for

HYBRID = "Qwen/Qwen3.5-4B"
GIB = 1024**3


def _record(model_id: str) -> ModelRecord:
    return next(r for r in knowledge_store.shipped() if r.model_id == model_id)


def _numbered(number: Number, value: int) -> Number:
    return replace(number, value=value)


def test_the_shipped_hybrid_states_a_recurrent_state() -> None:
    assert _record(HYBRID).recurrent_bytes_per_slot.value > 0


def test_a_hybrid_catalog_model_is_sized_with_its_recurrent_state() -> None:
    record = _record(HYBRID)
    spec = {s.name: s for s in sizing._catalog_specs()}[HYBRID]
    cache = record.context_length.value * record.kv_bytes_per_token.value
    expected = record.size_bytes.value + cache + record.recurrent_bytes_per_slot.value
    assert spec.vram_gb * GIB == pytest.approx(expected)
    assert spec.disk_gb * GIB == pytest.approx(record.size_bytes.value)


def test_setup_sizes_every_catalog_record_as_recommend_does_for_one_user() -> None:
    specs = {s.name: s for s in sizing._catalog_specs()}
    for record in knowledge_store.offline().records:
        priced = recommend._catalog_spec(recommend._flat(record), users=1)
        assert priced is not None
        assert specs[record.model_id].vram_gb == priced.vram_gb
        assert specs[record.model_id].disk_gb == priced.disk_gb


def test_a_context_short_of_a_whole_cell_is_padded_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipped = _record(HYBRID)
    ragged = CACHE_PAD_CELLS * 37 + 5
    record = replace(shipped, context_length=_numbered(shipped.context_length, ragged))
    monkeypatch.setattr(
        knowledge_store, "offline", lambda: SimpleNamespace(records=(record,))
    )
    (spec,) = sizing._catalog_specs()
    cells = CACHE_PAD_CELLS * 38
    expected = (
        record.size_bytes.value
        + cells * record.kv_bytes_per_token.value
        + record.recurrent_bytes_per_slot.value
    )
    assert spec.vram_gb * GIB == pytest.approx(expected)


def _hybrid_on(vram_mib: int) -> list[ServedUnit]:
    config = Config(
        path=None,
        data={},
        units={
            "rung": Unit(name="rung", address="http://rig.example:8080", model=HYBRID)
        },
        ladder=Ladder(names=("rung",)),
    )
    scan = Scan.of(
        host="rig.example",
        vram_mib=vram_mib,
        ram_gb=48.0,
        disk_free_gb=900.0,
        cores=8,
        threads=16,
        bandwidth_gbps=41.2,
    )
    return list(
        units_for(
            config,
            {"rig.example": scan},
            specs=sizing._model_specs(),
            ctx_per_slot=4096,
        )
    )


def test_a_card_with_room_for_the_cache_but_not_the_state_is_refused() -> None:
    """On an invented card that holds the file and the KV cache with the
    headroom to spare, but not the recurrent state on top, setup now refuses
    the hybrid: the state is on the card llama.cpp allocates. A card with room
    for the state as well takes it."""
    record = _record(HYBRID)
    without_state = (
        record.size_bytes.value
        + record.context_length.value * record.kv_bytes_per_token.value
    ) / GIB
    state = record.recurrent_bytes_per_slot.value / GIB
    short = int((without_state + DEFAULT_HEADROOM_GB + state / 2) * 1024)
    with pytest.raises(UnitError, match=r"Qwen3\.5-4B: needs .* GB on the card"):
        _hybrid_on(short)
    roomy = int((without_state + DEFAULT_HEADROOM_GB + state * 2) * 1024)
    (unit,) = _hybrid_on(roomy)
    assert unit.fit.fits is True
    assert unit.fit.vram_gb * GIB == pytest.approx(
        record.size_bytes.value
        + record.context_length.value * record.kv_bytes_per_token.value
        + record.recurrent_bytes_per_slot.value
    )
