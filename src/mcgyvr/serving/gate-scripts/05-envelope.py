#!/usr/bin/env python3
"""gate 5 — the envelope, and RUN_ID.

A step declares what it writes on one comment line per directive, which the
door READS and never executes:

    # RUN_ARTIFACTS: a.tsv [b.tsv ...]   created here; write-once
    # RUN_REWRITES:  b.tsv [...]         created here, and this step may run
                                         again over it; the existing file is
                                         admitted only if its `### START`
                                         carries a run_id THIS step minted, and
                                         is moved to
                                         <name>.superseded-<run_id>.<ext> first
    # RUN_APPENDS:   c.tsv [...]         another step created it; this one adds
                                         to it, and gate 8 checks the prefix
                                         survived

WHY WRITE-ONCE. Two measurements filed under one name are one measurement with
the other's history erased. Nothing recorded is overwritten and nothing is
deleted: the superseded file stays on disk beside its replacement.

WHY THE RUN_ID MAY NOT BE REUSED. It names the containers gate 7 looks for, the
`### START` of exactly one run, and any `### RIGMOVED` stamp. Two invocations
sharing one id make all three ambiguous, so a same-day re-run takes --suffix.

Everything here happens before any rig is touched and before anything is
written, except the deliberate moves at the end.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.serving.gatelib import export, need, refuse, root

DIRECTIVES = ("RUN_ARTIFACTS", "RUN_REWRITES", "RUN_APPENDS")
PLAIN_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: `### START ... run_id=<id>` on the file's first START line.
START_RUN_ID = re.compile(r"^###\s+START\s+.*\brun_id=(\S+)", re.MULTILINE)


def declarations(step_file: Path) -> dict[str, list[str]]:
    """The three directives, read as text. The step is never executed to learn them."""
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


def start_run_id(path: Path) -> str | None:
    match = START_RUN_ID.search(path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


def step_of_run_id(run_id: str, campaign: str, steps: list[str]) -> str | None:
    """Parse a run id back to the step that minted it, by LONGEST match.

    `<date>-<campaign>-<step>[-<suffix>]`, and a suffix can spell another step's
    name, so the longest candidate wins and the caller checks for the ambiguity
    before minting.
    """
    prefix = f"-{campaign}-"
    if prefix not in run_id:
        return None
    tail = run_id.split(prefix, 1)[1]
    matches = [s for s in steps if tail == s or tail.startswith(f"{s}-")]
    return max(matches, key=len) if matches else None


#: The step a caller gets without naming one. It belongs to no campaign
#: directory, so it is the one step an unknown --campaign may file under.
DEFAULT_STEP = Path(__file__).resolve().parent / "default-step.sh"


def main() -> int:
    step_file = Path(need("RUN_STEP_FILE"))
    campaign = need("RUN_CAMPAIGN")
    suffix = os.environ.get("RUN_SUFFIX", "")

    # The archived door's first check (archive/runs/run.sh, check_argv): a
    # campaign is a directory under tools/runs/campaigns/, and a name that is
    # not one mints nothing — a typo would otherwise open a fresh envelope
    # beside the real one and file a run where nobody looks. The default step
    # is the exception, deliberately: it is not a campaign's step.
    campaigns_dir = root() / "tools" / "runs" / "campaigns"
    campaign_dir = campaigns_dir / campaign
    if not campaign_dir.is_dir() and step_file.resolve() != DEFAULT_STEP:
        known = (
            sorted(p.name for p in campaigns_dir.iterdir() if p.is_dir())
            if campaigns_dir.is_dir()
            else []
        )
        refuse(
            f"gate 5: no campaign {campaign!r} under tools/runs/campaigns/ "
            f"(known: {', '.join(known) or 'none'}). A step files under its "
            "campaign's envelope, and a campaign nobody declared has none; "
            "only the default step (gate-scripts/default-step.sh) needs no "
            "campaign directory. Nothing is minted"
        )

    declared = declarations(step_file)
    every = [name for names in declared.values() for name in names]
    if not every:
        refuse(
            f"gate 5: {step_file} declares no '# RUN_ARTIFACTS: <name> ...' "
            "(or RUN_REWRITES / RUN_APPENDS) line, so the door cannot guard "
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

    # `<n>-<name>.sh` -> `<name>`, matching how a run id is parsed back.
    step_name = re.sub(r"^\d+-", "", step_file.stem)
    siblings = (
        [re.sub(r"^\d+-", "", p.stem) for p in sorted(campaign_dir.glob("[0-9]*-*.sh"))]
        if campaign_dir.is_dir()
        else []
    )
    if step_name not in siblings:
        siblings.append(step_name)
    if suffix:
        for other in siblings:
            if other != step_name and (
                f"{step_name}-{suffix}" == other
                or f"{step_name}-{suffix}".startswith(f"{other}-")
            ):
                refuse(
                    f"gate 5: --suffix {suffix!r} would mint a run id that "
                    f"reads as step {other!r}; a run id names exactly one step"
                )

    run_id = f"{run_date}-{campaign}-{step_name}" + (f"-{suffix}" if suffix else "")
    if not PLAIN_NAME.match(run_id):
        refuse(
            f"gate 5: RUN_ID {run_id!r} is not [A-Za-z0-9_.-]+; it names "
            "containers (<RUN_ID>-<role>) and must be legal as a docker name prefix"
        )
    out_dir = root() / "records" / "evidence" / f"{run_date}-{campaign}"

    for name in declared["RUN_ARTIFACTS"]:
        if (out_dir / name).exists():
            refuse(
                f"gate 5: {name} already exists under "
                f"records/evidence/{run_date}-{campaign}/; an artifact is "
                "written once. Move it aside deliberately if this is a re-run "
                "— the door does not overwrite evidence"
            )

    # Every rewrite is JUDGED before any is MOVED, so a refusal on the second
    # leaves the first where it was.
    aside_of: dict[str, str] = {}
    for name in declared["RUN_REWRITES"]:
        path = out_dir / name
        if not path.exists():
            continue
        old = start_run_id(path)
        if not old:
            refuse(
                f"gate 5: {name} exists and its ### START carries no run_id=, "
                "so no step can claim it; a file the door did not produce is "
                "never superseded by one it does"
            )
        writer = step_of_run_id(old, campaign, siblings)
        if writer != step_name:
            refuse(
                f"gate 5: {name} was written by run_id={old}"
                + (f" (step {writer})" if writer else "")
                + f", not by {campaign}/{step_name}; a step may supersede its "
                "own artifact and never another step's"
            )
        if old == run_id:
            refuse(
                f"gate 5: {name} carries run_id={old} — the id this run would "
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

    append_state: dict[str, dict[str, object]] = {}
    for name in declared["RUN_APPENDS"]:
        path = out_dir / name
        if not path.exists():
            refuse(
                f"gate 5: {name} is declared under RUN_APPENDS and does not "
                f"exist under records/evidence/{run_date}-{campaign}/; this "
                "step appends to a file another step creates, and that step "
                "has not run through the door yet"
            )
        old = start_run_id(path)
        if not old:
            refuse(
                f"gate 5: {name} exists and its ### START carries no run_id=, "
                "so the door did not produce it; nothing recorded outside the "
                "door is appended to"
            )
        if not step_of_run_id(old, campaign, siblings):
            refuse(
                f"gate 5: {name} was written by run_id={old}, which names no "
                f"step of campaign {campaign}; a step appends only to a file "
                "this campaign produced"
            )
        raw = path.read_bytes()
        append_state[name] = {
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, aside in aside_of.items():
        (out_dir / name).rename(out_dir / aside)
        print(
            f"gate 5: {name} was written by this step; moved to {aside} before "
            "this run supersedes it (nothing recorded is lost)",
            file=sys.stderr,
        )

    export("RUN_ID", run_id)
    export("RUN_OUT_DIR", out_dir)
    export("RUN_DATE", run_date)
    export("RUN_STEP", step_name)
    export("RUN_HOST", need("RUN_HOST"))
    export("RUN_DECLARED", json.dumps(declared, separators=(",", ":")))
    export("RUN_APPEND_STATE", json.dumps(append_state, separators=(",", ":")))
    # What was moved aside, so gate 8 can put it back if this run never
    # writes the successor: a rewrite pass that filed nothing must not leave
    # the earlier pass vacated under its own name.
    export("RUN_SUPERSEDED", json.dumps(aside_of, separators=(",", ":")))
    print(f"gate 5: RUN_ID={run_id} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
