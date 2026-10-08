#!/usr/bin/env python3
"""gate 7 — nothing of ours is left running, and the rig reads as it did.

RUNS AFTER THE STEP WHATEVER THE STEP DID, including a signal and including a
hard lock that took the ssh pipe with it. A step that dies before its own
end_stamp compares nothing, and the run whose end state is unknown is exactly
the one that ended silently — three of those on srv1 in one campaign, each
ending mid-log-stream with no OOM, no Xid and no shutdown record.

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

A RIG THAT MOVED IS STAMPED INTO THE ARTIFACTS. Rows produced under two
machines have to say so, so every TSV this run wrote gets a `### RIGMOVED`
line after the step's own `### END`; a non-TSV cannot carry the line and gets a
`<name>.RIGMOVED` sidecar instead. The stamp is `k=v` throughout
(`<key>=<after> <key>_start=<before>`), so the parser gate 8 runs next reads
it as a stamp and not as a loose token; and it lands on a line of its own even
when an interrupted step died mid-line.

`docker` here is the door's shim, so `docker ps` asks the RIG's daemon — the
same one gate 3 matched to the machine gate 2 read.

A STAMP LANDS ONLY IN ONE REGULAR FILE OF THE ENVELOPE. Before anything is
appended, every declared artifact is held to gatelib.artifact_escape: a
symlink, a hard link or a path resolving elsewhere is named — with where it
points — and left unstamped, and the run is not green. The envelope itself
must be a directory and not a link.

IN USER MODE (a door run from an install, ``--mode user``) the rig may run
things mcgyvr did not start, which gate 2 reported and admitted: a container
up before the run is not this run's leftover in any direction, and none is
touched. The compose file's own units are judged whatever was up before: a
`serve up` expects every one up, a `serve down` none.

A `serve up --unit` OR `serve down --unit` RUN (RUN_SERVE_ONLY) acts on the
named units alone, in either mode: those are judged whatever was up before
(an `up` expects each up, a `down` each gone), the file's other units are
left as they are and judged neither way, and anything else the run left is
named as on any run. A whole `serve up`, `sleep` or `wake` judges the file's
awake set: a service under a compose profile (RUN_SERVE_ASLEEP, a swap partner
that starts asleep) is left down by a whole `up` and judged neither way; a
whole `down` expects it gone like the rest. A `serve fetch` starts nothing, so
anything up after it that was not up before is named. And the run's log gets
its end, ``<RUN_ID>.end.json`` beside the header: the rig as read after the
step, the containers up, the units serving, what was left or missing, and how
the step exited.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.serving.gatelib import (
    USER_MODE,
    artifact_escape,
    displaced_by_run,
    door_required,
    envelope_escape,
    need,
    run_mode,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib.machinery import SourceFileLoader

#: Reuse gate 2's reader rather than keeping a second copy: a teardown that read
#: the rig differently from the gate that admitted it could not diff the two.
_rig = SourceFileLoader(
    "_gate02", str(Path(__file__).resolve().parent / "02-rig.py")
).load_module()

#: The keys hosts.json declares. `uptime_since` is added because a reboot is
#: the loudest possible "this is not the machine you measured on".
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
    if run_mode() != USER_MODE:
        return judge({}, user=False)
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
    # What this live run displaced at gate 2 (R1). A container of that run
    # that came back during the step — its step retrying a launch — is torn
    # down again here, by the name its lease gave it, and is not this run's
    # leftover: the displaced run is the one that left it. The units a
    # `serve up` declared are this run's, not the displaced run's, though
    # they share its `mcgyvr-` prefix, and are left running.
    displaced = displaced_by_run()
    if displaced is not None and displaced.run_id != "none":
        keep = frozenset(expected) if keeps else frozenset(untouched)
        _rig.teardown_displaced(need("RUN_HOST"), displaced, "gate 7", keep)
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
        post = _rig.snapshot(need("RUN_HOST"))
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

    # The reader's own account of the daemon, taken in the same breath as the
    # rest of the rig: a container it lists that `docker ps` did not is named
    # by id, so the two readings cannot disagree quietly.
    unseen = _ids(post.get("containers")) - before - set(up or {})
    if unseen:
        print(
            "gate 7: the rig's reader lists containers up after the step that "
            f"gate 2 read none of before it: {' '.join(sorted(unseen))} — a run "
            "that leaves a container is not green",
            file=sys.stderr,
        )
        status = 1

    moved = [key for key in COMPARED if pre.get(key) != post.get(key)]
    seen["moved"] = moved
    if moved:
        stamp = f"### RIGMOVED run_id={run_id} " + " ".join(
            f"{key}={post.get(key, 'unread')} {key}_start={pre.get(key, 'unread')}"
            for key in moved
        )
        print(
            "gate 7: THE RIG MOVED UNDER THIS RUN — "
            + ", ".join(f"{k} ({pre.get(k)} -> {post.get(k)})" for k in moved)
            + ". The rows were not all produced under one machine state; "
            f"{stamp!r} is stamped after the step's ### END and the run is not green",
            file=sys.stderr,
        )
        status = 1
        declared = json.loads(need("RUN_DECLARED"))
        appended = set(declared.get("RUN_APPENDS", []))
        state = json.loads(need("RUN_APPEND_STATE"))
        out_dir = Path(need("RUN_OUT_DIR"))
        escape = envelope_escape(out_dir)
        if escape is not None:
            print(f"gate 7: nothing is stamped: {escape}", file=sys.stderr)
            return 1
        for name in [n for names in declared.values() for n in names]:
            path = out_dir / name
            escape = artifact_escape(path, out_dir)
            if escape is not None:
                print(
                    f"gate 7: {name} is left unstamped: {escape}. A stamp lands "
                    "only in one regular file of the envelope, and a file "
                    "reached through a link is not this run's evidence",
                    file=sys.stderr,
                )
                continue
            if not path.exists():
                continue
            # An appended file is stamped only if THIS run actually added to it.
            if name in appended and path.stat().st_size == state.get(name, {}).get(
                "size"
            ):
                continue
            if path.suffix == ".tsv":
                # On its own line: a step that died mid-row (an interrupt, a
                # hard lock) leaves no trailing newline, and a stamp glued to
                # a half row is a stamp the parser never sees.
                raw = path.read_bytes()
                with path.open("a", encoding="utf-8") as handle:
                    if raw and not raw.endswith(b"\n"):
                        handle.write("\n")
                    handle.write(stamp + "\n")
            else:
                sidecar = path.with_name(path.name + ".RIGMOVED")
                escape = artifact_escape(sidecar, out_dir)
                if escape is not None:
                    print(
                        f"gate 7: {sidecar.name} is not written: {escape}",
                        file=sys.stderr,
                    )
                    continue
                sidecar.write_text(stamp + "\n", encoding="utf-8")
                print(
                    f"gate 7: {name} is not a TSV and is left readable; the "
                    f"stamp is beside it in {sidecar.name}",
                    file=sys.stderr,
                )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
