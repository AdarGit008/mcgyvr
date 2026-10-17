""

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

if TYPE_CHECKING:  #
    pass


def _scans() -> dict[str, Scan]:
    ""
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
    ""
    wanted: dict[str, str] = {}
    for name in config.ladder.names:
        unit = config.units.get(name)
        if unit is None:
            raise UnitError(f"{name}: no unit named {name!r}")
        wanted[name] = host_of(unit.address)
    return wanted


_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _names_this_machine(name: str) -> bool:
    ""
    lowered = name.strip().lower().rstrip(".")
    if lowered in _LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _same_host(recorded: str, wanted: str) -> bool:
    ""
    left = recorded.strip().lower().rstrip(".")
    right = wanted.strip().lower().rstrip(".")
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


def _resolve_hosts(scans: dict[str, Scan], wanted: Iterable[str]) -> dict[str, Scan]:
    ""
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
    ""
    for recorded in scans.values():
        if recorded.machine.id == os_machine_id:
            return recorded
    return None


def _named_scan(scans: dict[str, Scan], name: str) -> Scan | None:
    ""
    matched = [recorded for host, recorded in scans.items() if _same_host(host, name)]
    if len({recorded.machine.id for recorded in matched}) != 1:
        return None
    return matched[0]


def _model_spec(model: Model, moe: bool, name: str | None = None) -> ModelSpec:
    ""
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
    ""
    specs: list[ModelSpec] = list(_catalog_specs())
    architectures = _architectures()
    for model in load().models:
        moe = architectures.get(model.id) == "moe"
        specs.append(_model_spec(model, moe))
        if model.model_id is not None and model.model_id != model.id:
            specs.append(_model_spec(model, moe, name=model.model_id))
    return tuple(specs)


def _catalog_specs() -> tuple[ModelSpec, ...]:
    ""
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
    ""
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
