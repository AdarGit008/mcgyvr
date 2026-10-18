#!/usr/bin/env python3
# Gate 3 of a serve run. It runs the `docker` client on PATH and refuses the
# run unless the daemon that client reaches names itself the machine gate 2
# read, so no tag is resolved through one daemon while the container starts on
# another. No image is pulled and no container is started here.
"""Gate 3 of a serve run: the `docker` that resolves image tags has to answer,
and has to be the daemon on the machine gate 2 read.

The gate uses the `docker` on PATH, so the daemon asked is whichever one that
client is pointed at — on a door standing on the rig, the rig's own. It asks
that daemon for its name with `docker info --format {{.Name}}` and compares it
with the `hostname=` gate 2 exported in RUN_PRE_RIG; then it runs
`docker version` for the server's version, which proves the server answers and
not only that a client exists. A client missing from PATH, an unanswerable
daemon, a reading without `hostname=`, and a daemon naming another machine all
refuse the run, since a tag resolved through one daemon and a container started
on another is the hole this gate closes. Nothing about images happens here; a
passing gate prints the hostname and the server version.
"""

from __future__ import annotations

import shutil
import subprocess

from mcgyvr.serving.gatelib import (
    door_required,
    need,
    refuse,
)


def _docker(*args: str) -> str:
    try:
        done = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=60, check=False
        )
    except subprocess.TimeoutExpired:
        refuse(
            f"gate 3: 'docker {' '.join(args)}' did not answer in 60s; the "
            "daemon is not usable"
        )
    if done.returncode != 0:
        refuse(
            f"gate 3: 'docker {' '.join(args)}' failed — the daemon a tag is "
            "resolved through does not answer, so no tag becomes a digest and "
            "no container is started. Fix the daemon (or the operator's docker "
            f"group); nothing is measured until it answers. {done.stderr.strip()[:300]}"
        )
    return done.stdout.strip()


def main() -> int:
    door_required("gate 3")
    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)
    hostname = pre.get("hostname")
    if not hostname:
        refuse(
            "gate 3: gate 2's reading carries no hostname=, so the daemon "
            "cannot be matched to the machine that was read"
        )
    if shutil.which("docker") is None:
        refuse(
            "gate 3: 'docker' is not on PATH; no tag becomes a digest and no "
            "container is started, so nothing is measured"
        )

    name = _docker("info", "--format", "{{.Name}}")
    if name != hostname:
        refuse(
            f"gate 3: the daemon `docker` reaches calls itself {name!r}, and the "
            f"machine gate 2 read is {hostname!r}. A tag resolved through one "
            "daemon and a container started on another is the hole this gate "
            "closes, so nothing is measured"
        )
    version = _docker("version", "--format", "{{.Server.Version}}")
    print(f"gate 3: docker on {hostname} answers, {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
