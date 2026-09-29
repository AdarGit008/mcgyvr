"""A machine's short reading, and the short id that names the machine.

``gate-scripts/machine-read.sh`` reads a machine as an ordinary user, on any
vendor: its machine id, its host name, every card with its name and memory and
the processes holding it, and the running containers. :func:`parse` turns what
it prints into a :class:`Reading`; :func:`short_id` names the machine from it.

The shape of :class:`Reading` is what later readers of it rely on (the lock
evidence, the rows filed from a read, the machine declaration): every field is
named here, and a field is added, never renamed. The reading holds figures per
card only. Nothing in it sums the cards or picks one of them, so a machine of
several cards is never read as its first.

What the reader prints is untrusted: it comes from another machine, and parts
of it from tools there. :func:`parse` never raises. A value that is not what
its field allows is left ``None`` and listed in :attr:`Reading.unread` with a
reason, and so is a value the reader itself named as unread. A ``None`` field
of a card is always listed there, keyed ``card.<vendor>.<index>.<field>``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from mcgyvr.fleet import ids

#: The identity prefix of a machine's short id.
SHORT_ID_PREFIX = "mch-"

#: The longest name taken; the reader names a longer one unread.
NAME_MAX = 256

_DIGITS = re.compile(r"[0-9]{1,18}", re.ASCII)
_INDEX = re.compile(r"[0-9]{1,9}", re.ASCII)
_HEX16 = re.compile(r"[0-9a-f]{16}", re.ASCII)
_HOST = re.compile(r"[A-Za-z0-9._-]{1,253}", re.ASCII)
_VENDOR = re.compile(r"[a-z0-9][a-z0-9-]{0,31}", re.ASCII)
_SOURCE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}", re.ASCII)
_FIELD = re.compile(r"[A-Za-z0-9_.:@-]{1,200}", re.ASCII)
_ID_FROM = re.compile(r"hostname|/[A-Za-z0-9/._-]{1,200}", re.ASCII)
_TOKEN = re.compile(r"[^\s,]{1,256}")
_WHY_MAX = 300


@dataclass(frozen=True, kw_only=True)
class Holder:
    """A process holding memory on a card.

    ``name`` and ``mib`` are ``None`` when they could not be read.
    """

    pid: int
    name: str | None
    mib: int | None


@dataclass(frozen=True, kw_only=True)
class Card:
    """One card, known by its vendor and its index as its source numbers it.

    Sizes are in MiB. ``holders`` is ``None`` when the processes on the card
    could not be read, and ``()`` when none holds it. Every ``None`` here is
    named in :attr:`Reading.unread`.
    """

    vendor: str
    index: int
    name: str | None
    total_mib: int | None
    used_mib: int | None
    free_mib: int | None
    holders: tuple[Holder, ...] | None

    @property
    def key(self) -> str:
        """``card.<vendor>.<index>``, the prefix of this card's unread fields."""
        return f"card.{self.vendor}.{self.index}"


@dataclass(frozen=True, kw_only=True)
class Container:
    """A running container, as the unit reader lists it.

    ``project`` is ``None`` for a container of no compose project; ``restarts``
    is ``None`` when its restart count could not be read.
    """

    name: str
    id: str
    project: str | None
    restarts: int | None


@dataclass(frozen=True, kw_only=True)
class Unread:
    """A field that could not be read, and why."""

    field: str
    why: str


@dataclass(frozen=True, kw_only=True)
class Reading:
    """One short reading of a machine.

    ``machine_id`` is the machine's id as the reader derives it, and
    ``machine_id_from`` what it was derived from (a machine-id file's path, or
    ``hostname``). ``card_sources`` are the sources that gave a card, in the
    order the reader asked them; empty when none did. ``cards`` are sorted by
    vendor, then index. ``containers`` is ``None`` when they could not be
    listed. ``unread`` names every field that could not be read.
    """

    machine_id: str | None
    machine_id_from: str | None
    host: str | None
    card_sources: tuple[str, ...]
    cards: tuple[Card, ...]
    containers: tuple[Container, ...] | None
    unread: tuple[Unread, ...]


class _Parse:
    """The state of one :func:`parse`."""

    def __init__(self) -> None:
        self.single: dict[str, list[str]] = {}
        self.sources: list[str] | None = None
        self.cards: dict[tuple[str, int], Card] = {}
        self.twice: set[tuple[str, int]] = set()
        self.holders: dict[tuple[str, int], list[Holder]] = {}
        self.containers: list[Container] = []
        self.said: list[Unread] = []
        self.found: list[Unread] = []

    def note(self, field: str, why: str) -> None:
        self.found.append(Unread(field=field, why=why))

    def line(self, number: int, key: str, value: str) -> None:
        if key in ("machine_id", "machine_id_from", "host"):
            self.single.setdefault(key, []).append(value)
        elif key == "cards":
            self._sources(number, value)
        elif key == "card":
            self._card(number, value)
        elif key == "holder":
            self._holder(number, value)
        elif key == "container":
            self._container(number, value)
        elif key == "unread":
            self._unread(number, value)
        else:
            self.note("reading", f"line {number}: not a line the machine reader prints")

    def _sources(self, number: int, value: str) -> None:
        if self.sources is not None:
            self.note("cards", f"line {number}: the card sources are printed twice")
            return
        if value == "none":
            self.sources = []
            return
        names = value.split(",")
        if not all(_SOURCE.fullmatch(name) for name in names):
            self.note("cards", f"line {number}: the card sources are not source names")
            self.sources = []
            return
        self.sources = names

    def _card(self, number: int, value: str) -> None:
        parts = value.split(",", 5)
        if len(parts) != 6:
            self.note("reading", f"line {number}: a card line without six fields")
            return
        vendor, index, total, used, free, name = parts
        if not _VENDOR.fullmatch(vendor) or not _INDEX.fullmatch(index):
            self.note(
                "reading", f"line {number}: a card line without a vendor and index"
            )
            return
        where = (vendor, int(index))
        if where in self.cards or where in self.twice:
            self.cards.pop(where, None)
            self.twice.add(where)
            return
        key = f"card.{vendor}.{int(index)}"
        self.cards[where] = Card(
            vendor=vendor,
            index=int(index),
            name=self._name(name, f"{key}.name"),
            total_mib=self._mib(total, f"{key}.total"),
            used_mib=self._mib(used, f"{key}.used"),
            free_mib=self._mib(free, f"{key}.free"),
            holders=None,
        )

    def _holder(self, number: int, value: str) -> None:
        parts = value.split(",", 4)
        if len(parts) != 5 or not _VENDOR.fullmatch(parts[0]):
            self.note("reading", f"line {number}: a holder line without five fields")
            return
        vendor, index, pid, mib, name = parts
        if not _INDEX.fullmatch(index) or not _INDEX.fullmatch(pid):
            self.note("reading", f"line {number}: a holder line without a card and pid")
            return
        key = f"card.{vendor}.{int(index)}.holder.{int(pid)}"
        holder = Holder(
            pid=int(pid),
            name=self._name(name, f"{key}.name"),
            mib=self._mib(mib, f"{key}.mib"),
        )
        self.holders.setdefault((vendor, int(index)), []).append(holder)

    def _container(self, number: int, value: str) -> None:
        parts = value.split(",")
        if len(parts) != 4 or not all(
            _TOKEN.fullmatch(part) and _is_text(part) for part in parts
        ):
            self.note(
                "containers", f"line {number}: a container line without four fields"
            )
            return
        name, cid, project, restarts = parts
        count = int(restarts) if _DIGITS.fullmatch(restarts) else None
        if count is None:
            self.note(f"container.{cid}.restarts", "the restart count is unread")
        self.containers.append(
            Container(
                name=name,
                id=cid,
                project=None if project == "-" else project,
                restarts=count,
            )
        )

    def _unread(self, number: int, value: str) -> None:
        field, _, why = value.partition(",")
        if not _FIELD.fullmatch(field):
            self.note("reading", f"line {number}: an unread line naming no field")
            return
        why = "".join(c if c.isprintable() else " " for c in why).strip()
        self.said.append(Unread(field=field, why=why[:_WHY_MAX] or "no reason given"))

    def _mib(self, value: str, field: str) -> int | None:
        if value == "":
            return None
        if _DIGITS.fullmatch(value):
            return int(value)
        self.note(field, "the value printed is not a whole number of MiB")
        return None

    def _name(self, value: str, field: str) -> str | None:
        if value == "":
            return None
        if len(value) > NAME_MAX:
            self.note(field, f"the name printed is longer than {NAME_MAX} characters")
            return None
        if not _is_text(value) or value != value.strip():
            self.note(field, "the name printed holds characters a name does not")
            return None
        return value


def _is_text(value: str) -> bool:
    """No control, format, private, unassigned or line-breaking character."""
    return all(
        unicodedata.category(c)[0] != "C"
        and unicodedata.category(c) not in ("Zl", "Zp")
        for c in value
    )


def parse(text: str) -> Reading:
    """The reading in ``text``, as ``machine-read.sh`` prints it. Never raises."""
    state = _Parse()
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.removesuffix("\r")
        if not line.strip():
            continue
        key, equals, value = line.partition("=")
        if not equals:
            state.note(
                "reading", f"line {number}: not a line the machine reader prints"
            )
            continue
        state.line(number, key, value)

    single: dict[str, str | None] = {}
    checks = {"machine_id": _HEX16, "machine_id_from": _ID_FROM, "host": _HOST}
    for key, pattern in checks.items():
        values = state.single.get(key, [])
        if len(values) > 1:
            state.note(key, "the reader printed it more than once")
            single[key] = None
        elif not values or values[0] == "":
            single[key] = None
        elif pattern.fullmatch(values[0]):
            single[key] = values[0]
        else:
            state.note(key, "the value printed is not one this field takes")
            single[key] = None

    for vendor, index in state.twice:
        state.note(f"card.{vendor}.{index}", "the reader printed this card twice")
    unread_by_reader = {u.field for u in state.said}
    cards: list[Card] = []
    for where in sorted(state.cards):
        card = state.cards[where]
        listed = state.holders.pop(where, [])
        if f"{card.key}.holders" in unread_by_reader:
            if listed:
                state.note(
                    f"{card.key}.holders",
                    "holders are printed for a card "
                    "whose processes the reader named unread",
                )
            cards.append(card)
        else:
            cards.append(_with_holders(card, tuple(listed)))
    for vendor, index in state.holders:
        state.note(
            "reading",
            f"holders are printed for card.{vendor}.{index}, "
            "which the reading does not hold",
        )

    sources = state.sources
    if sources is None:
        state.note("cards", "the reader printed no card sources")
        sources = []
    elif not sources and cards:
        state.note("cards", "the reader printed cards and said it found none")

    containers: tuple[Container, ...] | None = tuple(state.containers)
    if "containers" in unread_by_reader:
        containers = None

    reading = Reading(
        machine_id=single["machine_id"],
        machine_id_from=single["machine_id_from"],
        host=single["host"],
        card_sources=tuple(sources),
        cards=tuple(cards),
        containers=containers,
        unread=(),
    )
    return _named(reading, [*state.said, *state.found])


def _with_holders(card: Card, holders: tuple[Holder, ...]) -> Card:
    return Card(
        vendor=card.vendor,
        index=card.index,
        name=card.name,
        total_mib=card.total_mib,
        used_mib=card.used_mib,
        free_mib=card.free_mib,
        holders=holders,
    )


def _named(reading: Reading, unread: list[Unread]) -> Reading:
    """``reading`` with every ``None`` field named in its unread list, once."""
    named = {u.field for u in unread}

    def need(field: str, value: object) -> None:
        if value is None and field not in named:
            unread.append(
                Unread(field=field, why="the reader printed no value and no reason")
            )
            named.add(field)

    need("machine_id", reading.machine_id)
    need("host", reading.host)
    need("containers", reading.containers)
    for card in reading.cards:
        need(f"{card.key}.name", card.name)
        need(f"{card.key}.total", card.total_mib)
        need(f"{card.key}.used", card.used_mib)
        need(f"{card.key}.free", card.free_mib)
        need(f"{card.key}.holders", card.holders)
        for holder in card.holders or ():
            need(f"{card.key}.holder.{holder.pid}.name", holder.name)
            need(f"{card.key}.holder.{holder.pid}.mib", holder.mib)
    seen: set[tuple[str, str]] = set()
    kept = []
    for item in unread:
        if (item.field, item.why) not in seen:
            seen.add((item.field, item.why))
            kept.append(item)
    return Reading(
        machine_id=reading.machine_id,
        machine_id_from=reading.machine_id_from,
        host=reading.host,
        card_sources=reading.card_sources,
        cards=reading.cards,
        containers=reading.containers,
        unread=tuple(kept),
    )


_CARD_WHOLE = re.compile(r"card\.[^.]+\.[0-9]+", re.ASCII)


def short_id(reading: Reading) -> str:
    """``mch-`` = H{ machine id, [(card name, total MiB) for every card] }.

    The cards are taken in the reading's order (by vendor, then index). A
    reading that could not read the machine id, a card's name or size, or a
    card source is refused by name: an id is never hashed over a field that
    was not read, nor over a list of cards that may be short.
    """
    missing: list[str] = []
    if reading.machine_id is None:
        missing.append("machine_id")
    for card in reading.cards:
        if card.name is None:
            missing.append(f"{card.key}.name")
        if card.total_mib is None:
            missing.append(f"{card.key}.total")
    for item in reading.unread:
        if (
            item.field in ("cards", "reading")
            or item.field.startswith("cards.")
            or _CARD_WHOLE.fullmatch(item.field)
        ):
            missing.append(item.field)
    if missing:
        why = {u.field: u.why for u in reading.unread}
        said = "; ".join(
            f"{field} ({why[field]})" if field in why else field
            for field in dict.fromkeys(missing)
        )
        raise ValueError(
            f"the reading does not read {said}, and a machine's short id is never "
            "hashed over a field that was not read"
        )
    return ids.digest(
        SHORT_ID_PREFIX,
        {
            "machine_id": reading.machine_id,
            "cards": [
                {"name": card.name, "total_mib": card.total_mib}
                for card in reading.cards
            ],
        },
    )
