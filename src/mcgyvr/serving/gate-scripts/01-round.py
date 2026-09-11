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
from pathlib import Path

from mcgyvr import config as configlib
from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX
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


def live_compose_dir() -> Path | None:
    """Where the **live** config keeps its launch specs, or ``None`` if unsaid.

    Loaded separately from the run's own config, and that separation is the
    point: a dev round is running under a config ``$MCGYVR_CONFIG`` names, and
    the question being asked is about somebody else's file — the live ladder's.
    Reading ``serving.compose_dir`` off the dev config would let a dev round
    declare its own tree to be the live one, which is the composition guard
    turned inside out.

    A live config that is absent or unreadable answers ``None``, and ``None``
    refuses every dev serve: there is no live ladder to operate, so operating it
    is not what is being asked for.
    """
    where = configlib.user_config_path()
    if not where.is_file():
        return None
    try:
        live = configlib.parse(where.read_text(encoding="utf-8"), path=where)
    except (configlib.ConfigError, OSError):
        return None
    stated = live.get("serving.compose_dir")
    return Path(str(stated)).expanduser() if stated else None


def refuse_unless_the_live_ladders_own(serve: str, source: str) -> None:
    """A dev round may **operate** the live ladder. It may never **install** one.

    **The owner overturned this gate's profile check on 2026-09-09**
    (``records/plans/sleep-wake.md`` §11): dev gets sleep and wake too. What the
    old check refused was two different things at once, and only one of them was
    ever this gate's.

    *Composition* is the real one. ``serve up`` starts whatever compose file it
    is handed, and a dev config is by definition a setup under development —
    different models, a different ``--gpu-memory-utilization``, a different
    image digest. Bring that up on a shared rig and every later live run, and
    every live measurement, is against a ladder nobody declared.

    *Availability* is the other, and it is already covered elsewhere: gate 2
    refuses a ``dev`` run any rig another run holds, and refuses **any** run —
    dev or live — a rig that is not idle for ``serve up``. So the conflict this
    gate uniquely covers is the narrow one: a dev run acting on a card no other
    run holds.

    So the check keys on **whose launch spec is being run** rather than on whose
    profile is running it. ``RUN_COMPOSE`` must name a file inside the live
    config's ``serving.compose_dir``, under the *shape* of a name ``emit_all``
    produces — ``compose.`` … ``.yml`` — which refuses the ordinary mistake: a
    dev config's freshly-emitted ``compose.srv2.yml`` sitting in the dev tree is
    not in that directory, and is refused exactly as it is today.

    **It is a directory check, and calling it a provenance check would overstate
    it twice.** Both are stated rather than closed, because closing either is a
    behavioural change to a gate that guards a live rig.

    1. *Nothing here reads the file.* Any file named ``compose.*.yml`` that
       reaches the live ``compose_dir`` is started, whatever is inside it, and a
       dev round reaches that directory with ``mcgyvr emit --out
       ~/.mcgyvr/config``. Asking the planner instead — "is this one of the
       specs this config plans?" — would need units, and units need a scan,
       which is the cost this check was chosen to avoid.
    2. *A dev config can declare itself live.* ``configlib.user_config_path()``
       expands ``~`` against ``$HOME``, and the door builds this gate's
       environment as ``dict(os.environ)`` with ``HOME`` untouched, so
       repointing ``HOME`` makes a dev tree the "live" config and its own
       ``compose_dir`` the one being compared against.

    Neither is a regression: the ``profile: live`` check this replaced was
    defeated by exactly the same two moves. What traversal and symlinks cannot
    do is escape the directory — ``spec.resolve()`` is compared against
    ``kept.resolve()`` — and that part is genuinely closed.

    It costs no rig time and needs no scan: this gate already loads a config and
    already knows ``user_config_path()``, which it named in the very refusal
    being replaced. The refusal below names the **spec**, not the profile,
    because telling an operator to change their profile when what is wrong is
    which file they pointed at sends them to the wrong repair.

    **The residual, stated rather than hidden.** A dev run can now put the live
    ladder to sleep on a free rig, which is the thing R1 was written to prevent.
    Its price is bounded by the same design's own machinery: the live run that
    arrives afterwards finds the card asleep, is refused by the port and wakes
    it, so it pays one wake — 50 to 130 seconds — and not a failure, in an
    envelope of its own. Whether that price is acceptable is N11 and is the
    owner's; this gate implements the ruling, not N11's resolution.
    """
    named = os.environ.get("RUN_COMPOSE") or ""
    kept = live_compose_dir()
    spec = Path(named) if named else None
    if (
        kept is not None
        and spec is not None
        and spec.name.startswith(COMPOSE_PREFIX)
        and spec.name.endswith(COMPOSE_SUFFIX)
        and spec.resolve().parent == kept.resolve()
    ):
        return
    refuse(
        f"gate 1: this run is under a dev profile ({source}) and "
        f"`serve {serve}` was pointed at {named or '(no --compose)'}, which is "
        f"not one of the live ladder's own launch specs. A dev round may "
        f"operate the live ladder and may never install one: the spec has to "
        f"be a file `mcgyvr emit` wrote into the live config's "
        f"`serving.compose_dir`"
        + (
            f", which is {kept}"
            if kept is not None
            else f" — and the live config at {configlib.user_config_path()} "
            f"states no `serving.compose_dir`, so there is no live ladder to "
            f"operate"
        )
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
    if serve and which == DEV:
        refuse_unless_the_live_ladders_own(serve, source)

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
