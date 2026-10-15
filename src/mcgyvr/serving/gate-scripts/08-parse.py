#!/usr/bin/env python3
"""gate 8 — every declared artifact exists and parses, here, as the run ends.

A run that wrote a file that does not parse is not green, and it is said
where the rig time was spent rather than discovered later. A `.json` is read
with `json.loads`; any other declared file is held to being there.

IT MUST BE ONE REGULAR FILE OF THE ENVELOPE. A declared name that is a
symlink, a hard link or a path resolving outside the resolved envelope is
named with where it points and is not read: a step once wrote through such a
link into another envelope's committed evidence, and this gate parsed the
victim as green.
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
            # Gate 5 moved the earlier pass aside for a successor that never
            # came. Nothing recorded is lost, and the name still resolves:
            # it goes back under its own name (the archived door's rule).
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
