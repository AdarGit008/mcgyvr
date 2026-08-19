"""Verify the harness is the harness we edited, then launch — as ONE step.

**Why this file exists.** This lane spent 1.5 h of rig time on a run whose patch
silently never reached the file: the unchanged harness ran, produced a full set of
plausible readings, and nobody could tell from the output. D8 turned that into a
process rule — assert the marker in the file after writing **and** after the
formatter, then launch — and made it one step, because two steps with a human
between them is exactly how the first one gets skipped.

So this does not *check* and then let someone else launch. It refuses, or it
launches. A separate verifier is a verifier that can be forgotten.

**And the launch is detached.** The recorded practice on these rigs is that when a
load or inference saturates the box, interactive ssh sessions time out; the
campaign driver therefore runs under `nohup` with a log, and the survey appends a
fsynced journal line per entry (D8). Nine hours must not depend on this terminal.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

#: Every marker is a decision that must be IN THE FILE at launch time, with the
#: decision it encodes named beside it. A marker is not a checksum: it is the
#: smallest string that is present if and only if the decision landed, so a
#: reader can see what would be lost if it were missing.
MARKERS: tuple[tuple[str, str, str], ...] = (
    ("tools/bench/serving/contract.py", "RAMP_TOKENS = 475", "D3"),
    ("tools/bench/serving/contract.py", "PLATEAU_FRACTION = 0.92", "D2"),
    (
        "tools/bench/serving/contract.py",
        "INFERRED_SATURATION_MIN_SPEEDUP = 1.0",
        "D1 — the inferred path only",
    ),
    (
        "tools/bench/serving/contract.py",
        "def saturation(",
        "D1 — the plateau is not a slot limit",
    ),
    (
        "tools/bench/serving/contract.py",
        "speedup <= INFERRED_SATURATION_MIN_SPEEDUP",
        "DE-1 — a curve that never rises is excluded",
    ),
    (
        "tools/bench/serving/contract.py",
        "RAMP_FLOOR_TOKENS_PER_S",
        "BL-4 — the per-request cap scales with the work asked for",
    ),
    (
        "tools/bench/serving/contract.py",
        '"ramp_repeats": RAMP_REPEATS',
        "D8 — every derived number ships with its parameters",
    ),
    (
        "tools/bench/serving/contract.py",
        '"repeats": attempts',
        "D6/D7 item 7 — the losing repeat is kept",
    ),
    (
        "tools/bench/serving/backends/ollama.py",
        'check["card_idle_before_load"] is True',
        "BL-1 — D4's replacement gate actually gates",
    ),
    (
        "tools/bench/serving/backends/ollama.py",
        "def blob_path(",
        "BL-5 — the child is identified by the blob it serves",
    ),
    (
        "tools/bench/serving/backends/ollama.py",
        '"keep_alive": -1',
        "BL-6 — the co-resident neighbour outlives the ramp",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "def declared_slots(",
        "E5 — the width, with its provenance",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "def launched_width(",
        "E5 revised — read off the host's own argv, not off our variable",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "ancestor={CONTAINER_IMAGE}",
        "E8 — the container filter is pinned to the tag we launch",
    ),
    (
        "tools/bench/serving/backends/vllm.py",
        "start_seconds",
        "D6/D7 item 7 — START_TIMEOUT_S gets a calibration point",
    ),
    ("tools/bench/observed.py", "ELIDE_BY_NAME", "D5"),
    ("tools/bench/observed.py", "MAX_INLINE_ITEMS = 4096", "D5 — the backstop"),
)

#: Markers that must NOT be present — a withdrawn thing is only withdrawn if it
#: is gone. Checked in the same pass, because "we removed it" is exactly the
#: claim a stale file makes look true.
#:
#: **Matched against CODE, not against the file.** The first version was a plain
#: substring test and it refused this very launch, because
#: ``BATCHING_SPEEDUP = 2.0`` appears in the docstring explaining what D1
#: replaced it with. A record saying what a constant used to be is the opposite
#: of the defect this list looks for, and a check that cannot tell a definition
#: from a mention of one pushes every author toward deleting the explanation.
#: So a comment or docstring line is not a hit.
WITHDRAWN: tuple[tuple[str, str, str], ...] = (
    (
        "tools/bench/serving/backends/ollama.py",
        "MIN_VRAM_FRACTION = 0.8",
        "D4 — the withdrawn gate must not still be a constant",
    ),
    (
        "tools/bench/serving/contract.py",
        "BATCHING_SPEEDUP = 2.0",
        "D1 — renamed and re-valued",
    ),
    (
        "tools/bench/serving/contract.py",
        "rate >= 0.95 * best",
        "D2 — the inline threshold is a named constant now",
    ),
    (
        "tools/bench/serving/contract.py",
        '"batches":',
        "D1 — retired",
    ),
)


#: **E15: the campaign, in order, as code.** Written down rather than typed,
#: because an order that exists only in one person's shell is not a decision
#: anybody can review, reproduce, or diff.
#:
#: Sleep runs first deliberately. It is the short phase — two arms on two hosts,
#: about twenty minutes — and it exercises the entire vLLM path both rigs
#: depend on: launch, the readiness assertion, `/server_info` parsing, and the
#: container release. Twenty minutes buys a smoke test for the eleven hours
#: behind it.
#:
#: Phases are independent. A phase that refuses must not cancel the two behind
#: it — the same durability argument as D8's journal, applied one level up.
#:
#: **Every phase carries ``--resume``, so relaunching this exact command
#: continues rather than restarts.** D8 made the output durable; durable output
#: nothing reads back is a record, not a checkpoint. Across eleven hours the
#: difference is whether a crash costs the elapsed time or costs nothing.
EVIDENCE = "records/evidence/calibration-2026-08-19"
CAMPAIGN: tuple[tuple[str, str], ...] = (
    (
        "sleep (D7 item 5)",
        f"{{python}} tools/bench/serving/calibrate.py --phase sleep --resume "
        f"--hosts srv1,srv2 --out {EVIDENCE}/d7-sleep.jsonl",
    ),
    (
        "survey (D7 items 1, 3, 4)",
        f"{{python}} tools/bench/serving/run.py "
        f"--config tools/bench/serving/configs/d7-campaign.json --resume "
        f"--out {EVIDENCE}/d7-survey.json",
    ),
    (
        "width matrices (D7 items 2, 6)",
        f"{{python}} tools/bench/serving/calibrate.py --phase ramp --resume "
        f"--tokens 475 --hosts srv1,srv2 --out {EVIDENCE}/d7-ramp.jsonl",
    ),
)


def already_running() -> list[str]:
    """Campaign drivers alive on this machine right now.

    **E14: the two rigs are measured one at a time.** Splitting the campaign by
    host would halve the wall-clock and the machines share nothing — but the
    ramp computes throughput from CLIENT-side wall-clock, and this client would
    then be driving two conversations at once. Measured on these rigs at 12-21%
    aggregate degradation, which would land inside the throughput curve that is
    the campaign's headline output rather than beside it.

    A decision not to do something is not enforced by intending not to do it, so
    a second driver is refused rather than trusted against.
    """
    # Matched on the PROCESS SHAPE, not on the text of a command line. The
    # first version was `pgrep -af serving/(run|calibrate).py` and it refused
    # this very launch, because the shell that was editing this file had the
    # script's name inside its own argv. A guard that fires on anything merely
    # MENTIONING the driver is a guard that gets switched off.
    found = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        capture_output=True,
        text=True,
        check=False,
    )
    mine = {str(os.getpid()), str(os.getppid())}
    drivers: list[str] = []
    for line in (found.stdout or "").splitlines():
        pid, _, args = line.strip().partition(" ")
        if pid in mine or not args:
            continue
        fields = args.split()
        # argv[0] is a python, and one of its arguments IS the script — not a
        # string that happens to contain the script's name.
        if not Path(fields[0]).name.startswith("python"):
            continue
        if any(
            arg.endswith(("serving/run.py", "serving/calibrate.py"))
            for arg in fields[1:]
        ):
            drivers.append(f"{pid} {args[:120]}")
    return drivers


def code_lines(text: str) -> list[str]:
    """The lines that are code, with comment and docstring lines dropped.

    Deliberately crude — line-oriented, not a parse. It has one job: stop a
    docstring that NAMES a withdrawn constant from reading as that constant
    still existing.
    """
    triple_double = chr(34) * 3
    triple_single = chr(39) * 3
    out: list[str] = []
    in_doc = False
    for raw in text.splitlines():
        line = raw.strip()
        fences = line.count(triple_double) + line.count(triple_single)
        if in_doc:
            if fences:
                in_doc = False
            continue
        if line.startswith("#"):
            continue
        if fences == 1:
            in_doc = True
            continue
        out.append(line)
    return out


def check(label: str) -> list[str]:
    """Every marker, against the files as they are on disk right now."""
    problems: list[str] = []
    for path, marker, decision in MARKERS:
        text = (REPO / path).read_text(encoding="utf-8")
        if marker not in text:
            problems.append(f"[{label}] {path}: MISSING {marker!r} — {decision}")
    for path, marker, decision in WITHDRAWN:
        code = code_lines((REPO / path).read_text(encoding="utf-8"))
        hit = next((line for line in code if marker in line), None)
        if hit is not None:
            problems.append(
                f"[{label}] {path}: STILL PRESENT {marker!r} — {decision} "
                f"(at: {hit[:70]!r})"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--command",
        default="",
        help="one shell string to launch instead of the declared CAMPAIGN",
    )
    parser.add_argument(
        "--campaign",
        action="store_true",
        help="launch the declared CAMPAIGN phases, in order (E15)",
    )
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="verify and report, launch nothing",
    )
    args = parser.parse_args(argv)

    # 1. As written.
    problems = check("after writing")
    # 2. After the formatter — which is what silently reverted a patch once
    #    before, and is the reason D8 names this step twice rather than once.
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "tools/bench"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    problems += check("after ruff format")

    if problems:
        print(
            "REFUSED — the harness on disk is not the harness these decisions describe:"
        )
        for line in problems:
            print(f"  {line}")
        print(
            "\nNothing was launched. This is the check that 1.5 h of rig time was "
            "spent for the want of."
        )
        return 1

    print(f"verified {len(MARKERS)} markers present and {len(WITHDRAWN)} absent")

    # E14, checked rather than assumed.
    running = already_running()
    if running:
        print("REFUSED — a campaign driver is already running on this client:")
        for line in running:
            print(f"  {line}")
        print(
            "\nThe rigs are measured one at a time (E14): the ramp times "
            "requests with THIS machine's clock, so a second driver would put "
            "its own contention inside the throughput curve."
        )
        return 1

    if args.campaign:
        phases = "; ".join(
            command.format(python=sys.executable) for _, command in CAMPAIGN
        )
        print("campaign phases, in order:")
        for name, _ in CAMPAIGN:
            print(f"  - {name}")
    else:
        phases = args.command
    if not phases:
        print("nothing to launch: pass --campaign or --command")
        return 1

    if args.dry_run:
        print(f"--dry-run: nothing launched. Would run:\n  {phases}")
        return 0

    args.log.parent.mkdir(parents=True, exist_ok=True)
    # Detached, because ssh sessions on these rigs drop under load and the
    # campaign must not depend on this terminal surviving nine hours.
    launched = subprocess.run(
        f"cd {REPO} && nohup sh -c {shlex.quote(phases)} > {args.log} 2>&1 "
        "< /dev/null & echo $!",
        shell=True,
        capture_output=True,
        text=True,
    )
    pid = (launched.stdout or "").strip()
    print(json.dumps({"launched": True, "pid": pid, "log": str(args.log)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
