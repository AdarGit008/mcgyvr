#
""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, need, refuse, ssh

#
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
