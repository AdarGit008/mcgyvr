"""Two units sharing a card start in an order, and the bigger one goes first.

``emit`` writes one compose file per host and no dependency between its
services, so ``docker compose up -d`` starts every unit at once. On a card that
fits both only if they load one after the other, that is a race.

Measured on srv2, 2026-09-05: started together, the 7B got 0.89 GiB of KV cache
and 4.08x concurrency; started alone after the 3B was resident, 2.77 GiB and
12.68x. The first attempt crash-looped until the two were sequenced by hand —
the 7B needed 8.37 GiB free and found 7.61.

The bigger unit goes first because it is the one that cannot recover: a small
model measuring the card after a large neighbour has taken its share still
fits, and the large one measuring after the small has taken its share does not.

**Built from real units through the shipped emit path.** An earlier draft
invented ``compose_document(tmp_path)`` — a function taking a directory and
somehow knowing to produce two co-resident units, with a ``units=1`` keyword for
the single case. Nothing could implement that except a shim written for this
test. The units here are built the way ``tests/test_emit.py`` builds them, from
a scan and a spec, and the document is whatever ``emit_all`` writes.

How the order is expressed is the port's choice — ``depends_on`` is compose's
usual spelling, but a single service with two commands, or an explicit start
script, would satisfy the requirement equally. What must be observable is that
the file does not tell the daemon to start both at once, and that the order,
however written, puts the larger first.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.emit import emit_all
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, unit_for
from tests.red_port.conftest import required

#: The window these tests were written against, stated because nothing supplies
#: one any more. ``mcgyvr.serving.DEFAULT_CONTEXT`` was retired on 2026-09-06:
#: the window is what the run declares, so a test is a run and declares its own.
WINDOW = 4096

#: One card big enough for both models only once, which is the whole case.
CARD_MIB = 12288

#: A vLLM unit loads a repository id out of the rig's HuggingFace cache, so a
#: spec served by it has to say where that cache is — the same requirement the
#: live srv2 config carries for both of these models.
BIG = ModelSpec(
    name="qwen2.5-coder-7b",
    vram_gb=8.4,
    ram_gb=0.0,
    disk_gb=5.2,
    hf_cache="/home/x/.cache/huggingface",
)
SMALL = ModelSpec(
    name="qwen2.5-coder-3b",
    vram_gb=3.5,
    ram_gb=0.0,
    disk_gb=2.1,
    hf_cache="/home/x/.cache/huggingface",
)


def _rig() -> Scan:
    """One card, built the way ``tests/test_emit.py`` builds a machine."""
    return Scan.of(
        host="srv2",
        vram_mib=CARD_MIB,
        ram_gb=64.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def _both() -> tuple[Unit, Unit]:
    """The two units srv2 actually serves, on one card, on two ports."""
    rig = _rig()
    big = unit_for(rig, BIG, engine="vllm", width=8, port=8002, ctx_per_slot=WINDOW)
    small = unit_for(rig, SMALL, engine="vllm", width=6, port=8001, ctx_per_slot=WINDOW)
    assert big.gpu == small.gpu, "the fixture is about two units on ONE card"
    return big, small


def _document(units: tuple[Unit, ...]) -> dict[str, Any]:
    written = emit_all(units, root=Path(tempfile.mkdtemp()))
    parsed: dict[str, Any] = yaml.safe_load(written[0].read_text(encoding="utf-8"))
    return parsed


def _waits_for(services: dict[str, Any]) -> dict[str, set[str]]:
    """Which service each one is declared to start after, however expressed."""
    order: dict[str, set[str]] = {}
    for name, body in services.items():
        named = set()
        for other in services:
            if other == name:
                continue
            if other in yaml.safe_dump(body):
                named.add(other)
        if named:
            order[name] = named
    return order


def test_two_units_sharing_a_card_do_not_start_at_once() -> None:
    """The race, stated as what the file tells the daemon to do."""
    ordered = required(
        "emit a compose file that sequences two units sharing one GPU",
        lambda: _document(_both()),
    )
    services = ordered["services"]
    assert len(services) == 2, f"the fixture is about two units: {list(services)}"
    assert _waits_for(services), (
        "neither service names the other, so `compose up -d` starts both at "
        f"once on one card: {list(services)}"
    )


def test_the_order_puts_the_larger_unit_first() -> None:
    """The direction matters, and is not satisfied by any order at all.

    The size comes from the units the fixture built, not from a flag parsed
    back out of the rendered command — a proxy that cannot be read would make
    every comparison ``0.0 >= 0.0`` and the assertion vacuous.
    """
    big, small = _both()
    services = _document((big, small))["services"]
    # Matched on the service's own name rather than anywhere in its rendered
    # body. Once an order exists at all, one service names the other inside
    # itself — that is what an order IS, and what `_waits_for` reads — so a
    # body-wide substring match reports both services as the big one and the
    # comparison below becomes 8.4 >= 8.4 either way. The service name is
    # derived from the model, which is the fixture's own fact and not a flag
    # parsed back out of a command.
    by_size = {}
    for name in services:
        if name.startswith(BIG.name):
            by_size[name] = BIG.vram_gb
        elif name.startswith(SMALL.name):
            by_size[name] = SMALL.vram_gb
    assert len(by_size) == 2 and len(set(by_size.values())) == 2, (
        f"the two services must be tellable apart by size: {by_size}"
    )

    order = _waits_for(services)
    assert order, "no order is declared at all"
    for name, waits_for in order.items():
        for other in waits_for:
            assert by_size[other] >= by_size[name], (
                f"{name} ({by_size[name]} GB) starts after {other} "
                f"({by_size[other]} GB); the larger unit must go first"
            )


def test_a_host_with_one_unit_declares_no_order() -> None:
    """An order where nothing contends is a dependency that only slows a restart."""
    big, _ = _both()
    services = _document((big,))["services"]
    assert len(services) == 1
    assert not _waits_for(services), (
        "a single unit has nothing to wait for; an order here is noise that "
        "delays every restart"
    )
