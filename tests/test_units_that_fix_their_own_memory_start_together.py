"""Units that take only the memory their launch states start together.

Two units on one card are chained (`depends_on` on a healthy neighbour) so one
does not size itself off memory the other has not taken yet. A llama.cpp unit
whose launch turns fitting off takes what its argv states and nothing more,
and the room for every unit on the card was reckoned before any was written;
so when every unit on a card does, they start at the same moment instead of
one after another. A unit that leaves fitting on, and any vLLM unit, keeps the
card's chain. The same holds for a locked fleet's layout on a host.

The machines here are invented.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import _document, _fixes_its_memory, emit_locked
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, unit_for

SPEC = ModelSpec(
    name="coder-small",
    vram_gb=1.5,
    ram_gb=0.0,
    disk_gb=1.0,
    kv_cache_dtype_k="f16",
    kv_cache_dtype_v="f16",
)
FIT_OFF = ("--fit", "off")


def pair(first: tuple[str, ...], second: tuple[str, ...]) -> dict[str, Any]:
    """The services of two llama.cpp units on one invented card."""
    scan = Scan.of(host="rig-b", vram_mib=16384, ram_gb=32.0, disk_free_gb=500.0)
    base = unit_for(scan, SPEC, engine="llama.cpp", width=1, ctx_per_slot=2048)
    units = (
        replace(base, port=8101, extra=first),
        replace(
            base,
            key=replace(base.key, model="coder-other", port=8102),
            model="coder-other",
            port=8102,
            extra=second,
        ),
    )
    services: dict[str, Any] = yaml.safe_load(_document(units))["services"]
    return services


def chained(services: dict[str, Any]) -> bool:
    return any("depends_on" in body for body in services.values())


def test_two_units_that_turn_fitting_off_start_together() -> None:
    services = pair(FIT_OFF, FIT_OFF)
    assert len(services) == 2
    assert not chained(services)
    assert not any("healthcheck" in body for body in services.values())


def test_one_unit_that_leaves_fitting_on_keeps_the_chain() -> None:
    assert chained(pair(FIT_OFF, ()))
    assert chained(pair((), ()))
    assert chained(pair(FIT_OFF, ("--fit", "on")))


@pytest.mark.parametrize(
    ("engine", "argv", "env", "fixed"),
    [
        ("llama.cpp", ["--fit", "off"], {}, True),
        ("llama.cpp", ["-fit", "0"], {}, True),
        ("llama.cpp", ["--fit=disabled"], {}, True),
        ("llama.cpp", [], {"LLAMA_ARG_FIT": "false"}, True),
        # A flag wins over the variable, as llama.cpp reads them.
        ("llama.cpp", ["--fit", "on"], {"LLAMA_ARG_FIT": "off"}, False),
        ("llama.cpp", [], {}, False),
        ("vllm", ["--fit", "off"], {"LLAMA_ARG_FIT": "off"}, False),
    ],
)
def test_what_fixes_a_units_memory(
    engine: str, argv: list[str], env: dict[str, str], fixed: bool
) -> None:
    assert _fixes_its_memory(engine, argv, env) is fixed


def locked_fleet(first: list[str], second: list[str]) -> dict[str, Any]:
    def unit(name: str, port: int, flags: list[str]) -> dict[str, Any]:
        return {
            "unit_id": f"id-{name}",
            "address": f"http://rig-c:{port}",
            "engine": "llama.cpp",
            "image": "example/llama-server:1",
            "container": f"mcgyvr-rig-c-{name}",
            "launch": {
                "argv": ["--port", str(port), *flags],
                "env": {},
                "volumes": ["/srv/models:/models:ro"],
            },
        }

    return {
        "units": {
            "small": unit("small", 8201, first),
            "other": unit("other", 8202, second),
        },
        "fleets": {"pair": {"layout": {"rig-c": [["small"], ["other"]]}}},
    }


def test_a_locked_layout_whose_units_turn_fitting_off_starts_together(
    tmp_path: Path,
) -> None:
    together = emit_locked(locked_fleet(list(FIT_OFF), list(FIT_OFF)), tmp_path / "a")
    services = yaml.safe_load(together[0].read_text(encoding="utf-8"))["services"]
    assert len(services) == 2
    assert not chained(services)

    ordered = emit_locked(locked_fleet(list(FIT_OFF), []), tmp_path / "b")
    services = yaml.safe_load(ordered[0].read_text(encoding="utf-8"))["services"]
    assert services["other"]["depends_on"] == {
        "small": {"condition": "service_healthy"}
    }
