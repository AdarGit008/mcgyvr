"""What a link between two cards carries, and whose word for it is used.

A model split across cards pays for the traffic between them, and that cost is
set by the link, not by the model: two cards in one machine talk over its bus,
two machines over the network (:mod:`mcgyvr.fleet.links` classes a link by what
any machine has, never by a machine's name). mcgyvr cannot read a link off a
machine it has not been shown, so each class starts from an estimate shipped
with mcgyvr (``link_gib_s`` and ``link_latency_us`` in :mod:`mcgyvr.derived`),
and gives way, in this order, to

1. the user's own setting of either number in ``numbers.yaml`` (derived's
   override layer: the user's word always answers first);
2. the user's own reading of their link, kept in the data folder
   (:func:`readings_path`) by :func:`read_link` and used from then on;
3. the estimate shipped with mcgyvr, which says it is one.

The two numbers are layered one at a time: if the user's file sets only the
bandwidth, the latency comes from the next layer down, and the :class:`Link`
says so. A reading is of one pair of cards and is kept for the class of that
pair: it replaces the estimate for every link of that class, because the
estimate it replaces was for the class, not for a pair.

Nothing here touches a machine. The timed transfers come from a reader the
caller passes in; this module only fits a line to them, keeps what the fit says,
and answers.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr import derived
from mcgyvr.fleet import links, roots

#: The readings file's name, in the user's data folder.
READINGS_FILENAME = "links.json"
#: The shape of the readings file this code reads, stated as its ``schema``.
READINGS_SCHEMA = 1
#: How many bytes make one GiB, and how many microseconds one second.
_BYTES_PER_GIB = 2**30
_MICROSECONDS_PER_SECOND = 1_000_000.0

#: Which layer answered, strongest first.
OVERRIDE = "override"
READING = "reading"
ESTIMATE = "estimate"
_LAYERS: tuple[str, ...] = (OVERRIDE, READING, ESTIMATE)

#: One timed transfer: how many payload bytes moved, and how many seconds it took.
Transfer = tuple[int, float]
#: What times a link: given the two hosts, the timed transfers between them.
#: The reader is the caller's; this module never opens a connection.
LinkReader = Callable[[str, str], Sequence[Transfer]]


class InterconnectError(Exception):
    """A link cannot be answered, read, fitted or recorded, and why."""


def readings_path() -> Path:
    """The user's readings of their own links: ``links.json`` in the data folder.

    Fleet readings the product needs belong in the user's data folder, not the
    config folder, which holds only what the user writes themselves.
    """
    return roots.data_home() / READINGS_FILENAME


@dataclass(frozen=True)
class Link:
    """One class of link: its bandwidth and latency, and whose word they are.

    ``source`` is the weakest layer either number came from (``override`` only
    when the user's file sets both, ``reading`` when neither is an estimate), and
    ``where`` the file of that layer. ``gib_s_source`` and ``latency_us_source``
    say each number's own layer; empty means ``source``.
    """

    link_class: str
    gib_s: float
    latency_us: float
    source: str
    where: Path
    gib_s_source: str = ""
    latency_us_source: str = ""

    def _layer(self, layer: str) -> str:
        """``layer`` in words, with the file that holds it."""
        if layer == OVERRIDE:
            return f"your own setting in {derived.overrides_path()}"
        if layer == READING:
            return f"your own reading in {readings_path()}"
        return f"an estimate shipped with mcgyvr in {self.where}"

    def says(self) -> str:
        """One line: the class, both values with units, and which layer gave them.

        An estimate says that it is one, that the first reading of the user's
        own link replaces it, and where the user can set their own value now.
        """
        bandwidth = self.gib_s_source or self.source
        latency = self.latency_us_source or self.source
        gib = f"{self.gib_s:g} GiB/s"
        lag = f"{self.latency_us:g} microseconds"
        if bandwidth == latency:
            line = f"{self.link_class} link: {gib} and {lag}, {self._layer(bandwidth)}"
        else:
            line = (
                f"{self.link_class} link: {gib}, {self._layer(bandwidth)}; "
                f"{lag}, {self._layer(latency)}"
            )
        if ESTIMATE in (bandwidth, latency):
            line += (
                f". An estimate is not a reading of your link: the first reading "
                f"of your own {self.link_class} link replaces it, and until then "
                f"you can set {derived.LINK_GIB_S} and {derived.LINK_LATENCY_US} "
                f"for {self.link_class!r} in {derived.overrides_path()}"
            )
        return line


def _positive(value: object, what: str, where: Path) -> float:
    """``value`` as a float when it is a finite number above 0, else refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InterconnectError(f"{what} in {where} is {value!r}, not a number")
    try:
        number = float(value)
    except OverflowError:
        raise InterconnectError(
            f"{what} in {where} is a whole number too large to be a float"
        ) from None
    if not math.isfinite(number) or number <= 0.0:
        raise InterconnectError(
            f"{what} in {where} is {value!r}; it must be finite and above 0"
        )
    return number


def _words(value: object, what: str, where: Path) -> str:
    """``value`` when it is text with something in it, else refused."""
    if not isinstance(value, str) or not value.strip():
        raise InterconnectError(f"{what} in {where} must be words, not {value!r}")
    return value


def _hosts(value: object, where: Path) -> list[str]:
    """The two hosts a reading was taken between, else refused."""
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(isinstance(host, str) and host.strip() for host in value)
    ):
        raise InterconnectError(
            f"'between' in {where} must name the two hosts the reading was taken "
            f"between, not {value!r}"
        )
    return list(value)


def _checked(name: str, reading: object, where: Path) -> dict[str, Any]:
    """One class's reading as the file keeps it, refused by name when it is not one."""
    if name not in links.LINK_CLASSES:
        raise InterconnectError(
            f"{where} holds a reading for {name!r}, which is not a class of link "
            f"({', '.join(links.LINK_CLASSES)})"
        )
    if not isinstance(reading, dict):
        raise InterconnectError(f"the {name} reading in {where} is not an object")
    return {
        "gib_s": _positive(reading.get("gib_s"), f"{name} gib_s", where),
        "latency_us": _positive(reading.get("latency_us"), f"{name} latency_us", where),
        "how": _words(reading.get("how"), f"{name} how", where),
        "at": _words(reading.get("at"), f"{name} at", where),
        "between": _hosts(reading.get("between"), where),
    }


def _read_readings(where: Path) -> dict[str, dict[str, Any]]:
    """The readings file's ``links`` object, checked; ``{}`` when no file is there.

    A file that is not there is no reading. Every other failure is refused by
    name with the file's path: unreadable, not UTF-8, not JSON, not an object of
    this schema, a class outside :data:`mcgyvr.fleet.links.LINK_CLASSES`, or a
    reading without finite positive values or the words that say how, when and
    between what it was taken. A file mcgyvr cannot read is never read as "no
    reading", because the estimate would then answer for a link the user has
    measured.
    """
    try:
        text = where.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return {}
    except OSError as exc:
        raise InterconnectError(
            f"cannot read your link readings from {where}: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise InterconnectError(f"{where} is not UTF-8 text: {exc}") from exc
    try:
        document = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise InterconnectError(
            f"{where} is not valid JSON, so your link readings cannot be read: "
            f"{exc}; fix or delete the file, and read the link again"
        ) from exc
    if not isinstance(document, dict) or document.get("schema") != READINGS_SCHEMA:
        raise InterconnectError(
            f"{where} is not a link readings file of schema {READINGS_SCHEMA} "
            '(an object with "schema" and "links"); fix or delete it'
        )
    by_class = document.get("links")
    if not isinstance(by_class, dict):
        raise InterconnectError(f'{where} has no "links" object; fix or delete it')
    return {name: _checked(name, reading, where) for name, reading in by_class.items()}


def link(link_class: str) -> Link:
    """The link of ``link_class``, each number from the first layer that states it.

    Per number: the user's own setting in ``numbers.yaml`` first, then the
    user's own reading, then the estimate shipped with mcgyvr. When the user
    sets only one of the two, that one is theirs and the other comes from the
    next layer down; the answer's ``source`` is then the weaker layer and its
    :meth:`Link.says` names each. A class mcgyvr does not know, an unreadable
    readings file, or a number no layer states is refused by name.
    """
    if link_class not in links.LINK_CLASSES:
        raise InterconnectError(
            f"{link_class!r} is not a class of link ({', '.join(links.LINK_CLASSES)}); "
            "a link is classed by whether its two cards share a machine, "
            "never by a machine's name"
        )
    kept = readings_path()
    reading = _read_readings(kept).get(link_class)
    answered = derived.lookup_all(
        [(derived.LINK_GIB_S, link_class), (derived.LINK_LATENCY_US, link_class)]
    )

    def layered(number: derived.Number, field: str) -> tuple[float, str, Path]:
        if number.source == OVERRIDE:
            return number.value, OVERRIDE, number.where
        if reading is not None:
            return float(reading[field]), READING, kept
        return number.value, ESTIMATE, number.where

    gib_s, gib_layer, gib_where = layered(
        answered[(derived.LINK_GIB_S, link_class)], "gib_s"
    )
    latency_us, lag_layer, lag_where = layered(
        answered[(derived.LINK_LATENCY_US, link_class)], "latency_us"
    )
    weakest = max(gib_layer, lag_layer, key=_LAYERS.index)
    return Link(
        link_class=link_class,
        gib_s=gib_s,
        latency_us=latency_us,
        source=weakest,
        where=gib_where if weakest == gib_layer else lag_where,
        gib_s_source=gib_layer,
        latency_us_source=lag_layer,
    )


def fit_transfers(samples: Sequence[Transfer]) -> tuple[float, float]:
    """The ``(gib_s, latency_us)`` of the line seconds = latency + bytes / bandwidth.

    A least-squares fit over timed transfers, because one transfer cannot say
    its bandwidth and its latency apart: a small payload is nearly all latency
    and a large one nearly all bandwidth, and the line through several sizes
    separates them. It needs at least two distinct payload sizes. It refuses
    what cannot be a link: a payload that is negative or not a whole number of
    bytes, a time that is not finite and above 0, a slope that is not above 0
    (a bigger payload took no longer, so no bandwidth can be named), and an
    intercept that is not above 0 (no transfer is free, so timings that say it
    is came from a clock too coarse for the payloads, or from payloads too large
    to show the latency; add a small payload). An intercept is never clamped to
    zero, because a latency made up to fit would be a number nobody read.
    """
    points: list[tuple[float, float]] = []
    for payload, seconds in samples:
        if isinstance(payload, bool) or not isinstance(payload, int) or payload < 0:
            raise InterconnectError(
                f"a payload of {payload!r} bytes cannot be timed; a payload is a "
                "whole number of bytes, 0 or more"
            )
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds <= 0.0
        ):
            raise InterconnectError(
                f"a transfer of {payload} bytes took {seconds!r} seconds; a time "
                "is finite and above 0"
            )
        points.append((float(payload), float(seconds)))
    if len({x for x, _ in points}) < 2:
        raise InterconnectError(
            "a link cannot be fitted from fewer than two distinct payload sizes: "
            "one size cannot tell bandwidth from latency; time a small and a "
            "large payload"
        )
    count = len(points)
    mean_x = math.fsum(x for x, _ in points) / count
    mean_y = math.fsum(y for _, y in points) / count
    spread = math.fsum((x - mean_x) ** 2 for x, _ in points)
    slope = math.fsum((x - mean_x) * (y - mean_y) for x, y in points) / spread
    if not slope > 0.0:
        raise InterconnectError(
            "the timed transfers do not grow with their payload (the fitted "
            "seconds per byte is not above 0), so no bandwidth can be named; "
            "time the transfers again"
        )
    intercept = mean_y - slope * mean_x
    if not intercept > 0.0:
        raise InterconnectError(
            "the timed transfers fit a latency that is not above 0, which no "
            "link has; include a small payload, or time with a finer clock, and "
            "read the link again"
        )
    gib_s = 1.0 / slope / _BYTES_PER_GIB
    latency_us = intercept * _MICROSECONDS_PER_SECOND
    if not (math.isfinite(gib_s) and math.isfinite(latency_us)):
        raise InterconnectError(
            "the timed transfers fit a bandwidth or latency too large to state"
        )
    return gib_s, latency_us


def record_reading(
    link_class: str,
    *,
    gib_s: float,
    latency_us: float,
    how: str,
    at: str,
    between: tuple[str, str],
) -> Path:
    """Keep the user's reading of a link class in the readings file, and say where.

    The file is merged, not replaced: a reading of one class leaves the other
    class's reading as it was. A file that cannot be read is refused rather than
    written over, since writing over it would destroy what it held. The write is
    atomic (a temporary file beside it, then ``os.replace``), and the folder is
    created when it is not there.
    """
    where = readings_path()
    entry = _checked(
        link_class,
        {
            "gib_s": gib_s,
            "latency_us": latency_us,
            "how": how,
            "at": at,
            "between": list(between),
        },
        where,
    )
    merged = _read_readings(where)
    merged[link_class] = entry
    document = {"schema": READINGS_SCHEMA, "links": merged}
    where.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        dir=where.parent, prefix=where.name, suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, where)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return where


def read_link(
    host_a: str, host_b: str, reader: LinkReader, *, how: str, at: str
) -> Link:
    """Read the link between two hosts, keep the reading, and answer for its class.

    The pair is classed (:func:`mcgyvr.fleet.links.link_class`), ``reader`` times
    transfers between the two hosts, the fit becomes the user's own reading of
    that class, and the answer is :func:`link`'s: source ``reading`` unless the
    user's own setting in ``numbers.yaml`` outranks it, in which case the setting
    answers and the reading is kept all the same, for the day the setting goes.
    ``how`` (what timed the transfers) and ``at`` (when) are the caller's words,
    kept with the reading, because a reading nobody can date or repeat is worth
    no more than an estimate. The reader is the caller's; nothing here opens a
    connection.
    """
    kind = links.link_class(host_a, host_b)
    gib_s, latency_us = fit_transfers(reader(host_a, host_b))
    record_reading(
        kind,
        gib_s=gib_s,
        latency_us=latency_us,
        how=how,
        at=at,
        between=(host_a, host_b),
    )
    return link(kind)
