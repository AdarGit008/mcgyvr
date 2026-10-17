#
""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import mcgyvr
from mcgyvr.fleet.roots import FolderError
from mcgyvr.serving.gatelib import (
    USER_MODE,
    artifact_escape,
    claim,
    claim_path,
    door_required,
    envelope_escape,
    envelope_of,
    export,
    lease_of_run,
    lease_stamp,
    need,
    refuse,
    release,
    run_id_of,
    step_name,
)

DIRECTIVES = ("RUN_REWRITES",)
PLAIN_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def declarations(step_file: Path) -> dict[str, list[str]]:
    ""
    text = step_file.read_text(encoding="utf-8", errors="replace")
    out: dict[str, list[str]] = {}
    for directive in DIRECTIVES:
        found = re.findall(rf"^#\s*{directive}:\s*(.*)$", text, re.MULTILINE)
        if len(found) > 1:
            refuse(
                f"gate 5: {step_file} carries {len(found)} '# {directive}:' "
                "lines; a step declares what it writes on one line per "
                "directive, and a file on a second line would be guarded by no "
                "gate at all"
            )
        out[directive] = found[0].split() if found else []
    return out


def artifact_run_id(path: Path) -> str | None:
    ""
    try:
        doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        return None
    run_id = doc.get("run_id") if isinstance(doc, dict) else None
    return run_id if isinstance(run_id, str) else None


def minted_by(run_id: str, host: str, step: str) -> bool:
    ""
    named = f"{re.escape(host)}-{re.escape(step)}"
    return re.fullmatch(rf"\d{{4}}-\d{{2}}-\d{{2}}-{named}(?:-.+)?", run_id) is not None


def header_path(out_dir: Path, run_id: str) -> Path:
    ""
    return out_dir / f"{run_id}.run.json"


def header_record(run_id: str, step_name: str, run_date: str) -> dict[str, str]:
    ""
    return {
        "run_id": run_id,
        "step": step_name,
        "host": need("RUN_HOST"),
        "date": run_date,
        "config": need("RUN_CONFIG"),
        "mcgyvr_version": mcgyvr.__version__,
        "started_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def user_header(record: dict[str, str]) -> dict[str, object]:
    ""
    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)
    compose = os.environ.get("RUN_COMPOSE")
    text = Path(compose).read_text(encoding="utf-8") if compose else None
    return {
        **record,
        "mode": USER_MODE,
        "command": os.environ.get("RUN_COMMAND", ""),
        "rig_before": pre,
        "compose_file": compose,
        "compose": text,
    }


def envelope(run_date: str, run_id: str) -> Path:
    ""
    try:
        return envelope_of(run_date, run_id)
    except (FolderError, RuntimeError) as exc:
        refuse(f"gate 5: the data folder cannot be named: {exc}. Nothing is minted")


def write_header(path: Path, record: Mapping[str, object]) -> None:
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    door_required("gate 5")
    step_file = Path(need("RUN_STEP_FILE"))
    host = need("RUN_HOST")
    suffix = os.environ.get("RUN_SUFFIX", "")

    declared = declarations(step_file)
    every = [name for names in declared.values() for name in names]
    if not every:
        refuse(
            f"gate 5: {step_file} declares no '# RUN_REWRITES: <name> ...' "
            "line, so the door cannot guard "
            "what it writes or parse it back at gate 8. A step that names "
            "nothing it produces is not run"
        )
    seen: set[str] = set()
    for name in every:
        if not PLAIN_NAME.match(name):
            refuse(
                f"gate 5: declared artifact {name!r} is not a plain file name "
                "([A-Za-z0-9_.-]+, relative to the envelope)"
            )
        if name in seen:
            refuse(
                f"gate 5: {step_file} declares {name!r} twice; one file is "
                "guarded by one rule, not by two"
            )
        seen.add(name)

    run_date = os.environ.get("RUN_DATE") or datetime.now(UTC).strftime("%Y-%m-%d")
    if not RUN_DATE_RE.match(run_date):
        refuse(f"gate 5: RUN_DATE={run_date!r} is not YYYY-MM-DD")

    #
    step = step_name(step_file)
    run_id = run_id_of(run_date, host, step_file, suffix)
    if not PLAIN_NAME.match(run_id):
        refuse(
            f"gate 5: RUN_ID {run_id!r} is not [A-Za-z0-9_.-]+; it names "
            "containers (<RUN_ID>-<role>) and must be legal as a docker name prefix"
        )
    out_dir = envelope(run_date, run_id)
    escape = envelope_escape(out_dir)
    if escape is not None:
        refuse(f"gate 5: {escape}. Nothing is minted into a directory that is a link")

    #
    #
    #
    if claim_path(out_dir, run_id).exists():
        refuse(
            f"gate 5: a run with this RUN_ID ({run_id}) is in progress or died "
            f"without releasing it; wait, or remove {claim_path(out_dir, run_id)} "
            "if you know it is dead. Two door invocations never share a run "
            "id: a same-day re-run takes --suffix"
        )

    def linked(name: str) -> None:
        ""
        escape = artifact_escape(out_dir / name, out_dir)
        if escape is not None:
            refuse(
                f"gate 5: {name} is refused as a declared artifact: {escape}. A "
                "declared artifact is one regular file inside the envelope, and "
                "a step that wrote through a link would write evidence the door "
                "never guarded"
            )

    #
    #
    aside_of: dict[str, str] = {}
    for name in declared["RUN_REWRITES"]:
        path = out_dir / name
        linked(name)
        if not path.exists():
            continue
        old = artifact_run_id(path)
        if not old:
            refuse(
                f"gate 5: {name} exists and carries no run_id, "
                "so no step can claim it; a file the door did not produce is "
                "never superseded by one it does"
            )
        if not minted_by(old, host, step):
            refuse(
                f"gate 5: {name} was written by run_id={old}, not by step "
                f"{step} on {host}; a step may supersede its own artifact and "
                "never another step's"
            )
        if old == run_id:
            refuse(
                f"gate 5: {name} carries run_id={old} â€” the id this run would "
                "mint. Two door invocations never share a run id; give this "
                "re-run its own with --suffix"
            )
        stem, dot, ext = name.rpartition(".")
        aside = f"{stem}.superseded-{old}.{ext}" if dot else f"{name}.superseded-{old}"
        if (out_dir / aside).exists():
            refuse(
                f"gate 5: {name} was written by run_id={old} and {aside} is "
                "already beside it; two runs carried one run id and nothing "
                "recorded is overwritten"
            )
        aside_of[name] = aside

    #€”
    #nd
    #
    #
    header = header_path(out_dir, run_id)
    if header.exists():
        refuse(
            f"gate 5: {header.name} is already in the envelope, so a run with "
            f"this RUN_ID ({run_id}) has been made before. Two door invocations "
            "never share a run id: a same-day re-run takes --suffix"
        )
    record = header_record(run_id, step, run_date)
    header_doc: Mapping[str, object] = user_header(record)

    #
    #
    #
    lease = lease_of_run()
    if lease is not None:
        lease_stamp(need("RUN_HOST"), lease, run_id)

    out_dir.mkdir(parents=True, exist_ok=True)
    claim(out_dir, run_id)
    try:
        write_header(header, header_doc)
        for name, aside in aside_of.items():
            (out_dir / name).rename(out_dir / aside)
            print(
                f"gate 5: {name} was written by this step; moved to {aside} before "
                "this run supersedes it (nothing recorded is lost)",
                file=sys.stderr,
            )
    except OSError:
        #
        #
        release(out_dir, run_id)
        raise

    export("RUN_ID", run_id)
    export("RUN_OUT_DIR", out_dir)
    export("RUN_DATE", run_date)
    export("RUN_STEP", step)
    export("RUN_HOST", need("RUN_HOST"))
    export("RUN_DECLARED", json.dumps(declared, separators=(",", ":")))
    #
    #
    #
    export("RUN_SUPERSEDED", json.dumps(aside_of, separators=(",", ":")))
    print(f"gate 5: RUN_ID={run_id} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
