#!/usr/bin/env python3
"""gate 7 — nothing of ours is left running, and the rig reads as it did.

RUNS AFTER THE STEP WHATEVER THE STEP DID, including a signal and including a
hard lock that took the ssh pipe with it. A step that dies compares nothing,
and the run whose end state is unknown is exactly the one that ended
silently, each ending mid-log-stream with no OOM, no Xid and no shutdown
record.

A LEFTOVER CONTAINER IS NAMED, NOT KILLED. The set of containers up AFTER the
step is compared with the set gate 2 read BEFORE it (`containers=` in the
snapshot, which gate 2 holds to `none`): anything up now that was not up then
is named, whatever it is called, and the run is not green. The `<RUN_ID>-`
prefix is only the label of "yours" — a step once left a container without
it and the prefix filter alone called the run clean. docker's name filter is
a prefix match, so `<RUN_ID>-` also covers a --suffix run of the same step;
killing on that basis could stop a container this invocation did not start.
The door does not repair a machine it found wrong: the kill is the operator's,
with the name in hand.

A RIG THAT MOVED IS FILED IN THE RUN'S END. What a run wrote under two
machine states has to say so: each `COMPARED` key that reads differently after
the step is filed in the run's end record as `rig_moved`
(`{"<key>": {"before": ..., "after": ...}}`, absent when nothing moved), the
run's output says it in one line, and the run is not green. The artifacts are
left as the step wrote them.

`docker` here is the door's shim, so `docker ps` asks the RIG's daemon — the
same one gate 3 matched to the machine gate 2 read.

The rig may run things mcgyvr did not start, which gate 2 reported and
admitted: a container up before the run is not this run's leftover in any
direction, and none is touched. The compose file's own units are judged
whatever was up before: a `serve up` expects every one up, a `serve down` none.

A `serve up --unit` OR `serve down --unit` RUN (RUN_SERVE_ONLY) acts on the
named units alone: those are judged whatever was up before
(an `up` expects each up, a `down` each gone), the file's other units are
left as they are and judged neither way, and anything else the run left is
named as on any run. A whole `serve up`, `sleep` or `wake` judges the file's
awake set: a service under a compose profile (RUN_SERVE_ASLEEP, a swap partner
that starts asleep) is left down by a whole `up` and judged neither way; a
whole `down` expects it gone like the rest. A `serve fetch` starts nothing, so
anything up after it that was not up before is named. And the run's log gets
its end, ``<RUN_ID>.end.json`` beside the header: the rig as read after the
step, the containers up, the units serving, what was left or missing, what of
the rig moved, and how the step exited.
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


#: The snapshot keys (:data:`mcgyvr.serving.rigscan.SNAPSHOT_KEYS`) a run is held
#: to from start to end. `uptime_since` is among them because a reboot is the
#: loudest possible "this is not the machine you measured on".
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
    """The container ids a snapshot's `containers=` names; `none` is none."""
    return {part for part in (reading or "").split(";") if part and part != "none"}


def _containers_up() -> dict[str, str] | None:
    """Every container the rig's daemon lists now, id -> name, or None if the
    daemon could not be asked (which is a finding of its own)."""
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
    """Write a user-mode run's end, once, beside its header in the envelope."""
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
    """Gate 7's judgement, with what it read kept in ``seen`` for a user's log."""
    status = 0
    run_id = need("RUN_ID")
    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)

    # AFTER against BEFORE. Gate 2 read `containers=` before the step and
    # refused unless it was `none`, so whatever is up now the step left —
    # named for this run or not. A serve run reads differently, and says so
    # in its own vocabulary: `serve up` EXPECTS the containers the door read
    # from the compose file, and every one of them, while `serve down`
    # opened on a busy daemon and expects it empty — so there `before` is
    # not a licence, and anything up at all is named.
    serve = os.environ.get("RUN_SERVE", "")
    expected = set(os.environ.get("RUN_SERVE_EXPECTED", "").split())
    # `serve up|down --unit` acts on the named units alone: they are judged,
    # up after an `up` and gone after a `down`, whatever was up before, and
    # the file's other units are left as they are, up or not, and judged
    # neither way. Anything else the run left is named as for any run.
    alone = serve in ("up", "down") and bool(
        os.environ.get("RUN_SERVE_ONLY", "").split()
    )
    judged = set(os.environ.get("RUN_SERVE_ONLY", "").split()) if alone else expected
    # A whole `up` leaves the file's sleepers down (a compose profile), and
    # `sleep` and `wake` act on what is up: those runs judge the awake set,
    # and a sleeper is judged neither way. A whole `down` takes them too.
    if not alone and serve in ("up", "sleep", "wake"):
        judged = expected - set(os.environ.get("RUN_SERVE_ASLEEP", "").split())
    untouched = expected - judged
    seen["only"] = sorted(judged) if alone else []
    # `sleep` and `wake` open on a serving rig as `down` does, and end with
    # the declared containers running as `up` does: the units keep their
    # process through both.
    opened_busy = serve in ("down", "sleep", "wake")
    keeps = serve in ("up", "sleep", "wake")
    # A user's rig may hold containers mcgyvr did not start: what was up
    # before the run is no leftover of it, in any direction. Nor, on a
    # `--unit` run, is a container up before it.
    before = (
        set() if opened_busy and not (user or alone) else _ids(pre.get("containers"))
    )
    up = _containers_up()
    if up is None:
        status = 1
    else:
        # A unit of the compose file is judged whatever was up before.
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
        # A unit a `serve down --unit` named and did not take down.
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
        # `snapshot` refuses by exiting; here that is a finding and not a
        # refusal — the run is simply not green, and gate 8 still runs.
        print(
            "gate 7: the rig could not be re-read after the step; its end "
            "state is unknown and the run is not green",
            file=sys.stderr,
        )
        return 1
    seen["rig_after"] = post

    # The runtime reader's own account of the daemon (rig-units.sh, read with
    # the rest of the rig): a container it lists that `docker ps` did not is
    # named by id, so the two readings cannot disagree quietly.
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
