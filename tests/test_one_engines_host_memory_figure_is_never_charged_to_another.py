"""A unit is charged only its own engine's host memory figure.

When a sizing leaves some of a model's experts in host memory, it also charges
the host memory the server holds beyond them, and that figure belongs to the
server's engine: the one shipped for llama.cpp, or the user's own value for
it, is llama.cpp's. A unit of another engine is never sized with it, so moving
llama.cpp's figure moves what a llama.cpp unit is asked for and leaves every
other engine's unit exactly where it was.

The machines are the invented shapes of :mod:`tests.machine_shapes`, as their
scans report them (no memory reading, so a unit whose experts spill is refused
for memory, and the refusal states what it was asked for). The model is
invented here and sized from the roomiest card of each machine, so that most of
its experts spill. The user's own values are invented too and written in the
HOME each test is given.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import derived
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, unit_for, vramfit
from tests import machine_shapes
from tests import numbers_fixture as nf

#: The window every sizing here declares.
WINDOW = 4096

#: The engines that carry a ``runtime_resident_gb`` figure: the one shipped,
#: plus the ones read on the machine.
ENGINES = (derived.RUNTIME_RESIDENT_KEY, *derived.RUNTIME_RESIDENT_READ)

#: The invented model: its name, and how many expert blocks it has.
MODEL = "example-moe"
BLOCKS = 8

#: Two values the user might set for llama.cpp's figure, in GiB: invented, and
#: far enough apart that any sizing charged with them states two figures.
SETTINGS = (0.25, 3.75)


def machines() -> list[machine_shapes.Shape]:
    """Every invented machine whose scan reports a card."""
    return [machine for machine in machine_shapes.shapes() if machine.readable_cards]


def spilling(scan: Scan) -> ModelSpec:
    """An invented MoE that fits the roomiest card of ``scan`` only by spilling.

    Its non-expert weights and the card's scratch allowance take half of the
    card's free memory; each expert block takes a quarter of what the
    allowance leaves, so two blocks stay on the card and the rest spill to
    host memory. It caches nothing and has no recurrent state, so its slot
    count moves nothing here.
    """
    free = max(gpu.vram.free_mib for gpu in scan.gpus) << 20
    room = free - (vramfit.SCRATCH_AND_CONTEXT_MIB << 20)
    nonexpert = room // 2
    block = room // 4
    by_block = {str(index): block for index in range(BLOCKS)}
    geometry: dict[str, Any] = {
        "file": f"/models/{MODEL}.gguf",
        "size_bytes": nonexpert + block * BLOCKS,
        "arch": "invented",
        "n_layer": BLOCKS,
        "bytes_nonexpert": nonexpert,
        "bytes_experts": block * BLOCKS,
        "placeable_blocks": list(range(BLOCKS)),
        "expert_bytes_by_block": by_block,
        "kv_layers": [],
        "n_recurrent": 0,
    }
    return ModelSpec(
        name=MODEL,
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=geometry,
        hf_cache="/models/hf",
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def refusal(scan: Scan, spec: ModelSpec, engine: str) -> str:
    """What sizing ``spec`` on ``scan`` for ``engine`` says when it refuses."""
    with pytest.raises(UnitError) as refused:
        unit_for(scan, spec, engine=engine, ctx_per_slot=WINDOW)
    return str(refused.value)


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
def test_only_its_own_engines_figure_moves_what_a_unit_is_asked_for(
    machine: machine_shapes.Shape, tmp_path_factory: pytest.TempPathFactory
) -> None:
    scan = machine_shapes.scan(machine)
    spec = spilling(scan)
    engines = ENGINES
    said: dict[str, list[str]] = {engine: [] for engine in engines}
    for value in SETTINGS:
        nf.write_user_file(
            tmp_path_factory,
            {derived.RUNTIME_RESIDENT: {derived.RUNTIME_RESIDENT_KEY: value}},
        )
        for engine in engines:
            said[engine].append(refusal(scan, spec, engine))

    own = said[derived.RUNTIME_RESIDENT_KEY]
    assert own[0] != own[1], (
        f"a {derived.RUNTIME_RESIDENT_KEY} unit is asked for the same memory "
        f"under two of its own figures: {own[0]!r}"
    )
    for engine in engines:
        if engine == derived.RUNTIME_RESIDENT_KEY:
            continue
        first, second = said[engine]
        assert first == second, (
            f"a {engine} unit moved with {derived.RUNTIME_RESIDENT_KEY}'s figure: "
            f"{first!r} became {second!r}"
        )
