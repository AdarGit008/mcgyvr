"""Identity strings for machines, rigs and combos.

An id is an identity prefix such as ``rig-`` followed by the SHA-256 hex digest
of a canonical YAML dump of the fields that identify the thing, so the same
fields always yield the same id and different fields never collide by prose.
Prefixes not in :data:`IDENTITY_PREFIXES` are refused rather than hashed: the
retired kinds and any unknown kind raise :class:`ValueError`.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

IDENTITY_PREFIXES = frozenset({"unt-", "rig-", "cmb-"})
_RETIRED_PREFIXES = frozenset({"msp-", "rsh-", "fsh-", "cfg-", "flt-", "mch-"})


class _CanonicalDumper(yaml.SafeDumper):
    """Safe dumper that never writes anchors or aliases.

    Repeating the same object in the dumped fields therefore produces the same
    text as separate but equal objects, which is what keeps the digest
    dependent on the values alone.
    """

    def ignore_aliases(self, data: object) -> bool:
        return True


def _plain(value: Any) -> Any:
    """Copy a value into plain containers the dumper writes identically.

    Mappings become dicts keyed by ``str(key)``, non-text sequences become
    lists, and :class:`~pathlib.Path` values become strings; anything else is
    returned as it is.
    """
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_dump(fields: Any) -> str:
    """Dump fields as YAML in one fixed shape.

    Keys are sorted, collections are block style, unicode is written as itself
    and the line width is effectively unbounded, so no field is ever wrapped.
    """
    return yaml.dump(
        _plain(fields),
        Dumper=_CanonicalDumper,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
    )


def digest(prefix: str, fields: dict[str, Any]) -> str:
    """Return the identity string for fields under the given prefix.

    The canonical UTF-8 YAML dump of fields is hashed with SHA-256 and its hex
    digest is appended to prefix. A prefix that is not one of
    :data:`IDENTITY_PREFIXES` raises :class:`ValueError`, naming it as retired
    or unknown and listing the live identity kinds.
    """
    if prefix not in IDENTITY_PREFIXES:
        kind = "retired" if prefix in _RETIRED_PREFIXES else "unknown"
        raise ValueError(
            f"{kind} identity prefix {prefix!r}; identity kinds are "
            f"{', '.join(sorted(IDENTITY_PREFIXES))}"
        )
    raw = _canonical_dump(fields).encode("utf-8")
    return prefix + hashlib.sha256(raw).hexdigest()


#: Longest reason quoted back from the reader, in characters, and a field path
#: naming one whole card such as card.nvidia.0 rather than one of its attributes.
_WHY_MAX = 300
_CARD_WHOLE = re.compile(r"card\.[^.]+\.[0-9]+", re.ASCII)

#: Remedy reported for each refused field: what was not read, and what would let
#: the machine be read again.
_REMEDY_MACHINE_ID = (
    "no machine id was read: the machine needs a machine-id file or a host name "
    "the reader can read"
)
_REMEDY_NAME = (
    "the card's name was not read: see the reason. Once its source prints a "
    "name that is text, read the machine again"
)
_REMEDY_SIZE = (
    "the card's memory size was not read: see the reason. A source on the "
    "machine should give it (its vendor's card tool is installed, or sysfs "
    "publishes a size that was not taken); once it does, read the machine again"
)
_REMEDY_SIZE_TYPE = (
    "the card's memory size is not a whole number of MiB of at most 18 digits"
)
_REMEDY_CARDS = (
    "the list of cards may be short: see the reason. Once the tool answers, "
    "read the machine again; a tool left over on a machine with no card of its "
    "vendor can be removed"
)
_REMEDY_READING = (
    "a card of the reading was not taken: see the reason. A reading this "
    "cannot take whole gets no id"
)


def _listed(value: object) -> list[Any]:
    return list(value) if isinstance(value, list | tuple) else []


def _policy(reading: Mapping[str, Any]) -> tuple[list[tuple[str, str]], list[Any]]:
    """Decide which fields of a reading can be hashed into a rig id.

    A field is refused, paired with its remedy, when the machine id is not a
    machine id or was not read, when a card's name has a problem or was not
    read, when a card's size was not read or is not a whole number of MiB, when
    the list of cards may be short, and when an unread field names a card or the
    reading as a whole. Cards whose vendor source publishes no size at all are
    neither refused nor kept; the second return value holds the cards that were
    kept, in the order the reading lists them.
    """
    from mcgyvr.serving import rigscan

    found: list[tuple[str, str]] = []
    unread = [u for u in _listed(reading.get("unread")) if isinstance(u, Mapping)]
    named = {str(u.get("field")) for u in unread}
    unsized = {str(key) for key in _listed(reading.get("unsized"))}
    machine = reading.get("machine")
    machine_id = machine.get("id") if isinstance(machine, Mapping) else None
    if not rigscan.is_machine_id(machine_id) or "machine_id" in named:
        found.append(("machine_id", _REMEDY_MACHINE_ID))
    kept: list[Any] = []
    for card in _listed(reading.get("cards")):
        if not isinstance(card, Mapping):
            found.append(("reading", _REMEDY_READING))
            continue
        key = f"card.{card.get('vendor')}.{card.get('index')}"
        total = card.get("total_mib")
        if key in unsized and total is None:
            continue
        if rigscan.name_problem(card.get("name")) or f"{key}.name" in named:
            found.append((f"{key}.name", _REMEDY_NAME))
        if total is None or f"{key}.total" in named:
            found.append((f"{key}.total", _REMEDY_SIZE))
        elif not rigscan.is_size(total):
            found.append((f"{key}.total", _REMEDY_SIZE_TYPE))
        kept.append(card)
    for item in unread:
        field = str(item.get("field"))
        if field.startswith("cards"):
            found.append((field, _REMEDY_CARDS))
        elif field == "reading" or _CARD_WHOLE.fullmatch(field):
            found.append((field, _REMEDY_READING))
    return found, kept


def rig_id(reading: Mapping[str, Any]) -> str:
    """Return the ``rig-`` id of a reading, or refuse to make one.

    If :func:`_policy` refuses any field, the reading is not hashed at all and
    :class:`ValueError` is raised naming each refused field with the reader's
    reason for it, when the reading gives one, and its remedy. Otherwise the
    id is the digest of the machine id and the cards' names and sizes, with the
    cards sorted by normalized name and size and the names normalized to NFC.

    A unified-memory GPU (a card of kind ``unified``) is hashed by its name
    alone, under its own key: its size is the share of memory the kernel lets
    it take, which a setting moves and a reboot resets, and a machine whose
    setting moved is the same machine. A reading with no such card hashes
    exactly as it did before the kind existed.
    """
    refused, cards = _policy(reading)
    if refused:
        # Flatten each field's reason to printable text, keep the first one, clip it.
        why: dict[str, str] = {}
        for item in _listed(reading.get("unread")):
            if isinstance(item, Mapping):
                said = "".join(
                    c if c.isprintable() else " " for c in str(item.get("why"))
                )
                why.setdefault(str(item.get("field")), said.strip()[:_WHY_MAX])
        # Name each refused field with its reason when given, then its remedy.
        said = "; ".join(
            f"{field} ({why[field]}; {remedy})"
            if field in why
            else f"{field} ({remedy})"
            for field, remedy in dict(refused).items()
        )
        raise ValueError(
            f"the reading does not read {said}, and a rig id is never hashed over "
            "a field that was not read"
        )
    pairs = sorted(
        (unicodedata.normalize("NFC", str(card["name"])), int(card["total_mib"]))
        for card in cards
        if card.get("kind") != "unified"
    )
    unified = sorted(
        unicodedata.normalize("NFC", str(card["name"]))
        for card in cards
        if card.get("kind") == "unified"
    )
    machine = reading["machine"]
    fields: dict[str, Any] = {
        "machine_id": str(machine["id"]),
        "cards": [{"name": name, "total_mib": total} for name, total in pairs],
    }
    if unified:
        fields["unified"] = unified
    return digest("rig-", fields)
