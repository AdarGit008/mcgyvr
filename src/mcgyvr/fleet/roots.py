"""The folders mcgyvr keeps its own files in, and what a fleet folder is named.

Promise: the config folder is ``$MCGYVR_HOME``, default ``~/.mcgyvr``, and the
data folder is ``$MCGYVR_DATA``, default ``mcgyvr`` under ``$XDG_STATE_HOME``,
default ``~/.local/state/mcgyvr``; either moves alone. Under those two, this
module names the promoted fleets, the user's rig files, the pointer that names
the live fleet, and the staging area a setup is sampled in before anything is
locked, and it settles whether a run is held to the live lock
(:func:`runs_live`). A fleet folder's name is a layout, optionally tagged with
the date of the lock it carries, so one fleet can be locked more than once
without its older folder being written over.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

#: The variable that moves the config folder, and the folder it names when
#: nothing does.
HOME_ENV = "MCGYVR_HOME"
HOME_DIR = "~/.mcgyvr"
#: The variable that moves the data folder, the convention's variable for state,
#: the folder taken under it, and the folder named when neither of the two is
#: set.
DATA_ENV = "MCGYVR_DATA"
STATE_ENV = "XDG_STATE_HOME"
DATA_NAME = "mcgyvr"
DATA_DIR = f"~/.local/state/{DATA_NAME}"
#: The config folder's own folder of promoted fleets, one folder per fleet.
FLEETS_DIR = "fleets"
#: The folder a setup or a fleet folder holds its locks in, one JSON file per
#: layout.
LOCK_DIR = Path("lock")
#: The data folder's staging area, where ``mcgyvr setup`` writes the run it is
#: sampling before any of it is locked.
SETUPS_DIR = "setup"
#: The pointer in the config folder that names the one fleet that is live.
LIVE_FILE = "live.json"
#: Those same places as help text names them: the variable that moves the config
#: folder, and the default it falls back to.
FLEETS_SHOWN = f"${HOME_ENV}/{FLEETS_DIR} (default {HOME_DIR}/{FLEETS_DIR})"
LIVE_FILE_SHOWN = f"${HOME_ENV}/{LIVE_FILE} (default {HOME_DIR}/{LIVE_FILE})"
#: The staging area as help text names it: the data folder, by variable and by
#: default, and the run's own folder under it.
STAGING_SHOWN = (
    f"${DATA_ENV}/{SETUPS_DIR}/<run> (default {DATA_DIR}/{SETUPS_DIR}/<run>)"
)
#: The variable that moves the user's rig files, and the folder inside the
#: config folder they sit in when nothing does.
RIGS_ENV = "MCGYVR_RIGS"
RIGS_DIR = "rigs"
#: The rig folder as help text names it: the variable, and the config folder's
#: own folder it defaults to.
RIGS_SHOWN = f"${RIGS_ENV} (default ${HOME_ENV}/{RIGS_DIR})"
#: What a fleet folder's name puts between the layout and the lock's date.
TAG = "@"
#: A lock date, with the count a later lock of the same day takes:
#: ``2026-10-15``, then ``2026-10-15-2``, ``2026-10-15-3``, and up.
_TAG_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-[2-9]|-[1-9]\d+)?$")


class LiveFleetError(Exception):
    """The live pointer cannot be read, or it names no fleet."""


class FolderError(RuntimeError):
    """A folder named in the environment cannot be expanded or resolved."""


def _named(variable: str, default: str) -> Path | None:
    """The folder ``variable`` names, or ``None`` when it names none.

    An empty value names no folder. A value that cannot be expanded, or that is
    not absolute — and so would name a different folder from each working
    directory — is refused in the variable's own name, and the refusal names
    ``default`` as the way out.
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
    """The config folder: ``$MCGYVR_HOME``, else ``~/.mcgyvr``."""
    named = _named(HOME_ENV, HOME_DIR)
    return named if named is not None else Path(HOME_DIR).expanduser()


def data_home() -> Path:
    """The data folder, which moves alone.

    ``$MCGYVR_DATA`` names it; failing that, ``mcgyvr`` under
    ``$XDG_STATE_HOME`` when that variable is absolute; failing both,
    ``~/.local/state/mcgyvr``.
    """
    state = os.environ.get(STATE_ENV)
    under_state = (
        Path(state) / DATA_NAME if state and Path(state).is_absolute() else None
    )
    named = _named(DATA_ENV, DATA_DIR if under_state is None else str(under_state))
    if named is not None:
        return named
    return under_state if under_state is not None else Path(DATA_DIR).expanduser()


def staging_dir(run_id: str) -> Path:
    """The folder the data folder stages one run in, by the run's id."""
    return data_home() / SETUPS_DIR / run_id


def fleets_dir() -> Path:
    """The config folder's own folder of promoted fleets."""
    return home() / FLEETS_DIR


def rigs_dir() -> Path:
    """The user's rig files: ``$MCGYVR_RIGS``, else the config folder's ``rigs``."""
    named = _named(RIGS_ENV, f"{HOME_ENV}/{RIGS_DIR}")
    return named if named is not None else home() / RIGS_DIR


def live_file() -> Path:
    """The pointer in the config folder that names the live fleet."""
    return home() / LIVE_FILE


def split_name(name: str) -> tuple[str, str | None]:
    """The layout a fleet folder's name holds, and its tag if it carries one.

    The tag is everything after the first ``@``; a name with no ``@`` has none.
    """
    fleet, separator, tag = name.partition(TAG)
    return fleet, (tag if separator else None)


def layout_of(name: str) -> str:
    """The layout named by a fleet folder's name, tagged or not."""
    return split_name(name)[0]


def tagged(fleet: str, lock_date: str) -> str:
    """A fleet folder's name for a layout locked on ``lock_date``."""
    return f"{fleet}{TAG}{lock_date}"


def is_tag_date(text: str) -> bool:
    """Whether ``text`` is a lock date, with or without a later lock's count."""
    matched = _TAG_DATE.match(text)
    if not matched:
        return False
    try:
        date.fromisoformat(matched.group(1))
    except ValueError:
        return False
    return True


def is_fleet_name(name: str) -> bool:
    """Whether ``name`` can name a fleet folder.

    The layout must be there and must be neither ``.`` nor ``..``, no part of
    the name may hold a ``/`` — a fleet folder sits directly under
    :func:`fleets_dir` — and a tag, if there is one, must be a lock date.
    """
    fleet, tag = split_name(name)
    if not fleet or fleet in (".", "..") or "/" in name:
        return False
    return tag is None or is_tag_date(tag)


def live_fleet() -> str | None:
    """The fleet the live pointer names, or ``None`` when there is no pointer."""
    try:
        path = live_file()
    except FolderError as exc:
        raise LiveFleetError(str(exc)) from exc
    try:
        if not path.is_file():
            return None
        named = json.loads(path.read_text(encoding="utf-8")).get("fleet")
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        raise LiveFleetError(f"{path} cannot be read: {exc}") from exc
    if not isinstance(named, str) or not is_fleet_name(named):
        raise LiveFleetError(f"{path} names no fleet: {named!r}")
    return named


def live_fleet_dir() -> Path | None:
    """The live fleet's folder, or ``None`` when no fleet is live."""
    named = live_fleet()
    return None if named is None else fleets_dir() / named


def runs_live(setup: Path | None) -> bool:
    """Whether a run under ``setup`` is held to the live fleet's lock.

    A setup in the data folder — the staging ``mcgyvr setup`` samples before
    anything of it is locked — is held to nothing, live fleet or none. Any
    other setup, including one held in memory (``None``), is held whenever a
    fleet is live; with none live, it is held only inside the config folder.
    A folder or a pointer that cannot be read counts as held, so a state this
    cannot make out never unguards a run.
    """
    try:
        if setup is not None and _resolved(setup).is_relative_to(
            _resolved(data_home())
        ):
            return False
        if live_fleet() is not None:
            return True
        return setup is not None and is_live(setup)
    except (FolderError, LiveFleetError, RuntimeError):
        return True


def _resolved(path: Path) -> Path:
    """``path`` with the home expanded and every link followed, or a refusal."""
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise FolderError(f"{path} cannot be resolved: {exc}") from exc


def is_live(path: Path) -> bool:
    """Whether ``path`` sits in the config folder.

    Both the folder the environment names and the default one count, the way a
    command started without the variable still reads its fleets there.
    """
    resolved = _resolved(path)
    return any(
        resolved.is_relative_to(_resolved(folder))
        for folder in (home(), Path(HOME_DIR))
    )
