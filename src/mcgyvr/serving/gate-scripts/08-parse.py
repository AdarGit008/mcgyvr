#!/usr/bin/env python3
# Gate 8, run at the end of every serve run whatever gate 6 did: it reads the
# names the step declared it writes and reports each one that is not there, is
# not this run's evidence, or is JSON that does not parse.

"""Gate 8: every artifact the step declared exists, and the JSON ones parse.

The run arrives on the environment the door exports. RUN_DECLARED maps each
declaration directive (RUN_REWRITES) to the names the step said it writes,
RUN_SUPERSEDED maps a name to the aside copy gate 5 moved it to before this run
was to rewrite it, and RUN_OUT_DIR is the run's envelope. A linked envelope is
refused before anything is read, and each declared name must be one regular
file inside the envelope — a name that is missing is reported, and the aside
copy, when it is a regular file inside the envelope, is renamed back under the
declared name. Anything that fails leaves the status at 1; only a clean run
says how many artifacts parse.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import (
    artifact_escape,
    door_required,
    envelope_escape,
    need,
)


def main() -> int:
    door_required("gate 8")
    declared = json.loads(need("RUN_DECLARED"))
    superseded = json.loads(need("RUN_SUPERSEDED"))
    out_dir = Path(need("RUN_OUT_DIR"))
    status = 0

    escape = envelope_escape(out_dir)
    if escape is not None:
        print(f"gate 8: nothing is read: {escape}", file=sys.stderr)
        return 1

    for name in [n for names in declared.values() for n in names]:
        path = out_dir / name
        escape = artifact_escape(path, out_dir)
        if escape is not None:
            print(
                f"gate 8: {name} is not this run's evidence: {escape}. A declared "
                "artifact is one regular file inside the envelope, and what was "
                "written through a link was written somewhere else",
                file=sys.stderr,
            )
            status = 1
            continue
        if not path.exists():
            print(
                f"gate 8: {name} was declared and does not exist; the step "
                "exited without writing what it said it writes",
                file=sys.stderr,
            )
            status = 1
            # Gate 5 set a previous run's copy aside to make room for this run's
            # rewrite; when the step writes nothing, that copy comes back to its
            # declared name if it is still one regular file in the envelope.
            aside = out_dir / str(superseded.get(name, ""))
            if (
                name in superseded
                and aside.is_file()
                and artifact_escape(aside, out_dir) is None
            ):
                aside.rename(path)
                print(
                    f"gate 8: {name} was not rewritten; {aside.name} is back "
                    "under its own name",
                    file=sys.stderr,
                )
            continue

        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as error:
                print(f"gate 8: {name} does not parse: {error!r}", file=sys.stderr)
                status = 1

    if status == 0:
        print(f"gate 8: {sum(len(v) for v in declared.values())} artifact(s) parse")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
