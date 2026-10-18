"""The inputs a sizing pass runs on: fleet scans, ladder hosts, and the models to fit.

The rig files in the fleet's rigs folder supply the scans, the config's ladder
supplies the hostnames a scan may be found under, and the models come from the
shipped knowledge catalogue and from the capability table, each row turned into
a `ModelSpec` the placement code can weigh.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING

from mcgyvr import scan as scan_module
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
from mcgyvr.fleet.roots import (
    FolderError,
)
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ModelSpec,
    UnitError,
    host_of,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


def _scans() -> dict[str, Scan]:
    """Every scan the fleet's rig files record, keyed by rig name and by hostname.

    A rigs folder that cannot be resolved gives no scans, and a rig file that
    cannot be read or parsed is skipped. Both keys of one rig point at the same
    scan, so a lookup by either name finds it.
    """
    from mcgyvr.fleet.roots import rigs_dir
    from mcgyvr.serving import rigfile

    try:
        folder = rigs_dir()
    except FolderError:
        return {}
    found: dict[str, Scan] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            recorded = rigfile.from_json(path.read_text(encoding="utf-8"))
        except (OSError, rigfile.RigFileError):
            continue
        found.setdefault(recorded.rig, recorded.scan)
        if recorded.hostname:
            found.setdefault(recorded.hostname, recorded.scan)
    return found


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


_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _names_this_machine(name: str) -> bool:
    """Whether a hostname names this machine: a localhost alias, or a local IP address.

    Anything else, including a name that is not an IP address at all, is another
    host's name as far as this check can tell.
    """
    lowered = name.strip().lower().rstrip(".")
    if lowered in _LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _same_host(recorded: str, wanted: str) -> bool:
    """Whether two hostnames name one host, either being the other's full form.

    The comparison ignores case and a trailing dot; an empty name on either side
    matches nothing.
    """
    left = recorded.strip().lower().rstrip(".")
    right = wanted.strip().lower().rstrip(".")
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


def _resolve_hosts(scans: dict[str, Scan], wanted: Iterable[str]) -> dict[str, Scan]:
    """The scans, plus an entry for each wanted host that no key already names.

    A name for this machine is resolved by the id of the machine it runs on, any
    other name by the hostnames the rig files recorded. A name that finds no
    scan, or more than one machine, is left out of the result.
    """
    resolved = dict(scans)
    local: str | None = None
    for name in wanted:
        if name in resolved:
            continue
        if _names_this_machine(name):
            if local is None:
                local = scan_module.local_machine_id()
            match = _local_scan(scans, local)
        else:
            match = _named_scan(scans, name)
        if match is not None:
            resolved[name] = match
    return resolved


def _local_scan(scans: dict[str, Scan], os_machine_id: str) -> Scan | None:
    """The first scan taken on the machine with this id, else none."""
    for recorded in scans.values():
        if recorded.machine.id == os_machine_id:
            return recorded
    return None


def _named_scan(scans: dict[str, Scan], name: str) -> Scan | None:
    """The scan recorded under a hostname naming `name`, or none when ambiguous.

    Several keys can point at one scan, so the matches are counted by machine id:
    a name matching more than one machine is refused rather than guessed at.
    """
    matched = [recorded for host, recorded in scans.items() if _same_host(host, name)]
    if len({recorded.machine.id for recorded in matched}) != 1:
        return None
    return matched[0]


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
        vae_decode_gb=(model.vae_decode_gb or 0.0) / GB_PER_GIB,
        cpu_only=model.cpu_only,
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
    """One `ModelSpec` per record in the shipped knowledge catalogue.

    Its VRAM is the file's size plus the KV cache a token takes at the whole
    context the record states, its disk cost the file's size alone. A catalogue
    that cannot be read is reported as a broken capability table.
    """
    from mcgyvr.knowledge import store as knowledge_store
    from mcgyvr.knowledge.record import KnowledgeError

    try:
        records = knowledge_store.shipped()
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
                cpu_only=False,
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
