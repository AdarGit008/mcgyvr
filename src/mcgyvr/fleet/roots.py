"""Dev and live read different fleet locks, and a fleet moves one way: dev to live.

Owner, 2026-09-15: "(~/.mcgyvr/ for live), (records/fleet/ for dev) - 2
separate locks and fleets - data flows one way dev->live"; "stamped for live =
another fleet setup available for live (no overwrite, not in place of, new
folder new files)"; "~/.mcgyvr/fleets/<name>/   live can switch between fleets
runtime".

* The dev lock is committed in the checkout at ``records/fleet/`` — committing
  it is the approval.
* A live fleet is a folder of its own, ``~/.mcgyvr/fleets/<fleet>/``, written
  once by ``mcgyvr fleet promote`` and never in place.
* ``~/.mcgyvr/live.json`` names the fleet live runs (``mcgyvr fleet use``), and
  so the lock live reads. With no ``live.json`` there is no live lock.

Every reader of a lock asks :func:`lock_root`; none reads the working
directory, because a lock found there is a lock nobody promoted.
"""

from __future__ import annotations

import json
from pathlib import Path

#: mcgyvr's own directory on this machine.
HOME_DIR = "~/.mcgyvr"
#: Where each live fleet folder sits under it.
FLEETS_DIR = "fleets"
#: The pointer naming the fleet live runs.
LIVE_FILE = "live.json"
#: The two as help text names them.
FLEETS_SHOWN = f"{HOME_DIR}/{FLEETS_DIR}"
LIVE_FILE_SHOWN = f"{HOME_DIR}/{LIVE_FILE}"


class LiveFleetError(Exception):
    """``~/.mcgyvr/live.json`` is there and does not name a fleet."""


def home() -> Path:
    """``~/.mcgyvr``, expanded against the current HOME."""
    return Path(HOME_DIR).expanduser()


def fleets_dir() -> Path:
    """``~/.mcgyvr/fleets``: one folder per promoted fleet."""
    return home() / FLEETS_DIR


def live_file() -> Path:
    """``~/.mcgyvr/live.json``: which promoted fleet live runs."""
    return home() / LIVE_FILE


def is_fleet_name(name: str) -> bool:
    """Whether ``name`` can name one folder directly under the fleets directory."""
    return bool(name) and name not in (".", "..") and "/" not in name


def live_fleet() -> str | None:
    """The fleet ``live.json`` names, or ``None`` when there is no ``live.json``.

    A ``live.json`` that is there and names no fleet raises
    :class:`LiveFleetError`: a pointer nobody can read is not the same as no
    pointer, and live must not quietly run as if nothing were named.
    """
    path = live_file()
    if not path.is_file():
        return None
    try:
        named = json.loads(path.read_text(encoding="utf-8")).get("fleet")
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        raise LiveFleetError(f"{path} cannot be read: {exc}") from exc
    if not isinstance(named, str) or not is_fleet_name(named):
        raise LiveFleetError(f"{path} names no fleet: {named!r}")
    return named


def live_fleet_dir() -> Path | None:
    """The folder of the fleet ``live.json`` names, or ``None`` with none named."""
    named = live_fleet()
    return None if named is None else fleets_dir() / named


def lock_root(profile: str) -> Path | None:
    """The directory whose ``records/fleet/`` is the lock ``profile`` reads.

    ``live`` is the fleet folder ``~/.mcgyvr/live.json`` names, and ``None``
    when no fleet is named — no live lock, so live admits nothing. ``dev`` is
    the run root — ``$MCGYVR_RUN_ROOT`` when the door names one, else the
    checkout — which is :func:`mcgyvr.serving.run.run_root`, so the dev lock
    and the dev evidence are found under one directory.
    """
    if profile == "live":
        return live_fleet_dir()
    if profile == "dev":
        from mcgyvr.serving.run import run_root

        return run_root()
    raise ValueError(f"no fleet lock root for profile {profile!r}: live or dev")


def is_live(path: Path) -> bool:
    """Whether ``path`` is ``~/.mcgyvr`` or lies under it."""
    live = home().resolve()
    resolved = path.expanduser().resolve()
    return resolved == live or resolved.is_relative_to(live)
