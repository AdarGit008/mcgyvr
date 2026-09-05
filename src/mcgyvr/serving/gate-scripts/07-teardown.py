#!/usr/bin/env python3
"""gate 7 — nothing of ours is left running, and the rig reads as it did.

RUNS AFTER THE STEP WHATEVER THE STEP DID, including a signal and including a
hard lock that took the ssh pipe with it. A step that dies before its own
end_stamp compares nothing, and the run whose end state is unknown is exactly
the one that ended silently — three of those on srv1 in one campaign, each
ending mid-log-stream with no OOM, no Xid and no shutdown record.

A LEFTOVER CONTAINER IS NAMED, NOT KILLED. docker's name filter is a prefix
match, so `<RUN_ID>-` also covers a --suffix run of the same step; killing on
that basis could stop a container this invocation did not start. Run contract
§4: a cell never repairs a machine it found wrong. The kill is the operator's,
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
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import need

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


def main() -> int:
    status = 0
    run_id = need("RUN_ID")

    try:
        listed = subprocess.run(
            ["docker", "ps", "--filter", f"name=^{run_id}-", "--format", "{{.Names}}"],
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
        listed = None
    if listed is None or listed.returncode != 0:
        if listed is not None:
            print(
                "gate 7: 'docker ps' failed; whether the run left a container is "
                f"unknown. {listed.stderr.strip()[:300]}",
                file=sys.stderr,
            )
        status = 1
    elif listed.stdout.strip():
        left = " ".join(listed.stdout.split())
        print(
            f"gate 7: the step left containers named for this run: {left} — a "
            "run that leaves a container is not green (kill what you started: "
            "docker rm -f <name>)",
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

    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)
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
        for name in [n for names in declared.values() for n in names]:
            path = out_dir / name
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
                sidecar.write_text(stamp + "\n", encoding="utf-8")
                print(
                    f"gate 7: {name} is not a TSV and is left readable; the "
                    f"stamp is beside it in {sidecar.name}",
                    file=sys.stderr,
                )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
