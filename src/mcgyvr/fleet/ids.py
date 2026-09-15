"""One primitive names a unit, a rig and a combination by what they cover.

The shape is a prefix plus the sha256 of a canonical YAML tree — so key order
is not identity and list order is.
``unt-`` a unit, ``rig-`` a rig, ``cmb-`` a combination. Every other prefix is
refused, so a record written under a retired design cannot pass for a current
one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

IDENTITY_PREFIXES = frozenset({"unt-", "rig-", "cmb-"})
_RETIRED_PREFIXES = frozenset({"msp-", "rsh-", "fsh-", "cfg-", "flt-"})


class _CanonicalDumper(yaml.SafeDumper):
    """A SafeDumper that never writes an anchor (see ``mcgyvr.config``)."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _plain(value: Any) -> Any:
    """``value`` as plain dicts, lists and scalars, for a canonical dump."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_dump(fields: Any) -> str:
    """The canonical YAML text for ``fields``, independent of key order."""
    return yaml.dump(
        _plain(fields),
        Dumper=_CanonicalDumper,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
    )


def digest(prefix: str, fields: dict[str, Any]) -> str:
    """``prefix`` plus the sha256 of a canonical dump of ``fields``."""
    if prefix not in IDENTITY_PREFIXES:
        kind = "retired" if prefix in _RETIRED_PREFIXES else "unknown"
        raise ValueError(
            f"{kind} identity prefix {prefix!r}; identity kinds are "
            f"{', '.join(sorted(IDENTITY_PREFIXES))}"
        )
    raw = _canonical_dump(fields).encode("utf-8")
    return prefix + hashlib.sha256(raw).hexdigest()


#: A rig's hardware, as ``rig-snapshot.sh`` names each reading.
RIG_HARDWARE: tuple[str, ...] = (
    "cpu_model",
    "cpu_max_mhz",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "gpu_name",
    "gpu_vram_mib",
    "gpu_cc",
)
#: A rig's system, as ``rig-snapshot.sh`` names each reading.
RIG_SYSTEM: tuple[str, ...] = ("os_machine_id", "kernel", "driver", "docker")


def rig_id(snapshot: Mapping[str, str]) -> str:
    """``rig-`` = H{ host, hardware, system } over one ``rig-snapshot.sh`` reading.

    Owner, 2026-09-15 (D1): the values are hashed exactly as the snapshot prints
    them — tokenized strings, ``host`` its ``hostname=`` — and nowhere else is a
    rig id spelled, so the lock and live admission name a rig the same way. A
    reading missing a field is refused by name and never hashed
    (``records/plans/fleet-identity.md`` §1, ID-1).
    """
    wanted = ("hostname", *RIG_HARDWARE, *RIG_SYSTEM)
    missing = [key for key in wanted if not str(snapshot.get(key) or "").strip()]
    if missing:
        raise ValueError(
            f"the rig snapshot does not read {', '.join(missing)}, and a rig id "
            "is never hashed over a field that was not read"
        )
    return digest(
        "rig-",
        {
            "host": str(snapshot["hostname"]),
            "hardware": {key: str(snapshot[key]) for key in RIG_HARDWARE},
            "system": {key: str(snapshot[key]) for key in RIG_SYSTEM},
        },
    )
