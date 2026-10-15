#!/usr/bin/env python3
"""read, rig — one reading of the rig, held to the user's rig file, and filed.

Two readers go to the rig over the door's ssh, neither landing on its disk:
the one reader of the machine (:mod:`mcgyvr.serving.rigscan`, as ``python3 -I -B -``)
for its facts, its cards and its rig id, and the runtime reader
(``rig-units.sh``, on stdin to ``bash -s``) for every container and its
restart count, every card holder by pid and container, and each unit's sleep
and in-flight page.

**Compared, never acted on.** The rig is held to the user's own rig file
(:mod:`mcgyvr.serving.rigfile`) by gate 2's own user check, and a rig that is
not its file is refused with nothing filed. Unlike gate 2 this takes no
lease, tears down no displaced run and refuses no busy rig: a read is how a
serving rig is looked at.

**Filed** under the journal of the fleet read, the live one or with
``--fleet`` one of the run's setup, by :func:`mcgyvr.fleet.read.record`.
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
from pathlib import Path

from mcgyvr.serving import rigfile
from mcgyvr.serving.gatelib import (
    door_required,
    need,
    refuse,
    scan_read_command,
    ssh,
)

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
    from mcgyvr.fleet import harness, read

    host = need("RUN_HOST")
    run_id = need("RUN_READ_ID")
    probe = os.environ.get("RUN_READ_PROBE", "").split()
    load = os.environ.get("RUN_READ_LOAD") or None
    # `read --fleet F`: F of the setup the run's config was loaded from, which
    # read-01 exported as RUN_CONFIG ("none" when there was no config).
    fleet_name = os.environ.get("RUN_READ_FLEET") or None
    config = os.environ.get("RUN_CONFIG", "none")
    setup = None if config == "none" else Path(config)
    try:
        fleet = read.prepare(host, probe, load, fleet_name=fleet_name, setup=setup)
        args = read.reader_args(fleet, host)
    except read.ReadError as exc:
        refuse(f"read: {exc}. Nothing was read and nothing is filed")

    saved = rigfile.required(host, "read")

    try:
        scanned = ssh(host, scan_read_command(), timeout=READ_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        refuse(f"read: {host} did not answer in {READ_TIMEOUT_S}s; nothing is filed")
    if scanned.returncode != 0:
        refuse(f"read: {host} could not be read: {scanned.stderr.strip()[:500]}")
    try:
        machine = json.loads(scanned.stdout)
    except ValueError:
        refuse(f"read: the reader on {host} printed no reading; nothing is filed")

    units = (
        "set -- "
        + " ".join(shlex.quote(arg) for arg in args)
        + "\n"
        + (HERE / "rig-units.sh").read_text(encoding="utf-8")
    )
    try:
        done = ssh(host, "bash -s", timeout=READ_TIMEOUT_S, input=units)
    except subprocess.TimeoutExpired:
        refuse(f"read: {host} did not answer in {READ_TIMEOUT_S}s; nothing is filed")
    if done.returncode != 0:
        refuse(f"read: {host} could not be read: {done.stderr.strip()[:500]}")
    try:
        read.reading(machine, done.stdout)
        now = rigfile.from_reading(host, machine)
    except (read.ReadError, rigfile.RigFileError) as exc:
        refuse(f"read: {exc}")

    rigfile.door_check(host, saved, now, None, "read")

    source = Path(harness.__file__).read_text(encoding="utf-8")

    def measure(unit: str, spec: str) -> str | None:
        print(f"read: running the lock's harness for {unit} on {host}")
        return harness_on_rig(host, spec, source)

    try:
        recorded = read.record(
            host,
            machine,
            done.stdout,
            run_id=run_id,
            probe=probe,
            measure=measure,
            load=load,
            fleet_name=fleet_name,
            setup=setup,
        )
    except read.ReadError as exc:
        refuse(f"read: {exc}")

    seen = recorded.observed
    print(f"read: {host} rig_id={seen.rig_id} run_id={run_id}")
    if not fleet.locked:
        print(
            f"read: fleet {fleet.name} of the setup {fleet.folder}, not the live "
            "lock: rows filed locked=false, probe figures unjudged"
        )
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
