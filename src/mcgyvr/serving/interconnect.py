"""What two cards' link is worth: its bandwidth and latency, read or estimated.

A link is classed by `mcgyvr.fleet.links` from the two hosts its cards sit on.
For a class of link this module answers two numbers, bandwidth in GiB/s and
latency in microseconds, from the strongest layer that states them: the user's
own setting in the numbers override file, else their own reading timed between
their hosts, else the estimate shipped with mcgyvr. A timed set of transfers is
fitted to a line whose slope is seconds per byte and whose intercept is the
latency, and the reading is kept in `links.json` under the data home beside the
readings taken for the other classes of link.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr import atomic, derived
from mcgyvr.fleet import links, roots

#: The name of the file, under the data home, that holds the user's own readings.
READINGS_FILENAME = "links.json"
#: The schema number a readings file must state; a file stating another is refused.
READINGS_SCHEMA = 1
#: Bytes in a GiB, and microseconds in a second, for turning a fitted slope and
#: intercept (seconds per byte, seconds) into GiB/s and microseconds.
_BYTES_PER_GIB = 2**30
_MICROSECONDS_PER_SECOND = 1_000_000.0

#: The layers a number can come from: the user's own setting, the user's own
#: reading, and the estimate shipped with mcgyvr, in that order, strongest first.
OVERRIDE = "override"
READING = "reading"
ESTIMATE = "estimate"
_LAYERS: tuple[str, ...] = (OVERRIDE, READING, ESTIMATE)

#: One timed transfer: a payload in bytes and the seconds it took.
Transfer = tuple[int, float]
#: Times each transfer between two named hosts: a payload in bytes and its
#: seconds, at least two distinct payload sizes, the way a link is read.
LinkReader = Callable[[str, str], Sequence[Transfer]]


class InterconnectError(Exception):
    """A link, a reading, or a set of timed transfers cannot be stated."""


def readings_path() -> Path:
    """Where the user's own link readings live: ``links.json`` in the data home."""
    return roots.data_home() / READINGS_FILENAME


@dataclass(frozen=True)
class Link:
    """One class of link, its bandwidth and latency, and which layers stated them.

    ``source`` is the weakest of the two layers that answered, and ``where`` is
    that layer's file, so a message can point at the least settled number;
    ``gib_s_source`` and ``latency_us_source`` name the layer behind each number
    on its own.
    """

    link_class: str
    gib_s: float
    latency_us: float
    source: str
    where: Path
    gib_s_source: str = ""
    latency_us_source: str = ""

    def _layer(self, layer: str) -> str:
        """The file behind a number, as a phrase naming whose file it is."""
        if layer == OVERRIDE:
            return f"your own setting in {derived.overrides_path()}"
        if layer == READING:
            return f"your own reading in {readings_path()}"
        return f"an estimate shipped with mcgyvr in {self.where}"

    def says(self) -> str:
        """The link as a sentence: both numbers, the file behind each, and the fix.

        Both numbers are named in one clause when one layer stated both, and in
        two clauses otherwise. When either number is still only the shipped
        estimate, the sentence adds that an estimate is not a reading of the
        user's link, and names the settings that replace it.
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
    """``value`` as a finite float above 0, refusing a bool or anything else."""
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
    """``value`` as a string holding something besides blanks, refusing the rest."""
    if not isinstance(value, str) or not value.strip():
        raise InterconnectError(f"{what} in {where} must be words, not {value!r}")
    return value


def _hosts(value: object, where: Path) -> list[str]:
    """The two host names a reading was taken between, refusing any other shape."""
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
    """One reading for a class of link, checked field by field, as a plain dict.

    The class must be one `mcgyvr.fleet.links` knows, and the reading an object
    stating its bandwidth, latency, the method and time it was taken, and the
    two hosts it was taken between.
    """
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
    """Every reading in the readings file, by class of link, checked.

    A file that is not there reads as no readings at all; a file that is there
    is refused unless it is UTF-8 JSON of this module's schema holding a
    ``links`` object, and each of its readings is checked with ``_checked``.
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
    """The link of one class, each number from the strongest layer stating it.

    A class that `mcgyvr.fleet.links` does not know is refused. For each of the
    two numbers the user's own setting in the numbers override file wins over
    the reading kept in the readings file, which wins over the shipped
    estimate; the returned link names the weakest layer it used and that
    layer's file.
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
    """Fit timed transfers to a bandwidth in GiB/s and a latency in microseconds.

    Each sample is a payload in whole bytes, 0 or more, and the seconds its
    transfer took, finite and above 0. A least-squares line through the points
    gives seconds per byte as its slope and the latency as its intercept, so the
    samples must include two distinct payload sizes, must grow with payload, and
    must fit a latency above 0; a fit failing any of these is refused.
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
    """Keep one reading for a class of link in the readings file, and say where.

    The reading is checked as the file's readings are, the file's existing
    readings for other classes are read and kept, and the whole document is
    written back as JSON private to the user, creating the folder it lives in.
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
    atomic.write(where, json.dumps(document, indent=2) + "\n", private=True)
    return where


def read_link(
    host_a: str, host_b: str, reader: LinkReader, *, how: str, at: str
) -> Link:
    """Time the link between two hosts, keep the reading, and answer that link.

    ``reader`` times the transfers between the two hosts, which are fitted to a
    bandwidth and a latency, checked and written to the readings file under the
    class `mcgyvr.fleet.links` gives the pair. The answer is ``link`` for that
    class, so a number the user sets themselves still wins over the reading just
    taken.
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
