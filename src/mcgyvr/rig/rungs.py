"""The relief rungs a hub matched this rider to, kept in ``relief.yaml``.

A hub matches a rider to other people's open slots (hitchhike) and lists them
at ``/api/v1/me/rungs``. :func:`sync` ``POST``s the rider's ladder there
(:func:`ladder_report`) and reads the list back, with the rider's *personal*
key — not the rig token — and writes it whole into ``relief.yaml``
beside the setup (:data:`mcgyvr.config.RELIEF_FILENAME`): one relief rung per
listed rung, so a rung the hub no longer lists is gone, and nothing else in the
setup is touched. Each rung names the variable that holds the key
(``api_key_env``), never the key: the runner reads it at dispatch, as it reads
every unit's.

**The key goes only where the rig token may.** The hub is asked over
``https://``, or ``http://`` on this machine, by the one rule
(:func:`mcgyvr.rig.verbs.hub_address`), and a redirect is not followed: it
would carry the key to an address nobody checked. Every address a rung names is
held to the same rule and must be the hub's own (scheme, host and port), since
the key is sent there with every ride.

**The rider reports their ladder, and only its shape.** The hub places each
host's model against the rider's own (above their ceiling, below their floor,
or within) from the model rungs in the order work climbs them, each with its
family, the weights file's size and the parameter count where the product
knows them (a unit's geometry scan, else the shipped capability table for the
count), and ``floor`` and ``ceiling``: the rung work starts on and the highest
one ``max_escalations`` lets it reach. No address, key or variable name is in
it, and no relief rung; it is checked against the contract before it is sent.

**The answer is hostile until read.** :func:`read` checks every field the
contract names — its type, its size, the model's pattern and that it names its
own rung, a width of at least one, a position the contract knows, an id once —
and refuses the whole answer at the first that fails, naming it. A hub that
half-speaks the contract is not trusted for the half it seems to get right, and
refusing whole keeps the relief rungs already kept as they were. Fields the
contract does not name are not read, so a newer hub may add some. The written
file is loaded with the rest of the setup before it replaces the old one, so a
sync never leaves a setup that does not load.

**The agent keeps them fresh when it may.** With the key's variable set, the
rig agent hands its heartbeat a :class:`Refresher` (:func:`refresher_for`),
which syncs at the first beat and then no sooner than the hub's ``refresh_s``,
on a thread of its own, one sync at a time, saying a failure rather than
raising it.
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

#: The rider's rungs, under a hub's address.
RUNGS_PATH = "/api/v1/me/rungs"
#: The variable the personal key is read from when none is named.
KEY_ENV = "MCGYVR_HUB_API_KEY"
#: What the key is called where a refusal names it.
CARRYING = "your personal hub key"
#: How long asking the hub may take, in seconds.
FETCH_TIMEOUT_S = 15.0
#: The largest answer read; a listing of :data:`MAX_RUNGS` rungs is far smaller.
MAX_ANSWER_BYTES = 256 * 1024
#: The most rungs one answer may list.
MAX_RUNGS = 64
#: The longest handle and model description kept, in characters.
MAX_TEXT = 256
#: The longest privacy warning shown, in characters.
MAX_PRIVACY = 2000
#: The longest rung address kept, in characters.
MAX_ADDRESS = 2048
#: The widest rung kept: no unit serves more requests at once.
MAX_RUNG_WIDTH = 1024
#: A relief rung's name in ``relief.yaml``: this prefix and the rung's id.
NAME_PREFIX = "hitchhike-"
#: The most rungs a reported ladder may hold, as the hub takes it.
MAX_LADDER_RUNGS = 64
#: A reported rung's model, as the hub takes it.
_LADDER_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@/:-]{0,127}")
#: How long the agent's refresher waits after a sync that failed, in seconds:
#: the hub's own re-match interval in the contract's example.
RETRY_S = 60.0

_ID = re.compile(r"[0-9a-f]{32}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@-]{0,127}")
_HTTP = {"http": "http", "https": "https", "ws": "http", "wss": "https"}


class SyncError(Exception):
    """A sync that could not be made: no setup here, or the hub not reached."""


class HubAnswerError(Exception):
    """The hub's answer is refused: it said no, or said something unreadable."""


@dataclass(frozen=True)
class Ride:
    """One relief rung, as the hub listed it."""

    id: str
    hosted_by: str
    address: str
    model: str
    served_model: str
    width: int
    position: str

    @property
    def name(self) -> str:
        """The rung's name in ``relief.yaml``, keyed on its id."""
        return f"{NAME_PREFIX}{self.id}"


@dataclass(frozen=True)
class Rides:
    """The hub's whole answer: whether the rider rides, and what to."""

    ride: bool
    privacy: str
    refresh_s: float
    rungs: tuple[Ride, ...]


def _origin(parts: urllib.parse.SplitResult) -> tuple[str, str, int]:
    """Scheme, host and port, the agent's schemes read as the web's."""
    scheme = _HTTP[parts.scheme.lower()]
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, (parts.hostname or "").lower(), port


def rungs_url(hub: str) -> str:
    """Where the hub at ``hub`` lists this rider's rungs.

    ``ValueError`` and :class:`~mcgyvr.rig.verbs._RefusalError` as
    :func:`~mcgyvr.rig.verbs.hub_address` raises them. A kept address that
    names the agent channel is read as the hub it belongs to.
    """
    parts = hub_address(hub, carrying=CARRYING)
    scheme, _, _ = _origin(parts)
    path = parts.path.rstrip("/")
    if path.endswith(AGENT_PATH):
        path = path[: -len(AGENT_PATH)]
    return urllib.parse.urlunsplit((scheme, parts.netloc, path + RUNGS_PATH, "", ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: it would carry the key to an unchecked address."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def ladder_report(config: Config) -> dict[str, Any]:
    """The rider's ladder as the hub is told it: ``{"ladder": {...}}``.

    The model rungs of ``config``'s ladder in the order work climbs them —
    families by the catalog's rank, the ladder's own order within each, which
    is the ladder's written order whenever it is written cheapest first — and
    the floor and ceiling as indexes into them. Relief rungs are not in it.
    :class:`SyncError` for a ladder the contract cannot carry, so nothing is
    sent that the hub would refuse.
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
    """The weights file's size and the parameter count in billions, or ``None``.

    Read from the unit's geometry scan (``launch.geometry_json``) where it names
    one that reads; the count otherwise from the shipped capability table by
    the unit's model. Anything that does not read is not known: a report says
    ``null`` rather than guess.
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
    """Report ``report`` to the hub at ``hub`` with ``key``, and read its rungs.

    :class:`HubAnswerError` for an error status (the hub's refusal) and for an
    answer :func:`read` refuses; :class:`SyncError` when the hub cannot be
    reached. No message carries the key.
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
    assert isinstance(position, str)  # one of the choices
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
    """The hub's answer for the hub at ``hub``, read whole, or refused whole.

    :class:`HubAnswerError` names the first field that fails.
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
    """``relief.yaml`` for ``rides``, each rung naming ``key_env`` for its key."""
    block = {
        each.name: {
            "address": each.address,
            "model": each.model,
            "api_key_env": key_env,
            "width": each.width,
            "position": each.position,
            "hosted_by": each.hosted_by,
            "served_model": each.served_model,
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
    """Ask the hub and keep its answer in ``folder``'s ``relief.yaml``.

    ``folder`` must hold a setup (a ``fleet.yaml``): a sync adds relief rungs to
    a setup and never starts one. The new file is loaded with the setup before
    it replaces the old one, and replaces it whole or not at all.
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
    staging = folder / f".{RELIEF_FILENAME}.part"
    staging.unlink(missing_ok=True)
    try:
        staging.write_text(text, encoding="utf-8")
        os.replace(staging, target)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return rides, target


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="relief-rungs", daemon=True).start()


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class Refresher:
    """A sync of the relief rungs, kept from the rig agent's heartbeat.

    :meth:`tick` is the agent's ``on_beat``: it returns at once. A sync is
    started when one is due — at the first tick, then once the hub's
    ``refresh_s`` has passed since the last sync ended, or :data:`RETRY_S`
    after one failed — and never while one is still going. A failure is said,
    once while it keeps failing the same way, and never raised.
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
        """Start a sync if one is due and none is going."""
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
    hub: str, *, environ: Mapping[str, str] = os.environ
) -> Refresher | None:
    """The agent's refresher for the hub it joined, or ``None`` without a key.

    Only when :data:`KEY_ENV` is set: the rig token is the agent's, and the
    rider's personal key is theirs to give. The key is read at each sync, so
    a variable changed under the agent is the one used next; the setup is the
    one :func:`mcgyvr.config.config_path` locates, as ``mcgyvr rig rungs
    sync`` does.
    """
    if not environ.get(KEY_ENV):
        return None

    def once() -> Rides:
        key = environ.get(KEY_ENV)
        if not key:
            raise SyncError(f"${KEY_ENV} is no longer set")
        try:
            folder = config_path()
        except ConfigError as exc:
            raise SyncError(str(exc)) from exc
        rides, _ = sync(folder, hub, key, KEY_ENV)
        return rides

    return Refresher(sync=once)
