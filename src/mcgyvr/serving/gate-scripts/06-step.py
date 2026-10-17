#!/usr/bin/env python3
# Gate 6: the wrapper run.py starts to run this run's step and wait it out.
"""Gate 6: run the serve direction's step for this run, and wait it out.

The door starts this wrapper as the sixth entry of a serve run's sequence,
after gate 5 has exported the run to it; the step to run is named by
RUN_STEP_FILE. The wrapper starts that step on the door's own interpreter, in
a session of its own so its whole process group can be signalled at once,
hands it nothing but the environment it inherited (which is how the run
reaches the step), and leaves its stdout and stderr to the operator.

An INT or TERM that reaches the wrapper is forwarded to the step's group once,
and the step is then given GRACE_S seconds to run its own trap and leave;
whatever is still in that group afterwards is SIGKILLed, so no step outlives
gate 6 and gate 7 never reads the rig over a step still running. The status
returned is the step's own; the door keeps it and runs gates 7 and 8 anyway.
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

# How long a signalled step is given to run its own INT/TERM trap and exit
# before its whole process group is SIGKILLed: gate 7 must not read the rig
# over a step that is still cleaning up.
GRACE_S = 20.0

FORWARDED = (signal.SIGINT, signal.SIGTERM)


def _run(argv: list[str]) -> int:
    """Run argv in the checkout, in a group of its own, and return its status.

    A terminal's Ctrl-C reaches both this wrapper and the step, and a kill of
    the door alone reaches only this wrapper, so the first forwarded signal is
    passed on to the step's group rather than acted on here; a second one is
    ignored, since the step has its signal and its deadline already. Waiting in
    0.2 s slices is what lets that deadline be noticed while the step is still
    running: once a signal is forwarded and GRACE_S has passed, the group is
    SIGKILLed so the wait ends even if the step's trap never does.
    """
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
        # The step exited under a signal; kill its group too, so nothing it
        # started is still running when gate 7 re-reads the rig.
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
    # The step inherits this process's environment, and the door's exports on
    # it are the whole path the run takes to the step: no argument is built.
    # It runs on the door's interpreter, not its own shebang, because a serve
    # step is mcgyvr code meant to run under the interpreter that ran the gates.
    # None of the door's own argv is handed on, so the step sees the run the
    # door exported and not the flags that opened the door.
    # Its stdout and stderr go straight to the operator uncaptured, and the
    # status returned is the step's own, which the door records before it runs
    # gates 7 and 8 over what the step left behind.
    return _run([sys.executable, step])


if __name__ == "__main__":
    raise SystemExit(main())
