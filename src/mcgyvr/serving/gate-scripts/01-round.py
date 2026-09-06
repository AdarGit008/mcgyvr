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
which profile it ran under. And a `serve up|down` under `dev` is refused here,
before any rig is read: the live ladder is prod's (R1, live outranks dev).
"""

from __future__ import annotations

import importlib.util
import os
import sys

from mcgyvr import config as configlib
from mcgyvr.serving.gatelib import door_required, export, refuse, root

#: What a config that says nothing runs as. Read from the schema and not
#: spelled here, so a moved default moves this gate with it.
LIVE = "live"
DEV = "dev"


def profile() -> tuple[str, str]:
    """The run's profile and the config it was read from (``none`` if none).

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
        return LIVE, "none"
    except configlib.ConfigError as error:
        refuse(
            f"gate 1: the config cannot be read: {error}. A run whose config "
            "cannot be read cannot say which profile it ran under, and nothing "
            "is measured under an unknown one"
        )
    return str(loaded.get("profile", LIVE)), str(loaded.path)


def main() -> int:
    door_required("gate 1")
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

    which, source = profile()
    serve = os.environ.get("RUN_SERVE")
    if serve and which == DEV:
        refuse(
            f"gate 1: this run is under a dev profile ({source}), and the live "
            f"ladder is not started or stopped under one: `serve {serve}` is "
            "prod's. Live outranks dev (owner, 2026-09-06). Run it under the "
            f"live config: unset {configlib.CONFIG_PATH_ENV}, or name "
            f"{configlib.user_config_path()}"
        )
    export("RUN_PROFILE", which)
    print(
        f"gate 1: round={round_id} product_sha256={digest[:16]}... "
        f"profile={which} (config: {source})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
