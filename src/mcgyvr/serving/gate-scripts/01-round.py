#!/usr/bin/env python3
"""gate 1 — name the round this run is measured under, opening one if needed.

Runs first and reaches no rig, so the round is settled before any rig time is
spent. A measurement taken against an unpinned tree is not comparable with any
other measurement, which makes it worse than no measurement: it looks like
evidence — so every run is stamped with a round that pins the tree it ran on.

It gets there by drawing the boundary rather than demanding it (owner,
2026-09-06). A round is a boundary in the record, not a permission to work: a
tree that has moved gets the next round opened for it here, pinned to the
revision about to run, and the run proceeds. What the pin is for is untouched —
two revisions never share a round — and this is exactly why the new round is
appended and the one that was open keeps the digest its own arms ran against.

THE PROFILE IS SETTLED HERE TOO, for the same reason: it is a fact about the
run that costs no rig time to know and that every later gate reads. The config
is the one `mcgyvr` itself would load — `$MCGYVR_CONFIG`, then `./mcgyvr.yaml`
under the run root, then `~/.mcgyvr/config/mcgyvr.yaml` — and its `profile:`
is exported as RUN_PROFILE. No config at all is `live` (owner's ruling R4: the
default is prod, and forgetting the variable lands there); a config that is
there and cannot be read, or a `$MCGYVR_CONFIG` naming a file that is not
there, is a refusal, because a run whose config cannot be read cannot say
which profile it ran under. Dev runs everything, `serve up` and `down`
included (the owner ruled N11 on 2026-09-10), and a live `serve up` is
admitted only for units the fleet lock names for this rig; a live
`serve down` is always admitted.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

from mcgyvr import config as configlib
from mcgyvr.serving.gatelib import DEV, door_required, export, refuse, root


def default_profile() -> str:
    """What a config that says nothing runs as: the schema's own default, so
    a moved default moves this gate with it rather than a literal here."""
    spec = configlib.field_at("profile")
    assert spec is not None and isinstance(spec.default, str)
    return spec.default


def profile() -> tuple[str, str, str]:
    """The run's profile, the config it was read from, and that config's digest.

    ``none`` for the last two when there is no config at all.

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
        return default_profile(), "none", "none"
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
    return str(loaded.get("profile")), str(loaded.path), loaded.digest()


def units_the_fleet_lock_names(rig: str) -> set[str]:
    """The containers the fleet lock names for ``rig``, read locally.

    The lock's combination records under ``records/fleet/rigs/<rig->/`` name
    each locked unit by its container. Gate 1 reaches no rig, so this is a
    read of committed files only: a live serve up is matched against the lock
    offline, before any rig time is spent.
    """
    rigs = root() / "records" / "fleet" / "rigs"
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
    any rig is read.
    """
    if serve != "up" or which == DEV:
        return
    host = os.environ.get("RUN_HOST", "")
    wanted = set(os.environ.get("RUN_SERVE_EXPECTED", "").split())
    locked = units_the_fleet_lock_names(host)
    missing = sorted(wanted - locked)
    if missing:
        refuse(
            f"gate 1: this live `serve up` names {', '.join(missing)}, which "
            f"the fleet lock for {host} does not name. A live run starts only "
            "units the fleet lock names (records/fleet/); re-lock from a "
            "passing dev run, or run this under a dev profile"
        )


def main() -> int:
    door_required("gate 1")
    # The profile first, and the round second: the round check may APPEND a
    # round to tools/bench/rounds.json when the tree moved (a boundary in the
    # record, and the door's job), while a run refused for its profile should
    # leave nothing behind at all — and the profile needs nothing from the
    # round to be judged.
    which, source, digest_of_config = profile()
    serve = os.environ.get("RUN_SERVE")
    if serve:
        refuse_unless_the_fleet_lock_names(serve, which)

    # tools/ is not a package, so product.py is reached by path. Loaded here and
    # not at module scope: a gate that failed to import would refuse with a
    # traceback instead of a rule.
    path = root() / "tools" / "bench" / "product.py"
    if not path.is_file():
        refuse(f"gate 1: {path} is missing; the round cannot be checked")
    spec = importlib.util.spec_from_file_location("bench_product", path)
    assert spec is not None and spec.loader is not None
    product = importlib.util.module_from_spec(spec)
    sys.modules["bench_product"] = product
    spec.loader.exec_module(product)

    try:
        round_id, digest = product.ensure_open()
    except product.ProductError as error:
        # What is left to refuse on is a rounds file that cannot be read or a
        # surface that cannot be digested — the run has no round to be stamped
        # with either way, and a run nobody can trace to a revision is the
        # thing this gate exists to prevent.
        refuse(f"gate 1: {error}. Nothing is measured against a round it has not got")

    if not round_id or not digest:
        refuse(
            f"gate 1: ensure_open() returned round={round_id!r} "
            f"digest={digest!r}; a round it cannot name is not a round it checked"
        )
    export("RUN_ROUND", round_id)
    export("RUN_PRODUCT_SHA256", digest)
    export("RUN_PROFILE", which)
    # The config's identity travels with the run (R2): gate 5 files it in the
    # envelope header and the default step stamps it, so a row can be traced
    # to the exact setup that produced it.
    export("RUN_CONFIG", source)
    export("RUN_CONFIG_DIGEST", digest_of_config)
    print(
        f"gate 1: round={round_id} product_sha256={digest[:16]}... "
        f"profile={which} config={digest_of_config} ({source})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
