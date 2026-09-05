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
Run contract §4: a cell never repairs a machine it found wrong. The kill is
the operator's, with the name in hand.

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
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import (
    artifact_escape,
    door_required,
    envelope_escape,
    need,
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
    before = set() if serve == "down" else _ids(pre.get("containers"))
    up = _containers_up()
    if up is None:
        status = 1
    else:
        left = {ident: name for ident, name in up.items() if ident not in before}
        if serve == "up":
            serving = {ident: name for ident, name in left.items() if name in expected}
            left = {ident: name for ident, name in left.items() if name not in expected}
            missing = sorted(expected - set(serving.values()))
            if serving:
                names = " ".join(sorted(serving.values()))
                print(f"gate 7: serving, as declared: {names}")
            if missing:
                print(
                    "gate 7: serve up ended with declared units not running: "
                    f"{' '.join(missing)} — the ladder is not up, and the run is "
                    "not green",
                    file=sys.stderr,
                )
                status = 1
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
