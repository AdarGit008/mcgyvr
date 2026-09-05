#!/usr/bin/env python3
"""gate 3 — the daemon a tag is resolved through answers now.

The door owns the daemon; a step owns its tags. Resolution itself (tag ->
digest) happens in the step, once, and every driver refuses an image value that
is not a digest. What is checked here is that the daemon exists and responds,
and that it is the SAME one gate 7 will ask about leftovers — so a step cannot
resolve against one daemon and start a container on another.

`command -v docker` is not this check. A CLI with no daemon behind it passes
that and fails inside the step, after the run is stamped, as a REFUSED row
against the arm rather than as a refusal to start.
"""

from __future__ import annotations

import shutil
import subprocess

from mcgyvr.serving.gatelib import docker, refuse


def main() -> int:
    cli = docker()
    if shutil.which(cli) is None:
        refuse(
            f"gate 3: '{cli}' is not on PATH; no tag becomes a digest and no "
            "container is started, so nothing is measured"
        )
    try:
        done = subprocess.run(
            [cli, "info"], capture_output=True, text=True, timeout=60, check=False
        )
    except subprocess.TimeoutExpired:
        refuse(f"gate 3: '{cli} info' did not answer in 60s; the daemon is not usable")
        raise
    if done.returncode != 0:
        refuse(
            f"gate 3: '{cli} info' failed — the daemon a tag is resolved "
            "through does not answer, so no tag becomes a digest and no "
            "container is started. Fix the daemon (or the operator's docker "
            f"group); nothing is measured until it answers. {done.stderr.strip()[:300]}"
        )
    print(f"gate 3: {cli} answers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
