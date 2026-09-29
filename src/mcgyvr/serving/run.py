#!/usr/bin/env python3
"""The one access point to the rigs.

    python -m mcgyvr.serving.run --host srv1 --campaign <name> --model <blob>
                                 --ctx-per-slot N [--step <path>] [--suffix S]
                                 [-- STEP ARGS...]

Nothing else opens an ssh to srv1/srv2 or starts a container on one. A caller
that wants rig time writes its own script and names it as ``--step``, or takes
the shipped ``gate-scripts/default-step.sh``; the door runs the gates around
it. The step is the one part of a campaign run a caller supplies; ``serve``
and ``read`` take a caller's own gates too (A CALLER'S GATES, below), which
run inside the door's fixed order and never in place of any of it.

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

GATE ORDER IS THE POINT, NOT AN IMPLEMENTATION DETAIL. Gates 1-4 write nothing
under ``records/``: gate 1 reaches no rig, gate 2 takes the rig's lease (a live
run tears down what it displaced) and reads the rig, gates 3-4 only read, and
none launches anything, so a tree on the wrong round or a machine that is not
what it claims leaves no artifact to clean up. Gate 5 stamps the lease and
makes the envelope. The data scripts run after the rig is known to be the
declared one and before the step, because a placement derived against the
wrong machine is worse than no placement. Gates 7-8 run after the step
whatever it did.

A CALLER'S GATES. ``serve`` and ``read`` take ``--gates FILE``: a JSON object
naming a ``root`` folder and a list of gates, each ``{path, why, phase,
exports[, timeout_s]}``. The door runs them inside its own run and never
instead of any part of it; a ``before`` or ``after`` gate that refuses ends
the run like a door gate that refuses. ``before`` runs after the door's
profile gate, which reads no machine, and before anything is sent to one. On
``serve``, ``after``
runs after the identity and daemon gates and before the envelope and the
step, and ``always`` after gates 7 and 8, before the lease is released, and
only when the run got as far as gate 5. On ``read``, ``after`` runs after the
reading gate has read the machine and filed what it read, and only when that
gate exited 0; it cannot stop the filing. ``always`` is refused on a read,
which has no teardown and no lease. The list is read and held to
:func:`load_gate_list` before any gate runs, and each gate's path is checked
again just before it starts. A caller's gate is run by the door's Python from
its list's root, which it sees as ``RUN_ROOT``, in a process group of its own,
for at most its ``timeout_s`` (:data:`CALLER_GATE_TIMEOUT_S` when the list
gives none); it may export only the ``RUN_`` names its list declares, none of
them a name the door sets (:data:`DOOR_NAMES`).

THE CONTRACT WITH A GATE SCRIPT. The door's own gates are executables under
``gate-scripts/``; a caller's gates are the executables its list names.
A gate reads the run from the environment (:data:`EXPORTED`), writes anything
it learned as ``KEY=VALUE`` lines on the descriptor ``RUN_EXPORT_FD`` names,
and exits 0 to admit or non-zero having said why. It is not imported: a gate
that could be imported could be monkeypatched, and the seam that lets a test
stub a gate is the seam that lets a caller do it.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import secrets
import select
import signal
import subprocess
import sys
import time
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from mcgyvr.config import CONFIG_PATH_ENV
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
#: `rig-units.sh` is the second half of the one reader the read run ships to a
#: rig, behind `rig-snapshot.sh` (gate-scripts/read-02-rig.py).
READERS = (
    DEFAULT_STEP,
    GATE_SCRIPTS / "rig-snapshot.sh",
    GATE_SCRIPTS / "rig-units.sh",
)
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
    #: Empty for the door's own entries. For a caller's gate, the root its
    #: gate list names: the gate runs there and sees it as ``RUN_ROOT``, and
    #: ``script`` is the absolute path the list names, resolved and held to
    #: the root again just before the gate starts.
    root: str = ""
    #: A caller's gate's time bound in seconds. The door's own entries have
    #: none (0).
    timeout_s: float = 0.0


#: THE RUN. Order is enforced, membership is enforced, and neither is
#: configurable. A caller's own script is gate 6's payload and appears nowhere
#: else in this list.
SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "01-round.py",
        "gate 1: the tree is on the open product round, and the run knows "
        "which profile it is under. A measurement taken against an unpinned "
        "tree cannot be compared with anything, and a dev run does not touch "
        "the live ladder, so both refuse before the rig is touched",
        exports=(
            "RUN_ROUND",
            "RUN_PRODUCT_SHA256",
            "RUN_PROFILE",
            "RUN_CONFIG",
        ),
    ),
    Entry(
        "02-rig.py",
        "gate 2: the rig is leased to this run — a dev run yields to a held "
        "rig, a live run takes it and tears down what it displaced (R1) — "
        "and the live machine equals its declaration in hosts.json. The "
        "steps' own start==end check catches a rig that moves DURING a run and "
        "says nothing about one that moved before it — RAM swapped between "
        "these two rigs twice in six days with every artifact internally "
        "consistent",
        exports=("RUN_LEASE", "RUN_DISPLACED", "RUN_PRE_RIG"),
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
        "not always idle, so the VRAM term is `free`",
        exports=("RUN_SCAN_JSON",),
    ),
    Entry(
        "data-20-geometry.py",
        "the checkpoint's geometry, summed from its own tensor table on the "
        "serving host. Bits-per-weight is a guess and the tensor table is not",
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
        "file kept its prefix and grew",
        status=1,
    ),
)

#: What releases the rig's lease on every way out. Spawned from the door's
#: `finally` like gate 5's claim is unlinked there, and on the manifest for
#: the same reason the gates are: a release that could go missing is a lease
#: that outlives every run.
LEASE_RELEASE = Entry(
    "lease-release.py",
    "the rig's lease is released if it is still this run's; a rig that "
    "cannot be reached is said, and the lease reads as stale to the next run "
    "on this machine",
    status=1,
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

#: THE READ RUN (`python -m mcgyvr.serving.run read --host H [--probe UNIT...
#: [--load WxN]]`). A third fixed sequence: the profile is settled and no round
#: is opened, then one reader goes to the rig, is compared with the rig's
#: declaration, and is filed. A plain read starts nothing on the rig; `--probe`
#: and `--load` run the lock's harness there against idle units. There is no
#: lease, no envelope, no teardown and no gate 7 or 8 in it.
READ_SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "read-01-profile.py",
        "read, profile: the read knows which profile it is under, as gate 1 "
        "settles it, and no round is appended: a reading pins no tree",
        exports=("RUN_PROFILE", "RUN_CONFIG"),
    ),
    Entry(
        "read-02-rig.py",
        "read, rig: one reader on the rig, its facts held to hosts.json and the "
        "rest filed under the read fleet's journal; nothing leased, nothing torn "
        "down, and a busy rig read as it is",
    ),
)
#: A read's id, which every row it files carries: the probe's own shape.
READ_ID = re.compile(r"^run-(\d{8}T\d{6})-([0-9a-f]{8})$")
#: A load a read runs on its probed units: W concurrent requests, each filling an
#: N-token window.
LOAD_SPEC = re.compile(r"^([1-9][0-9]*)x([1-9][0-9]*)$")


def mint_read_id(now: datetime | None = None) -> str:
    """A fresh read id, stamped with the moment it was minted."""
    moment = now if now is not None else datetime.now(UTC)
    return f"run-{moment:%Y%m%dT%H%M%S}-{secrets.token_hex(4)}"


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
    # The read run's own four: the id its rows are filed under, the units it
    # runs the lock's harness for on the rig, the load it runs on them, and
    # the setup fleet it reads in place of the live one (`--fleet`).
    "RUN_READ_ID",
    "RUN_READ_PROBE",
    "RUN_READ_LOAD",
    "RUN_READ_FLEET",
    *(name for entry in (*SEQUENCE, *ALWAYS) for name in entry.exports),
)

#: Every name the door sets for its own gates: the vocabulary above, what the
#: read's entries export, and the export descriptor's own name. A caller's
#: gate may not export one of these, because a door gate would read it.
DOOR_NAMES = frozenset(
    {
        *EXPORTED,
        *(name for entry in (*READ_SEQUENCE, LEASE_RELEASE) for name in entry.exports),
        "RUN_EXPORT_FD",
    }
)
#: The names a caller's gate may export: the door's own prefix, so no value
#: can be inherited under one (see :func:`_ambient`) and none is a variable
#: that changes how a program runs (``PATH``, ``LD_PRELOAD``, ...).
CALLER_EXPORT = re.compile(r"RUN_[A-Z0-9_]+")
#: The phases of a caller's gate list.
PHASES = ("before", "after", "always")
#: Where each phase runs, as the door entry it follows. ``before`` follows the
#: profile gate, which reads no machine, so it runs before the first gate that
#: reaches one. ``always`` is not here: on ``serve`` it runs after
#: :data:`ALWAYS`, and a read has no such phase.
SERVE_PHASES = {"before": "01-round.py", "after": "03-image.py"}
READ_PHASES = {"before": "read-01-profile.py", "after": "read-02-rig.py"}
#: The keys of a gate list, and of one gate in it. Anything else is refused.
GATE_LIST_KEYS = frozenset({"root", "gates"})
GATE_KEYS = frozenset({"path", "why", "phase", "exports", "timeout_s"})
#: How long a caller's gate may run when its list gives no ``timeout_s``.
CALLER_GATE_TIMEOUT_S = 600.0
#: The most gates a list may hold. Far above any list a caller writes by
#: hand; a list longer than this is refused rather than read at length.
MAX_GATES = 256
#: The package's own folder. A list whose root is, holds or lies inside it
#: could name the door's own scripts and run them out of the door's order.
PACKAGE = HERE.parent


@dataclass(frozen=True)
class GateList:
    """A caller's gates, by phase, as :func:`load_gate_list` admitted them."""

    source: Path
    root: Path
    before: tuple[Entry, ...] = ()
    after: tuple[Entry, ...] = ()
    always: tuple[Entry, ...] = ()

    @property
    def exports(self) -> frozenset[str]:
        """Every name a gate of this list may export."""
        return frozenset(
            name
            for entry in (*self.before, *self.after, *self.always)
            for name in entry.exports
        )


class _TwiceError(ValueError):
    """A JSON object names one key twice."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _once(pairs: list[tuple[str, object]]) -> dict[str, object]:
    held: dict[str, object] = {}
    for key, value in pairs:
        if key in held:
            raise _TwiceError(key)
        held[key] = value
    return held


def _printable(text: str) -> str:
    """``text`` as a terminal can print it: a lone surrogate is escaped."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def load_gate_list(named: str, phases: tuple[str, ...] = PHASES) -> GateList:
    """Read the gate list ``named``, or refuse it naming the file and the entry.

    A gate list is input the door does not trust. Refused here, before any
    gate runs: an empty name; a file that is not a regular file of JSON (too
    deep, a number JSON will not read and a key given twice included) holding
    an object of ``root`` and ``gates``; a key the door does not know; a root
    that is not an existing folder named by an absolute path, or that is,
    holds or lies inside :data:`PACKAGE`; more than :data:`MAX_GATES` gates;
    a gate whose path cannot be a path, is missing, is not an executable file,
    or resolves (through ``..`` or a link) outside the root; a phase not in
    ``phases``; a ``timeout_s`` that is not a positive number; an export that
    is not a ``RUN_`` name, is one of :data:`DOOR_NAMES`, or is declared by two
    gates.
    """
    if not named:
        _refuse(
            2,
            "--gates names no file. A launcher that meant to pass a list and "
            "passed an empty name would otherwise run without its gates",
        )
    source = Path(named)
    source = source if source.is_absolute() else Path.cwd() / source

    def no(where: str, why: str) -> NoReturn:
        _refuse(2, _printable(f"--gates {source}: {where} {why}"))

    try:
        regular = source.is_file()
    except (OSError, ValueError) as escape:
        no("the list", f"cannot be read ({escape})")
    if not regular:
        no("the list", "cannot be read: it is not a regular file")
    try:
        doc = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_once)
    except OSError as escape:
        no("the list", f"cannot be read ({escape.strerror or escape!r})")
    except _TwiceError as twice:
        no(f"key {twice.key!r}", "is given twice; a list states each key once")
    except (ValueError, RecursionError) as escape:
        no("the list", f"is not JSON the door reads ({type(escape).__name__})")
    if not isinstance(doc, dict):
        no("the list", "is not a JSON object of `root` and `gates`")
    for key in sorted(set(doc) - GATE_LIST_KEYS):
        no(f"key {key!r}", "is not a gate list key; a list holds `root` and `gates`")
    raw_root = doc.get("root")
    root = Path(raw_root) if isinstance(raw_root, str) and raw_root else None
    try:
        usable = root is not None and root.is_absolute() and root.is_dir()
    except (OSError, ValueError):
        usable = False
    if root is None or not usable:
        no(
            "root",
            f"{raw_root!r} is not an existing folder named by an absolute path; "
            "a caller's gates run there and read it as RUN_ROOT",
        )
    root = root.resolve()
    package = PACKAGE.resolve()
    if root.is_relative_to(package) or package.is_relative_to(root):
        no(
            "root",
            f"{root} is, holds or lies inside the package's own folder "
            f"{package}; a list could then run the door's own scripts out of "
            "the door's order",
        )
    gates = doc.get("gates")
    if not isinstance(gates, list):
        no("gates", "is not a list")
    if len(gates) > MAX_GATES:
        no("gates", f"holds {len(gates)} gates; a list holds at most {MAX_GATES}")

    held: dict[str, list[Entry]] = {phase: [] for phase in PHASES}
    declared: dict[str, str] = {}
    for index, gate in enumerate(gates):
        where = f"gates[{index}]"
        if not isinstance(gate, dict):
            no(where, "is not an object of path, why, phase and exports")
        path = gate.get("path")
        if isinstance(path, str) and path:
            where = f"{where} ({path!r})"
        for key in sorted(set(gate) - GATE_KEYS):
            no(where, f"carries {key!r}, which is not a gate key")
        if not isinstance(path, str) or not path:
            no(where, "names no path")
        why = gate.get("why")
        if not isinstance(why, str) or not why.strip():
            no(where, "says no `why`; a gate that refuses must say what it holds")
        phase = gate.get("phase")
        if phase not in phases:
            no(
                where,
                f"asks for phase {phase!r}; this run has "
                f"{', '.join(phases)} and no other"
                + (
                    " (a read has no teardown and no lease for an `always` "
                    "gate to follow)"
                    if phase == "always"
                    else ""
                ),
            )
        bound = gate.get("timeout_s", CALLER_GATE_TIMEOUT_S)
        if (
            isinstance(bound, bool)
            or not isinstance(bound, int | float)
            or not math.isfinite(bound)
            or bound <= 0
        ):
            no(where, f"gives timeout_s {bound!r}; a bound is a positive number")
        exports = gate.get("exports", [])
        if not isinstance(exports, list) or not all(
            isinstance(name, str) for name in exports
        ):
            no(where, "`exports` is not a list of names")
        target = Path(path)
        target = target if target.is_absolute() else root / target
        why_not = _outside(target, root)
        if why_not is not None:
            no(where, why_not)
        for name in exports:
            if CALLER_EXPORT.fullmatch(name) is None:
                no(
                    where,
                    f"exports {name!r}; a caller's gate exports RUN_ names only",
                )
            if name in DOOR_NAMES:
                no(where, f"exports {name!r}, a name the door sets for its own gates")
            if name in declared:
                no(where, f"exports {name!r}, which {declared[name]} exports too")
            declared[name] = where
        held[phase].append(
            Entry(
                str(target),
                why,
                status=1 if phase == "always" else 2,
                exports=tuple(exports),
                root=str(root),
                timeout_s=float(bound),
            )
        )
    return GateList(
        source=source,
        root=root,
        before=tuple(held["before"]),
        after=tuple(held["after"]),
        always=tuple(held["always"]),
    )


def _outside(target: Path, root: Path) -> str | None:
    """Why ``target`` cannot run as a gate of ``root``, or None when it can."""
    try:
        script = target.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return f"names {target}, which is not there"
    if not script.is_relative_to(root):
        return (
            f"resolves to {script}, outside the list's root {root}; a gate runs "
            "from inside its root or not at all"
        )
    try:
        runnable = script.is_file() and os.access(script, os.X_OK)
    except (OSError, ValueError):
        runnable = False
    if not runnable:
        return f"is not an executable file ({script})"
    return None


def _following(
    entry: Entry, anchors: dict[str, str], gates: GateList | None
) -> tuple[Entry, ...]:
    """The caller's gates that run right after the door's ``entry``."""
    if gates is None:
        return ()
    return tuple(
        gate
        for phase, anchor in anchors.items()
        if anchor == entry.script
        for gate in getattr(gates, phase)
    )


#: `KEY=VALUE`, where VALUE runs to end of line. Anything else on the export
#: descriptor is a
#: gate trying to say something the door has no vocabulary for.
EXPORT_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _refuse(status: int, rule: str) -> NoReturn:
    raise RefusedError(status, rule)


def pin_config(env: dict[str, str]) -> None:
    """Make ``$MCGYVR_CONFIG`` in ``env`` the path the operator meant.

    The gates run with the run root as their working directory, so a
    relative value — ``MCGYVR_CONFIG=dev.yaml`` typed in ``~/work`` — would
    have been read against the run root by gate 1 and against ``~/work`` by
    ``mcgyvr`` itself: refused if absent, silently another file if present.
    Resolved here, once, against the directory the door was invoked from, so
    the config a run is made under is the one the shell that typed it would
    load. Whether the file exists is gate 1's question, with its own rule;
    a value that cannot even be read as a path is refused here.
    """
    named = env.get(CONFIG_PATH_ENV)
    if not named:
        return
    try:
        path = Path(named).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    except (OSError, RuntimeError) as escape:
        _refuse(
            2,
            f"{CONFIG_PATH_ENV}={named!r} cannot be read as a path "
            f"({escape!r}); name the config file by an absolute path",
        )
    env[CONFIG_PATH_ENV] = str(path)


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
    # Absolute, or refused: a relative value lands somewhere different from
    # every directory the door is invoked in, which is the one thing a root
    # is for not doing. `~` is not absolute either, and a `~user` the shell
    # did not expand is a value nobody checked.
    try:
        path = Path(named).expanduser()
        usable = bool(named) and path.is_absolute() and path.is_dir()
    except (OSError, RuntimeError):
        # An unreadable parent, a `~nobody` — a root the door cannot judge
        # is a root it does not use, and says so rather than tracing back.
        usable = False
    if not usable:
        _refuse(
            2,
            f"{ROOT_ENV}={named!r} is not an existing directory named by an "
            "absolute path. The run root is where the envelope is made "
            "(records/evidence/) and where the round, hosts.json and the "
            "campaigns are read from; the door never creates it, because a "
            "root made silently is a run filed where nobody looks. Name a "
            "directory that exists, or unset the variable to use the tree "
            f"the door runs from ({ROOT})",
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
        for e in (*SEQUENCE, *ALWAYS, *READ_SEQUENCE, LEASE_RELEASE)
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
        for e in (*SEQUENCE, *ALWAYS, *READ_SEQUENCE, LEASE_RELEASE)
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
    # A caller's gate runs from its own root and sees it as RUN_ROOT; what it
    # exports still lands in the door's ``env``. Its path is held to its root
    # again here: the list was checked when it was read, and a gate that ran
    # since could have swapped this one's file for a link out of the root.
    if entry.root:
        why_not = _outside(Path(entry.script), Path(entry.root))
        if why_not is not None:
            _refuse(2, _printable(f"{entry.script} {why_not}, since the list was read"))
        script = Path(entry.script).resolve(strict=True)
        child = dict(env, RUN_ROOT=entry.root)
    else:
        script = GATE_SCRIPTS / entry.script
        child = env
    read_fd, write_fd = os.pipe()
    try:
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script), *(args or [])],
                cwd=child.get("RUN_ROOT") or ROOT,
                env=dict(child, RUN_EXPORT_FD=str(write_fd)),
                pass_fds=(write_fd,),
                start_new_session=bool(entry.root),
            )
        except (OSError, ValueError) as escape:
            _refuse(2, _printable(f"{entry.script} could not be started: {escape}"))
        os.close(write_fd)
        write_fd = -1
        if entry.root:
            fd, read_fd = read_fd, -1
            reported, status = _collect_bounded(entry, proc, fd)
        else:
            with os.fdopen(read_fd, "r", encoding="utf-8", errors="replace") as pipe:
                read_fd = -1
                try:
                    reported = pipe.read()
                    status = proc.wait()
                except KeyboardInterrupt:
                    # The entry is ended BEFORE the door moves on: gate 7
                    # re-reads the rig and looks for containers, and a step
                    # still running under it would make both readings lies. A
                    # terminal's Ctrl-C already reached the child; a bare
                    # `kill` of the door did not.
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
        if "\x00" in value:
            _refuse(
                2,
                f"{entry.script} exported {key} with a NUL byte in its value; no "
                "process can start with it in its environment",
            )
        if key not in entry.exports:
            _refuse(
                2,
                f"{entry.script} exported {key}, which it does not declare in "
                f"{'its gate list' if entry.root else 'SEQUENCE'}. The door knows "
                "the whole vocabulary before anything runs, so a gate cannot "
                "introduce a variable a later gate reads",
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
    # Required: a floor is only correct for the cache the unit will actually
    # allocate, so the run declares the window and a run that did not is
    # refused here rather than sized silently.
    parser.add_argument(
        "--ctx-per-slot",
        type=int,
        required=True,
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


def _end_group(proc: subprocess.Popen[bytes]) -> None:
    """End a caller's gate and every process in its group, and wait for it."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)
    # Whatever is left in the group, the gate included, is killed.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _collect_bounded(
    entry: Entry, proc: subprocess.Popen[bytes], fd: int
) -> tuple[str, int]:
    """What a caller's gate exported and its status, within its time bound.

    The export pipe is read until every writer has closed it and the gate has
    exited, or until the bound: a gate that runs long, or that exits and
    leaves a process holding the descriptor, is ended with its whole group
    and refused. A KeyboardInterrupt ends it the same way before it goes on.
    """
    deadline = time.monotonic() + entry.timeout_s
    chunks: list[bytes] = []

    def over() -> NoReturn:
        _end_group(proc)
        _refuse(
            2,
            _printable(
                f"{entry.script} ran past its bound of {entry.timeout_s:g} s and "
                "was ended with every process it started"
            ),
        )

    try:
        try:
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    over()
                ready, _, _ = select.select([fd], [], [], left)
                if ready:
                    data = os.read(fd, 65536)
                    if not data:
                        break
                    chunks.append(data)
            try:
                status = proc.wait(timeout=max(deadline - time.monotonic(), 0.0))
            except subprocess.TimeoutExpired:
                over()
        except KeyboardInterrupt:
            _end_group(proc)
            raise
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8", errors="replace"), status


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
    parser.add_argument(
        "--gates",
        default=None,
        metavar="FILE",
        help=(
            "a caller's gate list (JSON: root, gates of path, why, phase, "
            "exports, timeout_s), each gate run by the door's Python from the "
            "root, for at most its timeout_s (default "
            f"{CALLER_GATE_TIMEOUT_S:g} s). `before` gates run after the "
            "profile and before anything is sent to the machine; `after` gates "
            "after the identity and daemon gates and before the envelope and "
            "the step; `always` gates after gates 7 and 8 and before the lease "
            "is released, and only when the run got as far as gate 5. A "
            "`before` or `after` gate that refuses, runs past its bound or dies "
            "ends the run as a door gate's refusal does: the door's gates after "
            "it do not run, and the lease is still released. An `always` gate "
            "that refuses does not stop the next. A caller's gate never runs in "
            "place of a door gate or moves one"
        ),
    )
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
    try:
        gates = load_gate_list(opts.gates) if opts.gates is not None else None
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status

    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
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
                for gate in _following(entry, SERVE_PHASES, gates):
                    status = _run_entry(gate, env)
                    if status != 0:
                        return _stop_caller(gate, status)
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

        after = _always(env, gates.always if gates else ())
        if interrupted:
            return 130
        return step_status or after
    finally:
        # Gate 5's claim is released here and not only in `_always`, which
        # a refusal between the claim and the always-block returns straight
        # past. Releasing twice is releasing once: `gatelib.release`
        # unlinks `missing_ok`.
        _release_claim(env)
        _release_lease(env, gates.exports if gates else frozenset())


def _read_parse(argv: list[str]) -> argparse.Namespace:
    """The read run's arguments. As with :func:`_parse`, nothing skips a gate."""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run read",
        description=(
            "read a rig: its facts, its containers and its card, filed under "
            "the journal of the fleet read (the live one, or --fleet's); --probe "
            "and --load run the lock's harness on it"
        ),
    )
    parser.add_argument(
        "--host", required=True, help="srv1 | srv2, as declared in hosts.json"
    )
    parser.add_argument(
        "--probe",
        nargs="+",
        default=[],
        metavar="UNIT",
        help=(
            "awake units of the fleet read on this rig to measure on the rig with "
            "the lock's own harness, each only while it has nothing in flight"
        ),
    )
    parser.add_argument(
        "--load",
        default="",
        metavar="WxN",
        help=(
            "with --probe: W concurrent requests on the rig, each filling the "
            "unit's N-token window, while its container's card peak is sampled "
            "and judged against its room_mib"
        ),
    )
    parser.add_argument(
        "--fleet",
        default="",
        metavar="FLEET",
        help=(
            "read FLEET of the fleet.yaml in the folder of the config the read "
            "loads (MCGYVR_CONFIG, else the run root when it holds a fleet.yaml, "
            "else the live fleet folder) instead of the live fleet: no lock, rows "
            "filed locked=false, probe figures unjudged, card and load peak "
            "judged against room_mib"
        ),
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="the id the read's rows are filed under (default: minted)",
    )
    parser.add_argument(
        "--gates",
        default=None,
        metavar="FILE",
        help=(
            "a caller's gate list (JSON: root, gates of path, why, phase, "
            "exports, timeout_s), each gate run by the door's Python from the "
            "root, for at most its timeout_s (default "
            f"{CALLER_GATE_TIMEOUT_S:g} s). `before` gates run after the "
            "profile and before anything is sent to the machine. `after` gates "
            "run after the machine is read and what was read is filed, so they "
            "cannot stop that filing, and only when the reading gate exited 0: "
            "it exits non-zero when it refused, and also after filing when a "
            "probe or a load on the rig failed. A read has no `always` phase, "
            "and a list that asks for one is refused"
        ),
    )
    return parser.parse_args(argv)


def _read(argv: list[str]) -> int:
    """`read`: the third fixed sequence, to completion. Nothing is leased."""
    opts = _read_parse(argv)
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    run_id = opts.run_id or mint_read_id()
    if READ_ID.match(run_id) is None:
        print(
            f"run.py: REFUSED — --run-id {run_id!r} is not "
            "run-YYYYMMDDTHHMMSS-xxxxxxxx",
            file=sys.stderr,
        )
        return 2
    if opts.load and not opts.probe:
        print(
            "run.py: REFUSED — --load needs --probe: a load runs on the units a "
            "probe names, and only while each is idle",
            file=sys.stderr,
        )
        return 2
    if opts.load and LOAD_SPEC.match(opts.load) is None:
        print(
            f"run.py: REFUSED — --load {opts.load!r} is not WxN: W concurrent "
            "requests, each filling an N-token window (e.g. 8x4096)",
            file=sys.stderr,
        )
        return 2
    try:
        root = run_root()
        # A read has no teardown and no lease, so no `always` phase to run in.
        gates = (
            load_gate_list(opts.gates, tuple(READ_PHASES))
            if opts.gates is not None
            else None
        )
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env.update(
        RUN_ROOT=str(root),
        RUN_BIN=str(BIN),
        RUN_HOST=opts.host,
        RUN_READ_ID=run_id,
        RUN_READ_PROBE=" ".join(opts.probe),
        RUN_READ_LOAD=opts.load,
        RUN_READ_FLEET=opts.fleet,
    )
    try:
        check_manifest()
        for entry in READ_SEQUENCE:
            status = _run_entry(entry, env)
            if status == 2:
                return _stop(entry, status, env)
            if status != 0:
                return status
            for gate in _following(entry, READ_PHASES, gates):
                status = _run_entry(gate, env)
                if status != 0:
                    return _stop_caller(gate, status)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    except KeyboardInterrupt:
        return 130
    return 0


def main(argv: list[str] | None = None) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    if given[:1] == ["serve"]:
        return _serve(given[1:])
    if given[:1] == ["read"]:
        return _read(given[1:])
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
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
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
        # The date the envelope above was named and checked by, read off the
        # clock once: gate 5 files under it, and a gate reading the clock
        # again past midnight UTC would mint the next day's envelope.
        RUN_DATE=run_date,
    )

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
        _release_lease(env)


#: What the ALWAYS phase will not be stopped by.
UNSTOPPABLE = (signal.SIGINT, signal.SIGTERM)


def _always(env: dict[str, str], callers: tuple[Entry, ...] = ()) -> int:
    """Gates 7 and 8, then ``callers``, to completion, whatever signal arrives.

    A signal handled here would end the entry that was running — gate 7
    mid-read of the rig, gate 8 mid-parse — and the run's end state would be
    exactly as unknown as if neither had run. So both signals are ignored
    for the whole phase and restored after it; a run interrupted before this
    phase still exits 130 (the caller keeps that), and one interrupted
    during it exits with what 7 and 8 decided. ``callers`` are a caller's
    ``always`` gates, run after 7 and 8: a refusal in one does not stop the
    next, but a signal to the door ends the one that is running (it is the
    caller's code, with a time bound of its own, and the lease waits on it),
    and counts as its refusal. The claim gate 5 took on the RUN_ID is released
    last, on every path out of here.
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
        for entry in callers:
            for sig in UNSTOPPABLE:
                signal.signal(sig, _sigterm)
            try:
                status = _run_entry(entry, env)
                if status != 0:
                    print(
                        f"run.py: {entry.script} ({_ended(status)}) — {entry.why}",
                        file=sys.stderr,
                    )
                    after = entry.status
            except RefusedError as refusal:
                print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
                after = refusal.status
            except KeyboardInterrupt:
                print(
                    f"run.py: {entry.script} was ended by a signal to the door — "
                    f"{entry.why}",
                    file=sys.stderr,
                )
                after = entry.status
            finally:
                for sig in UNSTOPPABLE:
                    signal.signal(sig, signal.SIG_IGN)
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


def _release_lease(env: dict[str, str], callers: frozenset[str] = frozenset()) -> None:
    """Release the rig's lease, if gate 2 took one for this run.

    Through a script and not in-process: the door itself is not *under* the
    door — the shims prove an ancestor — so its own ssh would be refused,
    and rightly. Signals are ignored for the duration, as for gates 7 and
    8: a Ctrl-C that landed on the release would leave a lease a rig cannot
    tell from a live one. Released once: the variable is dropped after. The
    release starts with the door's names only: ``callers``, the names a
    caller's gates may have exported, are left out of its environment.
    """
    if not env.get(gatelib.LEASE_VAR):
        return
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in UNSTOPPABLE}
    try:
        _run_entry(LEASE_RELEASE, {k: v for k, v in env.items() if k not in callers})
    except RefusedError as refusal:
        print(f"run.py: {refusal.rule}", file=sys.stderr)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        env.pop(gatelib.LEASE_VAR, None)


def _ended(status: int) -> str:
    """How a process ended, from its status."""
    return f"killed by signal {-status}" if status < 0 else f"exit {status}"


def _stop_caller(entry: Entry, status: int) -> int:
    """A caller's gate refused: say which, how it ended and why, and stop.

    The door stops with its own refusal status, 2, whatever the gate's was:
    a gate's 130 or a signal that killed it is that gate's refusal, never the
    door's own interrupt (130).
    """
    print(
        f"run.py: REFUSED at {entry.script} ({_ended(status)}) — {entry.why}",
        file=sys.stderr,
    )
    return 2


def _stop(entry: Entry, status: int, env: dict[str, str]) -> int:
    """A gate before the step refused: say which rule, and stop."""
    print(f"run.py: REFUSED at {entry.script} — {entry.why}", file=sys.stderr)
    return status or entry.status


def _sigterm(_signum: int, _frame: types.FrameType | None) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    # Both signals end the entry that was running; gates 7 and 8 run after,
    # whatever arrives. Set explicitly rather than left to the default, so a
    # parent that ignored SIGINT cannot make the door ignore Ctrl-C too.
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)
    sys.exit(main())
