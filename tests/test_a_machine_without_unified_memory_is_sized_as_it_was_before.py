"""A machine without unified memory is sized as it was before.

Unified memory is now counted once, and the decode estimate is new; neither may
move a sizing of a machine whose cards have memory of their own. For every
invented machine that reports a card (the Linux shapes, and the hosts with a
discrete card or none), a few invented models are sized as a unit would be and
as a plan would be: a small dense model, one too big for any card, a
mixture-of-experts model that fits only by spilling experts to host memory,
and the same one stating its blob, so the loading mode is weighed. Each sizing's whole
answer (whether it fits, what it takes on the card and in memory, how it is
loaded, and the reason it gives) is pinned as the sizing made it before.
"""

from __future__ import annotations

import hashlib
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
        moe = spilling(scan)
        specs["moe-spilling"] = moe
        size = int((moe.geometry or {})["size_bytes"])
        specs["moe-spilling-with-its-blob"] = replace(moe, disk_gb=size / (1 << 30))
    return specs


def _header(spec: ModelSpec) -> dict[str, Any]:
    """The plan's view of a spec with a geometry: its file and a cache-less
    context, so only the weights decide."""
    geometry = dict(spec.geometry or {})
    return {**geometry, "n_ctx_train": WINDOW}


def sizings(scan: Scan) -> dict[str, str]:
    """Each sizing of ``scan``, as sixteen hex digits of sha256 over its answer."""
    out: dict[str, str] = {}
    for name, spec in _specs(scan).items():
        answer: tuple[Any, ...] = (fit(scan, spec, engine=ENGINE, ctx_per_slot=WINDOW),)
        if spec.geometry is not None:
            answer += (recommend._fits(scan, _header(spec), 1),)
        out[name] = hashlib.sha256(repr(answer).encode()).hexdigest()[:16]
    return out


#: Per invented machine and model: the digest of the sizing as it was before
#: unified memory was counted once.
BEFORE: dict[str, dict[str, str]] = {
    "busy-beside-free": {
        "dense-small": "1c83e7d34edfa17f",
        "dense-too-big": "c2fef6a354139bb2",
        "moe-spilling": "f4060f164f17c51e",
        "moe-spilling-with-its-blob": "f4060f164f17c51e",
    },
    "busy-card": {
        "dense-small": "671d019169ff500e",
        "dense-too-big": "9adcfc02b24f92bf",
        "moe-spilling": "2f51b123d4e16eb3",
        "moe-spilling-with-its-blob": "2f51b123d4e16eb3",
    },
    "four-equal": {
        "dense-small": "5632a5b53bc333ee",
        "dense-too-big": "a009b1ccf01f346a",
        "moe-spilling": "19293a47dbb77375",
        "moe-spilling-with-its-blob": "19293a47dbb77375",
    },
    "linux-one-card": {
        "dense-small": "1c83e7d34edfa17f",
        "dense-too-big": "c2fef6a354139bb2",
        "moe-spilling": "7ac88dd5327601e8",
        "moe-spilling-with-its-blob": "7ac88dd5327601e8",
    },
    "mac-without-unified": {
        "dense-small": "bcb851dae864d667",
        "dense-too-big": "6f5b162684544b8d",
    },
    "mixed-vendors": {
        "dense-small": "6e2446ae35a641a4",
        "dense-too-big": "3c78d102283a3fc9",
        "moe-spilling": "654cd2e11cbe286b",
        "moe-spilling-with-its-blob": "654cd2e11cbe286b",
    },
    "one-card": {
        "dense-small": "1c83e7d34edfa17f",
        "dense-too-big": "c2fef6a354139bb2",
        "moe-spilling": "f4060f164f17c51e",
        "moe-spilling-with-its-blob": "f4060f164f17c51e",
    },
    "same-cards-here": {
        "dense-small": "6e2446ae35a641a4",
        "dense-too-big": "3c78d102283a3fc9",
        "moe-spilling": "654cd2e11cbe286b",
        "moe-spilling-with-its-blob": "654cd2e11cbe286b",
    },
    "same-cards-there": {
        "dense-small": "6e2446ae35a641a4",
        "dense-too-big": "3c78d102283a3fc9",
        "moe-spilling": "654cd2e11cbe286b",
        "moe-spilling-with-its-blob": "654cd2e11cbe286b",
    },
    "several-sizes": {
        "dense-small": "d362fe374126cc17",
        "dense-too-big": "252d64c98541336a",
        "moe-spilling": "957aefeb5f5bdf67",
        "moe-spilling-with-its-blob": "957aefeb5f5bdf67",
    },
    "two-sizes": {
        "dense-small": "b92c3dd8bfbce28d",
        "dense-too-big": "a83460e723ef805e",
        "moe-spilling": "304aaa11123e19a5",
        "moe-spilling-with-its-blob": "304aaa11123e19a5",
    },
    "unreadable-size": {
        "dense-small": "1c83e7d34edfa17f",
        "dense-too-big": "c2fef6a354139bb2",
        "moe-spilling": "f4060f164f17c51e",
        "moe-spilling-with-its-blob": "f4060f164f17c51e",
    },
    "unreadable-size-first": {
        "dense-small": "1c83e7d34edfa17f",
        "dense-too-big": "c2fef6a354139bb2",
        "moe-spilling": "f4060f164f17c51e",
        "moe-spilling-with-its-blob": "f4060f164f17c51e",
    },
    "windows-card-tool-in-system": {
        "dense-small": "5632a5b53bc333ee",
        "dense-too-big": "a009b1ccf01f346a",
        "moe-spilling": "03d378a6be9bd1a0",
        "moe-spilling-with-its-blob": "03d378a6be9bd1a0",
    },
    "windows-card-tool-in-vendor-folder": {
        "dense-small": "8c2f371d5d88d418",
        "dense-too-big": "0f9b9d6593454d84",
        "moe-spilling": "004df9a799bcaeb5",
        "moe-spilling-with-its-blob": "004df9a799bcaeb5",
    },
    "windows-no-modules": {
        "dense-small": "bcb851dae864d667",
        "dense-too-big": "6f5b162684544b8d",
    },
    "windows-one-card": {
        "dense-small": "1c83e7d34edfa17f",
        "dense-too-big": "c2fef6a354139bb2",
        "moe-spilling": "5c2be8938572e041",
        "moe-spilling-with-its-blob": "5c2be8938572e041",
    },
    "windows-other-gpu": {
        "dense-small": "bcb851dae864d667",
        "dense-too-big": "6f5b162684544b8d",
    },
}


@pytest.mark.parametrize("label", sorted(_scans()))
def test_every_sizing_of_a_machine_with_its_own_card_memory_is_unchanged(
    label: str,
) -> None:
    assert sizings(_scans()[label]) == BEFORE[label]
