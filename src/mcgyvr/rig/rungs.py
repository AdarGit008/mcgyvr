"""Ask the hub for the relief rungs this setup may ride, and keep them written;
ask it for the member's balance with the same key.

A relief rung is a unit other people lend you through the hub (hitchhike): it
is a step of the ladder only where you name it there, so all this module does
is report the shape of your own ladder to the hub and record the rungs it
answers with.

* :func:`ladder_report` is what is reported: each model rung's model, family,
  file size and parameter count where known, plus the floor and ceiling the hub
  places the ladder at. No address, no key, no variable's name leaves here.
* :func:`fetch` posts that report to ``RUNGS_PATH`` on the hub's own address
  with the personal key, and :func:`read` validates the answer whole: one
  unreadable rung refuses the answer rather than being half-kept.
* :func:`render` turns the answer into the ``relief`` block of the setup's
  ``relief.yaml``, and :func:`sync` writes it, loading the setup with it first
  so an answer the setup would refuse is never written.
* :func:`ask`, :func:`load_setup` and :func:`keep` are the one fetch and the
  one writer of every file a sync keeps beside a setup (:data:`KEPT`):
  ``relief.yaml`` here, ``crew.yaml`` for :mod:`mcgyvr.rig.crew`.
* :class:`Refresher` re-runs a sync off the rig agent's heartbeat, no more
  often than the hub's ``refresh_s``, and once every ``RETRY_S`` after a
  failure.
* :func:`balance` asks ``CREDITS_PATH`` for the member's credits, through the
  same :func:`ask` a sync posts with.
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
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from mcgyvr import atomic
from mcgyvr.config import (
    CREW_FILENAME,
    FLEET_FILENAME,
    POLICY_FILENAME,
    RELIEF_FILENAME,
    RIDE_SCOPE,
    Config,
    ConfigError,
    Unit,
    config_path,
    parse,
)
from mcgyvr.fleet.files import RELIEF_KEY_ENV, FleetFileError, relief_key_env
from mcgyvr.hubwire import (
    LADDER_MAX_RUNGS,
    LADDER_MODEL,
    MODEL_NAME,
    OFFER_ID,
    RUNG_BUSY,
    RUNG_POSITIONS,
    SCOPE_ANYONE,
    SCOPE_CREW,
    SCOPE_OWN,
    SEAL_KEY_FIELD,
    rung_offer,
)
from mcgyvr.rig.verbs import AGENT_PATH, _RefusalError, hub_address
from mcgyvr.seal import SealKey

#: The hub's rider API path, taken on the hub's own address and not on a rung's.
RUNGS_PATH = "/api/v1/me/rungs"
#: The member's balance and ledger on the hub, asked with the same key.
CREDITS_PATH = "/api/v1/me/credits"
#: Most bytes of the credits answer read: a balance and the latest entries.
MAX_CREDITS_BYTES = 64 * 1024
#: A balance as the hub writes one: an exact decimal, at most this long.
MAX_BALANCE = 40
BALANCE = re.compile(rf"(?=.{{1,{MAX_BALANCE}}}$)-?[0-9]+(\.[0-9]+)?")
#: The variable name a sync reads the rider's personal hub key from when it is
#: told none, and the agent's refresh when ``relief.yaml`` records none.
KEY_ENV = "MCGYVR_HUB_API_KEY"
#: What the address check names as the credential that would travel in clear.
CARRYING = "your personal hub key"
#: Seconds one request to the hub may take before it counts as unreachable.
FETCH_TIMEOUT_S = 15.0
#: Most bytes of the hub's answer that are read; one more is read to tell an
#: overrun from an answer that fills the mark exactly.
MAX_ANSWER_BYTES = 256 * 1024
#: Most relief rungs one answer may list.
MAX_RUNGS = 64
#: Longest host handle or served model an answer may name.
MAX_TEXT = 256
#: Longest privacy warning the hub may send, which a sync prints as it reads it.
MAX_PRIVACY = 2000
#: Longest rung address an answer may carry.
MAX_ADDRESS = 2048
#: Widest a rung may say it takes at once, which becomes its width in relief.yaml.
MAX_RUNG_WIDTH = 1024
#: What a relief rung's name in relief.yaml starts with: the hub's rung id follows.
NAME_PREFIX = "hitchhike-"
#: Seconds before a failed sync is tried again, whatever the hub last asked for:
#: a failure leaves no refresh interval behind to wait by.
RETRY_S = 60.0

_HTTP = {"http": "http", "https": "https", "ws": "http", "wss": "https"}


class SyncError(Exception):
    """A sync that could not be done on this machine's side.

    A folder with no ``fleet.yaml``, a setup that does not load, a ladder the
    hub cannot take, a file that cannot be read, or a hub that could not be
    reached. Whatever ``relief.yaml`` already holds is left as it was.
    """


class PrivateSetupError(SyncError):
    """The setup says ``private: true``: it rides no relief rung, so nothing
    is synced and the hub is sent nothing."""


class HubAnswerError(Exception):
    """The hub's answer refused whole, so nothing of it is written.

    A refusal status, a body over ``MAX_ANSWER_BYTES``, a body that is not
    JSON, a listing shaped otherwise than :func:`read` requires, or a listing
    the setup would not load with. ``relief.yaml`` is left as it was.
    """


@dataclass(frozen=True)
class Kept:
    """A file a sync writes whole beside a setup.

    ``filename`` is where it is kept, ``argument`` the :func:`mcgyvr.config.parse`
    argument its text is read as, and ``holds`` what it holds, as a message
    names it.
    """

    filename: str
    argument: str
    holds: str


#: The relief rungs a hub lent you, kept by this module.
RELIEF = Kept(RELIEF_FILENAME, "relief_text", "relief rungs")
#: The units your crews lend you, kept by :mod:`mcgyvr.rig.crew`.
CREW = Kept(CREW_FILENAME, "crew_text", "crew units")
#: Every file a sync keeps, each read with the setup whichever one is written.
KEPT: tuple[Kept, ...] = (RELIEF, CREW)


@dataclass(frozen=True)
class Setup:
    """A setup as a sync reads it: its folder, the text of each of its files
    by the :func:`mcgyvr.config.parse` argument it is read as, and what that
    text loads as."""

    folder: Path
    texts: Mapping[str, str]
    config: Config


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
    #: The key the host's unit opens sealed requests with, None where the hub
    #: lists none (an older agent or hub): such a rung is asked in clear.
    seal: SealKey | None = None

    @property
    def name(self) -> str:
        """The rung's name in ``relief.yaml``: the prefix, then the rung id."""
        return f"{NAME_PREFIX}{self.id}"

    @property
    def sealing(self) -> str:
        """How the rung is asked, as a sync says it: ``sealed`` and the start of
        its key's id, which the host's ``rig up`` prints too, or ``in clear``."""
        return "in clear" if self.seal is None else f"sealed {self.seal.kid[:8]}"


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
    #: The rungs the setup asked sealed before this answer that it lists with no
    #: key now, so they are asked in clear from here on (:func:`sync` fills it).
    unsealed: tuple[str, ...] = ()


def _origin(parts: urllib.parse.SplitResult) -> tuple[str, str, int]:
    """The scheme, host and port a parsed hub address points at.

    ws reads as the http scheme it carries and wss as https, and a scheme's
    default port stands in for one left unsaid. Two addresses with the same
    triple are the same origin, so the key may be sent to either.
    """
    scheme = _HTTP[parts.scheme.lower()]
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, (parts.hostname or "").lower(), port


def hub_url(hub: str, path: str) -> str:
    """The address of ``path`` on the hub, built from the hub's own address.

    An ``AGENT_PATH`` suffix is dropped and ``path`` put in its place, so a
    request goes to the host and port the key is meant for and not to a rung.
    """
    parts = hub_address(hub, carrying=CARRYING)
    scheme, _, _ = _origin(parts)
    base = parts.path.rstrip("/")
    if base.endswith(AGENT_PATH):
        base = base[: -len(AGENT_PATH)]
    return urllib.parse.urlunsplit((scheme, parts.netloc, base + path, "", ""))


def rungs_url(hub: str) -> str:
    """The hub's rider API address: ``RUNGS_PATH`` on the hub (:func:`hub_url`)."""
    return hub_url(hub, RUNGS_PATH)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A hub that answers where it stands: a redirect is read as an HTTP error.

    Following one would send the personal key to an address the hub names, not
    to the one the setup names.
    """

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def ladder_report(config: Config) -> dict[str, Any]:
    """The ladder this setup runs, in the shape the hub places rungs by.

    The units of your own the ladder names (a relief rung a step names is the
    hub's, not yours) are sorted by family rank and each reported with
    its model, its family name, its file size in bytes and its parameter count
    in billions where either is known. ``floor`` is the index of the first rung
    at or above the lowest family any task type starts on, and ``ceiling`` is as
    many rungs above the floor as ``max_escalations`` allows — the top rung when
    it is unset — so a stated ceiling shorter than the ladder reports one below
    its top rung.

    Raises :class:`SyncError` when the ladder has no rungs, has more than
    ``LADDER_MAX_RUNGS``, or names a model outside ``LADDER_MODEL``
    (:mod:`mcgyvr.hubwire`).
    """
    from mcgyvr.catalog import catalog
    from mcgyvr.escalate import Ceiling

    known = catalog()
    units = [
        config.units[name]
        for name in config.ladder.names
        if not config.units[name].relief
    ]
    climbing = sorted(units, key=lambda unit: known.family_of(unit).rank)
    if not 1 <= len(climbing) <= LADDER_MAX_RUNGS:
        raise SyncError(
            f"the ladder cannot be reported: it has {len(climbing)} rungs of "
            f"your own (a relief rung a step names is the hub's and not "
            f"reported), and the hub takes 1 to {LADDER_MAX_RUNGS}"
        )
    rungs = []
    for unit in climbing:
        if not LADDER_MODEL.fullmatch(unit.model):
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
    reach = Ceiling.of(config).rungs(len(climbing) - floor)
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
    """POST the report to the hub (:func:`ask`) and read the answer whole."""
    return read(ask(rungs_url(hub), hub, key, body=report, timeout=timeout), hub)


def ask(
    url: str,
    hub: str,
    key: str,
    *,
    body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = FETCH_TIMEOUT_S,
    most: int = MAX_ANSWER_BYTES,
) -> object:
    """Ask the hub at ``url`` and return its answer, parsed as JSON.

    ``body`` is POSTed as JSON; with none the request is a GET. ``headers`` go
    beside the key, which travels in an ``Authorization: Bearer`` header, never
    in the URL, and a redirect is not followed. :class:`HubAnswerError` covers
    a refusal status, an answer over ``most`` bytes (``MAX_ANSWER_BYTES`` unless
    said) and a body that is not JSON; :class:`SyncError` covers a hub that
    could not be reached at all.
    """
    sent = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if body is not None:
        sent["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={**(headers or {}), **sent},
        method="GET" if body is None else "POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw: bytes = response.read(most + 1)
    except urllib.error.HTTPError as exc:
        raise HubAnswerError(
            f"the hub refused: {url} answered HTTP {exc.code}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise SyncError(f"the hub at {hub} could not be reached: {exc}") from exc
    if len(raw) > most:
        raise HubAnswerError(f"the hub's answer is refused: it is over {most} bytes")
    try:
        document: object = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise HubAnswerError("the hub's answer is refused: it is not JSON") from exc
    return document


def balance(hub: str, key: str) -> str:
    """The member's credits as the hub states them (``CREDITS_PATH``): an
    exact decimal of at most ``MAX_BALANCE`` characters, or
    :class:`HubAnswerError` for anything else."""
    document = ask(hub_url(hub, CREDITS_PATH), hub, key, most=MAX_CREDITS_BYTES)
    said = document.get("balance") if isinstance(document, dict) else None
    if not isinstance(said, str) or not BALANCE.fullmatch(said):
        raise refused("balance", "is not a decimal number of credits")
    return said


def refused(where: str, why: str) -> HubAnswerError:
    """The refusal of a hub's answer, naming ``where`` in it and ``why``."""
    return HubAnswerError(f"the hub's answer is refused: {where} {why}")


def _text(value: object, where: str, longest: int) -> str:
    if not isinstance(value, str) or not value or len(value) > longest:
        raise refused(where, f"is not text of 1 to {longest} characters")
    if not value.isprintable():
        raise refused(where, "holds a character that is not printable")
    return value


def _count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise refused(where, "is not a whole number")
    if not 1 <= value <= MAX_RUNG_WIDTH:
        raise refused(where, f"is not between 1 and {MAX_RUNG_WIDTH}")
    return value


def _address(value: object, where: str, origin: tuple[str, str, int]) -> str:
    address = _text(value, where, MAX_ADDRESS)
    try:
        parts = hub_address(address, carrying=CARRYING)
    except _RefusalError as exc:
        raise refused(where, str(exc)) from exc
    except ValueError as exc:
        raise refused(where, f"is not a hub's address: {exc}") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise refused(where, "is not an http(s) address")
    if _origin(parts) != origin:
        raise refused(
            where, "is not the hub's own address, and the key would be sent there"
        )
    if not parts.path.rstrip("/").endswith("/v1"):
        raise refused(where, "does not end in /v1")
    return address


def _ride(raw: object, where: str, origin: tuple[str, str, int]) -> Ride:
    if not isinstance(raw, dict):
        raise refused(where, "is not an object")
    rung_id = raw.get("id")
    if not isinstance(rung_id, str) or not OFFER_ID.fullmatch(rung_id):
        raise refused(f"{where}.id", "is not 32 lowercase hex digits")
    model = raw.get("model")
    if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
        raise refused(f"{where}.model", "is outside the model pattern")
    if rung_offer(model) != rung_id:
        raise refused(f"{where}.model", "does not name this rung")
    if raw.get("relief") is not True:
        raise refused(f"{where}.relief", "is not true")
    position = raw.get("position")
    if position not in RUNG_POSITIONS:
        raise refused(f"{where}.position", f"is not one of {', '.join(RUNG_POSITIONS)}")
    assert isinstance(position, str)  # RUNG_POSITIONS is text: the type narrows
    key = raw.get(SEAL_KEY_FIELD)
    try:
        sealed = None if key is None else SealKey.of(key)
    except ValueError as exc:
        raise refused(
            f"{where}.{SEAL_KEY_FIELD}", f"is not a seal key ({exc})"
        ) from exc
    return Ride(
        id=rung_id,
        hosted_by=_text(raw.get("host"), f"{where}.host", MAX_TEXT),
        address=_address(raw.get("address"), f"{where}.address", origin),
        model=model,
        served_model=_text(raw.get("served_model"), f"{where}.served_model", MAX_TEXT),
        width=_count(raw.get("width"), f"{where}.width"),
        position=position,
        seal=sealed,
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
        raise refused("the answer", "is not a JSON object")
    ride = document.get("ride")
    if not isinstance(ride, bool):
        raise refused("ride", "is not true or false")
    privacy = _text(document.get("privacy"), "privacy", MAX_PRIVACY)
    refresh = document.get("refresh_s")
    if (
        isinstance(refresh, bool)
        or not isinstance(refresh, int | float)
        or not math.isfinite(refresh)
        or refresh <= 0
    ):
        raise refused("refresh_s", "is not a number above zero")
    listed = document.get("rungs")
    if not isinstance(listed, list):
        raise refused("rungs", "is not a list")
    if len(listed) > MAX_RUNGS:
        raise refused("rungs", f"lists more than {MAX_RUNGS}")
    if listed and not ride:
        raise refused("rungs", "are listed for a rider who does not ride")
    rides = tuple(
        _ride(raw, f"rungs[{index}]", origin) for index, raw in enumerate(listed)
    )
    seen: set[str] = set()
    for index, each in enumerate(rides):
        if each.id in seen:
            raise refused(f"rungs[{index}].id", "is listed twice")
        seen.add(each.id)
    return Rides(ride=ride, privacy=privacy, refresh_s=float(refresh), rungs=rides)


def render(rides: Rides, key_env: str, scope: str = RIDE_SCOPE) -> str:
    """The ``relief.yaml`` text for one answer.

    ``key_env``, the NAME of the variable the key was read from, is recorded
    beside the rungs (:data:`mcgyvr.fleet.files.RELIEF_KEY_ENV`), so the
    agent's refresh reads the key where this sync did (:func:`key_env`). Every
    rung becomes a block under ``relief``, keyed by its name and carrying
    its address, model, key variable name, width, position, host, served model,
    the answers that say it is full (:data:`mcgyvr.hubwire.RUNG_BUSY`), the
    scope its requests name: ``scope``, the setup's ``ride_scope`` (unsaid:
    :data:`mcgyvr.config.RIDE_SCOPE`), and the key its requests are sealed to
    where the hub lists one. A
    header says a sync rewrites the file whole and that each host can read the
    prompts sent to their rung.
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
            "busy_answers": [
                {"status": status, "code": code} for status, code in RUNG_BUSY
            ],
            "scope": scope,
        }
        | ({} if each.seal is None else {SEAL_KEY_FIELD: each.seal.wire()})
        for each in rides.rungs
    }
    header = (
        "# Written by `mcgyvr rig rungs sync`, which rewrites it whole: an edit\n"
        "# here lasts until the next sync. Each host can read the prompts sent\n"
        "# to their rung. A rung with a `seal` key is asked sealed to it: its\n"
        "# prompts and answers are unread by a hub that lists the host's own key;\n"
        "# until rig identity signs it, the key is the hub's word (SECURITY.md).\n"
    )
    return header + yaml.safe_dump(
        {RELIEF_KEY_ENV: key_env, "relief": block}, sort_keys=False
    )


def key_env(folder: Path) -> str:
    """The NAME of the variable a sync of the setup in ``folder`` reads the
    personal hub key from: the one its ``relief.yaml`` records, as the last
    ``mcgyvr rig rungs sync`` was told it, else :data:`KEY_ENV`.

    A file that cannot be read, or records something not a variable's name,
    raises :class:`SyncError`.
    """
    path = folder / RELIEF_FILENAME
    text = _read_text(path)
    if not text.strip():
        return KEY_ENV
    try:
        return relief_key_env(text) or KEY_ENV
    except FleetFileError as exc:
        raise SyncError(f"{path}: {exc}") from exc


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        raise SyncError(f"cannot read {path}: {exc}") from exc


def load_setup(folder: Path, kept: Kept) -> Setup:
    """Read the setup in ``folder`` for a sync that rewrites ``kept``.

    The folder must hold a ``fleet.yaml``. The setup is loaded with every file
    of :data:`KEPT` already there, since a step or a role may name what one
    holds, or without ``kept``'s file when it does not load with it. Raises
    :class:`SyncError` when neither loads.
    """
    fleet = folder / FLEET_FILENAME
    if not fleet.is_file():
        raise SyncError(
            f"no {FLEET_FILENAME} in {folder}: a sync keeps {kept.holds} beside a "
            "setup, and there is none here"
        )
    texts = {
        "fleet_text": _read_text(fleet),
        "policy_text": _read_text(folder / POLICY_FILENAME),
        **{each.argument: _read_text(folder / each.filename) for each in KEPT},
    }
    try:
        config = _parse(folder, texts)
    except ConfigError as held:
        try:
            config = _parse(folder, {**texts, kept.argument: ""})
        except ConfigError as exc:
            raise SyncError(
                f"the setup in {folder} does not load: {held}; "
                f"read without {kept.filename}: {exc}"
            ) from exc
    return Setup(folder=folder, texts=texts, config=config)


def _parse(folder: Path, texts: Mapping[str, str]) -> Config:
    """The setup ``texts`` (by :func:`mcgyvr.config.parse` argument) load as."""
    return parse(
        texts["fleet_text"],
        texts["policy_text"],
        path=folder,
        relief_text=texts[RELIEF.argument],
        crew_text=texts[CREW.argument],
    )


def keep(
    setup: Setup,
    kept: Kept,
    text: str,
    *,
    held: Collection[str],
    listed: Collection[str],
) -> Path:
    """Write ``text`` whole as ``kept``'s file beside ``setup``, and return it.

    ``held`` are the names the file holds now and ``listed`` the ones the hub
    answered with. One a ladder step or a role binds that the hub no longer
    lists raises :class:`SyncError` naming it. The setup is loaded with
    ``text`` before anything is written, so an answer the setup would refuse
    raises :class:`HubAnswerError`. Either way the file is left as it was.
    """
    dropped = sorted(
        name for name in held if name in setup.config.bound and name not in listed
    )
    if dropped:
        raise SyncError(
            f"the hub no longer lends {', '.join(dropped)}, which a ladder step or "
            f"a role binds: unbind it and sync again; {kept.filename} is left as "
            "it was"
        )
    try:
        _parse(setup.folder, {**setup.texts, kept.argument: text})
    except ConfigError as exc:
        raise HubAnswerError(
            f"the hub's answer is refused: the setup would not load with it ({exc})"
        ) from exc
    target = setup.folder / kept.filename
    atomic.write(target, text)
    return target


def sync(
    folder: Path,
    hub: str,
    key: str,
    key_env: str,
    *,
    ride_scope: str | None = None,
    scoped: list[str] | None = None,
) -> tuple[Rides, Path]:
    """Sync once: report the setup's ladder, then write the answer beside it.

    The setup is read by :func:`load_setup`, its ladder reported, and the
    answer written by :func:`keep` as ``relief.yaml``, each rung under
    ``ride_scope`` (unsaid: the setup's): a relief rung a step or a role binds
    that the hub no longer lists, or an answer the setup would refuse, leaves
    the file as it was. A private setup raises :class:`PrivateSetupError`
    before anything is sent. Returns the answer read and the file it was
    written to; the scope the rungs were written under is put in ``scoped``
    when one is given; its ``unsealed`` names each rung the setup asked sealed
    that the answer lists with no key.
    """
    setup = load_setup(folder, RELIEF)
    own = setup.config
    if own.private:
        raise PrivateSetupError(
            f"the setup in {folder} is private (`private: true`): it rides no "
            "relief rung, so nothing is synced and the hub is sent nothing; set "
            "`private: false` in its policy to ride"
        )
    rides = fetch(hub, key, ladder_report(own))
    scope = ride_scope or own.ride_scope
    sealed_before = {name for name, unit in own.relief.items() if unit.seal is not None}
    rides = replace(
        rides,
        unsealed=tuple(
            each.name
            for each in rides.rungs
            if each.seal is None and each.name in sealed_before
        ),
    )
    target = keep(
        setup,
        RELIEF,
        render(rides, key_env, scope),
        held=[name for name, unit in own.units.items() if unit.relief],
        listed={each.name for each in rides.rungs},
    )
    if scoped is not None:
        scoped[:] = [scope]
    return rides, target


#: What each narrower ride scope means for the rungs a sync kept, as the sync
#: says it. The hub never lists a rider's own rigs as relief rungs, so under
#: `own` none of them can serve.
_WHOSE = {
    SCOPE_OWN: (
        "only your own rigs may take this setup's rides, and the hub never "
        "lists your own rigs as relief rungs, so no relief rung serves it; "
        "`--ride-scope crew` lets your crewmates' rigs take them"
    ),
    SCOPE_CREW: (
        "only your own and your crewmates' rigs take this setup's rides, and "
        "the hub refuses a host outside them"
    ),
}


def ride_scope_line(rides: Rides, scope: str) -> str | None:
    """The line a sync says about whose rigs take the rides of a setup under
    ride scope `scope`, `None` when it kept no rung or rides under `anyone`."""
    if not rides.rungs or scope == SCOPE_ANYONE:
        return None
    return (
        f"ride scope: {scope}: {_WHOSE[scope]}; `--ride-scope anyone` opts this "
        "setup in to any host"
    )


def unsealed_note(name: str) -> str:
    """What a sync says of a rung it asked sealed that the hub lists keyless."""
    return (
        f"note: relief rung {name} was asked sealed and the hub lists no key for "
        "it now, so it is asked in clear from here on (its host's agent or the "
        "hub may be older, or the hub dropped the key)"
    )


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="relief-rungs", daemon=True).start()


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class Refresher:
    """A sync kept fresh against a clock, one run at a time.

    :meth:`tick` decides whether a sync is due and hands the work to the thread
    ``start`` gives it, so the caller is never blocked. The next sync is due
    ``refresh_s`` after an answer, or ``RETRY_S`` after a failure, and a failure
    is said once rather than on every tick that follows it. What ``told`` makes
    of an answer (the ride-scope line a sync says) is said once too, and again
    only when it changes.
    """

    def __init__(
        self,
        *,
        sync: Callable[[], Rides],
        clock: Callable[[], float] = time.monotonic,
        say: Callable[[str], None] = _say,
        start: Callable[[Callable[[], None]], None] = _thread,
        told: Callable[[Rides], str | None] = lambda _: None,
        key_env: str = KEY_ENV,
    ) -> None:
        self._sync = sync
        self._told = told
        self._last_told: str | None = None
        self._clock = clock
        self._say = say
        self._start = start
        self._lock = threading.Lock()
        self._due: float | None = None
        self._going = False
        self._last_failure = ""
        #: The variable the key is read from, as the agent says when it starts.
        self.key_env = key_env

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
        line = self._told(rides)  # after: what it says never stops a sync
        with self._lock:
            fresh, self._last_told = line != self._last_told, line
        if fresh and line is not None:
            self._say(line)
        for name in rides.unsealed:
            self._say(unsealed_note(name))


def refresher_for(
    hub: str,
    *,
    environ: Mapping[str, str] = os.environ,
    folder: Path | None = None,
) -> Refresher | None:
    """A :class:`Refresher` for this machine, or ``None`` where no key is set.

    The setup synced is ``folder`` or, left unsaid, the config path the rig
    itself reads, and the key is read from the variable its ``relief.yaml``
    names (:func:`key_env`): that variable must hold a key or nothing is synced
    at all. Each run reads the name and the key again, since a sync by hand may
    have named another variable since, or the key been removed, and writes the
    name back as it read it. The refresher's ``key_env`` is the name read here.
    """

    def setup() -> Path:
        try:
            return folder if folder is not None else config_path()
        except ConfigError as exc:
            raise SyncError(str(exc)) from exc

    try:
        named = key_env(setup())
    except SyncError:
        named = KEY_ENV  # each run says what is wrong, once
    if not environ.get(named):
        return None
    scope = [RIDE_SCOPE]  # the setup's, as the last sync read it

    def once() -> Rides:
        where = setup()
        name = key_env(where)
        key = environ.get(name)
        if not key:
            raise SyncError(f"${name} is no longer set")
        rides, _ = sync(where, hub, key, name, scoped=scope)
        return rides

    return Refresher(
        sync=once,
        told=lambda rides: ride_scope_line(rides, scope[0]),
        key_env=named,
    )
