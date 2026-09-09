#!/usr/bin/env python3
"""gate 8 — every declared artifact exists and parses, here, on the rig night.

THE PARSER ONCE RAN ONLY IN CI. A run that wrote a file the parser rejects
exited green on the rig and turned red a commit later, by which time the rig
was booked for something else and the rows could not be retaken. So the
read-back happens where the rig time is spent.

A TSV is read with the campaign's own parser and not with a second one written
for this gate: a shim that accepts what the parser rejects is not a check. A
`.json` is read with `json.loads` — one artifact was checked as TSV, passed,
and turned out to be two JSON documents concatenated.

An appended file must have KEPT ITS PREFIX and GROWN: gate 5 recorded the size
and digest before the step, so a step that rewrote the file it was supposed to
add to is caught here rather than discovered later as missing history.

A TSV THAT PARSES IS NOT YET THIS RUN'S. An empty file parses; a file with no
stamp at all parses; a file stamped by another run parses. So the part of
every declared TSV that this run wrote — the whole file, or the bytes after
gate 5's recorded size for an appended one — must open with `### START
run_id=<RUN_ID>` (the first of the run's stamps), carry a `### ROUND
id=<RUN_ROUND> product_sha256=<RUN_PRODUCT_SHA256>` and close with `### END
run_id=<RUN_ID>`, each equal to what the door exported to the step. A stamp
that names another run, another round or nothing is exit 1 naming both. A
`.json` keeps its own rule: it parses as JSON and is never stamped.

AND IT MUST BE ONE REGULAR FILE OF THE ENVELOPE. A declared name that is a
symlink, a hard link or a path resolving outside the resolved envelope is
named with where it points and is not read: a step once wrote through such a
link into another envelope's committed evidence, and this gate parsed the
victim as green.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from mcgyvr.serving.gatelib import (
    artifact_escape,
    door_required,
    envelope_escape,
    need,
    root,
)


def _named(line: str, word: str) -> bool:
    """Whether a marker line is a `### <word>` stamp, by its first token."""
    return line.removeprefix("###").split()[:1] == [word]


def _stamped(
    rows: ModuleType, sweep: Any, skip: int, word: str
) -> list[tuple[int, dict[str, str]]]:
    """Every `### <word>` in this run's portion, as (line, fields).

    The portion is every marker after line ``skip``. The fields are read by
    the parser's own `Sweep.stamps` over exactly those markers — not by a
    second parser here — so what this gate accepts is what the parser reads.
    """
    own = tuple((n, line) for n, line in sweep.markers if n > skip)
    numbers = [n for n, line in own if _named(line, word)]
    fields = rows.Sweep(sweep.path, (), own, {}).stamps(word)
    return list(zip(numbers, fields, strict=True))


def _unbound(
    rows: ModuleType,
    sweep: Any,
    raw: bytes,
    start: int,
    run_id: str,
    round_id: str,
    digest: str,
) -> list[str]:
    """Every way the TSV's own portion fails to name THIS run, in words.

    ``start`` is the byte where this run's writing begins: 0 for a file it
    created, gate 5's recorded size for one it appended to.
    """
    if not raw[start:].strip():
        return [
            f"is empty ({len(raw) - start} bytes of this run's writing): a "
            "declared artifact that says nothing measured nothing"
        ]
    skip = raw[:start].count(b"\n")
    starts = _stamped(rows, sweep, skip, "START")
    rounds = _stamped(rows, sweep, skip, "ROUND")
    ends = _stamped(rows, sweep, skip, "END")
    problems: list[str] = []
    if not starts:
        problems.append(
            "carries no `### START run_id=` stamp of its own; an artifact the "
            f"door produced opens with the run that made it ({run_id}), and one "
            "that names no run is not this run's evidence"
        )
    for lineno, fields in starts:
        if fields.get("run_id") != run_id:
            problems.append(
                f"line {lineno}: ### START names run_id={fields.get('run_id')!r} "
                f"and this run is run_id={run_id!r}; a stamp that names another "
                "run (or none) is not this run's evidence"
            )
    if not rounds:
        problems.append(
            "carries no `### ROUND id= product_sha256=` stamp of its own; the "
            f"door handed the step id={round_id} product_sha256={digest} and a "
            "file that does not say which round it measured under is comparable "
            "with nothing"
        )
    for lineno, fields in rounds:
        if fields.get("id") != round_id or fields.get("product_sha256") != digest:
            problems.append(
                f"line {lineno}: ### ROUND names id={fields.get('id')!r} "
                f"product_sha256={fields.get('product_sha256')!r} and this run "
                f"measured under id={round_id!r} product_sha256={digest!r}"
            )
    if not ends:
        problems.append(
            "carries no `### END run_id=` stamp of its own; a run that did not "
            "close is one whose end state is unknown, and an END that does not "
            "name the run is not its close"
        )
    for lineno, fields in ends:
        if fields.get("run_id") != run_id:
            problems.append(
                f"line {lineno}: ### END names run_id={fields.get('run_id')!r} "
                f"and this run is run_id={run_id!r}"
            )
    if starts:
        first = starts[0][0]
        for word, found in (("ROUND", rounds), ("END", ends)):
            for lineno, _ in found:
                if lineno < first:
                    problems.append(
                        f"line {lineno}: ### {word} precedes this run's first "
                        f"### START (line {first}); START is the first stamp a "
                        "run writes"
                    )
    return problems


def main() -> int:
    door_required("gate 8")
    sys.path.insert(0, str(root()))
    from tools.runs import rows
    from tools.runs.rows import read as read_rows

    declared = json.loads(need("RUN_DECLARED"))
    state = json.loads(need("RUN_APPEND_STATE"))
    superseded = json.loads(need("RUN_SUPERSEDED"))
    out_dir = Path(need("RUN_OUT_DIR"))
    run_id = need("RUN_ID")
    round_id = need("RUN_ROUND")
    digest = need("RUN_PRODUCT_SHA256")
    appended = set(declared.get("RUN_APPENDS", []))
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

        raw = path.read_bytes()
        size_before = 0
        if name in appended:
            before = state.get(name, {})
            size_before = int(before.get("size", 0))
            if len(raw) < size_before:
                print(
                    f"gate 8: {name} SHRANK ({size_before} -> {len(raw)} "
                    "bytes); a step appends to a file and never truncates one",
                    file=sys.stderr,
                )
                status = 1
                continue
            if hashlib.sha256(raw[:size_before]).hexdigest() != before.get("sha256"):
                print(
                    f"gate 8: {name}'s first {size_before} bytes changed; the "
                    "step rewrote a file it declared it would append to, so "
                    "the history that was there is gone",
                    file=sys.stderr,
                )
                status = 1
                continue
            if len(raw) == size_before:
                print(
                    f"gate 8: {name} was declared under RUN_APPENDS and did not "
                    "grow; a step that appended nothing measured nothing, and "
                    "the run is not green",
                    file=sys.stderr,
                )
                status = 1
                continue

        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
                continue
            if path.suffix != ".tsv":
                continue
            sweep = read_rows(path)
            unbound = _unbound(rows, sweep, raw, size_before, run_id, round_id, digest)
        except Exception as error:
            print(f"gate 8: {name} does not parse: {error!r}", file=sys.stderr)
            status = 1
            continue
        for problem in unbound:
            print(f"gate 8: {name} {problem}", file=sys.stderr)
        if unbound:
            print(
                f"gate 8: {name} is not this run's evidence until its own "
                "stamps name it; the run is not green",
                file=sys.stderr,
            )
            status = 1

    if status == 0:
        print(f"gate 8: {sum(len(v) for v in declared.values())} artifact(s) parse")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
