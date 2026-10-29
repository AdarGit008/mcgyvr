"""A machine without unified memory is sized as it was before.

Unified memory is now counted once, and the decode estimate is new; neither may
move a sizing of a machine whose cards have memory of their own. For every
invented machine that reports a card (the Linux shapes, and the hosts with a
discrete card or none), a few invented models are sized as a unit would be and
as a plan would be: a small dense model, one too big for any card, and a
mixture-of-experts model that fits only by spilling experts to host memory.
Each sizing's answer (whether it fits, what it takes on the card and in memory,
how it is loaded, and the reason it gives) is pinned as the sizing made it
before.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

import pytest

from mcgyvr import recommend
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, fit
from tests import machine_shapes
from tests.sizings import WINDOW, machines, spilling

#: The engine every sizing here is for.
ENGINE = "llama.cpp"

#: The parts of a unit's fit that are pinned: every field a sizing set before.
FIT_FIELDS = (
    "fits",
    "headroom_gb",
    "why",
    "vram_gb",
    "ram_gb",
    "load_mode",
    "card_free_gb",
    "notes",
)


def _scans() -> dict[str, Scan]:
    """Every invented machine with a card or with its memory read, by label,
    unified-memory machines left out. The disk is the test host's own, so it is
    left out too."""
    found = {machine.label: machine_shapes.scan(machine) for machine in machines()}
    for host in machine_shapes.host_shapes():
        scan = machine_shapes.host_scan(host)
        if any(gpu.kind == "unified" for gpu in scan.gpus):
            continue
        found[host.label] = scan
    return {label: replace(scan, disk=None) for label, scan in found.items()}


def _specs(scan: Scan) -> dict[str, ModelSpec]:
    dense = ModelSpec(name="example-dense", vram_gb=1.0, ram_gb=0.0, disk_gb=1.0)
    specs = {
        "dense-small": dense,
        "dense-too-big": replace(dense, name="example-huge", vram_gb=4096.0),
    }
    if scan.gpus and max(gpu.vram.free_mib for gpu in scan.gpus) > 0:
        specs["moe-spilling"] = spilling(scan)
    return specs


def _header(spec: ModelSpec) -> dict[str, Any]:
    """The plan's view of a spec with a geometry: its file and a cache-less
    context, so only the weights decide."""
    geometry = dict(spec.geometry or {})
    return {**geometry, "n_ctx_train": WINDOW}


def sizings(scan: Scan) -> dict[str, str]:
    """Each sizing of ``scan``, as sixteen hex digits of sha256 over its answer:
    the unit's fit, field by field, and the plan's yes or no."""
    out: dict[str, str] = {}
    for name, spec in _specs(scan).items():
        sized = fit(scan, spec, engine=ENGINE, ctx_per_slot=WINDOW)
        answer: dict[str, Any] = {field: getattr(sized, field) for field in FIT_FIELDS}
        if spec.geometry is not None:
            answer["plan_fits"] = recommend._fits(scan, _header(spec), 1)
        text = json.dumps(answer, sort_keys=True, default=str)
        out[name] = hashlib.sha256(text.encode()).hexdigest()[:16]
    return out


#: Per invented machine and model: the digest of the sizing as it was before
#: unified memory was counted once.
BEFORE: dict[str, dict[str, str]] = {
    "busy-beside-free": {
        "dense-small": "61477553d501c2db",
        "dense-too-big": "127d568ce8b0754c",
        "moe-spilling": "71ab7928adf801be",
    },
    "busy-card": {
        "dense-small": "e9ae439e1995e077",
        "dense-too-big": "032c16b37d791eb6",
        "moe-spilling": "3d9569ace2b311d8",
    },
    "four-equal": {
        "dense-small": "b95ee9d1430c850c",
        "dense-too-big": "0c3a82a19f34ab4c",
        "moe-spilling": "0e5c37b19cc535d6",
    },
    "linux-one-card": {
        "dense-small": "61477553d501c2db",
        "dense-too-big": "127d568ce8b0754c",
        "moe-spilling": "0da83a710e977315",
    },
    "mac-without-unified": {
        "dense-small": "6ac7fe9eb778d0d6",
        "dense-too-big": "0f40e5f91a21fca2",
    },
    "mixed-vendors": {
        "dense-small": "f45a19b67f102650",
        "dense-too-big": "199bc672c4fbaa2b",
        "moe-spilling": "5a2542b79ee783be",
    },
    "one-card": {
        "dense-small": "61477553d501c2db",
        "dense-too-big": "127d568ce8b0754c",
        "moe-spilling": "71ab7928adf801be",
    },
    "same-cards-here": {
        "dense-small": "f45a19b67f102650",
        "dense-too-big": "199bc672c4fbaa2b",
        "moe-spilling": "5a2542b79ee783be",
    },
    "same-cards-there": {
        "dense-small": "f45a19b67f102650",
        "dense-too-big": "199bc672c4fbaa2b",
        "moe-spilling": "5a2542b79ee783be",
    },
    "several-sizes": {
        "dense-small": "21d98ea1d564f781",
        "dense-too-big": "b333124cc680aa1b",
        "moe-spilling": "79abfb6dc84580a7",
    },
    "two-sizes": {
        "dense-small": "ce4af6490f5b1ca1",
        "dense-too-big": "60fee3eca1aeaa8d",
        "moe-spilling": "78f52a9af6c30c5e",
    },
    "unreadable-size": {
        "dense-small": "61477553d501c2db",
        "dense-too-big": "127d568ce8b0754c",
        "moe-spilling": "71ab7928adf801be",
    },
    "unreadable-size-first": {
        "dense-small": "61477553d501c2db",
        "dense-too-big": "127d568ce8b0754c",
        "moe-spilling": "71ab7928adf801be",
    },
    "windows-card-tool-in-system": {
        "dense-small": "b95ee9d1430c850c",
        "dense-too-big": "0c3a82a19f34ab4c",
        "moe-spilling": "4dc0686ed3854784",
    },
    "windows-card-tool-in-vendor-folder": {
        "dense-small": "40dd99a1a0355f7c",
        "dense-too-big": "b1ea77d5911d479f",
        "moe-spilling": "c6c33b0e438234ba",
    },
    "windows-no-modules": {
        "dense-small": "6ac7fe9eb778d0d6",
        "dense-too-big": "0f40e5f91a21fca2",
    },
    "windows-one-card": {
        "dense-small": "61477553d501c2db",
        "dense-too-big": "127d568ce8b0754c",
        "moe-spilling": "a8a221b6b284929c",
    },
    "windows-other-gpu": {
        "dense-small": "6ac7fe9eb778d0d6",
        "dense-too-big": "0f40e5f91a21fca2",
    },
}


def test_every_pinned_machine_is_one_of_the_shapes() -> None:
    assert sorted(BEFORE) == sorted(_scans())


@pytest.mark.parametrize("label", sorted(_scans()))
def test_every_sizing_of_a_machine_with_its_own_card_memory_is_unchanged(
    label: str,
) -> None:
    assert sizings(_scans()[label]) == BEFORE[label]
