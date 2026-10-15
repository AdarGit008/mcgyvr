"""One primitive names a unit, a rig and a combination by what they cover.

The shape is a prefix plus the sha256 of a canonical YAML tree — so key order
is not identity and list order is.
``unt-`` a unit, ``rig-`` a machine (:func:`rig_id`, the one name a machine
has: the lock pins it, live admission compares it, and a rig's hub hears it),
``cmb-`` a combination. Every other prefix is refused, so a record written
under a retired design cannot pass for a current one.
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
    """A SafeDumper that never writes an anchor.

    Two keys sharing one default object would otherwise render as ``&id001``
    and ``*id001``, and a digest would depend on object identity inside this
    process. ``mcgyvr.config`` renders its canonical form through this too.
    """

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


#: The most of a reading's reason a refusal repeats.
_WHY_MAX = 300
_CARD_WHOLE = re.compile(r"card\.[^.]+\.[0-9]+", re.ASCII)

#: What the user can do, for each kind of field that refuses a rig id.
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
    """The rig id's policy, all of it in one place: what refuses the id, each
    with what the user can do, and the cards the id is hashed over.

    A card the reading names in ``unsized`` whose size is unread (no card tool
    installed there reads its vendor, and its sysfs entry publishes no size: a
    management adapter, an integrated one, a virtual display) is left out; a
    machine whose every card is such is named as a machine with no card. Any
    other card refuses the id when its name or size was not read, is named
    unread, or is not a value a reading takes. A machine id that is not 16 hex
    or is named unread refuses it, and so do a card source that failed or may
    be short and a card the reader dropped. The reading may come from another
    machine, so nothing in it is taken on trust: every value is checked here
    by the reader's own rules (:mod:`mcgyvr.serving.rigscan`).
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
    """``rig-`` = H{ machine id, [(card name, total MiB) for every card] }.

    ``reading`` is :mod:`mcgyvr.serving.rigscan`'s document, of this machine or
    of another. The cards are sorted by name, then size, so their indexes and
    their order, which a card tool may change, do not move the id; two equal
    cards are both in it. A name is taken in Unicode normal form C. A reading
    the policy (:func:`_policy`) finds anything in is refused by name, with the
    reason the reading gave and what the user can do: an id is never hashed
    over a field that was not read, nor over a list of cards that a source it
    asked names as short.

    Nothing else is in the id. The kernel, the driver, docker, the CPU's clock
    and power limits stay in the reading and in the rig file, and the door's
    gates compare them there (:func:`mcgyvr.serving.rigfile.moved`): a driver
    upgrade is a machine that changed, said by the gate, not a new machine.
    """
    refused, cards = _policy(reading)
    if refused:
        # A reason may come from another machine: it is made printable and
        # bounded before it reaches a terminal.
        why: dict[str, str] = {}
        for item in _listed(reading.get("unread")):
            if isinstance(item, Mapping):
                said = "".join(
                    c if c.isprintable() else " " for c in str(item.get("why"))
                )
                why.setdefault(str(item.get("field")), said.strip()[:_WHY_MAX])
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
    )
    machine = reading["machine"]
    return digest(
        "rig-",
        {
            "machine_id": str(machine["id"]),
            "cards": [{"name": name, "total_mib": total} for name, total in pairs],
        },
    )
