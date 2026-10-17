""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

#
HOME_ENV = "MCGYVR_HOME"
HOME_DIR = "~/.mcgyvr"
#
#
#
DATA_ENV = "MCGYVR_DATA"
STATE_ENV = "XDG_STATE_HOME"
DATA_NAME = "mcgyvr"
DATA_DIR = f"~/.local/state/{DATA_NAME}"
#
FLEETS_DIR = "fleets"
#
#
LOCK_DIR = Path("lock")
#
SETUPS_DIR = "setup"
#
LIVE_FILE = "live.json"
#
#
FLEETS_SHOWN = f"${HOME_ENV}/{FLEETS_DIR} (default {HOME_DIR}/{FLEETS_DIR})"
LIVE_FILE_SHOWN = f"${HOME_ENV}/{LIVE_FILE} (default {HOME_DIR}/{LIVE_FILE})"
#
STAGING_SHOWN = (
    f"${DATA_ENV}/{SETUPS_DIR}/<run> (default {DATA_DIR}/{SETUPS_DIR}/<run>)"
)
#
#
RIGS_ENV = "MCGYVR_RIGS"
RIGS_DIR = "rigs"
#
#
RIGS_SHOWN = f"${RIGS_ENV} (default ${HOME_ENV}/{RIGS_DIR})"
#
TAG = "@"
#
#
_TAG_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-[2-9]|-[1-9]\d+)?$")


class LiveFleetError(Exception):
    ""


class FolderError(RuntimeError):
    ""


def _named(variable: str, default: str) -> Path | None:
    ""
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
    ""
    named = _named(HOME_ENV, HOME_DIR)
    return named if named is not None else Path(HOME_DIR).expanduser()


def data_home() -> Path:
    ""
    state = os.environ.get(STATE_ENV)
    under_state = (
        Path(state) / DATA_NAME if state and Path(state).is_absolute() else None
    )
    named = _named(DATA_ENV, DATA_DIR if under_state is None else str(under_state))
    if named is not None:
        return named
    return under_state if under_state is not None else Path(DATA_DIR).expanduser()


def staging_dir(run_id: str) -> Path:
    ""
    return data_home() / SETUPS_DIR / run_id


def fleets_dir() -> Path:
    ""
    return home() / FLEETS_DIR


def rigs_dir() -> Path:
    ""
    named = _named(RIGS_ENV, f"{HOME_ENV}/{RIGS_DIR}")
    return named if named is not None else home() / RIGS_DIR


def live_file() -> Path:
    ""
    return home() / LIVE_FILE


def split_name(name: str) -> tuple[str, str | None]:
    ""
    fleet, separator, tag = name.partition(TAG)
    return fleet, (tag if separator else None)


def layout_of(name: str) -> str:
    ""
    return split_name(name)[0]


def tagged(fleet: str, lock_date: str) -> str:
    ""
    return f"{fleet}{TAG}{lock_date}"


def is_tag_date(text: str) -> bool:
    ""
    matched = _TAG_DATE.match(text)
    if not matched:
        return False
    try:
        date.fromisoformat(matched.group(1))
    except ValueError:
        return False
    return True


def is_fleet_name(name: str) -> bool:
    ""
    fleet, tag = split_name(name)
    if not fleet or fleet in (".", "..") or "/" in name:
        return False
    return tag is None or is_tag_date(tag)


def live_fleet() -> str | None:
    ""
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
    ""
    named = live_fleet()
    return None if named is None else fleets_dir() / named


def runs_live(setup: Path | None) -> bool:
    ""
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
    ""
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise FolderError(f"{path} cannot be resolved: {exc}") from exc


def is_live(path: Path) -> bool:
    ""
    resolved = _resolved(path)
    return any(
        resolved.is_relative_to(_resolved(folder))
        for folder in (home(), Path(HOME_DIR))
    )
