"""The inputs a sizing pass runs on: fleet scans, ladder hosts, and the models to fit.

The rig files in the fleet's rigs folder supply the scans (through
`mcgyvr.serving.rigfile.recorded_scans` and `resolve_hosts`), the config's ladder
supplies the hostnames a scan may be found under, and the models come from the
shipped knowledge catalogue and from the capability table, each row turned into
a `ModelSpec` the placement code can weigh.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcgyvr.capability import (
    GB_PER_GIB,
    CapabilityTableError,
    Model,
    load,
    table_path,
)
from mcgyvr.config import (
    Config,
)
from mcgyvr.serving import (
    ModelSpec,
    UnitError,
    host_of,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


def _hosts_wanted(config: Config) -> dict[str, str]:
    """Each ladder rung mapped to the host its unit's address points at.

    A rung with no unit of that name, or a unit whose address names no host, is
    a `UnitError` rather than a missing entry.
    """
    wanted: dict[str, str] = {}
    for name in config.ladder.names:
        unit = config.units.get(name)
        if unit is None:
            raise UnitError(f"{name}: no unit named {name!r}")
        wanted[name] = host_of(unit.address)
    return wanted


def _model_spec(model: Model, moe: bool, name: str | None = None) -> ModelSpec:
    """One table row as a `ModelSpec`, named by the row's id unless told another.

    The row's GiB figures become the spec's GB ones; nothing holds host RAM, no
    geometry came from a scan, and the KV cache is f16 in both directions.
    """
    return ModelSpec(
        name=name or model.id,
        vram_gb=model.vram_gb_working / GB_PER_GIB,
        ram_gb=0.0,
        disk_gb=model.weights_gb / GB_PER_GIB,
        moe=moe,
        geometry=None,
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def _model_specs() -> tuple[ModelSpec, ...]:
    """Every model a placement may fit: the catalogue's records, then the table's rows.

    A row's `moe` comes from the architecture the table declares for it, and a
    row that also answers to a second `model_id` is listed under both names.
    """
    specs: list[ModelSpec] = list(_catalog_specs())
    architectures = _architectures()
    for model in load().models:
        moe = architectures.get(model.id) == "moe"
        specs.append(_model_spec(model, moe))
        if model.model_id is not None and model.model_id != model.id:
            specs.append(_model_spec(model, moe, name=model.model_id))
    return tuple(specs)


def _catalog_specs() -> tuple[ModelSpec, ...]:
    """One `ModelSpec` per record the knowledge holds: the shipped catalogue with
    the cache over it, so a model a Hub read filed there is sized as a shipped
    one is.

    Its VRAM is the file's size plus the KV cache a token takes at the whole
    context the record states, its disk cost the file's size alone. A catalogue
    that cannot be read is reported as a broken capability table.
    """
    from mcgyvr.knowledge import store as knowledge_store
    from mcgyvr.knowledge.record import KnowledgeError

    try:
        records = knowledge_store.offline().records
    except KnowledgeError as exc:
        raise CapabilityTableError(str(exc)) from exc
    specs: list[ModelSpec] = []
    for one in records:
        size_gib = one.size_bytes.value / (1024**3)
        kv_gib = one.context_length.value * one.kv_bytes_per_token.value / (1024**3)
        specs.append(
            ModelSpec(
                name=one.model_id,
                vram_gb=size_gib + kv_gib,
                ram_gb=0.0,
                disk_gb=size_gib,
                moe=False,
                geometry=None,
                kv_cache_dtype_k="f16",
                kv_cache_dtype_v="f16",
            )
        )
    return tuple(specs)


def _architectures() -> dict[str, str]:
    """Each capability table row's id mapped to the architecture it declares.

    Rows that declare no architecture are absent from the map, which is what
    leaves them not-MoE. A table that cannot be read is a `CapabilityTableError`.
    """
    path = table_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityTableError(f"cannot read {path}: {exc}") from exc
    return {
        str(entry["id"]): str(entry["architecture"])
        for entry in raw.get("models", [])
        if entry.get("architecture")
    }
