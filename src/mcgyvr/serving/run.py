#!/usr/bin/env python3
"""The one access point to the rigs.

    python -m mcgyvr.serving.run --host srv1 --campaign <name> --model <blob>
                                 [--step <path>] [--suffix S] [-- STEP ARGS...]

Nothing else opens an ssh to srv1/srv2 or starts a container on one. A caller
that wants rig time writes its own script and names it as ``--step``, or takes
the shipped ``gate-scripts/default-step.sh``; the door runs the gates around
it. The step is the only part a caller supplies, and it is the only part that
is not fixed here.

HOW THE DOOR IS THE ONLY WAY IN. The environment a gate or a step runs under
has ``gate-scripts/bin`` first on PATH, where ``ssh`` and ``docker`` are shims
that admit exactly the host the door was opened for and refuse any process
the door did not start (:func:`mcgyvr.serving.gatelib.under_door` reads the
parent chain from /proc, which nothing can set). ``docker`` under the door is
the RIG's daemon (``-H ssh://<host>``), never the operator's. And the door
refuses to start under an ambient ``RUN_*`` or ``DOCKER_*`` variable: it mints
its own vocabulary, and a value inherited from the shell is one no gate set.

THE ACCEPTED LIMITS, in two sentences. The proof every gate, step and driver
applies is an ancestor's command line plus RUN_HOST, both of which an operator
can forge with ``bash -c ... x/mcgyvr/serving/run.py``, so the seal is against
every code path in this repository and not against an operator impersonating
the door. And a step is operator code run under the door: one that calls
``/usr/bin/ssh srv2`` by absolute path or ``env -i ssh srv2`` on a cleared
PATH reaches a second host, and that is the same limit — the seal is against
every code path in this repo (the tripwire in ``tests/test_one_door.py`` bans
an absolute-path ssh and an ``env -i`` in repo code), not against the step's
author.

WHAT "NONE IS SKIPPABLE" MEANS, MECHANICALLY. :data:`SEQUENCE` is the whole
run. There is no flag that omits an entry, no environment variable that short
-circuits one, and no ordering a caller can choose: `--help` will not show you
a way past a gate because there is not one. Deleting a script from
``gate-scripts/`` does not skip it either — a missing entry is a refusal, not
an absence, because "the file was gone" is exactly how a check stops running
without anyone deciding that it should.

WHY EVERY ENTRY FAILS LOUD. A gate that returns a warning is a gate that gets
ignored at 02:00 with a rig booked. Each entry exits non-zero and names the
rule it enforced; the door prints that text and stops. The one exception is
the pair that must run even when the step died — see :data:`ALWAYS` — and they
still refuse loudly, they simply do not prevent each other from running. Nor
does a signal: SIGINT and SIGTERM are ignored for the whole of the ALWAYS
phase (a ``kill -INT`` during gate 7 once escaped as a traceback with gate 8
never run), so 7 and 8 complete whatever arrives; an interrupt that landed
earlier still exits 130, otherwise the exit is what 7 and 8 decided. And the
claim gate 5 took on the RUN_ID (``.<RUN_ID>.running`` in the envelope) is
released on every exit path, the interrupted ones included.

WHERE A RUN IS FILED. The run root is ``$MCGYVR_RUN_ROOT`` when it is set and
the checkout otherwise (:func:`run_root`): the envelope is made under its
``records/evidence/``, and the round, ``hosts.json`` and the campaigns are
read from it. The code and the root are two places on purpose — an installed
wheel has no ``records/`` — and the door exports both, ``RUN_ROOT`` and
``RUN_BIN`` (its shim directory), so a step derives neither from the other. A
value naming a directory that does not exist is refused, never created.

GATE ORDER IS THE POINT, NOT AN IMPLEMENTATION DETAIL. Gates 1-5 refuse having
written nothing under ``records/``: gate 1 reaches no rig at all, and gates 2-5
only read one (a snapshot over ssh, a daemon's name) and never launch on it, so
a tree on the wrong round or a machine that is not what it claims costs no rig
time and leaves no artifact to clean up. The data scripts run after the rig is known to
be the declared one and before the step, because a placement derived against
the wrong machine is worse than no placement. Gates 7-8 run after the step
whatever it did.

THE CONTRACT WITH A GATE SCRIPT. It is an executable under ``gate-scripts/``.
It reads the run from the environment (:data:`EXPORTED`), writes anything it
learned as ``KEY=VALUE`` lines on the descriptor ``RUN_EXPORT_FD`` names, and exits 0 to
admit or non-zero having said why. It is not imported: a gate that could be
imported could be monkeypatched, and the seam that lets a test stub a gate is
the seam that lets a caller do it.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from mcgyvr.serving import gatelib

#: The package directory. ``gate-scripts`` carries a hyphen so it can never be
#: imported: these are executables the door SPAWNS, and a caller that could
#: `from mcgyvr.serving.gate_scripts import ...` could also replace one.
HERE = Path(__file__).resolve().parent
GATE_SCRIPTS = HERE / "gate-scripts"
#: What `ssh` and `docker` resolve to for everything the door starts.
BIN = GATE_SCRIPTS / "bin"
SHIMS = ("docker", "ssh")
#: The step a caller gets without naming one.
DEFAULT_STEP = GATE_SCRIPTS / "default-step.sh"
#: The shell files beside the gates that a gate READS rather than spawns.
#: `rig-snapshot.sh` is the reader gate 2 sends to the rig and gate 7 compares
#: against; `default-step.sh` is what a run without `--step` executes. Neither
#: is an entry in SEQUENCE, so neither was on the manifest — and a check that
#: covers only the entries someone remembered is the absence the manifest
#: exists to turn into a refusal: delete `rig-snapshot.sh` and gate 2 died on a
#: FileNotFoundError traceback, which is a gate that stopped running without
#: anyone deciding it should.
READERS = (DEFAULT_STEP, GATE_SCRIPTS / "rig-snapshot.sh")
#: The door's own serve steps, one per direction. Shipped beside the gates
#: because, like the default step, they belong to no campaign: a live ladder
#: is not an experiment, and the envelope it files under is the host's.
SERVE_STEPS = {
    "up": GATE_SCRIPTS / "serve-up.py",
    "down": GATE_SCRIPTS / "serve-down.py",
}
#: The door's vocabulary, and the daemon's: neither may be inherited.
MINTED_PREFIXES = ("RUN_", "DOCKER_")
#: A step's own output override, and its exists-check waiver. Refused before
#: gate 1 unless the path they name is inside the envelope (see
#: :func:`_check_step_args`).
OUTPUT_FLAGS = ("--out", "--out-dir")

#: The checkout this file sits in, four levels up (src/mcgyvr/serving/run.py),
#: and the run root when nothing names one. Read from the file's own location
#: and never from the caller's cwd, because a door invoked from a subdirectory
#: must still put evidence in one place.
ROOT = HERE.parents[2]
#: Names the run root: where the envelope is made (``records/evidence/``) and
#: where the gates read the declarations a run is measured against — the
#: round (``tools/bench/``), the rigs (``tools/runs/hosts.json``) and the
#: campaigns. Separate from the code because the code need not be a checkout:
#: from an installed wheel :data:`ROOT` is ``site-packages/``, and a run's
#: evidence written there is evidence nobody finds. See :func:`run_root`.
ROOT_ENV = "MCGYVR_RUN_ROOT"


class RefusedError(Exception):
    """A gate said no. Carries the exit status the door must propagate."""

    def __init__(self, status: int, rule: str) -> None:
        super().__init__(rule)
        self.status = status
        self.rule = rule


@dataclass(frozen=True)
class Entry:
    """One step of the run: a script under ``gate-scripts/`` and why it runs.

    ``exports`` names the KEY=VALUE lines this entry is allowed to add to the
    run environment. Declared here rather than trusted from the script's output
    so a gate cannot quietly introduce a variable a later gate reads: the door
    knows the whole vocabulary before anything runs.
    """

    script: str
    why: str
    status: int = 2
    exports: tuple[str, ...] = ()


#: THE RUN. Order is enforced, membership is enforced, and neither is
#: configurable. A caller's own script is gate 6's payload and appears nowhere
#: else in this list.
SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "01-round.py",
        "gate 1: the tree is on the open product round. A measurement taken "
        "against an unpinned tree cannot be compared with anything, so this "
        "refuses before the rig is touched",
        exports=("RUN_ROUND", "RUN_PRODUCT_SHA256"),
    ),
    Entry(
        "02-rig.py",
        "gate 2: the live machine equals its declaration in hosts.json. The "
        "steps' own start==end check catches a rig that moves DURING a run and "
        "says nothing about one that moved before it — RAM swapped between "
        "these two rigs twice in six days with every artifact internally "
        "consistent",
        exports=("RUN_PRE_RIG",),
    ),
    Entry(
        "03-image.py",
        "gate 3: the daemon a tag is resolved through answers NOW, and is the "
        "same one gate 7 asks about leftovers. A CLI with no daemon behind it "
        "passes `command -v` and fails inside the step, after the run is "
        "stamped, as a REFUSED row against the arm",
    ),
    Entry(
        "04-workload.py",
        "gate 4: the workload module generates the pinned prompts. The digest "
        "is over generated output and not the file text, so a formatter cannot "
        "void a comparison and a changed decile does",
    ),
    Entry(
        "05-envelope.py",
        "gate 5: the evidence directory is made, the step's declared artifacts "
        "are write-once, and RUN_ID is minted. Nothing recorded is overwritten",
        exports=(
            "RUN_ID",
            "RUN_OUT_DIR",
            "RUN_DATE",
            "RUN_STEP",
            "RUN_HOST",
            "RUN_DECLARED",
            "RUN_APPEND_STATE",
            "RUN_SUPERSEDED",
        ),
    ),
    # --- data scripts: the facts a placement needs, taken in the only order
    # --- in which each is meaningful. All three are mandatory for the same
    # --- reason the gates are: a run that sized itself from a stale reading is
    # --- indistinguishable, in the artifact, from one that measured.
    Entry(
        "data-10-scan.py",
        "the rig's own account of itself — card buckets, MemAvailable, "
        "threads — read live. `total = reserved + used + free`, and a card is "
        "not always idle: a foreign process held 3,374 of 5,743 MiB on srv1 "
        "with nothing of ours running",
        exports=("RUN_SCAN_JSON",),
    ),
    Entry(
        "data-20-geometry.py",
        "the checkpoint's geometry, summed from its own tensor table on the "
        "serving host. Bits-per-weight is a guess and the tensor table is not: "
        "two defensible estimates of one file's expert bytes disagreed by 14% "
        "and both were wrong",
        exports=("RUN_GEOMETRY_JSON",),
    ),
    Entry(
        "data-30-placement.py",
        "the --n-cpu-moe floor and what the card will hold, from the geometry "
        "and the scan. Refuses rather than guessing a cache it cannot size",
        exports=("RUN_PLACEMENT_JSON",),
    ),
    Entry(
        "06-step.py",
        "gate 6: the caller's own script, with the run exported to it. Its "
        "stdout and stderr are the operator's; the door adds nothing",
        status=1,
    ),
)

#: Runs after gate 6 whatever gate 6 did — a non-zero exit, a signal, a hard
#: lock that took the ssh pipe with it. A run whose end state is unknown is
#: exactly the one that ended silently, so these two are not conditional on the
#: step having succeeded, and a refusal in one does not stop the other.
ALWAYS: tuple[Entry, ...] = (
    Entry(
        "07-teardown.py",
        "gate 7: no container named for this run is left, and the rig reads as "
        "it did before. A leftover container is NAMED and not removed — the "
        "kill is the operator's, with the name in hand",
        status=1,
    ),
    Entry(
        "08-parse.py",
        "gate 8: every declared artifact exists and parses, and an appended "
        "file kept its prefix and grew. The parser once ran only in CI, so a "
        "run that wrote a file it rejects exited green on the rig and turned "
        "red a commit later",
        status=1,
    ),
)

#: THE SERVE RUN (`python -m mcgyvr.serving.run serve up|down --host H
#: --compose FILE`). A second fixed sequence, not a switch on the first: a
#: live ladder is started and LEFT RUNNING, which is the one thing the
#: campaign run exists to refuse, so the two cannot share gate 7's reading of
#: "left a container". What they share is every gate that makes a rig the
#: declared rig — the round, the machine, the daemon, the envelope — and the
#: two that run after whatever the step did. Gate 4 (the pinned workload) and
#: the three data scripts (a checkpoint's geometry and placement) are about
#: one model under measurement and have no meaning for a compose file
#: `mcgyvr emit` already sized; they are not skipped, they are not in this
#: run. Order and membership are enforced exactly as for SEQUENCE.
SERVE_SEQUENCE: tuple[Entry, ...] = tuple(
    entry
    for entry in SEQUENCE
    if entry.script
    in ("01-round.py", "02-rig.py", "03-image.py", "05-envelope.py", "06-step.py")
)

#: The full vocabulary a gate script may read. A script that wants something
#: not on this list is asking for a fact nobody gated.
EXPORTED = (
    # The run root (:func:`run_root`) and the door's own shim directory. Two
    # variables because they are two places: the root is where a run is filed
    # and measured against, the shims are part of the code, and a step that
    # derived one from the other found no shims under a run root that was not
    # a checkout.
    "RUN_ROOT",
    "RUN_BIN",
    "RUN_CAMPAIGN",
    "RUN_STEP_FILE",
    "RUN_HOST",
    "RUN_SUFFIX",
    "RUN_MODEL",
    "RUN_PARALLEL",
    "RUN_CTX_PER_SLOT",
    "RUN_UBATCH",
    # The serve run's own three: which direction, which file, and the
    # container names the door read out of it before anything ran.
    "RUN_SERVE",
    "RUN_COMPOSE",
    "RUN_SERVE_EXPECTED",
    *(name for entry in (*SEQUENCE, *ALWAYS) for name in entry.exports),
)

#: `KEY=VALUE`, where VALUE runs to end of line. Anything else on the export
#: descriptor is a
#: gate trying to say something the door has no vocabulary for.
EXPORT_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _refuse(status: int, rule: str) -> NoReturn:
    raise RefusedError(status, rule)


def run_root() -> Path:
    """The run root: ``$MCGYVR_RUN_ROOT`` when it is set, else the checkout.

    A value that is set names a directory that exists, or the run is refused
    before any gate — the door does not create it. A root the door made
    silently is how evidence goes missing: the operator meant one directory,
    typed another, and the run filed itself under a path nobody looks at,
    exit 0. Resolved, so every gate sees one spelling of it (``RUN_ROOT`` is
    exported once, by the door, and gate 5 files under exactly that).
    """
    named = os.environ.get(ROOT_ENV)
    if named is None:
        return ROOT
    path = Path(named).expanduser()
    if not named or not path.is_dir():
        _refuse(
            2,
            f"{ROOT_ENV}={named!r} is not an existing directory. The run root "
            "is where the envelope is made (records/evidence/) and where the "
            "round, hosts.json and the campaigns are read from; the door never "
            "creates it, because a root made silently is a run filed where "
            "nobody looks. Name a directory that exists, or unset the variable "
            f"to use the checkout ({ROOT})",
        )
    return path.resolve()


def check_manifest() -> None:
    """Every entry exists and is executable, BEFORE anything runs.

    Checked as a set rather than lazily at each step, so a run cannot get four
    gates in — past the round check, past the rig comparison — and then stop
    because the fifth file is missing. And checked at all because a deleted
    script is the cheapest way to skip a gate: without this, `rm` is a flag.

    :data:`READERS` is on the list for the same reason the gates are. A file a
    gate reads is part of the door whether or not the door spawns it, and one
    that can go missing unnoticed makes the promise above true only of the
    entries someone remembered to list.
    """
    missing = [
        e.script
        for e in (*SEQUENCE, *ALWAYS)
        if not (GATE_SCRIPTS / e.script).is_file()
    ] + [path.name for path in (*SERVE_STEPS.values(), *READERS) if not path.is_file()]
    if missing:
        _refuse(
            2,
            f"the door is incomplete: {', '.join(missing)} not under "
            f"{_rel(GATE_SCRIPTS)}. Every entry in SEQUENCE runs on "
            "every run; a missing one is a refusal and never a skip, because "
            "'the file was gone' is how a check stops running without anyone "
            "deciding it should",
        )
    unrunnable = [
        e.script
        for e in (*SEQUENCE, *ALWAYS)
        if not os.access(GATE_SCRIPTS / e.script, os.X_OK)
    ] + [step.name for step in SERVE_STEPS.values() if not os.access(step, os.X_OK)]
    if unrunnable:
        _refuse(
            2,
            f"not executable: {', '.join(unrunnable)}. chmod +x, or the door "
            "cannot run a gate it is holding you to",
        )
    # The shims are what make `ssh` and `docker` under the door reach the
    # door's host and nothing else; a missing one means PATH falls through to
    # the operator's binaries, which is every hole at once.
    shims_gone = [
        name
        for name in SHIMS
        if not ((BIN / name).is_file() and os.access(BIN / name, os.X_OK))
    ]
    if shims_gone:
        _refuse(
            2,
            f"the door is incomplete: {', '.join(shims_gone)} not executable "
            f"under {_rel(BIN)}. Under the door every rig connection and every "
            "docker call goes through these shims; without one, PATH falls "
            "through to the operator's binary and nothing admits the host",
        )


def _run_entry(entry: Entry, env: dict[str, str], args: list[str] | None = None) -> int:
    """Spawn one entry, fold its exports into ``env``, return its status.

    A pipe and not stdout: a gate's stdout belongs to the operator, and a gate
    that had to keep quiet to pass a value back would be a gate nobody could
    debug. The pipe is read after the process exits, so a gate that dies
    mid-sentence exports nothing rather than half a value.

    The descriptor's NUMBER is named in the child's environment. ``pass_fds``
    keeps a descriptor open at the number it already has and does not move it
    to 3, so a gate writing to a hardcoded 3 writes to whatever happens to sit
    there — which it did, silently, while still exiting 0. The declared-exports
    check below is what caught it.
    """
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(
            [sys.executable, str(GATE_SCRIPTS / entry.script), *(args or [])],
            cwd=env.get("RUN_ROOT") or ROOT,
            env=dict(env, RUN_EXPORT_FD=str(write_fd)),
            pass_fds=(write_fd,),
        )
        os.close(write_fd)
        write_fd = -1
        with os.fdopen(read_fd, "r", encoding="utf-8", errors="replace") as pipe:
            read_fd = -1
            try:
                reported = pipe.read()
                status = proc.wait()
            except KeyboardInterrupt:
                # The entry is ended BEFORE the door moves on: gate 7 re-reads
                # the rig and looks for containers, and a step still running
                # under it would make both readings lies. A terminal's Ctrl-C
                # already reached the child; a bare `kill` of the door did not.
                _end(proc)
                raise
    finally:
        for fd in (read_fd, write_fd):
            if fd >= 0:
                os.close(fd)

    for line in reported.splitlines():
        if not line.strip():
            continue
        match = EXPORT_LINE.match(line)
        if match is None:
            _refuse(
                2,
                f"{entry.script} wrote {line!r} on RUN_EXPORT_FD, which is not "
                "KEY=VALUE; the door passes named facts between gates and "
                "nothing else",
            )
        key, value = match.group(1), match.group(2)
        if key not in entry.exports:
            _refuse(
                2,
                f"{entry.script} exported {key}, which it does not declare in "
                "SEQUENCE. The door knows the whole vocabulary before anything "
                "runs, so a gate cannot introduce a variable a later gate reads",
            )
        env[key] = value

    missing = [k for k in entry.exports if k not in env]
    if status == 0 and missing:
        _refuse(
            2,
            f"{entry.script} exited 0 without exporting {', '.join(missing)}; "
            "an entry that admits the run must produce what it declares, or a "
            "later gate reads an empty value as a fact",
        )
    return status


def _parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Arguments. Note what is absent: there is no --skip, --no-gate or --force.

    Adding one would not be a feature, it would be the hole every gate here was
    written to close, and the flag would be reached for on exactly the night it
    should not be.
    """
    step_args: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, step_args = argv[:cut], argv[cut + 1 :]
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run",
        description="the one access point to the rigs",
    )
    parser.add_argument(
        "--host", required=True, help="srv1 | srv2, as declared in hosts.json"
    )
    parser.add_argument("--campaign", required=True, help="names the evidence envelope")
    parser.add_argument(
        "--step",
        default="",
        help="the caller's own script; gate 6 runs it (default: "
        "gate-scripts/default-step.sh)",
    )
    parser.add_argument("--suffix", default="", help="distinguishes a re-run's RUN_ID")
    parser.add_argument("--date", default="", help="YYYY-MM-DD; defaults to today, UTC")
    # --model is required, and that is the door saying what it is for. Every run
    # through mcgyvr.serving.run serves a checkpoint, so the geometry and
    # placement scripts always have something to read; an optional model would
    # make them conditional, and a conditional gate is a skippable one.
    parser.add_argument("--model", required=True, help="blob path AS THE RIG SEES IT")
    parser.add_argument("--parallel", type=int, default=8, help="slots (-np)")
    parser.add_argument(
        "--ctx-per-slot",
        type=int,
        default=2048,
        help="per-slot window; -c is this times --parallel",
    )
    parser.add_argument("--ubatch", type=int, default=512, help="-ub, and -b with it")
    return parser.parse_args(argv), step_args


def _end(proc: subprocess.Popen[bytes]) -> None:
    """Stop a child that outlived the interrupt, and wait for it to be gone."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


#: What a `--model` may contain: an absolute path of ordinary path characters.
#: The value is interpolated into a remote shell line by data-20 (quoted there
#: too), named in container argv by the step, and stamped into rows, so a
#: character that means something to a shell is refused here, before a gate
#: runs, rather than escaped in three places.
MODEL_PATH = re.compile(r"^/[A-Za-z0-9._+@=,:/-]+$")


def _model_escape(model: str) -> str | None:
    """Why ``model`` cannot be handed to a rig, or None when it can."""
    if not MODEL_PATH.match(model):
        bad = sorted({c for c in model if not re.match(r"[A-Za-z0-9._+@=,:/-]", c)})
        where = f"characters {bad!r}" if bad else "a relative path"
        return (
            f"--model {model!r} is refused: it carries {where}, and a model path "
            "is an absolute path of ordinary characters AS THE RIG SEES IT "
            "(e.g. /models/moe/x.gguf); it is handed to a remote shell and to "
            "container argv, and nothing here escapes it"
        )
    if "/../" in model or model.endswith("/..") or "//" in model:
        return (
            f"--model {model!r} is refused: a model path names one blob outright, "
            "with no '..' segment and no empty segment"
        )
    return None


def _ambient() -> str | None:
    """The first inherited variable the door would otherwise have to trust.

    ``RUN_*`` is the door's vocabulary and ``DOCKER_*`` is the daemon's
    (``DOCKER_HOST`` alone redirects every container to another machine). A
    value that was in the shell before the door ran is one no gate set, and a
    gate reads its environment as fact.
    """
    for name in sorted(os.environ):
        if name.startswith(MINTED_PREFIXES):
            return name
    return None


def _inside(path: Path, envelope: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(envelope.resolve(strict=False))
    except ValueError:
        return False
    return True


def _check_step_args(
    step_args: list[str], envelope: Path, root: Path = ROOT
) -> str | None:
    """A step's own output flag may not leave the envelope — the door owns it.

    Ported from the archived door (archive/runs/run.sh, check_step_args): six
    steps kept an output override from their bare-run days and three a
    ``--force``; through the door, ``-- --out <recorded file>`` overwrote
    committed evidence under a green line and ``-- --out-dir <anywhere>``
    filed a run where gates 5, 7 and 8 could not see it. Refused here, before
    gate 1, so nothing is checked and nothing is made. An output flag naming
    a path INSIDE the envelope is the one form that changes nothing, so it is
    admitted; ``--force`` has no such form.
    """
    for index, token in enumerate(step_args):
        if token == "--force":
            return (
                f"step argument '{token}' is refused: the door owns the envelope "
                f"({_rel(envelope, root)}/) and every declared artifact is written "
                "there, once. A re-run is --suffix S over a RUN_REWRITES "
                "declaration; nothing is written elsewhere, or by force"
            )
        for flag in OUTPUT_FLAGS:
            if token == flag:
                value = step_args[index + 1] if index + 1 < len(step_args) else ""
            elif token.startswith(flag + "="):
                value = token[len(flag) + 1 :]
            else:
                continue
            target = Path(value)
            target = target if target.is_absolute() else root / target
            if not value or not _inside(target, envelope):
                return (
                    f"step argument '{flag} {value}' is refused: it names a path "
                    f"outside the envelope {_rel(envelope, root)}/, and the door owns "
                    "the envelope — every declared artifact is written there, "
                    "once. A re-run is --suffix S over a RUN_REWRITES "
                    "declaration; nothing is written elsewhere"
                )
    return None


def _rel(path: Path, base: Path = ROOT) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _serve_parse(argv: list[str]) -> argparse.Namespace:
    """The serve run's arguments. As with :func:`_parse`, nothing skips a gate."""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run serve",
        description="start a live ladder on a rig and leave it running, or stop it",
    )
    parser.add_argument("mode", choices=sorted(SERVE_STEPS), help="up | down")
    parser.add_argument(
        "--host", required=True, help="srv1 | srv2, as declared in hosts.json"
    )
    parser.add_argument(
        "--compose",
        required=True,
        help="the compose file `mcgyvr emit` wrote for this host",
    )
    parser.add_argument("--suffix", default="", help="distinguishes a re-run's RUN_ID")
    parser.add_argument("--date", default="", help="YYYY-MM-DD; defaults to today, UTC")
    return parser.parse_args(argv)


def _serve(argv: list[str]) -> int:
    """`serve up|down`: the second fixed sequence, to completion."""
    opts = _serve_parse(argv)
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    try:
        root = run_root()
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    compose_file = Path(opts.compose)
    compose_file = (
        compose_file if compose_file.is_absolute() else Path.cwd() / compose_file
    )
    if not compose_file.is_file():
        print(
            f"run.py: REFUSED — --compose {opts.compose} is not a file; "
            "`mcgyvr emit` writes one per host",
            file=sys.stderr,
        )
        return 2
    # Read here, before any gate, so the names gate 7 will expect are the
    # door's reading of the file and not the step's: a step that could
    # declare its own expected set could declare away a stranger.
    from mcgyvr.serving import servelib

    try:
        units = servelib.services(compose_file)
    except servelib.ComposeError as escape:
        print(f"run.py: REFUSED — {escape}", file=sys.stderr)
        return 2

    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    env.update(
        RUN_ROOT=str(root),
        RUN_BIN=str(BIN),
        RUN_CAMPAIGN=f"live-{opts.host}",
        RUN_STEP_FILE=str(SERVE_STEPS[opts.mode].resolve()),
        RUN_HOST=opts.host,
        RUN_SUFFIX=opts.suffix,
        RUN_SERVE=opts.mode,
        RUN_COMPOSE=str(compose_file.resolve()),
        RUN_SERVE_EXPECTED=" ".join(unit.container for unit in units),
    )
    if opts.date:
        env["RUN_DATE"] = opts.date

    interrupted = False
    step_status = 0
    try:
        try:
            check_manifest()
            for entry in SERVE_SEQUENCE:
                status = _run_entry(entry, env)
                if status != 0:
                    if entry.script != "06-step.py":
                        return _stop(entry, status, env)
                    step_status = status
        except RefusedError as refusal:
            print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
            return refusal.status
        except KeyboardInterrupt:
            interrupted = True
            print(
                "run.py: interrupted — gates 7 and 8 still run; a run whose end "
                "state is unknown is the one that ended silently",
                file=sys.stderr,
            )

        after = _always(env)
        if interrupted:
            return 130
        return step_status or after
    finally:
        # Gate 5's claim is released here and not only in `_always`, which
        # a refusal between the claim and the always-block returns straight
        # past. Releasing twice is releasing once: `gatelib.release`
        # unlinks `missing_ok`.
        _release_claim(env)


def main(argv: list[str] | None = None) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    if given[:1] == ["serve"]:
        return _serve(given[1:])
    opts, step_args = _parse(given)

    # Every refusal below happens before a gate runs: nothing checked, nothing
    # made, no rig read.
    escape = _model_escape(opts.model)
    if escape is not None:
        print(f"run.py: REFUSED — {escape}", file=sys.stderr)
        return 2
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary (RUN_* and "
            "DOCKER_* are the door's to set, and a value inherited from the "
            "shell is one no gate set)",
            file=sys.stderr,
        )
        return 2
    # The root is settled before the step is looked for and before the
    # envelope is named, because both are said relative to it.
    try:
        root = run_root()
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status

    if opts.step:
        step = Path(opts.step)
        step = step if step.is_absolute() else (Path.cwd() / step)
        if not step.is_file():
            print(
                f"run.py: REFUSED — --step {opts.step} is not a file", file=sys.stderr
            )
            return 2
    else:
        step = DEFAULT_STEP
        if not step.is_file():
            print(
                f"run.py: REFUSED — the default step is missing: "
                f"{_rel(DEFAULT_STEP)} does not exist, and the door does not "
                "write one; name a step with --step PATH",
                file=sys.stderr,
            )
            return 2

    run_date = opts.date or datetime.now(UTC).strftime("%Y-%m-%d")
    envelope = root / "records" / "evidence" / f"{run_date}-{opts.campaign}"
    escape = _check_step_args(step_args, envelope, root)
    if escape is not None:
        print(f"run.py: REFUSED — {escape}", file=sys.stderr)
        return 2

    env = dict(os.environ)
    # The shims come first, so `ssh` and `docker` under the door are the
    # door's; whatever PATH the operator had follows for everything else.
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    env.update(
        RUN_ROOT=str(root),
        RUN_BIN=str(BIN),
        RUN_CAMPAIGN=opts.campaign,
        RUN_STEP_FILE=str(step.resolve()),
        RUN_HOST=opts.host,
        RUN_SUFFIX=opts.suffix,
        RUN_MODEL=opts.model,
        RUN_PARALLEL=str(opts.parallel),
        RUN_CTX_PER_SLOT=str(opts.ctx_per_slot),
        RUN_UBATCH=str(opts.ubatch),
    )
    if opts.date:
        env["RUN_DATE"] = opts.date

    interrupted = False
    step_status = 0
    try:
        try:
            check_manifest()
            for entry in SEQUENCE:
                args = step_args if entry.script == "06-step.py" else None
                status = _run_entry(entry, env, args)
                if status != 0:
                    if entry.script != "06-step.py":
                        return _stop(entry, status, env)
                    # The step's own failure is the operator's result, not the
                    # door's refusal: 7 and 8 still run, and its status propagates
                    # after them.
                    step_status = status
        except RefusedError as refusal:
            print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
            return refusal.status
        except KeyboardInterrupt:
            # Ctrl-C or SIGTERM (`_sigterm` turns it into this). The entry that
            # was running has been ended by `_run_entry`; what follows is the
            # main flow, not a signal handler, so gate 7's own ssh is not the
            # nested read that came back empty in the shell door.
            interrupted = True
            print(
                "run.py: interrupted — gates 7 and 8 still run; a run whose end "
                "state is unknown is the one that ended silently",
                file=sys.stderr,
            )

        after = _always(env)

        if interrupted:
            return 130
        return step_status or after
    finally:
        # Gate 5's claim is released here and not only in `_always`, which
        # a refusal between the claim and the always-block returns straight
        # past. Releasing twice is releasing once: `gatelib.release`
        # unlinks `missing_ok`.
        _release_claim(env)


#: What the ALWAYS phase will not be stopped by.
UNSTOPPABLE = (signal.SIGINT, signal.SIGTERM)


def _always(env: dict[str, str]) -> int:
    """Gates 7 and 8, to completion, whatever signal arrives meanwhile.

    A signal handled here would end the entry that was running — gate 7
    mid-read of the rig, gate 8 mid-parse — and the run's end state would be
    exactly as unknown as if neither had run. So both signals are ignored
    for the whole phase and restored after it; a run interrupted before this
    phase still exits 130 (the caller keeps that), and one interrupted
    during it exits with what 7 and 8 decided. The claim gate 5 took on the
    RUN_ID is released last, on every path out of here.
    """
    if "RUN_ID" not in env:
        return 0  # gate 5 never minted a run: nothing was started to tear down
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in UNSTOPPABLE}
    after = 0
    try:
        for entry in ALWAYS:
            try:
                if _run_entry(entry, env) != 0:
                    print(f"run.py: {entry.why}", file=sys.stderr)
                    after = entry.status
            except RefusedError as refusal:
                print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
                after = refusal.status
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        _release_claim(env)
    return after


def _release_claim(env: dict[str, str]) -> None:
    """Release gate 5's claim on the RUN_ID, if this run holds one."""
    out_dir, run_id = env.get("RUN_OUT_DIR"), env.get("RUN_ID")
    if out_dir and run_id:
        gatelib.release(Path(out_dir), run_id)


def _stop(entry: Entry, status: int, env: dict[str, str]) -> int:
    """A gate before the step refused: say which rule, and stop."""
    print(f"run.py: REFUSED at {entry.script} — {entry.why}", file=sys.stderr)
    return status or entry.status


def _sigterm(_signum: int, _frame: types.FrameType | None) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _sigterm)
    sys.exit(main())
