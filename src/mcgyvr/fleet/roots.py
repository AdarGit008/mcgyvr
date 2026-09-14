"""Two fleet locks: dev's in the checkout, live's under ``~/.mcgyvr``.

Owner, 2026-09-15: "(~/.mcgyvr/ for live), (records/fleet/ for dev) - 2
separate locks and fleets - data flows one way dev->live". The dev lock is
committed in the repository at ``records/fleet/`` — committing it is the
approval — and ``mcgyvr fleet promote`` copies a fleet from it into the live
root. Every reader of a lock asks :func:`lock_root` which root its profile
reads; none reads the working directory, because a lock found there is a lock
nobody promoted.
"""

from __future__ import annotations

from pathlib import Path

#: The live root: the live ``config/fleet.yaml`` and ``records/fleet/`` lock.
LIVE_ROOT = "~/.mcgyvr"


def lock_root(profile: str) -> Path:
    """The directory whose ``records/fleet/`` is the lock ``profile`` reads.

    ``live`` is ``~/.mcgyvr``, expanded against the current HOME. ``dev`` is
    the run root — ``$MCGYVR_RUN_ROOT`` when the door names one, else the
    checkout — which is :func:`mcgyvr.serving.run.run_root`, so the dev lock
    and the dev evidence are found under one directory.
    """
    if profile == "live":
        return Path(LIVE_ROOT).expanduser()
    if profile == "dev":
        from mcgyvr.serving.run import run_root

        return run_root()
    raise ValueError(f"no fleet lock root for profile {profile!r}: live or dev")


def is_live(path: Path) -> bool:
    """Whether ``path`` is the live root or lies under it."""
    live = lock_root("live").resolve()
    resolved = path.expanduser().resolve()
    return resolved == live or resolved.is_relative_to(live)
