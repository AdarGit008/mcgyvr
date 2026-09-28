#!/usr/bin/env python3
"""read, rig — one reading of the rig, compared with its declaration, and filed.

One reader goes to the rig on stdin, ``rig-snapshot.sh`` then
``rig-units.sh``, over the door's ssh: the rig's facts and machine id,
every container and its restart count, every card holder by pid and container,
and each unit's sleep and in-flight page. Nothing lands on the rig's disk.

**Compared, never acted on.** The reading is held to
``tools/runs/hosts.json[HOST].rig`` by gate 2's own comparison (``02-rig.py``'s
``_matches``, loaded rather than copied), and a rig that is not its declaration
is refused with nothing filed. Unlike gate 2 this takes no lease, tears down no
displaced run and refuses no busy rig: a read is how a serving rig is looked at.

**Filed** under the live fleet's journal by :func:`mcgyvr.fleet.read.record`.
With ``--probe``, each idle unit named has the lock's own harness
(``mcgyvr/fleet/harness.py``) run on the rig as ``python3 -``, at 127.0.0.1
(:func:`harness_on_rig`).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, need, refuse, root, ssh

HERE = Path(__file__).resolve().parent
#: A reading of the rig, and a probe's harness run on it. A load's harness run has
#: none: see :func:`harness_on_rig`.
READ_TIMEOUT_S = 180
PROBE_TIMEOUT_S = 1800


def harness_on_rig(host: str, spec: str, source: str) -> str | None:
    """The lock's harness run on ``host`` over the door's ssh, its source on stdin.

    Its stdout, or ``None`` when a probe's run outlasts ``PROBE_TIMEOUT_S``. A load
    (spec ``mode`` ``load``) is run with no timeout: a load is held to its own
    ``harness.LOAD_LIMIT_S`` and its wait for the unit to read idle after the
    close has no time limit, so an ssh timeout here would cap both. The probes
    keep ``PROBE_TIMEOUT_S``.
    """
    from mcgyvr.fleet import harness

    try:
        asked = json.loads(spec)
    except ValueError:
        asked = None
    is_load = isinstance(asked, dict) and asked.get("mode") == "load"
    try:
        answered = ssh(
            host,
            f"python3 - {harness.HARNESS_WORD} {shlex.quote(spec)}",
            timeout=None if is_load else PROBE_TIMEOUT_S,
            input=source,
        )
    except subprocess.TimeoutExpired:
        return None
    return answered.stdout


def main() -> int:
    door_required("read")
    from mcgyvr.fleet import alerts, harness, read

    host = need("RUN_HOST")
    run_id = need("RUN_READ_ID")
    profile = need("RUN_PROFILE")
    probe = os.environ.get("RUN_READ_PROBE", "").split()
    load = os.environ.get("RUN_READ_LOAD") or None
    try:
        fleet = read.prepare(host, probe, load)
        args = read.reader_args(fleet, host)
    except read.ReadError as exc:
        refuse(f"read: {exc}. Nothing was read and nothing is filed")

    hosts_file = root() / "tools" / "runs" / "hosts.json"
    if not hosts_file.is_file():
        refuse(
            f"read: {hosts_file} is missing; there is no declaration to compare with"
        )
    declared = json.loads(hosts_file.read_text(encoding="utf-8")).get(host, {})
    if not isinstance(declared.get("rig"), dict):
        refuse(f"read: tools/runs/hosts.json declares no rig for {host}")

    reader = (
        "set -- "
        + " ".join(shlex.quote(arg) for arg in args)
        + "\n"
        + (HERE / "rig-snapshot.sh").read_text(encoding="utf-8")
        + "\n"
        + (HERE / "rig-units.sh").read_text(encoding="utf-8")
    )
    try:
        done = ssh(host, "bash -s", timeout=READ_TIMEOUT_S, input=reader)
    except subprocess.TimeoutExpired:
        refuse(f"read: {host} did not answer in {READ_TIMEOUT_S}s; nothing is filed")
    if done.returncode != 0:
        refuse(f"read: {host} could not be read: {done.stderr.strip()[:500]}")
    try:
        snapshot = read.parse(done.stdout).snapshot
    except read.ReadError as exc:
        refuse(f"read: {exc}")

    gate2 = SourceFileLoader("_gate02", str(HERE / "02-rig.py")).load_module()
    bad = [
        f"{key}: declared {value!r}, reads {snapshot.get(key)!r}"
        for key, value in declared["rig"].items()
        if not gate2._matches(key, value, snapshot.get(key))
    ]
    if bad:
        refuse(
            f"read: THIS MACHINE IS NOT THE DECLARED {host} — "
            + "; ".join(bad)
            + f". tools/runs/hosts.json[{host}].rig is what the rig was declared "
            "as; nothing is filed from a machine that is not it"
        )

    source = Path(harness.__file__).read_text(encoding="utf-8")

    def measure(unit: str, spec: str) -> str | None:
        print(f"read: running the lock's harness for {unit} on {host}")
        return harness_on_rig(host, spec, source)

    try:
        recorded = read.record(
            host,
            done.stdout,
            run_id=run_id,
            profile=profile,
            probe=probe,
            measure=measure,
            load=load,
        )
    except read.ReadError as exc:
        refuse(f"read: {exc}")
    except alerts.AlertError as exc:
        print(f"read: {exc}", file=sys.stderr)
        return 1

    seen = recorded.observed
    print(f"read: {host} rig_id={seen.rig_id} run_id={run_id}")
    for unit, state in sorted(seen.units.items()):
        print(f"read: unit {unit} {state}")
    for name in sorted(seen.card_mib):
        print(
            f"read: {name} card_mib={seen.card_mib[name]} "
            f"restarts={seen.restarts.get(name)} in_flight={seen.in_flight.get(name)}"
        )
    for holder in seen.foreign:
        print(f"read: not ours on the card: {holder}")
    for name, figures in recorded.probed.items():
        shown = ", ".join(f"{k} {v:.2f}" for k, v in figures.items())
        print(f"read: probed {name} on the rig: {shown}")
    for name, count in recorded.busy.items():
        print(f"read: busy {name}: {count} in flight, not probed")
    for name in recorded.contended:
        print(f"read: contended {name}: took work during the probe; filed, not judged")
    for name, row in recorded.loads.items():
        print(
            f"read: loaded {name} {row['spec']}: peak_mib={row['peak_mib']} "
            f"samples={row['samples']} completed={row['completed']}/{row['width']} "
            f"closed={row['closed_unfinished']} limit_s={row['limit_s']} "
            f"pace_prompt_tok_s={row['pace_prompt_tok_s']} "
            f"idle_after={row['idle_after']} "
            f"restarts {row['restarts_before']}->{row['restarts_after']}"
        )
    for name, why in recorded.unloaded.items():
        print(f"read: not loaded {name}: {why}")
    for alert in recorded.alerts:
        print(f"read: alert {alert.get('unit_id')} {alert.get('field')}")
    for name, why in recorded.failed.items():
        print(f"read: {name}: {why}", file=sys.stderr)
    return 1 if recorded.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
