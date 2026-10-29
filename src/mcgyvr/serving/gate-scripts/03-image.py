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

A native run (``RUN_LAUNCHER=native``) starts no container and resolves no
tag, so there is no daemon to hold to the machine: the gate says so and
passes. Docker Desktop names its daemon ``docker-desktop``, after the virtual
machine it runs in rather than the host; that name is taken for the machine
gate 2 read only when the door reaches the rig through its local transport,
where the client cannot be talking to a daemon anywhere else.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from mcgyvr.config import LAUNCHER_NATIVE
from mcgyvr.serving.gatelib import (
    door_required,
    local_transport,
    need,
    refuse,
    tool,
)

#: The name Docker Desktop's daemon gives itself, on macOS and Windows alike.
DOCKER_DESKTOP = "docker-desktop"


def _docker(*args: str) -> str:
    try:
        done = subprocess.run(
            [*tool("docker"), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
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
    if os.environ.get("RUN_LAUNCHER") == LAUNCHER_NATIVE:
        print(
            f"gate 3: {need('RUN_HOST')} runs this launch spec natively; no "
            "container is started and no tag resolved, so no daemon is asked"
        )
        return 0
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
    desktop = name == DOCKER_DESKTOP and local_transport(need("RUN_HOST"))
    if name != hostname and not desktop:
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
