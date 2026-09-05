#!/usr/bin/env python3
"""gate 3 — the daemon a tag is resolved through is the rig's, and answers now.

The door owns the daemon; a step owns its tags. Resolution itself (tag ->
digest) happens in the step, once, and every driver refuses an image value that
is not a digest. What is checked here is that `docker` — the shim on the PATH
the door exports, which reaches `ssh://RUN_HOST` — answers, that the daemon
answering is the machine gate 2 read (its `Name` is the snapshot's hostname),
and that it runs the docker version hosts.json declares for that rig. A tag
resolved against one daemon and a container started on another is the hole
this gate closes; a daemon on the wrong docker mounts a different set of
device files (the Vulkan ICD manifest, 2026-09-03) and benches a different
machine under the same name.

`command -v docker` is not this check. A CLI with no daemon behind it passes
that and fails inside the step, after the run is stamped, as a REFUSED row
against the arm rather than as a refusal to start.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from mcgyvr.serving.gatelib import door_required, need, refuse, root


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
    host = need("RUN_HOST")
    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)
    hostname = pre.get("hostname")
    if not hostname:
        refuse(
            "gate 3: gate 2's reading carries no hostname=, so the daemon "
            "cannot be matched to the machine that was read"
        )
    hosts_file = root() / "tools" / "runs" / "hosts.json"
    if not hosts_file.is_file():
        refuse(f"gate 3: {hosts_file} is missing; no docker version is declared")
    declared = (
        json.loads(hosts_file.read_text(encoding="utf-8")).get(host, {}).get("rig", {})
    ).get("docker")
    if not declared:
        refuse(
            f"gate 3: tools/runs/hosts.json[{host}].rig.docker is not declared; "
            "the daemon's version is a fact of the rig and is compared like the "
            "hardware"
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
    if version != declared:
        refuse(
            f"gate 3: the daemon `docker` reaches runs {version}, and "
            f"tools/runs/hosts.json[{host}].rig.docker declares {declared}. The "
            "containers a rig runs are a version-dependent fact of the rig, so "
            "nothing is measured until they agree"
        )
    print(f"gate 3: docker on {hostname} answers, {version} as declared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
