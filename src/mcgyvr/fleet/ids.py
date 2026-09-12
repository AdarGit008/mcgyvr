"""One primitive names a unit, a rig and a combination by what they cover.

The shape is :meth:`mcgyvr.config.Config.digest` — a prefix plus the sha256 of
a canonical YAML tree — so key order is not identity and list order is.
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
