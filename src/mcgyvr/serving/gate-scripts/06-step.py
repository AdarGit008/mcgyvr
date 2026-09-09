#!/usr/bin/env python3
"""gate 6 — the caller's own script.

The only part of a run the door does not fix. It runs from the repo root with
the run exported to it and its own arguments after `--`; its stdout and stderr
are the operator's and the door adds nothing to them.

Its exit status is a RESULT, not a refusal: a step that fails has measured
something (that this cell does not run), so gates 7 and 8 still run and the
status propagates after them.
"""

from __future__ import annotations

import os
import subprocess
import sys

from mcgyvr.serving.gatelib import door_required, need, root


def main() -> int:
    door_required("gate 6")
    step = need("RUN_STEP_FILE")
    if not os.access(step, os.X_OK):
        # Not `refuse`: a step that cannot be executed is the caller's mistake
        # to fix, and saying so with the same exit code as a gate refusal would
        # blur the two.
        sys.stderr.write(f"06-step.py: {step} is not executable (chmod +x)\n")
        return 2
    print(
        f"gate 6: {step} --host {need('RUN_HOST')} -> {need('RUN_OUT_DIR')} "
        f"(RUN_ID={need('RUN_ID')})",
        file=sys.stderr,
    )
    return subprocess.run([step, *sys.argv[1:]], cwd=root(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
