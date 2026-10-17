#
""

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
#
#
READ_TIMEOUT_S = 180
PROBE_TIMEOUT_S = 1800


def harness_on_rig(host: str, spec: str, source: str) -> str | None:
    ""
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
    #
    #
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
