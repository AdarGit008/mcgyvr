"""Ask the hub for the relief rungs this setup may ride, and keep them written.

A relief rung is a unit other people lend you through the hub (hitchhike): it
is never a step of the ladder, so all this module does is report the ladder's
shape to the hub and record the rungs it answers with.

* :func:`ladder_report` is what is reported: each model rung's model, family,
  file size and parameter count where known, plus the floor and ceiling the hub
  places the ladder at. No address, no key, no variable's name leaves here.
* :func:`fetch` posts that report to ``RUNGS_PATH`` on the hub's own address
  with the personal key, and :func:`read` validates the answer whole: one
  unreadable rung refuses the answer rather than being half-kept.
* :func:`render` turns the answer into the ``relief`` block of the setup's
  ``relief.yaml``, and :func:`sync` writes it, loading the setup with it first
  so an answer the setup would refuse is never written.
* :class:`Refresher` re-runs a sync off the rig agent's heartbeat, no more
  often than the hub's ``refresh_s``, and once every ``RETRY_S`` after a
  failure.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mcgyvr import atomic
from mcgyvr.config import (
    FLEET_FILENAME,
    POLICY_FILENAME,
    POSITION_CHOICES,
    RELIEF_FILENAME,
    Config,
    ConfigError,
    Unit,
    config_path,
    parse,
)
from mcgyvr.rig.verbs import AGENT_PATH, _RefusalError, hub_address

# The hub's rider API path, taken on the hub's own address and not on a rung's.
RUNGS_PATH = "/api/v1/me/rungs"
# The variable name a sync reads the rider's personal hub key from.
KEY_ENV = "MCGYVR_HUB_API_KEY"
# What the address check names as the credential that would travel in clear.
CARRYING = "your personal hub key"
# Seconds one request to the hub may take before it counts as unreachable.
FETCH_TIMEOUT_S = 15.0
# Most bytes of the hub's answer that are read; one more is read to tell an
# overrun from an answer that fills the mark exactly.
MAX_ANSWER_BYTES = 256 * 1024
# Most relief rungs one answer may list.
MAX_RUNGS = 64
# Longest host handle or served model an answer may name.
MAX_TEXT = 256
# Longest privacy warning the hub may send, which a sync prints as it reads it.
MAX_PRIVACY = 2000
# Longest rung address an answer may carry.
MAX_ADDRESS = 2048
# Widest a rung may say it takes at once, which becomes its width in relief.yaml.
MAX_RUNG_WIDTH = 1024
# What a relief rung's name in relief.yaml starts with: the hub's rung id follows.
NAME_PREFIX = "hitchhike-"
# Most rungs a reported ladder may have: the hub takes 1 to this many.
MAX_LADDER_RUNGS = 64
# What a reported rung's model must match: 1 to 128 characters, and no spaces.
_LADDER_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@/:-]{0,127}")
# The answers that say a relief rung cannot take a request now: an HTTP status
# and the error code its body carries. `render` writes them all into every
# rung's `busy_answers`, in the sorted order below: the hub has not yet
# matched this host to work (503 `hitchhike_not_served_yet`), the host's
# machine is away (503 `hitchhike_host_away`), and the hub names no host
# running the model asked for (404 `model_not_found`). A busy answer is a
# full rung, passed over at no cost; an answer not listed here is read as on
# any rung.
BUSY: tuple[tuple[int, str], ...] = tuple(
    sorted(
        {
            (503, "hitchhike_not_served_yet"),
            (503, "hitchhike_host_away"),
            (404, "model_not_found"),
        }
    )
)
# Seconds before a failed sync is tried again, whatever the hub last asked for:
# a failure leaves no refresh interval behind to wait by.
RETRY_S = 60.0

_ID = re.compile(r"[0-9a-f]{32}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@-]{0,127}")
_HTTP = {"http": "http", "https": "https", "ws": "http", "wss": "https"}


class SyncError(Exception):
    """A sync that could not be done on this machine's side.

    A folder with no ``fleet.yaml``, a setup that does not load, a ladder the
    hub cannot take, a file that cannot be read, or a hub that could not be
    reached. Whatever ``relief.yaml`` already holds is left as it was.
    """


class HubAnswerError(Exception):
    """The hub's answer refused whole, so nothing of it is written.

    A refusal status, a body over ``MAX_ANSWER_BYTES``, a body that is not
    JSON, a listing shaped otherwise than :func:`read` requires, or a listing
    the setup would not load with. ``relief.yaml`` is left as it was.
    """


@dataclass(frozen=True)
class Ride:
    """One relief rung as the hub describes it.

    ``id`` is the 32 hex digits its name carries, and ``address`` is checked to
    be the hub's own origin because the key is sent there.
    """

    id: str
    hosted_by: str
    address: str
    model: str
    served_model: str
    width: int
    position: str

    @property
    def name(self) -> str:
        """The rung's name in ``relief.yaml``: the prefix, then the rung id."""
        return f"{NAME_PREFIX}{self.id}"


@dataclass(frozen=True)
class Rides:
    """One hub answer, validated whole.

    ``ride`` is whether the hub matches this rider to work at all, ``privacy``
    is the warning it wants shown, ``refresh_s`` is how long to wait before
    asking again, and ``rungs`` are the relief rungs to write, in the order the
    hub listed them.
    """

    ride: bool
    privacy: str
    refresh_s: float
    rungs: tuple[Ride, ...]


def _origin(parts: urllib.parse.SplitResult) -> tuple[str, str, int]:
    """The scheme, host and port a parsed hub address points at.

    ws reads as the http scheme it carries and wss as https, and a scheme's
    default port stands in for one left unsaid. Two addresses with the same
    triple are the same origin, so the key may be sent to either.
    """
    scheme = _HTTP[parts.scheme.lower()]
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, (parts.hostname or "").lower(), port


def rungs_url(hub: str) -> str:
    """The hub's rider API address, built from the hub's own address.

    An ``AGENT_PATH`` suffix is dropped and ``RUNGS_PATH`` put in its place, so
    the report goes to the host and port the key is meant for and not to a rung.
    """
    parts = hub_address(hub, carrying=CARRYING)
    scheme, _, _ = _origin(parts)
    path = parts.path.rstrip("/")
    if path.endswith(AGENT_PATH):
        path = path[: -len(AGENT_PATH)]
    return urllib.parse.urlunsplit((scheme, parts.netloc, path + RUNGS_PATH, "", ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A hub that answers where it stands: a redirect is read as an HTTP error.

    Following one would send the personal key to an address the hub names, not
    to the one the setup names.
    """

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def ladder_report(config: Config) -> dict[str, Any]:
    """The ladder this setup runs, in the shape the hub places rungs by.

    The units the ladder names are sorted by family rank and each reported with
    its model, its family name, its file size in bytes and its parameter count
    in billions where either is known. ``floor`` is the index of the first rung
    at or above the lowest family any task type starts on, and ``ceiling`` is as
    many rungs above the floor as ``max_escalations`` allows, so a ladder
    shorter than that reports a ceiling below its top rung.

    Raises :class:`SyncError` when the ladder has no rungs, has more than
    ``MAX_LADDER_RUNGS``, or names a model outside ``_LADDER_MODEL``.
    """
    from mcgyvr.catalog import catalog
    from mcgyvr.escalate import Ceiling

    known = catalog()
    units = [config.units[name] for name in config.ladder.names]
    climbing = sorted(units, key=lambda unit: known.family_of(unit).rank)
    if not 1 <= len(climbing) <= MAX_LADDER_RUNGS:
        raise SyncError(
            f"the ladder cannot be reported: it has {len(climbing)} rungs, and "
            f"the hub takes 1 to {MAX_LADDER_RUNGS}"
        )
    rungs = []
    for unit in climbing:
        if not _LADDER_MODEL.fullmatch(unit.model):
            raise SyncError(
                f"the ladder cannot be reported: unit {unit.name!r} serves "
                f"{unit.model!r}, which is outside the hub's model pattern"
            )
        size, params = _what_is_known(unit)
        rungs.append(
            {
                "model": unit.model,
                "family": known.family_of(unit).name,
                "size_bytes": size,
                "params_b": params,
            }
        )
    lowest = min(kind.starts_on.rank for kind in known.task_types)
    floor = next(
        index
        for index, unit in enumerate(climbing)
        if known.family_of(unit).rank >= lowest
    )
    reach = min(len(climbing) - floor, Ceiling.of(config).escalations + 1)
    return {"ladder": {"rungs": rungs, "floor": floor, "ceiling": floor + reach - 1}}


def _what_is_known(unit: Unit) -> tuple[int | None, float | None]:
    """The unit's size in bytes and its parameter count in billions.

    Both are read from the geometry file the unit's ``geometry_json`` launch
    setting names, and the parameter count falls back to the capability table
    when the geometry file states none. Either is ``None`` when nothing states
    it or what states it cannot be read: a rung is reported without it.
    """
    size: int | None = None
    params: float | None = None
    stated = unit.launch.get("geometry_json") if unit.launch else None
    if stated:
        from mcgyvr.serving import UnitError, load_geometry

        try:
            row = load_geometry(str(stated), name=unit.model)
        except UnitError:
            row = {}
        scanned = row.get("size_bytes")
        if isinstance(scanned, int) and not isinstance(scanned, bool) and scanned >= 1:
            size = scanned
        total = row.get("params_total")
        if isinstance(total, int | float) and not isinstance(total, bool) and total > 0:
            params = total / 1e9
    if params is None:
        from mcgyvr.capability import CapabilityTableError, load

        try:
            listed = load().get(unit.model)
        except CapabilityTableError:
            listed = None
        if listed is not None and listed.params_b > 0:
            params = listed.params_b
    return size, params


def fetch(
    hub: str,
    key: str,
    report: Mapping[str, Any],
    *,
    timeout: float = FETCH_TIMEOUT_S,
) -> Rides:
    """POST the report to the hub and read the answer whole.

    The key travels in an ``Authorization: Bearer`` header, never in the URL,
    and a redirect is not followed. :class:`HubAnswerError` covers a refusal
    status, an answer over ``MAX_ANSWER_BYTES`` and a body that is not JSON;
    :class:`SyncError` covers a hub that could not be reached at all.
    """
    url = rungs_url(hub)
    request = urllib.request.Request(
        url,
        data=json.dumps(report).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw: bytes = response.read(MAX_ANSWER_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise HubAnswerError(
            f"the hub refused: {url} answered HTTP {exc.code}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise SyncError(f"the hub at {hub} could not be reached: {exc}") from exc
    if len(raw) > MAX_ANSWER_BYTES:
        raise HubAnswerError(
            f"the hub's answer is refused: it is over {MAX_ANSWER_BYTES} bytes"
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise HubAnswerError("the hub's answer is refused: it is not JSON") from exc
    return read(document, hub)


def _refused(where: str, why: str) -> HubAnswerError:
    return HubAnswerError(f"the hub's answer is refused: {where} {why}")


def _text(value: object, where: str, longest: int) -> str:
    if not isinstance(value, str) or not value or len(value) > longest:
        raise _refused(where, f"is not text of 1 to {longest} characters")
    if not value.isprintable():
        raise _refused(where, "holds a character that is not printable")
    return value


def _count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _refused(where, "is not a whole number")
    if not 1 <= value <= MAX_RUNG_WIDTH:
        raise _refused(where, f"is not between 1 and {MAX_RUNG_WIDTH}")
    return value


def _address(value: object, where: str, origin: tuple[str, str, int]) -> str:
    address = _text(value, where, MAX_ADDRESS)
    try:
        parts = hub_address(address, carrying=CARRYING)
    except _RefusalError as exc:
        raise _refused(where, str(exc)) from exc
    except ValueError as exc:
        raise _refused(where, f"is not a hub's address: {exc}") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise _refused(where, "is not an http(s) address")
    if _origin(parts) != origin:
        raise _refused(
            where, "is not the hub's own address, and the key would be sent there"
        )
    if not parts.path.rstrip("/").endswith("/v1"):
        raise _refused(where, "does not end in /v1")
    return address


def _ride(raw: object, where: str, origin: tuple[str, str, int]) -> Ride:
    if not isinstance(raw, dict):
        raise _refused(where, "is not an object")
    rung_id = raw.get("id")
    if not isinstance(rung_id, str) or not _ID.fullmatch(rung_id):
        raise _refused(f"{where}.id", "is not 32 lowercase hex digits")
    model = raw.get("model")
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise _refused(f"{where}.model", "is outside the model pattern")
    if model != f"hitchhike@{rung_id}":
        raise _refused(f"{where}.model", "does not name this rung")
    if raw.get("relief") is not True:
        raise _refused(f"{where}.relief", "is not true")
    position = raw.get("position")
    if position not in POSITION_CHOICES:
        raise _refused(
            f"{where}.position", f"is not one of {', '.join(POSITION_CHOICES)}"
        )
    assert isinstance(position, str)  # POSITION_CHOICES is text: the type narrows
    return Ride(
        id=rung_id,
        hosted_by=_text(raw.get("host"), f"{where}.host", MAX_TEXT),
        address=_address(raw.get("address"), f"{where}.address", origin),
        model=model,
        served_model=_text(raw.get("served_model"), f"{where}.served_model", MAX_TEXT),
        width=_count(raw.get("width"), f"{where}.width"),
        position=position,
    )


def read(document: object, hub: str) -> Rides:
    """Validate the hub's answer as a whole and return it.

    ``ride`` must be a boolean, ``privacy`` text, ``refresh_s`` a finite number
    above zero and ``rungs`` a list of at most ``MAX_RUNGS`` entries. Every rung
    must name its own model, carry the hub's own origin as its address, and be
    listed once; one bad entry raises :class:`HubAnswerError` naming where it
    is, so no partial listing is ever returned.
    """
    origin = _origin(hub_address(hub, carrying=CARRYING))
    if not isinstance(document, dict):
        raise _refused("the answer", "is not a JSON object")
    ride = document.get("ride")
    if not isinstance(ride, bool):
        raise _refused("ride", "is not true or false")
    privacy = _text(document.get("privacy"), "privacy", MAX_PRIVACY)
    refresh = document.get("refresh_s")
    if (
        isinstance(refresh, bool)
        or not isinstance(refresh, int | float)
        or not math.isfinite(refresh)
        or refresh <= 0
    ):
        raise _refused("refresh_s", "is not a number above zero")
    listed = document.get("rungs")
    if not isinstance(listed, list):
        raise _refused("rungs", "is not a list")
    if len(listed) > MAX_RUNGS:
        raise _refused("rungs", f"lists more than {MAX_RUNGS}")
    if listed and not ride:
        raise _refused("rungs", "are listed for a rider who does not ride")
    rides = tuple(
        _ride(raw, f"rungs[{index}]", origin) for index, raw in enumerate(listed)
    )
    seen: set[str] = set()
    for index, each in enumerate(rides):
        if each.id in seen:
            raise _refused(f"rungs[{index}].id", "is listed twice")
        seen.add(each.id)
    return Rides(ride=ride, privacy=privacy, refresh_s=float(refresh), rungs=rides)


def render(rides: Rides, key_env: str) -> str:
    """The ``relief.yaml`` text for one answer.

    Every rung becomes a block under ``relief``, keyed by its name and carrying
    its address, model, key variable name, width, position, host, served model
    and the ``BUSY`` answers. A header says a sync rewrites the file whole and
    that each host can read the prompts sent to their rung.
    """
    block = {
        each.name: {
            "address": each.address,
            "model": each.model,
            "api_key_env": key_env,
            "width": each.width,
            "position": each.position,
            "hosted_by": each.hosted_by,
            "served_model": each.served_model,
            "busy_answers": [{"status": status, "code": code} for status, code in BUSY],
        }
        for each in rides.rungs
    }
    header = (
        "# Written by `mcgyvr rig rungs sync`, which rewrites it whole: an edit\n"
        "# here lasts until the next sync. Each host can read the prompts sent\n"
        "# to their rung.\n"
    )
    return header + yaml.safe_dump({"relief": block}, sort_keys=False)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        raise SyncError(f"cannot read {path}: {exc}") from exc


def sync(folder: Path, hub: str, key: str, key_env: str) -> tuple[Rides, Path]:
    """Sync once: report the setup's ladder, then write the answer beside it.

    The folder must hold a ``fleet.yaml``. The answer is loaded with that setup
    as its ``relief_text`` before anything is written, so an answer the setup
    would refuse raises :class:`HubAnswerError` and leaves ``relief.yaml`` as
    it was. Returns the answer read and the file it was written to.
    """
    fleet = folder / FLEET_FILENAME
    if not fleet.is_file():
        raise SyncError(
            f"no {FLEET_FILENAME} in {folder}: a sync keeps relief rungs beside a "
            "setup, and there is none here"
        )
    try:
        own = parse(
            _read_text(fleet), _read_text(folder / POLICY_FILENAME), path=folder
        )
    except ConfigError as exc:
        raise SyncError(f"the setup in {folder} does not load: {exc}") from exc
    rides = fetch(hub, key, ladder_report(own))
    text = render(rides, key_env)
    try:
        parse(
            _read_text(fleet),
            _read_text(folder / POLICY_FILENAME),
            path=folder,
            relief_text=text,
        )
    except ConfigError as exc:
        raise HubAnswerError(
            f"the hub's answer is refused: the setup would not load with it ({exc})"
        ) from exc
    target = folder / RELIEF_FILENAME
    atomic.write(target, text)
    return rides, target


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="relief-rungs", daemon=True).start()


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class Refresher:
    """A sync kept fresh against a clock, one run at a time.

    :meth:`tick` decides whether a sync is due and hands the work to the thread
    ``start`` gives it, so the caller is never blocked. The next sync is due
    ``refresh_s`` after an answer, or ``RETRY_S`` after a failure, and a failure
    is said once rather than on every tick that follows it.
    """

    def __init__(
        self,
        *,
        sync: Callable[[], Rides],
        clock: Callable[[], float] = time.monotonic,
        say: Callable[[str], None] = _say,
        start: Callable[[Callable[[], None]], None] = _thread,
    ) -> None:
        self._sync = sync
        self._clock = clock
        self._say = say
        self._start = start
        self._lock = threading.Lock()
        self._due: float | None = None
        self._going = False
        self._last_failure = ""

    def tick(self) -> None:
        """Start a sync off the calling thread if one is due and none is going.

        Returns at once either way. With no failure and no answer yet the first
        call syncs immediately; after that the hub's own interval, or ``RETRY_S``,
        holds the next one back. Nothing is printed here: the failure is said on
        the thread that ran it.
        """
        with self._lock:
            now = self._clock()
            if self._going or (self._due is not None and now < self._due):
                return
            self._going = True
        self._start(self._run)

    def _run(self) -> None:
        try:
            rides = self._sync()
        except (SyncError, HubAnswerError, OSError, ValueError) as exc:
            failure = f"note: the relief rungs were not synced: {exc}"
            with self._lock:
                self._due = self._clock() + RETRY_S
                self._going = False
                repeated, self._last_failure = failure == self._last_failure, failure
            if not repeated:
                self._say(failure)
            return
        with self._lock:
            self._due = self._clock() + rides.refresh_s
            self._going = False
            self._last_failure = ""


def refresher_for(
    hub: str,
    *,
    environ: Mapping[str, str] = os.environ,
    folder: Path | None = None,
) -> Refresher | None:
    """A :class:`Refresher` for this machine, or ``None`` where no key is set.

    ``$KEY_ENV`` must hold a key or nothing is synced at all. Each run reads the
    key again, since it may have been removed since, and the setup synced is
    ``folder`` or, left unsaid, the config path the rig itself reads.
    """
    if not environ.get(KEY_ENV):
        return None

    def once() -> Rides:
        key = environ.get(KEY_ENV)
        if not key:
            raise SyncError(f"${KEY_ENV} is no longer set")
        try:
            where = folder if folder is not None else config_path()
        except ConfigError as exc:
            raise SyncError(str(exc)) from exc
        rides, _ = sync(where, hub, key, KEY_ENV)
        return rides

    return Refresher(sync=once)
