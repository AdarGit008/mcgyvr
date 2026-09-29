"""Dev and live read different fleet locks, and a fleet moves one way: dev to live.

Owner, 2026-09-15: "(~/.mcgyvr/ for live), (records/fleet/ for dev) - 2
separate locks and fleets - data flows one way dev->live"; "stamped for live =
another fleet setup available for live (no overwrite, not in place of, new
folder new files)"; "~/.mcgyvr/fleets/<name>/   live can switch between fleets
runtime".

* The dev lock is committed in the checkout at ``records/fleet/`` — committing
  it is the approval.
* A live fleet is a folder of its own, ``~/.mcgyvr/fleets/<fleet>@<date>/``,
  written once by ``mcgyvr fleet promote`` and never in place. Owner,
  2026-09-16: "all fleets get tagged with date" — the date is the lock's own
  (:func:`mcgyvr.fleet.promote.lock_date`), and the folder's name is the only
  place it is spelled: inside, the fleet keeps its plain name, and
  :func:`layout_of` is how every reader gets from the one to the other. A
  folder promoted before the ruling has no tag, and reads the same way.
* ``~/.mcgyvr/live.json`` names the fleet live runs (``mcgyvr fleet use``), and
  so the lock live reads. With no ``live.json`` there is no live lock.

Every reader of a lock asks :func:`lock_root`; none reads the working
directory, because a lock found there is a lock nobody promoted.

Two folders on the machine mcgyvr runs on can each be moved by the user: the
config folder, for settings (:func:`home`: ``$MCGYVR_HOME``, else
``~/.mcgyvr``), and the data folder, for mcgyvr's own files
(:func:`data_home`: ``$MCGYVR_DATA``, else ``$XDG_STATE_HOME/mcgyvr``, else
``~/.local/state/mcgyvr``). ``~/.mcgyvr`` above is the config folder's
default.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

#: The variable that moves the config folder, and the folder when it is unset.
HOME_ENV = "MCGYVR_HOME"
HOME_DIR = "~/.mcgyvr"
#: The variable that moves the data folder; with it unset, the folder is
#: :data:`DATA_NAME` under the XDG state folder, whose own default is
#: :data:`DATA_DIR`'s parent.
DATA_ENV = "MCGYVR_DATA"
STATE_ENV = "XDG_STATE_HOME"
DATA_NAME = "mcgyvr"
DATA_DIR = f"~/.local/state/{DATA_NAME}"
#: Where each live fleet folder sits under the config folder.
FLEETS_DIR = "fleets"
#: The pointer naming the fleet live runs.
LIVE_FILE = "live.json"
#: The two under the config folder's default, for help text only: a refusal
#: names the file it read (:func:`live_file`).
FLEETS_SHOWN = f"{HOME_DIR}/{FLEETS_DIR}"
LIVE_FILE_SHOWN = f"{HOME_DIR}/{LIVE_FILE}"
#: What separates a fleet from the date of its lock in a promoted folder's name.
TAG = "@"
#: The date a tag carries: the lock's ``validated_at`` day, ``YYYY-MM-DD``.
_TAG_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LiveFleetError(Exception):
    """The config folder's ``live.json`` cannot be read or names no fleet.

    A config folder that cannot be located is one of these too: its
    ``live.json`` cannot be read.
    """


class FolderError(RuntimeError):
    """A variable that moves one of mcgyvr's folders names no usable folder.

    A ``RuntimeError``, as an unresolvable HOME already is for every reader of
    these folders.
    """


def _named(variable: str, default: str) -> Path | None:
    """The folder ``variable`` names, or ``None`` when it is unset or empty.

    Absolute after ``~`` is expanded, or refused: a relative folder is a
    different folder from each working directory, and the door's gates run
    from another directory than the command that opened it.
    """
    value = os.environ.get(variable)
    if not value:
        return None
    try:
        path = Path(value).expanduser()
    except RuntimeError as exc:
        raise FolderError(f"${variable}={value!r} cannot be expanded: {exc}") from exc
    if not path.is_absolute():
        raise FolderError(
            f"${variable}={value!r} is not an absolute path, so it would name "
            f"a different folder from each working directory; name the folder "
            f"by an absolute path, or unset {variable} to use {default}"
        )
    return path


def home() -> Path:
    """The config folder: ``$MCGYVR_HOME``, else ``~/.mcgyvr``.

    The lease a served machine keeps on itself never follows the variable: it
    is :data:`mcgyvr.serving.gatelib.LEASE_FILE`, named from that machine's own
    home. It lies in this folder only when the served machine is this one and
    the folder is at its default.
    """
    named = _named(HOME_ENV, HOME_DIR)
    return named if named is not None else Path(HOME_DIR).expanduser()


def data_home() -> Path:
    """The data folder: ``$MCGYVR_DATA``, else ``$XDG_STATE_HOME/mcgyvr``, else
    ``~/.local/state/mcgyvr``.

    An ``$XDG_STATE_HOME`` that is not absolute is ignored, as the XDG base
    directory convention says.
    """
    state = os.environ.get(STATE_ENV)
    under_state = (
        Path(state) / DATA_NAME if state and Path(state).is_absolute() else None
    )
    named = _named(DATA_ENV, DATA_DIR if under_state is None else str(under_state))
    if named is not None:
        return named
    return under_state if under_state is not None else Path(DATA_DIR).expanduser()


def fleets_dir() -> Path:
    """``<config folder>/fleets``: one folder per promoted fleet."""
    return home() / FLEETS_DIR


def live_file() -> Path:
    """``<config folder>/live.json``: which promoted fleet live runs."""
    return home() / LIVE_FILE


def split_name(name: str) -> tuple[str, str | None]:
    """``(fleet, date)`` of a live name: ``<fleet>@<YYYY-MM-DD>``, or ``<fleet>`` alone.

    The fleet is the layout's name — what ``fleet.yaml`` keys it by inside the
    folder — and the date is the tag, ``None`` for a folder promoted before
    the ruling. Nothing is checked here; :func:`is_fleet_name` does that.
    """
    fleet, separator, tag = name.partition(TAG)
    return fleet, (tag if separator else None)


def layout_of(name: str) -> str:
    """The layout a live name is a promotion of: its fleet, tag or no tag."""
    return split_name(name)[0]


def tagged(fleet: str, lock_date: str) -> str:
    """The live name of ``fleet`` promoted from a lock dated ``lock_date``."""
    return f"{fleet}{TAG}{lock_date}"


def is_tag_date(text: str) -> bool:
    """Whether ``text`` is a calendar day spelled ``YYYY-MM-DD``."""
    if not _TAG_DATE.match(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_fleet_name(name: str) -> bool:
    """Whether ``name`` can name one folder directly under the fleets directory.

    A fleet, or a fleet at a date: ``<fleet>`` or ``<fleet>@<YYYY-MM-DD>``.
    """
    fleet, tag = split_name(name)
    if not fleet or fleet in (".", "..") or "/" in name:
        return False
    return tag is None or is_tag_date(tag)


def live_fleet() -> str | None:
    """The fleet ``live.json`` names, or ``None`` when there is no ``live.json``.

    A ``live.json`` that is there and names no fleet raises
    :class:`LiveFleetError`: a pointer nobody can read is not the same as no
    pointer, and live must not quietly run as if nothing were named. A config
    folder that cannot be located raises it too, with the variable's refusal.
    """
    try:
        path = live_file()
    except FolderError as exc:
        raise LiveFleetError(str(exc)) from exc
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

    ``live`` is the fleet folder the config folder's ``live.json`` names, and
    ``None`` when no fleet is named — no live lock, so live admits nothing.
    ``dev`` is the run root — ``$MCGYVR_RUN_ROOT`` when the door names one,
    else the checkout — which is :func:`mcgyvr.serving.run.run_root`, so the
    dev lock and the dev evidence are found under one directory.
    """
    if profile == "live":
        return live_fleet_dir()
    if profile == "dev":
        from mcgyvr.serving.run import run_root

        return run_root()
    raise ValueError(f"no fleet lock root for profile {profile!r}: live or dev")


def is_live(path: Path) -> bool:
    """Whether ``path`` is the config folder or its default, or lies under either.

    The default stays guarded when the variable moves the folder: a server
    started without the variable reads its fleets there.
    """
    resolved = path.expanduser().resolve()
    return any(
        resolved.is_relative_to(folder)
        for folder in (home().resolve(), Path(HOME_DIR).expanduser().resolve())
    )
