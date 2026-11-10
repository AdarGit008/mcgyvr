"""The inputs a sizing pass runs on: fleet scans, ladder hosts, and the models to fit.

The rig files in the fleet's rigs folder supply the scans (through
`mcgyvr.serving.rigfile.recorded_scans` and `resolve_hosts`), the config's ladder
supplies the hostnames a scan may be found under, and the models come from the
shipped knowledge catalogue and from the capability table, each row turned into
a `ModelSpec` the placement code can weigh.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    for model in load().models:
        moe = model.architecture == MOE
        specs.append(_model_spec(model, moe))
        if model.model_id is not None and model.model_id != model.id:
            specs.append(_model_spec(model, moe, name=model.model_id))
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
    alone. A catalogue that cannot be read, or a record that cannot be sized,
    is reported as a broken capability table.
    """
    from mcgyvr import recommend
    from mcgyvr.knowledge import store as knowledge_store
    from mcgyvr.knowledge.record import KnowledgeError

    try:
        records = knowledge_store.offline().records
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
        specs.append(spec)
    return tuple(specs)
