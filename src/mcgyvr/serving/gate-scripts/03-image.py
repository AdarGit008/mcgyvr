#
""

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
