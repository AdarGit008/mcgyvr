#!/usr/bin/env python3
# The one gate of the `link` sequence: the timer is read from the checkout as
# source, run on the rig as `python3 -`, and the one line of JSON it prints is
# the whole reading — nothing is leased, filed or left behind.
"""Time one link on the rig, with the timer's source on stdin.

The gate reads two variables and exports nothing: ``RUN_HOST``, and
``RUN_LINK``, the timer's mode word followed by its two arguments,
space-joined the way the door writes it. A ``RUN_LINK`` that is empty, or
whose first word names no mode of :data:`mcgyvr.serving.linktime.MODES`
(``peer``, ``sink``, ``send``), is refused with a rule on stderr and exit 2;
so is a run started outside the door, before anything is read, which is why
:func:`mcgyvr.serving.gatelib.door_required` comes first and
:mod:`mcgyvr.serving.linktime` is imported only after it. The mode is what is
measured: a card-to-card copy between two card indices (``peer``), or a TCP
transfer to an address and port (``sink`` waits for one, ``send`` connects to
one).

The timer is shipped, not installed: ``linktime.py`` beside this gate's folder
is read as text here and handed to :func:`mcgyvr.serving.gatelib.ssh` as the
remote command's stdin, so what runs on the rig is

    python3 - mcgyvr-linktime <mode> <first> <second>

and no part of it is written to the rig's disk. ``ssh`` admits exactly the host
``RUN_HOST`` named, and the timeout is the timer's own bound,
:data:`mcgyvr.serving.linktime.WHOLE_S`, plus 30 s of slack: the timer is
expected to end itself first, and if the outer bound is reached instead, the
gate prints one line of JSON saying the timer outlasted its own bound and
exits 1.

Everything the timer said comes back unchanged — its stdout and stderr are
written to this gate's own, and its status is the gate's. Nothing is leased or
filed, so the run's environment is left as it was.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, need, refuse, ssh

#: The timer as text: linktime.py sits beside this gate's folder (parents[1] is
#: src/mcgyvr/serving), and the file read here is the source that is shipped to
#: the rig, never a copy already on the rig.
TIMER = Path(__file__).resolve().parents[1] / "linktime.py"


def main() -> int:
    door_required("link")
    from mcgyvr.serving import linktime

    host = need("RUN_HOST")
    words = os.environ.get("RUN_LINK", "").split()
    if not words or words[0] not in linktime.MODES:
        refuse(f"link: RUN_LINK {' '.join(words)!r} names no mode of the timer")
    try:
        source = TIMER.read_text(encoding="utf-8")
    except OSError as exc:
        refuse(f"link: the timer {TIMER} cannot be read: {exc}")
        raise
    command = " ".join(
        shlex.quote(word) for word in ("python3", "-", linktime.LINK_WORD, *words)
    )
    try:
        done = ssh(host, command, timeout=linktime.WHOLE_S + 30, input=source)
    except subprocess.TimeoutExpired:
        print(
            '{"error": "the timer on the rig outlasted its own bound and the '
            'door ended it"}'
        )
        return 1
    if done.stdout:
        sys.stdout.write(done.stdout)
    if done.stderr:
        sys.stderr.write(done.stderr)
    return 0 if done.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
