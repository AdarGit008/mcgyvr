#!/usr/bin/env python3
# Gate 7 of a serve run: it names the containers the step left up, holds the
# rig's card to gate 2's reading, and files the run's end record. It removes
# nothing — the kill is the operator's, with the name in hand.
"""Gate 7 of the door's ladder: what the step left, and how the run ended.

It runs after gate 6 whatever the step did, and reads two views of the one
host the door named: `docker ps`, for the id and name of every container up,
and the rig's runtime reader over ssh, for the card and the containers it
lists. What it finds is held to the containers the compose file declares
(`RUN_SERVE_EXPECTED`, less the `RUN_SERVE_ASLEEP` sleepers) and to the
reading gate 2 took before the step (`RUN_PRE_RIG`): a container gate 2 read
none of, a judged unit still up after `serve down`, a judged unit missing
after `up`/`sleep`/`wake`, or a `COMPARED` key that moved each print one
`gate 7:` line on stderr and make the gate exit 1. No container is removed.

Either way `file_end` files the run's end as `<RUN_ID>.end.json` in
`RUN_OUT_DIR`, once and never again.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.serving.gatelib import (
    artifact_escape,
    door_required,
    envelope_escape,
    need,
)
from mcgyvr.serving.rigread import snapshot

# The card and daemon keys gate 7 holds a run to: gate 2 read them before the
# step and gate 7 reads them again after it, so a key that differs is the rig
# having moved under the run — filed as `rig_moved` in the end record, said in
# one line on stderr, and the run is not green.
COMPARED = (
    "uptime_since",
    "cpu_max_mhz",
    "cpu_model",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "gpu_name",
    "gpu_vram_mib",
    "gpu_cc",
    "driver",
    "gpu_reserve_mib",
    "docker",
)


def _ids(reading: str | None) -> set[str]:
    """The container ids in one rig reading, as a set.

    The runtime reader writes `containers=` as ids joined by `;`, or the word
    `none` when nothing holds the rig; an absent reading has no ids at all.
    """
    return {part for part in (reading or "").split(";") if part and part != "none"}


def _containers_up() -> dict[str, str] | None:
    """Every container up, as id -> name, from one `docker ps` on the rig.

    The call carries no name filter: gate 7 asks what is up, not what is up
    under this run's prefix, since a step that named its container something
    else still left it standing. None comes back when the daemon did not answer
    in 120s or the call failed — whether the run left a container is then
    unknown, which is said on stderr and leaves the caller holding the run not
    green.
    """
    try:
        listed = subprocess.run(
            ["docker", "ps", "--format", "{{.ID}}\t{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            "gate 7: 'docker ps' did not answer in 120s; whether the run left a "
            "container is unknown",
            file=sys.stderr,
        )
        return None
    if listed.returncode != 0:
        print(
            "gate 7: 'docker ps' failed; whether the run left a container is "
            f"unknown. {listed.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        return None
    up: dict[str, str] = {}
    for line in listed.stdout.splitlines():
        if not line.strip():
            continue
        ident, _, name = line.partition("\t")
        up[ident.strip()] = name.strip() or ident.strip()
    return up


def main() -> int:
    door_required("gate 7")
    seen: dict[str, object] = {
        "run_id": need("RUN_ID"),
        "step_exit": os.environ.get("RUN_STEP_EXIT") or "unknown",
    }
    status = 1
    try:
        status = judge(seen, user=True)
    finally:
        seen["teardown_exit"] = status
        file_end(seen)
    return status


def file_end(seen: dict[str, object]) -> None:
    """File the run's end as `<RUN_ID>.end.json` in the run's envelope.

    `seen` is everything gate 7 decided about the run, plus the `ended_at`
    stamped here. The file is opened `x`, so a run's end is filed exactly once:
    a second call says it is already filed and writes nothing. A folder or path
    that escapes the envelope — a symlinked directory or file, a hard link, a
    name landing elsewhere — is said on stderr, and nothing is written there.
    """
    out_dir = Path(need("RUN_OUT_DIR"))
    path = out_dir / f"{need('RUN_ID')}.end.json"
    escape = envelope_escape(out_dir) or artifact_escape(path, out_dir)
    if escape is not None:
        print(f"gate 7: the run's end is not filed: {escape}", file=sys.stderr)
        return
    seen["ended_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(seen, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        print(
            f"gate 7: {path.name} is already filed; not written again", file=sys.stderr
        )


def judge(seen: dict[str, object], *, user: bool) -> int:
    """Hold the run to what it left on the rig, and answer the run's status.

    `seen` collects what the gate read, for the end record: `only` when a
    `--unit` run judged a subset, `containers_up`, `serving`, `missing`,
    `left`, `rig_after` and `rig_moved`. The return is 0 when the rig reads as
    gate 2 read it and nothing the run is held to is left up, 1 otherwise.

    `user` marks the door's own teardown of a serve run, which `main` is: it
    makes a judged unit that gate 2 already read before the step count as this
    run's too, since by the end it had to be serving or stopped.
    """
    status = 0
    run_id = need("RUN_ID")
    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)

    # The shape of the run, from the environment the door exported: the
    # direction it serves, and the containers the compose file declares. A
    # `fetch`, `read` or `link` run serves nothing, so both are empty there and
    # no container is judged for it — its step's leftovers are still named.
    serve = os.environ.get("RUN_SERVE", "")
    expected = set(os.environ.get("RUN_SERVE_EXPECTED", "").split())
    # A `--unit` run of `up` or `down` moves only the units it named, so it is
    # judged on exactly those and the file's other containers are untouched
    # (neither expected up nor named as left). `sleep` and `wake` with `--unit`
    # still need the awake ladder up, so they are judged on all of it.
    alone = serve in ("up", "down") and bool(
        os.environ.get("RUN_SERVE_ONLY", "").split()
    )
    judged = set(os.environ.get("RUN_SERVE_ONLY", "").split()) if alone else expected
    # A whole `up`, `sleep` or `wake` is judged on the awake units only: a
    # sleeper under a compose profile is neither expected up nor named as
    # missing, and what `expected` holds beyond `judged` is untouched.
    if not alone and serve in ("up", "sleep", "wake"):
        judged = expected - set(os.environ.get("RUN_SERVE_ASLEEP", "").split())
    untouched = expected - judged
    seen["only"] = sorted(judged) if alone else []
    # `opened_busy`: the directions that reach a ladder something else left up,
    # so gate 2's reading is not necessarily this run's work. `keeps`: the
    # directions that leave the ladder up, so a judged unit should be serving
    # when the step ends rather than gone.
    opened_busy = serve in ("down", "sleep", "wake")
    keeps = serve in ("up", "sleep", "wake")
    # What gate 2 read before the step, by container id: a container already up
    # then is not one this run left — except on a busy-opened ladder with
    # neither the door's teardown (`user`) nor a `--unit` run asking, where
    # nothing is excused.
    before = (
        set() if opened_busy and not (user or alone) else _ids(pre.get("containers"))
    )
    up = _containers_up()
    if up is None:
        status = 1
    else:
        # Left: what gate 2 read none of before the step, plus — for the door's
        # teardown or a `--unit` run — the judged units gate 2 did read, since
        # those had to be serving or stopped by now.
        left = {
            ident: name
            for ident, name in up.items()
            if name not in untouched
            and (ident not in before or ((user or alone) and name in judged))
        }
        seen["containers_up"] = sorted(up.values())
        if keeps:
            serving = {ident: name for ident, name in left.items() if name in judged}
            left = {ident: name for ident, name in left.items() if name not in judged}
            missing = sorted(judged - set(serving.values()))
            seen["serving"] = sorted(serving.values())
            seen["missing"] = missing
            if serving:
                names = " ".join(sorted(serving.values()))
                print(f"gate 7: serving, as declared: {names}")
            if missing:
                print(
                    f"gate 7: serve {serve} ended with declared units not running: "
                    f"{' '.join(missing)} — the ladder is not up, and the run is "
                    "not green",
                    file=sys.stderr,
                )
                status = 1
        seen["left"] = sorted(left.values())
        # Judged units still up after `down`: the step was asked to stop them
        # and did not.
        stuck = sorted(name for name in left.values() if name in judged)
        if stuck:
            print(
                f"gate 7: serve {serve} ended with named units still up: "
                f"{' '.join(stuck)} — they were not stopped, and the run is not "
                "green",
                file=sys.stderr,
            )
            status = 1
        left = {ident: name for ident, name in left.items() if name not in judged}
        if left:
            yours = [n for n in left.values() if n.startswith(f"{run_id}-")]
            others = [n for n in left.values() if not n.startswith(f"{run_id}-")]
            described = []
            if yours:
                described.append(f"named for this run: {' '.join(sorted(yours))}")
            if others:
                described.append(
                    "NOT named for this run (no "
                    f"{run_id}- prefix): {' '.join(sorted(others))}"
                )
            print(
                "gate 7: the step left containers up that gate 2 read none of "
                f"before it — {'; '.join(described)} — a run that leaves a "
                "container is not green, and one it did not name is still one "
                "it left (kill what you started: docker rm -f <name>)",
                file=sys.stderr,
            )
            status = 1

    try:
        post = snapshot(need("RUN_HOST"))
    except SystemExit:
        # `snapshot` — and the `need` it calls — says a rig that cannot be read
        # through `refuse()`, which raises `SystemExit`; caught here so the run
        # is still ended and judged not green rather than dying mid-teardown.
        print(
            "gate 7: the rig could not be re-read after the step; its end "
            "state is unknown and the run is not green",
            file=sys.stderr,
        )
        return 1
    seen["rig_after"] = post

    # The rig's runtime reader is a second view of the same host. What it lists
    # now that neither gate 2's reading nor `docker ps` carried is a container
    # the step left, however `docker ps` came to miss it.
    unseen = _ids(post.get("containers")) - before - set(up or {})
    if unseen:
        print(
            "gate 7: the rig's reader lists containers up after the step that "
            f"gate 2 read none of before it: {' '.join(sorted(unseen))} — a run "
            "that leaves a container is not green",
            file=sys.stderr,
        )
        status = 1

    moved = {
        key: {"before": pre.get(key), "after": post.get(key)}
        for key in COMPARED
        if pre.get(key) != post.get(key)
    }
    if moved:
        seen["rig_moved"] = moved
        print(
            "gate 7: rig changed during the run: "
            + ", ".join(
                f"{key} {change['before']} -> {change['after']}"
                for key, change in moved.items()
            ),
            file=sys.stderr,
        )
        status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
