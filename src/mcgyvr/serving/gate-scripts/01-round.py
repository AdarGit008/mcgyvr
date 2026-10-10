#!/usr/bin/env python3
"""gate 1 — name the profile this run is under.

Runs first and reaches no rig, so the profile is settled before any rig time
is spent. The config is the one `mcgyvr` itself would load — `$MCGYVR_CONFIG`,
then `./fleet.yaml`, then the live fleet folder the config folder's
`live.json` names — and its `profile:` is exported as RUN_PROFILE. No config
at all is `live` (owner's ruling R4: the default is prod, and forgetting the
variable lands there); a config that is there and cannot be read, or a
`$MCGYVR_CONFIG` naming a file that is not there, is a refusal, because a run
whose config cannot be read cannot say which profile it ran under. Dev runs
everything, `serve up` and `down` included (the owner ruled N11 on
2026-09-10), and a live `serve up` is admitted only for units the fleet lock
names for this rig; a live `serve down` is always admitted.

No round is opened or pinned: the round is the lab's. RUN_ROUND and
RUN_PRODUCT_SHA256 are exported as ``none``.
"""

from __future__ import annotations

import json
import os

from mcgyvr import config as configlib
from mcgyvr.fleet.roots import LiveFleetError, live_file, lock_root
from mcgyvr.serving.gatelib import (
    DEV,
    door_required,
    export,
    refuse,
)


def default_profile() -> str:
    """What a config that says nothing runs as: the schema's own default, so
    a moved default moves this gate with it rather than a literal here."""
    spec = configlib.field_at("profile")
    assert spec is not None and isinstance(spec.default, str)
    return spec.default


def profile() -> tuple[str, str]:
    """The run's profile and the config it was read from.

    ``none`` for the config when there is no config at all.

    Refuses on a config that is there and cannot be read, and on a named
    (``$MCGYVR_CONFIG``) config that is not there: both are files somebody
    chose, and a run that went on under some other profile would be the
    silent landing the profile exists to prevent. The absent *default* is
    the one silence: nobody chose it, and it is ``live``.
    """
    try:
        loaded = configlib.load()
    except configlib.ConfigMissingError as absent:
        if configlib.named_config_path() is not None:
            refuse(
                f"gate 1: {absent}. {configlib.CONFIG_PATH_ENV} names a config "
                "that is not there, and a run made under some other one would "
                "not be the run that was asked for. Nothing is measured under "
                "a profile nobody can name"
            )
        return default_profile(), "none"
    except configlib.ConfigError as error:
        refuse(
            f"gate 1: the config cannot be read: {error}. A run whose config "
            "cannot be read cannot say which profile it ran under, and nothing "
            "is measured under an unknown one"
        )
    except (OSError, RuntimeError) as error:
        # A `~nobody` in the variable, a working directory that went away:
        # a config the gate cannot even locate is refused with the reason,
        # not left as a traceback.
        refuse(
            f"gate 1: the config cannot be located: {error!r}. Nothing is "
            "measured under a profile nobody can name"
        )
    return str(loaded.get("profile")), str(loaded.path)


def units_the_fleet_lock_names(rig: str, which: str) -> set[str]:
    """The containers the ``which`` profile's fleet lock names for ``rig``.

    The lock's combination records under its rigs tree name each locked unit
    by its container, under the root the profile reads
    (:func:`mcgyvr.fleet.roots.lock_root`: for live, the fleet folder the
    config folder's ``live.json`` names, and no lock at all without one) and never
    under the run root. Gate 1 reaches no rig, so this is a read of local
    files only: a live serve up is matched against the lock offline, before
    any rig time is spent.
    """
    try:
        where = lock_root(which)
    except LiveFleetError as exc:
        refuse(f"gate 1: {exc}. A live run cannot say which fleet it serves")
    if where is None:
        return set()
    rigs = where / "records" / "fleet" / "rigs"
    if not rigs.is_dir():
        return set()
    locked: set[str] = set()
    for path in sorted(rigs.glob("*/cmb-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("rig") != rig:
            continue
        approved = record.get("approved")
        if not isinstance(approved, dict):
            continue
        for entry in approved.values():
            if not isinstance(entry, dict):
                continue
            container = entry.get("container")
            if isinstance(container, str) and container:
                locked.add(container)
    return locked


def refuse_unless_the_fleet_lock_names(serve: str, which: str) -> None:
    """A live ``serve up`` admits only units the fleet lock names for this rig.

    Dev runs everything, ``serve up`` and ``down`` included (the owner ruled N11
    on 2026-09-10), and a live ``serve down`` is always admitted: stopping
    starts nothing unapproved, and it is the way out of a rig left in a state
    nobody locked. A live ``serve up`` is the one direction that starts
    processes, so it is matched against the fleet lock here — offline, before
    any rig is read. A ``serve up --unit`` starts only the units it names, so
    only those are matched; a ``serve fetch`` starts nothing.
    """
    if serve != "up" or which == DEV:
        return
    host = os.environ.get("RUN_HOST", "")
    wanted = set(os.environ.get("RUN_SERVE_ONLY", "").split()) or set(
        os.environ.get("RUN_SERVE_EXPECTED", "").split()
    )
    locked = units_the_fleet_lock_names(host, which)
    missing = sorted(wanted - locked)
    if missing:
        refuse(
            f"gate 1: this live `serve up` names {', '.join(missing)}, which "
            f"the fleet lock for {host} does not name. A live run starts only "
            f"units the live fleet lock names — the fleet {live_file()} "
            "names; lock them from a passing dev run, `mcgyvr fleet promote` "
            "and `mcgyvr fleet use` the fleet, or run this under a dev profile"
        )


def main() -> int:
    door_required("gate 1")
    # The profile first, and the round second: the round check may APPEND a
    # round to the round record when the tree moved (a boundary in the record,
    # and the door's job), while a run refused for its profile should leave
    # nothing behind at all — and the profile needs nothing from the round to
    # be judged.
    which, source = profile()
    serve = os.environ.get("RUN_SERVE")
    if serve:
        refuse_unless_the_fleet_lock_names(serve, which)

    export("RUN_ROUND", "none")
    export("RUN_PRODUCT_SHA256", "none")
    export("RUN_PROFILE", which)
    export("RUN_CONFIG", source)
    print(f"gate 1: no round pinned; profile={which} config={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
