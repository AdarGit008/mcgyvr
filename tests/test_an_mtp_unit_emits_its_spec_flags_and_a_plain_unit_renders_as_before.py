"""An MTP unit emits its spec flags, and a plain unit renders as before.

``--spec-type draft-mtp`` and ``--spec-draft-n-max N`` are derived flags on the
unit's ``args`` — the same mapping ``--n-cpu-moe`` and ``-ctk`` ride on — so
:func:`mcgyvr.emit.argv` sorts them with the rest and both renderings carry
them. A unit declaring ``speculative: none`` renders byte-identically to a unit
built before the keys existed: no flag appears, and the file does not move.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.emit import argv, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, unit_for

WINDOW = 4096
GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)
KAT = "KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf"


def card() -> Scan:
    return Scan.of(
        host="srv2",
        vram_mib=12288,
        ram_gb=48.0,
        disk_free_gb=120.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def unit(**declared: Any) -> Unit:
    spec = ModelSpec(
        name=KAT[: -len(".gguf")],
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=GEOMETRY[KAT],
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
        **declared,
    )
    return unit_for(card(), spec, width=1, ctx_per_slot=WINDOW)


def command_of(document: str) -> list[str]:
    services = yaml.safe_load(document)["services"]
    (service,) = services.values()
    command: list[str] = service["command"]
    return command


def test_both_renderings_carry_the_spec_flags_in_flag_order() -> None:
    mtp = unit(speculative="mtp", spec_draft_n_max=2)
    parts = argv(mtp)
    flags = [part for part in parts if part.startswith("-")]
    assert flags == sorted(flags), "derived flags are emitted in one fixed order"
    index = parts.index("--spec-draft-n-max")
    assert parts[index : index + 4] == (
        "--spec-draft-n-max",
        "2",
        "--spec-type",
        "draft-mtp",
    )
    assert command_of(render_compose(mtp)) == list(parts)
    assert shlex.split(render_command(mtp))[1:] == list(parts)


def test_a_plain_unit_renders_byte_identically_to_one_built_before() -> None:
    before = unit()
    plain = unit(speculative="none", spec_draft_n_max=2)
    assert render_compose(plain) == render_compose(before)
    assert render_command(plain) == render_command(before)
    assert "--spec-type" not in argv(plain)
    assert "--spec-draft-n-max" not in argv(plain)


def test_a_declared_draft_width_is_the_flag_in_both_renderings() -> None:
    mtp = unit(speculative="mtp", spec_draft_n_max=4)
    parts = argv(mtp)
    assert parts[parts.index("--spec-draft-n-max") + 1] == "4"
    command = command_of(render_compose(mtp))
    assert command[command.index("--spec-draft-n-max") + 1] == "4"
