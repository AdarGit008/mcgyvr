#
""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import types

from mcgyvr.serving.gatelib import door_required, need, root

#
#
GRACE_S = 20.0

FORWARDED = (signal.SIGINT, signal.SIGTERM)


def _run(argv: list[str]) -> int:
    ""
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
        #
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
    #
    #
    #
    #
    return _run([sys.executable, step])


if __name__ == "__main__":
    raise SystemExit(main())
