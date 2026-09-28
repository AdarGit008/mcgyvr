#!/usr/bin/env python3
"""gate 6 — the caller's own script.

The only part of a run the door does not fix. It runs from the repo root with
the run exported to it and its own arguments after `--`; its stdout and stderr
are the operator's and the door adds nothing to them.

Its exit status is a RESULT, not a refusal: a step that fails has measured
something (that this cell does not run), so gates 7 and 8 still run and the
status propagates after them.

A SIGNAL REACHES THE STEP ONCE, AND THE STEP IS GONE BEFORE THIS EXITS. The
step runs in its own session, so a terminal's Ctrl-C reaches it only through
here, and the first SIGINT or SIGTERM that arrives here — the terminal's, or
the door's `_end` — is forwarded to the step's whole process group. Then this
waits for the step to run its own INT/TERM trap (`default-step.sh` removes the
container it started there), and only past :data:`GRACE_S` kills the group.
Ending here at once instead left the step running, reparented, while gate 7
read the rig; answering Ctrl-C with a kill cut the step's trap short. The grace
is below the door's own wait on this entry, so the door never kills this
wrapper while it still holds the step.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import types

from mcgyvr.serving.gatelib import door_required, need, root

#: How long the step has, once signalled, to run its own trap and exit. Below
#: `run.py:_end`'s 30 s wait on this entry.
GRACE_S = 20.0

FORWARDED = (signal.SIGINT, signal.SIGTERM)


def _run(argv: list[str]) -> int:
    """Run the step in its own session; forward the first signal to its group."""
    step = subprocess.Popen(argv, cwd=root(), start_new_session=True)
    signalled: list[float] = []

    def forward(signum: int, _frame: types.FrameType | None) -> None:
        if signalled:
            return
        signalled.append(time.monotonic() + GRACE_S)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(step.pid, signum)

    for sig in FORWARDED:
        signal.signal(sig, forward)
    status: int | None = None
    while status is None:
        try:
            status = step.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            if signalled and time.monotonic() > signalled[0]:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(step.pid, signal.SIGKILL)
    if signalled:
        # Asked to stop: whatever the step left in its own group goes with it.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(step.pid, signal.SIGKILL)
    return status


def main() -> int:
    door_required("gate 6")
    step = need("RUN_STEP_FILE")
    if not os.access(step, os.X_OK):
        sys.stderr.write(f"06-step.py: {step} is not executable (chmod +x)\n")
        return 2
    print(
        f"gate 6: {step} --host {need('RUN_HOST')} -> {need('RUN_OUT_DIR')} "
        f"(RUN_ID={need('RUN_ID')})",
        file=sys.stderr,
    )
    return _run([step, *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
