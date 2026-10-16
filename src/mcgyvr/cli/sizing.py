"""Model and host sizing shared across ladder and setup commands."""

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
    """Every machine recorded as a rig file, keyed by the name it calls itself
    and by its rig name.

    The name it calls itself is ``platform.node()``, which is not the name a
    unit's ``address`` carries; :func:`_resolve_hosts` is what bridges the two.
    The rig name is what the user's ssh names it, which a unit's address often
    does carry. Keying by both — never by an invented name — keeps this a
    faithful reading of the folder, and the reconciliation is somewhere a
    reader can find it and argue with it.

    A record that cannot be read is skipped rather than fatal, on the same rule
    the rest of the scan layer runs on: the answer to an unreadable record is
    to read the machine again, and that is what ``_emit``'s never-scanned
    refusal asks for anyway.
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
    """Which machine each rung would run on — rung name to host."""
    wanted: dict[str, str] = {}
    for name in config.ladder.names:
        unit = config.units.get(name)
        if unit is None:
            raise UnitError(f"{name}: no unit named {name!r}")
        wanted[name] = host_of(unit.address)
    return wanted


_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _names_this_machine(name: str) -> bool:
    """Whether ``name`` can only ever mean the machine this process runs on.

    ``0.0.0.0`` counts. It is not a loopback address, but nothing else can be
    reached at it either: written in a unit's ``address`` it means "the server I am
    about to start here, on every interface", which is a statement about this
    machine.
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
    """Whether two hostnames are one machine written long and short.

    ``desktop-9`` and ``desktop-9.lan`` are the same rig: a config names it the
    way the operator types it, and ``platform.node()`` reports it the way the
    machine was configured. Only a whole leading label counts, so ``rig`` does
    not match ``rigel.lan`` — the failure this must never have is two different
    machines treated as one, because that sizes a unit from the wrong rig's
    free VRAM and the compose file it writes looks entirely reasonable.
    """
    left = recorded.strip().lower().rstrip(".")
    right = wanted.strip().lower().rstrip(".")
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


def _resolve_hosts(scans: dict[str, Scan], wanted: Iterable[str]) -> dict[str, Scan]:
    """``scans`` again, with a key added for each wanted name that resolves to
    a machine already in it.

    Without this, ``emit`` refuses the machine it is running on whenever a
    config spells it otherwise than its record does. ``mcgyvr scan`` records
    this machine as ``localhost`` (and :func:`_scans` keys it by the name
    ``platform.node()`` gives it too), but a config may say
    ``http://127.0.0.1:8080`` or ``http://0.0.0.0:8080`` — so the most ordinary
    setup there is, one rig serving itself, would report "never been scanned"
    the instant after it was scanned.

    Resolution is by identity rather than by name wherever it can be: a
    loopback source is matched to the local scan through
    :func:`mcgyvr.scan.local_machine_id`, so it stays right on a machine that
    was renamed and cannot be fooled by a second rig that happens to answer to
    the same hostname. Only the long/short form of a real hostname is matched
    by string, and only when exactly one recorded machine answers to it:
    an ambiguous name resolves to nothing and falls through to the refusal,
    because being told to run `mcgyvr scan` costs a minute and being sized
    against another machine's hardware costs a debugging session.
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
    """The recorded scan of this very machine, or None if it has never run one."""
    for recorded in scans.values():
        if recorded.machine.id == os_machine_id:
            return recorded
    return None


def _named_scan(scans: dict[str, Scan], name: str) -> Scan | None:
    """The one recorded machine ``name`` names, or None if it is not exactly one.

    Two records answering to one name is not a tie to be broken. They are two
    machines, and picking either would hand back hardware the operator did not
    ask about.
    """
    matched = [recorded for host, recorded in scans.items() if _same_host(host, name)]
    if len({recorded.machine.id for recorded in matched}) != 1:
        return None
    return matched[0]


def _model_spec(model: Model, moe: bool, name: str | None = None) -> ModelSpec:
    """One serving spec from one capability row; the table's decimal GB to GiB.

    ``name`` is the key the catalogue files the spec under, which is normally
    the row's ``id``; a row that also carries a catalog ``model_id`` is filed
    under that id too (the same measured numbers, so a unit named by its
    catalog pick resolves to this benchmarked row).
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
    """Serving specs for the rows of the shipped capability estimates.

    The shipped model catalog's own facts are folded in first, keyed by each
    entry's ``model_id``: a catalog pick the capability table does not name is
    still servable, sized from the file's bytes and its own context and KV
    figures (:func:`_catalog_specs`). Then the capability table's measured
    rows are added, keyed by BOTH their ``id`` and (when one is mapped) their
    ``model_id``, so the measured ``vram_gb_working`` wins over the computed
    catalog figure wherever the two name one model.

    ``vram_gb`` and ``disk_gb`` come off the typed reader. Whether a model has
    experts — and so a knob for *where* its weights sit — is in the table file
    but not in :class:`mcgyvr.capability.Model`, so it is read
    from the same file rather than guessed from a name. Getting it wrong is not
    cosmetic: a dense model that does not fit is a refusal, while an MoE that
    does not fit is a model that fits differently (:mod:`mcgyvr.serving`).

    ``geometry`` is ``None`` for every row because neither the table nor the
    catalog carries GGUF geometry. A dense row is therefore sized on its
    scalar figures, one slot wide; an MoE row is refused rather than sized
    (:func:`mcgyvr.serving.fit`), because ``--n-cpu-moe`` moves whole blocks
    and what each block's experts weigh is in the tensor table and nowhere
    else. An operator who has scanned the file points
    ``units.<name>.launch.geometry_json`` at the scan, and that lifts the
    refusal for the model they scanned — on the scan's numbers, not the
    table's.

    The table is in decimal GB and sizing is in GiB; the conversion happens
    here, once (:data:`mcgyvr.capability.GB_PER_GIB`).

    ``ram_gb`` is ``0.0`` for every row, dense and MoE alike. It is a floor an
    operator may raise, not a declaration this function can make: what an MoE
    actually spills depends on the card and is derived per machine by
    :func:`mcgyvr.serving._placement`.
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
    """Serving specs derived from the shipped model catalog's own facts.

    A catalog pick the capability table does not name is still servable: the
    file's bytes and the KV cache its own ``context_length`` and
    ``kv_bytes_per_token`` price give a dense scalar spec, one slot wide, with
    no GGUF geometry. ``disk_gb`` is the file's bytes in GiB; ``vram_gb`` is
    the weights plus the full-context KV cache, also in GiB, so the fit check
    no longer relies on a measured scalar that may not exist. ``moe`` and
    ``cpu_only`` are false because these rows are dense GGUF checkpoints, and
    ``geometry`` is ``None``: the catalog carries no tensor table.
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
    """``model id -> architecture`` from the shipped table, for the one field
    :mod:`mcgyvr.capability` does not carry yet."""
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
