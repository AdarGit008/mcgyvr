"""The inputs a sizing pass runs on: fleet scans, ladder hosts, and the models to fit.

The rig files in the fleet's rigs folder supply the scans (through
`mcgyvr.serving.rigfile.recorded_scans` and `resolve_hosts`), the config's ladder
supplies the hostnames a scan may be found under, and the models come from the
shipped knowledge catalogue and from the capability table, each row turned into
a `ModelSpec` the placement code can weigh.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from mcgyvr.capability import (
    GB_PER_GIB,
    CapabilityTableError,
    Model,
    load,
)
from mcgyvr.config import (
    Config,
)
from mcgyvr.knowledge.record import MOE
from mcgyvr.serving import (
    ModelSpec,
    UnitError,
    fetchlist,
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
    An MoE row whose `model_id` names a catalog record is sized from that
    record's header row under both names (`_moe_spec`), so the two lists size
    one mixture of experts alike; the table holds no geometry of its own.
    """
    catalog = _catalog_specs()
    headers = {s.name: s.geometry for s in catalog if s.geometry is not None}
    specs: list[ModelSpec] = list(catalog)
    for model in load().models:
        moe = model.architecture == MOE
        names = [model.id]
        if model.model_id is not None and model.model_id != model.id:
            names.append(model.model_id)
        header = headers.get(model.model_id or "") if moe else None
        for name in names:
            spec = _model_spec(model, moe, name=name)
            specs.append(_moe_spec(spec, header) if header is not None else spec)
    return tuple(specs)


def _catalog_specs() -> tuple[ModelSpec, ...]:
    """One `ModelSpec` per record the knowledge holds: the shipped catalogue with
    the cache over it, so a model a Hub read filed there is sized as a shipped
    one is.

    Each is sized as `mcgyvr recommend` sizes a catalog record for one user
    (`recommend._catalog_spec`, through the one catalog-slot law
    `recommend._catalog_slot_bytes`): its VRAM is the file's size plus the KV
    cache of the record's whole context padded to whole cache cells plus one
    sequence's recurrent (state-space) bytes, its disk cost the file's size
    alone. A record whose architecture is `moe` is a mixture of experts, sized
    from its file's header row (`_moe_spec`). A catalogue that cannot be read,
    or a record that cannot be sized, is reported as a broken capability table.
    """
    from mcgyvr import recommend
    from mcgyvr.knowledge import geometry as geometry_rows
    from mcgyvr.knowledge import store as knowledge_store
    from mcgyvr.knowledge.record import KnowledgeError

    try:
        records = knowledge_store.offline().records
        rows = geometry_rows.load()
    except KnowledgeError as exc:
        raise CapabilityTableError(str(exc)) from exc
    specs: list[ModelSpec] = []
    for one in records:
        spec = recommend._catalog_spec(recommend._flat(one), users=1)
        if spec is None:
            raise CapabilityTableError(
                f"{one.model_id} {one.quant}: the record states no context, KV "
                f"or recurrent figure its cache can be sized from"
            )
        if one.architecture == MOE:
            found = rows.of(one.weights)
            spec = _moe_spec(spec, found.row if found is not None else None)
        specs.append(spec)
    return tuple(specs)


def _moe_spec(spec: ModelSpec, row: Mapping[str, Any] | None) -> ModelSpec:
    """A catalog mixture of experts, sized as one: `moe` set, and the header row
    of the file its record names as the geometry placement spills expert blocks
    by.

    The row is filed under the file's Hub name; a pick lands the same bytes,
    sha256-checked, under the model id's name (`fetchlist.from_records`), which
    is the file placement serves, so the row is carried under that name. That
    rename takes the row past `ModelSpec`'s scanned-file check; what then holds
    it to the spec's file is its size, which `ModelSpec` checks against
    `disk_gb`. With no row, or one whose size does not match (the refusal kept
    as `geometry_refused`, so placement's refusal says why the row was not
    taken), the spec is an MoE without a geometry, which placement refuses by
    name, as it refuses a capability table MoE row: an MoE whose record states
    its architecture is never sized as dense.
    """
    if row is None:
        return replace(spec, moe=True)
    served = {**row, "file": fetchlist._weights_file_name(spec.name)}
    try:
        return replace(spec, moe=True, geometry=served)
    except UnitError as exc:
        return replace(spec, moe=True, geometry_refused=str(exc))
