"""What names the live fleet, read by the command line."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from mcgyvr.config import (
    Config,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


def _live(config: Config) -> bool:
    """Whether a command run under ``config`` is held to the live fleet's lock.

    It is whenever a fleet is live, but under a setup in the data folder: the
    staging folder ``mcgyvr setup`` starts and samples before anything of it is
    locked, which is admitted against nothing
    (:func:`mcgyvr.fleet.roots.runs_live`).
    """
    from mcgyvr.fleet.roots import runs_live

    return runs_live(config.path)


def _admitted_live(config: Config) -> str | None:
    """``None`` when live admission admits this command, else why not, printed.

    Each rig of the live fleet is read through the door and held to the lock
    (:func:`mcgyvr.fleet.admission.admit`), and a unit on a rig in ``config``,
    the config the command loaded, must be one the live fleet lays out there. A
    plan to clean or restore refuses, and the door commands that would carry it
    out are printed and not run: that a live command carries its plan out is not
    decided.
    """
    from mcgyvr.fleet.admission import admit
    from mcgyvr.fleet.admit import LiveRefusedError

    try:
        admission = admit(units=config.get("units") or {})
    except LiveRefusedError as exc:
        detail = f"live admission: {exc}"
        print(f"refused: {detail}", file=sys.stderr)
        return detail
    if admission.admitted:
        return None
    detail = (
        f"live admission: the rigs of {admission.fleet} do not read as locked; "
        "nothing was cleaned or restored, and these door commands would do it"
    )
    print(f"refused: {detail}:", file=sys.stderr)
    for line in admission.commands:
        print(f"  {line}", file=sys.stderr)
    return detail
