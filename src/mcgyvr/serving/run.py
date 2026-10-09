#!/usr/bin/env python3
"""The one access point to the rigs.

    python -m mcgyvr.serving.run serve|read|link ...
    python -m mcgyvr.serving.run step --host <rig> --campaign <name>
                                 --step <path> [--out-root DIR] [--gates FILE]
                                 [-- STEP ARGS...]

Nothing else opens an ssh to a rig or starts a container on one. A caller
that wants rig time writes its own script and names it as ``--step``; the door
runs the gates around it. The step is the one part of a run a caller
supplies; ``serve``, ``read``, ``link`` and ``step`` take a caller's own
gates too (A CALLER'S GATES, below), which run inside the door's fixed order
and never in place of any of it.

THE STEP RUN (``step``, an advanced command) is the run: the door's profile
gate, the rig's lease and reading, its daemon, the envelope, then the
caller's own ``--step``, then gates 7 and 8 whatever the step did, and the
lease released last (:data:`STEP_SEQUENCE`). Its envelope is the user's door
log, or ``--out-root DIR`` as ``DIR/<date>-<campaign>/``
(:func:`gatelib.envelope_of`).

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
``/usr/bin/ssh <other-rig>`` by absolute path or ``env -i ssh <other-rig>``
on a cleared PATH reaches a second host, and that is the same limit — the
seal is against
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

THE RUN ROOT. The run root is ``$MCGYVR_RUN_ROOT`` when it is set and the
checkout otherwise (:func:`run_root`): the door's own gates run from it and
see it as ``RUN_ROOT``, so a gate that reads a file of the run reads it from
one named place. The code and the root are two places on purpose — an
installed wheel has no checkout — and the door exports both, ``RUN_ROOT`` and
``RUN_BIN`` (its shim directory), so a step derives neither from the other. A
value naming a directory that does not exist is refused, never created.

GATE ORDER IS THE POINT, NOT AN IMPLEMENTATION DETAIL. Gates 1-4 write nothing
under the run root: gate 1 reaches no rig, gate 2 takes the rig's lease (a live
run tears down what it displaced) and reads the rig, gates 3-4 only read, and
none launches anything, so a tree on the wrong round or a machine that is not
what it claims leaves no artifact to clean up. Gate 5 stamps the lease and
makes the envelope. The data scripts run after the rig is known to be the
declared one and before the step, because a placement derived against the
wrong machine is worse than no placement. Gates 7-8 run after the step
whatever it did.

A CALLER'S GATES. ``serve``, ``read``, ``link`` and ``step`` take ``--gates
FILE``: a JSON object
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
its list's root, which it sees as ``RUN_ROOT``, in a session and a process
group of its own. At its ``timeout_s`` (:data:`CALLER_GATE_TIMEOUT_S` when the
list gives none, at most :data:`CALLER_GATE_MOST_S`) the door sends TERM to
that group, KILL when the group is still there :data:`GROUP_GRACE_S` later,
and then waits up to :data:`GROUP_GONE_S` for it to be empty
(:func:`_end_group`). In a session of its own, the gate is outside every
signal sent to the door's process group: the door ends it on INT or TERM,
except a gate the signal reaches while the door is starting it, which can be
left running past the lease release (see :func:`_run_entry`); a door that is
killed or hung up leaves it running with no bound. It may
export only the ``RUN_`` names its list declares, none of them a name the
door sets (:data:`DOOR_NAMES`), in at most :data:`MAX_EXPORT_BYTES`.
``step`` places its phases as ``serve`` does. ``link`` takes ``before``
alone: it runs before the timer reaches the rig, and nothing may follow the
timer's reading, which is the last line its caller reads.

THE GATES A CALLER ADDS FROM THE ENVIRONMENT. ``$MCGYVR_DOOR_GATES``
(:data:`GATES_ENV`) names a folder of gate lists, one per verb
(``<verb>.json``). A ``serve``, ``read``, ``link`` or ``step`` run loads its
verb's list from there, so a door that mcgyvr's own code opens (the waker, the
ladder manager, the fleet's read and probe) carries the caller's gates too,
with no product code naming them. Given ``--gates`` as well, the run holds
both lists: in each phase the folder's gates run first, then the option's,
and the door says on stderr that the variable is also set (owner, on
mcgyvr#633). A folder with no list
for a verb adds none to it; a value that is not an existing folder named by an
absolute path is refused before any gate. Its gates are a caller's gates like
any other: they can add a refusal, and never skip, move or stand in for a
door gate.

ONE MODE, THE USER'S. The round, ``hosts.json`` and the declared docker
version are not asked for: the rig is held to the user's own rig file
(``<rig-file folder>/<rig>.json``, :mod:`mcgyvr.serving.rigfile`, written by
``mcgyvr scan --rig``). Each run reads the rig again, says what moved, and
refuses only when the fleet no longer fits. Every gate is the same on every
run: the profile and the live fleet's lock, the lease, the daemon that
answers and is the machine that was read, the envelope, the step, and the
stray-container check. A serve run is filed under the data folder's
``door/<date>/<run_id>/`` (command, rig reading before and after, compose
text, units up, step exit), and a container or a card holder mcgyvr did not
start is reported and left as it is.

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
import codecs
import contextlib
import ipaddress
import json
import math
import os
import re
import secrets
import select
import shlex
import signal
import subprocess
import sys
import time
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from mcgyvr.config import CONFIG_PATH_ENV
from mcgyvr.fleet.roots import RIGS_SHOWN
from mcgyvr.serving import gatelib
from mcgyvr.serving.gatelib import DOOR_MODULE

#: The package directory. ``gate-scripts`` carries a hyphen so it can never be
#: imported: these are executables the door SPAWNS, and a caller that could
#: `from mcgyvr.serving.gate_scripts import ...` could also replace one.
HERE = Path(__file__).resolve().parent
GATE_SCRIPTS = HERE / "gate-scripts"
#: What `ssh` and `docker` resolve to for everything the door starts.
BIN = GATE_SCRIPTS / "bin"
SHIMS = ("docker", "ssh")
#: The shell files beside the gates that a gate READS rather than spawns.
#: `rig-snapshot.sh` is the reader gate 2 sends to the rig and gate 7 compares
#: against. It is not an entry in SEQUENCE, so it was not on the manifest —
#: and a check that covers only the entries someone remembered is the absence
#: the manifest exists to turn into a refusal: delete `rig-snapshot.sh` and
#: gate 2 died on a FileNotFoundError traceback, which is a gate that stopped
#: running without anyone deciding it should.
#: `rig-units.sh` is the second half of the one reader the read run ships to a
#: rig, behind `rig-snapshot.sh` (gate-scripts/read-02-rig.py).
#: `linktime.py` is the one timer the link run ships to a rig
#: (gate-scripts/link-01-time.py), and `fetcher.py` the one downloader a
#: `serve fetch` ships (gate-scripts/serve-fetch.py).
READERS = (
    GATE_SCRIPTS / "rig-snapshot.sh",
    GATE_SCRIPTS / "rig-units.sh",
    HERE / "linktime.py",
    HERE / "fetcher.py",
)
#: The door's own serve steps, one per direction. Shipped beside the gates
#: because, like the default step, they belong to no campaign: a live ladder
#: is not an experiment, and the envelope it files under is the host's.
#: ``sleep`` and ``wake`` are vLLM's level-2 sleep and its wake: the containers
#: stay up through both, and only the card's memory is given back and taken.
#: ``up`` and ``down`` with ``--unit`` start or stop those containers of the
#: compose file alone (the swap's start and stop for a unit that cannot
#: sleep). ``fetch`` downloads weights on the rig, held to their sha256
#: (:mod:`mcgyvr.serving.fetchlist`), and starts nothing.
SERVE_STEPS = {
    "up": GATE_SCRIPTS / "serve-up.py",
    "down": GATE_SCRIPTS / "serve-down.py",
    "sleep": GATE_SCRIPTS / "serve-sleep.py",
    "wake": GATE_SCRIPTS / "serve-wake.py",
    "fetch": GATE_SCRIPTS / "serve-fetch.py",
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
#: Names the run root: the folder the door's gates run from, separate from the
#: code because the code need not be a checkout: from an installed wheel
#: :data:`ROOT` is ``site-packages/``. See :func:`run_root`.
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
        "gate 1: the run knows which profile it is under, and a live `serve "
        "up` starts only units of the stamped fleet; a user's run pins no "
        "round",
        exports=(
            "RUN_ROUND",
            "RUN_PRODUCT_SHA256",
            "RUN_PROFILE",
            "RUN_CONFIG",
        ),
    ),
    Entry(
        "02-rig.py",
        "gate 2: the rig is leased to this run and read again, and held to "
        f"your rig file ({RIGS_SHOWN}/<rig>.json, written by "
        "`mcgyvr scan --rig`): what moved is said, and the run is refused only "
        "when the fleet no longer fits",
        exports=("RUN_LEASE", "RUN_DISPLACED", "RUN_PRE_RIG"),
    ),
    Entry(
        "03-image.py",
        "gate 3: the daemon `docker` reaches answers now and is the machine "
        "gate 2 read",
    ),
    Entry(
        "05-envelope.py",
        "gate 5: the run's folder in the door's log is made, the step's "
        "declared artifacts are write-once, and RUN_ID is minted",
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
#: --compose FILE`). The same fixed sequence as a step run: profile, rig,
#: daemon, envelope, then the serve step, then gates 7 and 8. A live ladder
#: is started and LEFT RUNNING, which gate 7 reads in its own serve
#: vocabulary; `serve fetch --weights FILE` runs the same sequence: it leases
#: the rig it downloads onto, and gate 7 names any container that is up after
#: it and was not before.
SERVE_SEQUENCE: tuple[Entry, ...] = tuple(
    entry
    for entry in SEQUENCE
    if entry.script
    in ("01-round.py", "02-rig.py", "03-image.py", "05-envelope.py", "06-step.py")
)

#: THE STEP RUN (`python -m mcgyvr.serving.run step --host H --campaign C
#: --step PATH`). The same entries as the serve run, and :data:`ALWAYS` after
#: whatever the step did; order and membership are enforced exactly as for
#: SEQUENCE.
STEP_SEQUENCE: tuple[Entry, ...] = SERVE_SEQUENCE

#: THE READ RUN (`python -m mcgyvr.serving.run read --host H [--probe UNIT...
#: [--load WxN]]`). A third fixed sequence: the profile is settled and no round
#: is opened, then one reader goes to the rig, is compared with the rig's
#: file, and is filed. A plain read starts nothing on the rig; `--probe`
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
        "read, rig: one reader on the rig, its facts held to the user's rig "
        "file and the rest filed under the read fleet's journal; nothing "
        "leased, nothing torn down, and a busy rig read as it is",
    ),
)
#: THE LINK RUN (`python -m mcgyvr.serving.run link --host H (--peer A B |
#: --sink ADDR PORT | --send ADDR PORT)`). A fourth fixed sequence, and the
#: smallest: one bounded timer goes to the rig on stdin and its one line of
#: JSON comes back on stdout. `mcgyvr fleet probe` asks for it to time a link a
#: split unit crosses: two cards of one rig (`--peer`), or the network between
#: two rigs (a `--sink` on the worker, a `--send` from the head). No lease, no
#: envelope, nothing filed by the door and nothing left on the rig.
LINK_SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "link-01-time.py",
        "link, time: one bounded timer on the rig, its source on stdin and its "
        "reading on stdout; nothing leased, nothing filed, nothing left behind",
    ),
)
#: The timer's three modes and the arguments each takes.
LINK_MODES = {
    "--peer": ("GPU_A", "GPU_B"),
    "--sink": ("ADDR", "PORT"),
    "--send": ("ADDR", "PORT"),
}
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
    # variables because they are two places: the root is where the door's
    # gates run, the shims are part of the code, and a step that derived one
    # from the other found no shims under a run root that was not a checkout.
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
    # `serve up|down|sleep|wake --unit`: the containers the step acts on,
    # empty for all.
    "RUN_SERVE_ONLY",
    # The containers of the file that start asleep (a compose profile): a
    # whole `serve up` leaves them down and gate 7 does not expect them.
    "RUN_SERVE_ASLEEP",
    # `serve fetch`: the fetch list the door read and held to a hash, and the
    # NAME of the variable a Hugging Face token is read from (never its value).
    "RUN_FETCH",
    "RUN_FETCH_TOKEN_ENV",
    # The read run's own four: the id its rows are filed under, the units it
    # runs the lock's harness for on the rig, the load it runs on them, and
    # the setup fleet it reads in place of the live one (`--fleet`).
    "RUN_READ_ID",
    "RUN_READ_PROBE",
    "RUN_READ_LOAD",
    "RUN_READ_FLEET",
    # The link run's one: the timer's mode and its arguments, as one line.
    "RUN_LINK",
    # The step run's one: the folder its envelope is made under, when it
    # names one (`--out-root`).
    gatelib.OUT_ROOT_VAR,
    # The command line it was opened with, and, once a serve run's step has
    # ended, how it ended: what the run files in its log.
    "RUN_COMMAND",
    "RUN_STEP_EXIT",
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
#: A step run places its caller's gates as a serve run does: ``after`` once
#: the rig is leased and read and its daemon answers, before the envelope.
STEP_PHASES = SERVE_PHASES
READ_PHASES = {"before": "read-01-profile.py", "after": "read-02-rig.py"}
#: A link run's one phase: ``before``, which runs before the timer reaches the
#: rig. Nothing runs after the timer: its reading is the last line of the
#: run's stdout, and that line is what its caller reads.
LINK_PHASES = ("before",)
#: Names a folder of a caller's gate lists, one per verb (``<verb>.json``),
#: run before a ``--gates`` list's in each phase (:func:`callers_gates`).
GATES_ENV = "MCGYVR_DOOR_GATES"
#: What ``--campaign`` names on a step run: one folder name, which the
#: envelope and the RUN_ID are made of.
CAMPAIGN_NAME = re.compile(r"[A-Za-z0-9_.-]+")
#: The keys of a gate list, and of one gate in it. Anything else is refused.
GATE_LIST_KEYS = frozenset({"root", "gates"})
GATE_KEYS = frozenset({"path", "why", "phase", "exports", "timeout_s"})
#: How long a caller's gate may run when its list gives no ``timeout_s``.
CALLER_GATE_TIMEOUT_S = 600.0
#: The longest bound a list may give a gate: a day. A longer one is refused
#: when the list is read, before any gate runs.
CALLER_GATE_MOST_S = 86400.0
#: The most gates a list may hold. Far above any list a caller writes by
#: hand. The list is read whole (at most :data:`MAX_LIST_BYTES`) and parsed
#: before its gates are counted.
MAX_GATES = 256
#: The most bytes of a gate list the door reads: far above a list of
#: :data:`MAX_GATES` gates written by hand. A larger file is refused before it
#: is parsed.
MAX_LIST_BYTES = 1024 * 1024
#: How long the door waits, after TERM to a caller's gate's process group,
#: for the group to be empty before it sends KILL (see :func:`_end_group`).
GROUP_GRACE_S = 5.0
#: How long the door waits, after KILL, for that group to be empty.
GROUP_GONE_S = 5.0
#: The most a caller's gate may write on its export descriptor. A gate that
#: writes more is ended with its process group and refused by name. It is
#: well under the 128 KiB Linux lets one environment string hold (with 4 KiB
#: pages), so one value that passes can still start a process. What all gates
#: export together must fit in the environment a process starts with too;
#: when it does not, the next gate cannot start, and the door refuses naming
#: that gate.
MAX_EXPORT_BYTES = 64 * 1024
#: The package's own folder, where the door's own scripts are. A list whose
#: root is or lies inside it is refused, and so is a gate that resolves
#: inside it: either could run the door's scripts out of the door's order. A
#: root may hold it (a project with the package in its virtual environment).
#: Paths are compared by their spelling, after links are resolved: on a file
#: system that ignores case, a path spelled in another case is not caught. A
#: copy or a hard link of a door script outside the package is not caught.
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
    """``text`` as a terminal can print it.

    A refusal quotes the caller's list, and a list may carry a NUL, a
    terminal escape or a lone surrogate; each character that is not
    printable is written as its escape (``\\x1b``), never raw.
    """
    return "".join(
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in text
    )


def _brief(value: object, most: int = 80) -> str:
    """``value`` quoted, cut to its first ``most`` characters when it is longer."""
    if isinstance(value, str):
        return _start_of(value, most)
    quoted = repr(value)
    if len(quoted) <= most + 2:
        return quoted
    return f"{quoted[:most]}... ({len(quoted)} characters)"


def load_gate_list(named: str, phases: tuple[str, ...] = PHASES) -> GateList:
    """Read the gate list ``named``, or refuse it naming the file and the entry.

    A gate list is input the door does not trust. Refused here, before any
    gate runs: an empty name; a name relative to a working folder the door
    cannot name; a file that is not a regular file of at most
    :data:`MAX_LIST_BYTES` of UTF-8 JSON, with no byte order mark (too deep, a
    number JSON will not read and a key given twice included) holding an
    object of ``root`` and ``gates``; a key the door does not know; a root
    that is not an existing folder named by an absolute path, or that is or
    lies inside :data:`PACKAGE`; more than :data:`MAX_GATES` gates; a gate
    whose path cannot be a path, is missing, is not an executable file, or
    resolves (through ``..`` or a link) outside the root or inside
    :data:`PACKAGE`; a phase not in ``phases``; a ``timeout_s`` that is not a
    positive number of seconds up to :data:`CALLER_GATE_MOST_S`; an export that
    is not a ``RUN_`` name, is one of :data:`DOOR_NAMES`, or is declared by two
    gates. A refusal quotes a field of the list by its first characters only
    (:func:`_brief`).
    """
    if not named:
        _refuse(
            2,
            "--gates names no file. A launcher that meant to pass a list and "
            "passed an empty name would otherwise run without its gates",
        )
    source = Path(named)
    if not source.is_absolute():
        try:
            source = Path.cwd() / source
        except OSError as escape:
            which = (
                "is gone"
                if isinstance(escape, FileNotFoundError)
                else "the door cannot name"
            )
            _refuse(
                2,
                _printable(
                    f"--gates {named}: the list is named relative to the working "
                    f"folder, which {which} ({escape.strerror or repr(escape)}); "
                    "name it by an absolute path"
                ),
            )

    def no(where: str, why: str) -> NoReturn:
        _refuse(2, _printable(f"--gates {source}: {where} {why}"))

    try:
        regular = source.is_file()
    except (OSError, ValueError) as escape:
        no("the list", f"cannot be read ({escape})")
    if not regular:
        no("the list", "cannot be read: it is not a regular file")
    try:
        with source.open("rb") as handle:
            raw = handle.read(MAX_LIST_BYTES + 1)
    except OSError as escape:
        no("the list", f"cannot be read ({escape.strerror or repr(escape)})")
    if len(raw) > MAX_LIST_BYTES:
        no(
            "the list",
            f"is larger than {MAX_LIST_BYTES} bytes, the most the door reads",
        )
    if raw.startswith(codecs.BOM_UTF8):
        no("the list", "starts with a byte order mark; the door reads UTF-8 with none")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as bad:
        no("the list", f"is not UTF-8 (at byte {bad.start + 1})")
    try:
        doc = json.loads(text, object_pairs_hook=_once)
    except _TwiceError as twice:
        no(f"key {_brief(twice.key)}", "is given twice; a list states each key once")
    except json.JSONDecodeError as escape:
        no(
            "the list",
            f"is not JSON the door reads ({escape.msg.removesuffix(' at')}, "
            f"at line {escape.lineno}, column {escape.colno})",
        )
    except RecursionError:
        no("the list", "is not JSON the door reads (it nests deeper than it reads)")
    except ValueError as escape:
        no(
            "the list",
            "holds a number with more digits than the door reads"
            if "digits" in str(escape)
            else f"is not JSON the door reads ({type(escape).__name__})",
        )
    if not isinstance(doc, dict):
        no("the list", "is not a JSON object of `root` and `gates`")
    for key in sorted(set(doc) - GATE_LIST_KEYS):
        no(
            f"key {_brief(key)}",
            "is not a gate list key; a list holds `root` and `gates`",
        )
    raw_root = doc.get("root")
    root = Path(raw_root) if isinstance(raw_root, str) and raw_root else None
    try:
        usable = root is not None and root.is_absolute() and root.is_dir()
    except PermissionError as escape:
        no("root", f"{_brief(raw_root)} cannot be reached ({escape.strerror})")
    except (OSError, ValueError):
        usable = False
    if root is None or not usable:
        no(
            "root",
            f"{_brief(raw_root)} is not an existing folder named by an absolute path; "
            "a caller's gates run there and read it as RUN_ROOT",
        )
    root = root.resolve()
    if root.is_relative_to(PACKAGE.resolve()):
        no(
            "root",
            f"{root} is or lies inside the package's own folder "
            f"{PACKAGE.resolve()}; a list could then run the door's own scripts "
            "out of the door's order",
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
            where = f"{where} ({_brief(path)})"
        for key in sorted(set(gate) - GATE_KEYS):
            no(where, f"carries {_brief(key)}, which is not a gate key")
        if not isinstance(path, str) or not path:
            no(where, "names no path")
        why = gate.get("why")
        if not isinstance(why, str) or not why.strip():
            no(where, "says no `why`; a gate that refuses must say what it holds")
        phase = gate.get("phase")
        if phase not in phases:
            no(
                where,
                f"asks for phase {_brief(phase)}; this run has "
                f"{', '.join(phases)} and no other"
                + (
                    " (a read and a link have no teardown and no lease for an "
                    "`always` gate to follow)"
                    if phase == "always"
                    else ""
                )
                + (
                    " (nothing runs after a link's timer: its reading is the "
                    "last line its caller reads)"
                    if phase == "after" and "after" not in phases
                    else ""
                ),
            )
        bound = gate.get("timeout_s", CALLER_GATE_TIMEOUT_S)
        try:
            seconds = (
                float(bound)
                if isinstance(bound, int | float) and not isinstance(bound, bool)
                else math.nan
            )
        except OverflowError:
            seconds = math.nan
        if not math.isfinite(seconds) or not 0 < seconds <= CALLER_GATE_MOST_S:
            no(
                where,
                f"gives timeout_s {_brief(bound)}; a bound is a positive number of "
                f"seconds, at most {CALLER_GATE_MOST_S:g}",
            )
        exports = gate.get("exports", [])
        if not isinstance(exports, list) or not all(
            isinstance(name, str) for name in exports
        ):
            no(where, "`exports` is not a list of names")
        target = Path(path)
        target = target if target.is_absolute() else root / target
        why_not, _ = _outside(target, root)
        if why_not is not None:
            no(where, why_not)
        for name in exports:
            if CALLER_EXPORT.fullmatch(name) is None:
                no(
                    where,
                    f"exports {_brief(name)}; a caller's gate exports RUN_ names only",
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
                timeout_s=seconds,
            )
        )
    return GateList(
        source=source,
        root=root,
        before=tuple(held["before"]),
        after=tuple(held["after"]),
        always=tuple(held["always"]),
    )


def callers_gates(
    verb: str, named: str | None, phases: tuple[str, ...] = PHASES
) -> GateList | None:
    """The caller's gates of a ``verb`` run, or None when there are none.

    The verb's list in the folder ``$MCGYVR_DOOR_GATES`` names,
    ``<folder>/<verb>.json``, when it is set and holds one (a folder with no
    list for this verb adds no gate to it), and ``--gates FILE`` (``named``)
    when it is given. With both (owner, on mcgyvr#633) both run: in each phase
    the folder's gates first, then the option's, and the door says on stderr
    that the variable is also set when its folder holds a list for this verb;
    one file named both ways is one list. A name both lists export is refused,
    as two gates of one list exporting it are. A value of the variable that is
    empty, relative or not an existing folder is refused, as is a list that
    :func:`load_gate_list` refuses; a path that cannot be looked at is refused,
    never read as no list.
    """
    from_env = _env_gates(verb, phases)
    if named is None:
        return from_env
    if from_env is not None:
        print(
            f"run.py: {GATES_ENV} is also set; its gates for `{verb}` run "
            "before the --gates list's in each phase, and both lists run",
            file=sys.stderr,
        )
    given = load_gate_list(named, phases)
    if from_env is None or from_env.source.resolve() == given.source.resolve():
        return given
    shared = sorted(from_env.exports & given.exports)
    if shared:
        _refuse(
            2,
            _printable(
                f"--gates {given.source} and {from_env.source} both export "
                f"{', '.join(shared)}; a name is exported by one gate, so no "
                "gate reads a value it cannot tell the source of"
            ),
        )
    return GateList(
        source=given.source,
        root=given.root,
        before=(*from_env.before, *given.before),
        after=(*from_env.after, *given.after),
        always=(*from_env.always, *given.always),
    )


def _env_gates(verb: str, phases: tuple[str, ...]) -> GateList | None:
    """The verb's list in the ``$MCGYVR_DOOR_GATES`` folder, or None."""
    folder = os.environ.get(GATES_ENV)
    if folder is None:
        return None
    try:
        where = Path(folder)
        usable = bool(folder) and where.is_absolute() and where.is_dir()
    except (OSError, ValueError):
        usable = False
    if not usable:
        _refuse(
            2,
            _printable(
                f"{GATES_ENV}={folder!r} is not an existing folder named by an "
                "absolute path. It names the folder of a caller's gate lists, "
                "one per verb (<verb>.json); a value that names none would run "
                "the door without the gates it was set to add. Name a folder "
                "that exists, or unset the variable"
            ),
        )
    listed = where / f"{verb}.json"
    try:
        listed.lstat()
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as escape:
        _refuse(
            2,
            _printable(
                f"{GATES_ENV}: {listed} cannot be looked at ({escape}); a list "
                "that cannot be looked at is refused, never taken for no list"
            ),
        )
    return load_gate_list(str(listed), phases)


def _outside(target: Path, root: Path) -> tuple[str | None, Path]:
    """Why ``target`` cannot run as a gate of ``root`` (None when it can), and
    the path it resolves to, which is the one to run.

    A root may hold the package's folder (a project with the package in its
    virtual environment); a gate may not resolve inside it, since the door's
    own scripts are there and a list must not run them out of order. The
    comparison is by spelling: on a file system that ignores case, a path
    spelled in another case is not caught.
    """
    try:
        script = target.resolve(strict=True)
    except FileNotFoundError:
        return "is not there", target
    except OSError as escape:
        return f"cannot be reached ({escape.strerror or escape})", target
    except (RuntimeError, ValueError) as escape:
        return f"cannot be reached ({escape})", target
    if not script.is_relative_to(root):
        return (
            f"resolves to {script}, outside the list's root {root}; a gate runs "
            "from inside its root or not at all",
            script,
        )
    if script.is_relative_to(PACKAGE.resolve()):
        return (
            f"resolves to {script}, inside the package's own folder; a gate "
            "that resolves inside the package is refused",
            script,
        )
    try:
        runnable = script.is_file() and os.access(script, os.X_OK)
    except (OSError, ValueError):
        runnable = False
    if not runnable:
        return f"is not an executable file ({script})", script
    return None, script


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
    before any gate — the door does not create it. Resolved, so every gate
    sees one spelling of it (``RUN_ROOT`` is exported once, by the door, and
    every gate runs with that folder as its working directory).
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
            "absolute path. The run root is the folder the door's gates run "
            "from; the door never creates it, because a root made silently is "
            "a run that runs where nobody looks. Name a directory that exists, "
            "or unset the variable to use the tree "
            f"the door runs from ({ROOT})",
        )
    return path.resolve()


def _command(verb: str, argv: list[str]) -> str:
    """The command line a run was opened with, as its log files it."""
    return shlex.join(["python", "-m", DOOR_MODULE, *([verb] if verb else []), *argv])


#: What ``--host`` says on every run.
HOST_HELP = f"the rig, as your ssh names it: its name in {RIGS_SHOWN}/"


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
        for e in (*SEQUENCE, *ALWAYS, *READ_SEQUENCE, *LINK_SEQUENCE, LEASE_RELEASE)
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
        for e in (*SEQUENCE, *ALWAYS, *READ_SEQUENCE, *LINK_SEQUENCE, LEASE_RELEASE)
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

    A caller's gate is started by the path :func:`_outside` resolved and
    checked, opened by name again at the spawn: the gate file, or a folder on
    its path, swapped between the check and the spawn is not caught. A signal
    to the door that lands while a caller's gate is being started, before the
    door waits on it in :func:`_collect_bounded`, raises past it, and that gate
    is left running; a burst of signals can land there. Both are known limits,
    held to be acceptable while the caller is the user.
    """
    # A caller's gate runs from its own root and sees it as RUN_ROOT; what it
    # exports still lands in the door's ``env``. Its path is held to its root
    # again here: the list was checked when it was read, and a gate that ran
    # since could have swapped this one's file for a link out of the root.
    # A caller's gate is named by the list's own text; what the door prints
    # of it is escaped (see :func:`_printable`).
    name = _printable(entry.script) if entry.root else entry.script
    if entry.root:
        why_not, script = _outside(Path(entry.script), Path(entry.root))
        if why_not is not None:
            _refuse(2, _printable(f"{entry.script} {why_not}, since the list was read"))
        child = dict(env, RUN_ROOT=entry.root)
        # The handlers to set back once the gate's group is ended, taken
        # before the gate starts: ending it sets both signals aside.
        restore = {sig: signal.getsignal(sig) for sig in UNSTOPPABLE}
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
            reported, status = _collect_bounded(entry, proc, fd, restore)
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
                f"{name} wrote {_start_of(line) if entry.root else repr(line)} "
                "on RUN_EXPORT_FD, which is not "
                "KEY=VALUE; the door passes named facts between gates and "
                "nothing else",
            )
        key, value = match.group(1), match.group(2)
        if "\x00" in value:
            _refuse(
                2,
                f"{name} exported {key} with a NUL byte in its value; no "
                "process can start with it in its environment",
            )
        if key not in entry.exports:
            _refuse(
                2,
                f"{name} exported {key}, which it does not declare in "
                f"{'its gate list' if entry.root else 'SEQUENCE'}. The door knows "
                "the whole vocabulary before anything runs, so a gate cannot "
                "introduce a variable a later gate reads",
            )
        env[key] = value

    missing = [k for k in entry.exports if k not in env]
    if status == 0 and missing:
        _refuse(
            2,
            f"{name} exited 0 without exporting {', '.join(missing)}; "
            "an entry that admits the run must produce what it declares, or a "
            "later gate reads an empty value as a fact",
        )
    return status


def _add_serving(parser: argparse.ArgumentParser) -> None:
    """``--model``, ``--parallel``, ``--ctx-per-slot`` and ``--ubatch``, the
    same four on a step run, exported to the step as RUN_MODEL,
    RUN_PARALLEL, RUN_CTX_PER_SLOT and RUN_UBATCH. A step run has no default
    for any of the four (owner, on mcgyvr#633): nothing of the door reads
    them, and each is exported only when it is given.
    """
    parser.add_argument(
        "--model",
        default=None,
        help="blob path AS THE RIG SEES IT",
    )
    parser.add_argument("--parallel", type=int, default=None, help="slots (-np)")
    parser.add_argument(
        "--ctx-per-slot",
        type=int,
        default=None,
        help="per-slot window; -c is this times --parallel",
    )
    parser.add_argument(
        "--ubatch",
        type=int,
        default=None,
        help="-ub, and -b with it",
    )


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


def _start_of(line: str, most: int = 80) -> str:
    """``line`` quoted, cut to its first ``most`` characters when it is longer."""
    if len(line) <= most:
        return repr(line)
    return f"{line[:most]!r}... ({len(line)} characters)"


def _end_group(
    proc: subprocess.Popen[bytes], restore: dict[signal.Signals, Any]
) -> None:
    """End a caller's gate and its process group, and wait for the group to be gone.

    TERM goes to the gate's process group. The door waits up to
    :data:`GROUP_GRACE_S` for the group to be empty, so a process of it that
    cleans up on TERM gets to finish, and sends KILL to what is left of it
    only then; after KILL it waits up to :data:`GROUP_GONE_S` for the group
    to be empty. A process stays in its group until it is reaped. The door
    reaps the gate, and any process of the group that has become its own
    child (a door running as PID 1 or as a child subreaper adopts the ones
    the gate left); any other is reaped by whoever adopted it. When the bound
    after KILL passes with the group not yet empty (a process KILL cannot end
    at once, or one nobody has reaped), the door goes on: the lease release
    still runs, with those processes still in the group. A process the gate
    started in a group or a session of its own is outside the group and is
    not ended.

    INT and TERM are ignored while it runs, and set back to ``restore`` when
    it returns. A signal that landed in a wait would otherwise raise out of
    it: the caller would call it again, which sends TERM again and starts the
    grace over, and a gate ended at its bound would be reported as an
    interrupted run (130) rather than refused (2). A signal already pending
    when it is called can raise before they are ignored; the caller calls it
    again until it returns (see :func:`_collect_bounded`).
    """
    try:
        for sig in UNSTOPPABLE:
            signal.signal(sig, signal.SIG_IGN)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGTERM)
        if not _group_gone(proc, GROUP_GRACE_S):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)
            _group_gone(proc, GROUP_GONE_S)
    finally:
        for sig, handler in restore.items():
            signal.signal(sig, handler)


def _group_gone(proc: subprocess.Popen[bytes], within: float) -> bool:
    """Whether the gate's process group is empty within ``within`` seconds.

    The gate is reaped as it ends. Once it is, a process of its group that is
    the door's child now is reaped too: only a process the door adopted can
    be, since the gate was the door's one child in the group.
    """
    until = time.monotonic() + within
    while True:
        if proc.poll() is not None:
            with contextlib.suppress(ChildProcessError):
                while os.waitpid(-proc.pid, os.WNOHANG)[0]:
                    pass
        try:
            os.killpg(proc.pid, 0)
        except (ProcessLookupError, PermissionError):
            return True
        if time.monotonic() >= until:
            return False
        time.sleep(0.02)


def _collect_bounded(
    entry: Entry,
    proc: subprocess.Popen[bytes],
    fd: int,
    restore: dict[signal.Signals, Any],
) -> tuple[str, int]:
    """What a caller's gate exported and its status, within its time bound.

    The export pipe is read until every writer has closed it and the gate has
    exited, or until the bound, and is waited on with ``poll``, which takes a
    descriptor of any number. At the bound the gate's process group is ended
    (:func:`_end_group`) and the gate refused, whether the gate still runs or
    exited and left a process holding the descriptor open; the refusal says
    which. A gate that writes more than :data:`MAX_EXPORT_BYTES` on it is
    ended and refused the same way, and one that writes bytes that are not
    UTF-8 is refused: carried on, each would grow into three.

    A KeyboardInterrupt ends the group the same way before it goes on. A
    second signal can land before :func:`_end_group` has set both aside, and
    raise out of it; the door calls it again until it returns, and it sets
    the handlers back to ``restore``, taken before the gate started.
    """
    deadline = time.monotonic() + entry.timeout_s
    chunks: list[bytes] = []
    held = 0

    def ended(why: str) -> NoReturn:
        _end_group(proc, restore)
        _refuse(2, _printable(f"{entry.script} {why}"))

    def over() -> NoReturn:
        bound = f"{entry.timeout_s:g} s"
        if proc.poll() is None:
            ended(f"ran past its bound of {bound} and was ended with its process group")
        ended(
            "exited, but a process it left held its export descriptor past the "
            f"bound of {bound}; what was left of its process group was ended"
        )

    try:
        try:
            poller = select.poll()
            poller.register(fd, select.POLLIN)
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    over()
                if poller.poll(math.ceil(left * 1000)):
                    data = os.read(fd, 65536)
                    if not data:
                        break
                    held += len(data)
                    if held > MAX_EXPORT_BYTES:
                        wrote = (
                            f"wrote more than {MAX_EXPORT_BYTES} bytes on "
                            "RUN_EXPORT_FD, more than the door reads from a gate"
                        )
                        if proc.poll() is None:
                            ended(f"{wrote}, and was ended with its process group")
                        ended(
                            f"{wrote}, and exited; what was left of its process "
                            "group was ended"
                        )
                    chunks.append(data)
            try:
                status = proc.wait(timeout=max(deadline - time.monotonic(), 0.0))
            except subprocess.TimeoutExpired:
                over()
        except KeyboardInterrupt:
            while True:
                try:
                    _end_group(proc, restore)
                    break
                except KeyboardInterrupt:
                    continue
            raise
    finally:
        os.close(fd)
    try:
        return b"".join(chunks).decode("utf-8"), status
    except UnicodeDecodeError as bad:
        _refuse(
            2,
            _printable(
                f"{entry.script} wrote bytes that are not UTF-8 on RUN_EXPORT_FD "
                f"(at byte {bad.start + 1}); the door passes text between gates"
            ),
        )


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

    Ported from the lab's archived door (its ``check_step_args``): six steps
    kept an output override from their bare-run days and three a
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


def _gates_help(verb: str, phases: str) -> str:
    """``--gates``'s help on ``verb``: what every caller's gate is held to,
    then ``phases``, where this verb runs each phase."""
    return (
        "a caller's gate list (JSON: root, gates of path, why, phase, "
        "exports, timeout_s), each gate run by the door's Python from the "
        "root, in a session of its own. The list "
        f"${GATES_ENV}/{verb}.json, when that variable is set and the folder "
        "holds one, runs too, its gates before this list's in each phase. "
        "At a gate's timeout_s (default "
        f"{CALLER_GATE_TIMEOUT_S:g} s, at most {CALLER_GATE_MOST_S:g} s) the "
        "door sends TERM to its process group, KILL when the group is still "
        f"there {GROUP_GRACE_S:g} s later, then waits up to {GROUP_GONE_S:g} s "
        "for the group to be empty, and refuses the gate; there is no bound "
        "over the whole list, each gate has its own. A signal to the door's "
        "process group does not reach a gate: the door ends it on INT or "
        "TERM, except a gate the signal reaches while the door is starting "
        "it, which can be left running past the lease release; a door that "
        "is killed or hung up leaves it running with no bound. A process "
        "a gate leaves behind after ending within its "
        "bound outlives the door, unless it holds the gate's export "
        "descriptor open: then the door waits up to the bound for it to "
        "close it, and if it has not, refuses the gate and ends the gate's "
        "process group, which ends that process only while it is in the "
        "group. One in a group or a session of its own outlives the door "
        "even while it holds the descriptor. A gate may write at most "
        f"{MAX_EXPORT_BYTES // 1024} KiB of UTF-8 on its export descriptor; "
        "one that writes more is ended and refused. What all gates export "
        "together must fit in the environment a process starts with: when "
        "it does not, the next gate cannot start, and the door refuses "
        "naming that gate. " + phases
    )


#: Where a serve or a step run places each phase of a caller's gates, as its
#: ``--gates`` help says it.
SERVE_PHASES_HELP = (
    "`before` gates run after the "
    "profile and before anything is sent to the machine; `after` gates "
    "after the identity and daemon gates and before the envelope and "
    "the step; `always` gates after gates 7 and 8 and before the lease "
    "is released, and only when the run got as far as gate 5. A "
    "`before` or `after` gate that refuses, runs past its bound or dies "
    "ends the run as a door gate's refusal does: the door's gates after "
    "it do not run, and the lease is still released. An `always` gate "
    "that refuses does not stop the next. A caller's gate never runs in "
    "place of a door gate or moves one"
)


def _serve_parse(argv: list[str]) -> argparse.Namespace:
    """The serve run's arguments. Nothing skips a gate."""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run serve",
        description=(
            "start a live ladder on a rig and leave it running, or stop it; put "
            "its units to sleep or wake them; or fetch weights onto it"
        ),
    )
    parser.add_argument(
        "direction",
        choices=sorted(SERVE_STEPS),
        help="up | down | sleep | wake | fetch",
    )
    parser.add_argument("--host", required=True, help=HOST_HELP)
    parser.add_argument(
        "--compose",
        default=None,
        help=(
            "up, down, sleep and wake: the compose file `mcgyvr emit` wrote for "
            "this host"
        ),
    )
    parser.add_argument(
        "--weights",
        default=None,
        metavar="FILE",
        help=(
            'fetch only: the fetch list (JSON: {"files": [{repo, revision, file, '
            "sha256, bytes}]}), each file pinned to a commit and its sha256 as "
            "the model knowledge records it. The files land in the rig's weights "
            "folder ($MCGYVR_WEIGHTS there, else ~/.cache/mcgyvr/weights) under "
            "their base names; a download resumes from its .part, and one whose "
            "sha256 does not match is deleted. No size cap: the total is said "
            "before a byte moves. The Hub is $HF_ENDPOINT when set (https, or "
            "http on this machine's loopback), else huggingface.co"
        ),
    )
    parser.add_argument(
        "--hf-token-env",
        default=None,
        metavar="VAR",
        help=(
            "fetch only: the variable a Hugging Face token is read from, for a "
            "gated or private repository (default: HF_TOKEN, used when set). "
            "Named and empty is refused. The token goes to the fetch on the rig "
            "inside the ssh connection, never on a command line or into a file"
        ),
    )
    parser.add_argument("--suffix", default="", help="distinguishes a re-run's RUN_ID")
    parser.add_argument("--date", default="", help="YYYY-MM-DD; defaults to today, UTC")
    parser.add_argument(
        "--unit",
        action="append",
        default=[],
        metavar="CONTAINER",
        help=(
            "up, down, sleep and wake: act on this container of the compose file "
            "and leave the file's other units as they are (repeatable). `up` "
            "starts it without its compose neighbours, `down` stops and removes "
            "it, and a card's co-resident vLLM units each sleep at level 2 on "
            "their own"
        ),
    )
    parser.add_argument(
        "--gates",
        default=None,
        metavar="FILE",
        help=_gates_help(
            "serve",
            SERVE_PHASES_HELP,
        ),
    )
    return parser.parse_args(argv)


def _serve_refusal(opts: argparse.Namespace) -> str | None:
    """Why the flags of a serve run do not go together, or None when they do."""
    if opts.direction == "fetch":
        given = [
            flag
            for flag, value in (("--compose", opts.compose), ("--unit", opts.unit))
            if value
        ]
        if given:
            return (
                f"serve fetch takes no {' or '.join(given)}: a fetch downloads "
                "weights and starts nothing; name what it downloads with --weights"
            )
        if opts.weights is None:
            return "serve fetch names what it downloads with --weights FILE"
        return None
    if opts.compose is None:
        return f"serve {opts.direction} needs --compose, the file `mcgyvr emit` wrote"
    if opts.weights is not None or opts.hf_token_env is not None:
        return (
            f"serve {opts.direction} takes no --weights or --hf-token-env; only "
            "serve fetch downloads"
        )
    return None


def _serve(argv: list[str]) -> int:
    """`serve up|down|sleep|wake|fetch`: the serve run's fixed sequence."""
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
    mismatched = _serve_refusal(opts)
    if mismatched is not None:
        print(f"run.py: REFUSED — {mismatched}", file=sys.stderr)
        return 2
    compose_file: Path | None = None
    units: tuple[Any, ...] = ()
    fetch: dict[str, str] = {}
    if opts.direction == "fetch":
        # Read here, before any gate, for the reason the compose file is: the
        # files the step downloads are the door's reading of the list, held to
        # a hash, and nothing reaches the rig for a list it cannot hold.
        from mcgyvr.serving import fetchlist

        listed = Path(opts.weights)
        listed = listed if listed.is_absolute() else Path.cwd() / listed
        try:
            wants = fetchlist.read(listed)
        except fetchlist.FetchListError as escape:
            print(
                f"run.py: REFUSED — --weights {opts.weights}: {escape}", file=sys.stderr
            )
            return 2
        try:
            fetchlist.endpoint(os.environ)
            token_env = fetchlist.token_variable(opts.hf_token_env, os.environ)
        except fetchlist.FetchListError as escape:
            print(f"run.py: REFUSED — {escape}", file=sys.stderr)
            return 2
        fetch = {"RUN_FETCH": fetchlist.dump(wants), "RUN_FETCH_TOKEN_ENV": token_env}
    else:
        assert opts.compose is not None
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
        # `--unit` is read against the same reading, for the same reason: the
        # step acts only on containers the door named from the file.
        unknown = sorted(set(opts.unit) - {unit.container for unit in units})
        if unknown:
            print(
                f"run.py: REFUSED — the compose file names no container "
                f"{', '.join(unknown)}; --unit names a container the file declares",
                file=sys.stderr,
            )
            return 2
    try:
        gates = callers_gates("serve", opts.gates)
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
        RUN_STEP_FILE=str(SERVE_STEPS[opts.direction].resolve()),
        RUN_HOST=opts.host,
        RUN_SUFFIX=opts.suffix,
        RUN_SERVE=opts.direction,
        RUN_COMPOSE=str(compose_file.resolve()) if compose_file is not None else "",
        RUN_SERVE_EXPECTED=" ".join(unit.container for unit in units),
        RUN_SERVE_ONLY=" ".join(sorted(set(opts.unit))),
        RUN_SERVE_ASLEEP=" ".join(sorted(u.container for u in units if u.asleep)),
        RUN_COMMAND=_command("serve", argv),
        **fetch,
    )
    if opts.date:
        env["RUN_DATE"] = opts.date
    return _through_step(SERVE_SEQUENCE, SERVE_PHASES, env, gates)


def _through_step(
    sequence: tuple[Entry, ...],
    phases: dict[str, str],
    env: dict[str, str],
    gates: GateList | None,
    step_args: list[str] | None = None,
) -> int:
    """A serve or a step run's fixed ``sequence``, to completion.

    Each entry in order, a caller's gates placed after the entry their phase
    names in ``phases``; the step's own failure is a result, not a refusal,
    so the run goes on past it. Then gates 7 and 8 and the caller's
    ``always`` gates (:func:`_always`), whatever the step did, and gate 5's
    claim and the rig's lease released on every way out. ``step_args`` are
    handed to gate 6 alone.
    """
    interrupted = False
    step_status = 0
    try:
        try:
            check_manifest()
            for entry in sequence:
                args = step_args if entry.script == "06-step.py" else None
                status = _run_entry(entry, env, args)
                if status != 0:
                    if entry.script != "06-step.py":
                        return _stop(entry, status, env)
                    step_status = status
                for gate in _following(entry, phases, gates):
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

        env["RUN_STEP_EXIT"] = "interrupted" if interrupted else str(step_status)
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
    """The read run's arguments. Nothing skips a gate."""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run read",
        description=(
            "read a rig: its facts, its containers and its card, filed under "
            "the journal of the fleet read (the live one, or --fleet's); --probe "
            "and --load run the lock's harness on it"
        ),
    )
    parser.add_argument("--host", required=True, help=HOST_HELP)
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
        help=_gates_help(
            "read",
            "`before` gates run after the "
            "profile and before anything is sent to the machine. `after` gates "
            "run after the machine is read and what was read is filed, so they "
            "cannot stop that filing, and only when the reading gate exited 0: "
            "it exits non-zero when it refused, and also after filing when a "
            "probe or a load on the rig failed, or when a read under the dev "
            "profile raised an alert. A read has no `always` phase, and a list "
            "that asks for one is refused",
        ),
    )
    return parser.parse_args(argv)


def _read(argv: list[str]) -> int:
    """`read`: the read run's fixed sequence, to completion. Nothing is leased."""
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
        gates = callers_gates("read", opts.gates, tuple(READ_PHASES))
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
        RUN_COMMAND=_command("read", argv),
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


def _link_parse(argv: list[str]) -> argparse.Namespace:
    """The link run's arguments: the host, and exactly one of the timer's modes."""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run link",
        description=(
            "time a link on a rig: copies between two of its cards (--peer), or "
            "the network to another rig (--sink there, --send here); one bounded "
            "timer, its reading printed as one line of JSON and nothing filed"
        ),
    )
    parser.add_argument(
        "--host", required=True, help="the rig the timer runs on, as ssh names it"
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    for flag, names in LINK_MODES.items():
        modes.add_argument(flag, nargs=2, metavar=names)
    parser.add_argument(
        "--gates",
        default=None,
        metavar="FILE",
        help=_gates_help(
            "link",
            "A link takes `before` gates alone, which run before the timer "
            "reaches the rig; a gate that refuses, runs past its bound or dies "
            "ends the run and the timer does not run. Nothing runs after the "
            "timer: its reading is the last line the run prints, and a list "
            "that asks for `after` or `always` is refused",
        ),
    )
    return parser.parse_args(argv)


def _link_args(opts: argparse.Namespace) -> list[str]:
    """The timer's mode and arguments, checked before anything reaches a rig."""
    for flag in LINK_MODES:
        given = getattr(opts, flag[2:])
        if given is None:
            continue
        first, second = given
        if flag == "--peer":
            cards = [first, second]
            if not all(card.isascii() and card.isdigit() for card in cards):
                raise RefusedError(2, f"--peer {first} {second}: a card is its index")
            if first == second:
                raise RefusedError(2, f"--peer {first} {second}: two cards, not one")
            return ["peer", str(int(first)), str(int(second))]
        try:
            ipaddress.IPv4Address(first)
        except ValueError:
            raise RefusedError(
                2, f"{flag} {first!r}: the address is an IPv4 literal, never a name"
            ) from None
        if not (second.isascii() and second.isdigit() and 1024 <= int(second) < 65536):
            raise RefusedError(2, f"{flag} port {second!r}: a port from 1024 to 65535")
        return [flag[2:], first, str(int(second))]
    raise RefusedError(2, "link: no mode given")


def _link(argv: list[str]) -> int:
    """`link`: the link run's fixed sequence, to completion. Nothing is leased."""
    opts = _link_parse(argv)
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    try:
        timer = _link_args(opts)
        root = run_root()
        gates = callers_gates("link", opts.gates, LINK_PHASES)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    env.update(
        RUN_ROOT=str(root),
        RUN_BIN=str(BIN),
        RUN_HOST=opts.host,
        RUN_LINK=" ".join(timer),
        RUN_COMMAND=_command("link", argv),
    )
    try:
        check_manifest()
        # The link's one phase, before the timer: nothing has reached the rig.
        for gate in gates.before if gates else ():
            status = _run_entry(gate, env)
            if status != 0:
                return _stop_caller(gate, status)
        for entry in LINK_SEQUENCE:
            status = _run_entry(entry, env)
            if status != 0:
                return status
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    except KeyboardInterrupt:
        return 130
    return 0


#: What ``step --help`` says the step run is.
STEP_HELP = (
    "advanced: run one script of your own on a rig, under the door's fixed "
    "gates. The door settles the profile, leases the rig and reads it (held to "
    f"your rig file, {RIGS_SHOWN}/RIG.json), checks that its docker daemon "
    "answers and is that machine, and makes the run's envelope; "
    "then it runs your --step with the run exported to it (RUN_ID, "
    "RUN_OUT_DIR, RUN_HOST, ...) and its ssh and docker reaching that rig "
    "alone; then, whatever the step did, it names any container the step left "
    "and parses what the step declared it writes, and releases the lease. "
    "Nothing here skips a gate"
)


def _step_parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """The step run's arguments. Nothing skips a gate."""
    step_args: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, step_args = argv[:cut], argv[cut + 1 :]
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run step", description=STEP_HELP
    )
    parser.add_argument("--host", required=True, help=HOST_HELP)
    parser.add_argument(
        "--campaign",
        required=True,
        help="names the run, as one folder name: its envelope and its RUN_ID",
    )
    parser.add_argument(
        "--step",
        required=True,
        metavar="PATH",
        help=(
            "your own executable script; gate 6 runs it from the run root with "
            "the run exported to it and the arguments after `--`. It declares "
            "what it writes on one `# RUN_ARTIFACTS: NAME...` comment line (or "
            "RUN_REWRITES / RUN_APPENDS), and writes it under RUN_OUT_DIR"
        ),
    )
    parser.add_argument(
        "--out-root",
        default=None,
        metavar="DIR",
        help=(
            "an existing folder the run is filed under, as "
            "DIR/<date>-<campaign>/ (default: the run's own folder of the "
            "door's log under the data folder). The door never makes it"
        ),
    )
    parser.add_argument("--suffix", default="", help="distinguishes a re-run's RUN_ID")
    parser.add_argument("--date", default="", help="YYYY-MM-DD; defaults to today, UTC")
    _add_serving(parser)
    parser.add_argument(
        "--gates",
        default=None,
        metavar="FILE",
        help=_gates_help("step", SERVE_PHASES_HELP),
    )
    return parser.parse_args(argv), step_args


def _step(argv: list[str]) -> int:
    """`step`: the step run's fixed sequence around the caller's own step."""
    opts, step_args = _step_parse(argv)
    # Every refusal below happens before a gate runs: nothing checked,
    # nothing made, no rig read.
    inherited = _ambient()
    if inherited is not None:
        print(
            f"run.py: REFUSED — {inherited} is set in the calling environment; "
            "unset it and rerun; the door mints its own vocabulary",
            file=sys.stderr,
        )
        return 2
    if CAMPAIGN_NAME.fullmatch(opts.campaign) is None or opts.campaign in (".", ".."):
        print(
            _printable(
                f"run.py: REFUSED — --campaign {opts.campaign!r} is not one folder "
                "name ([A-Za-z0-9_.-]+): it names the run's envelope and its "
                "RUN_ID, and a name that is a path would file the run elsewhere"
            ),
            file=sys.stderr,
        )
        return 2
    escape = _model_escape(opts.model) if opts.model is not None else None
    if escape is not None:
        print(f"run.py: REFUSED — {escape}", file=sys.stderr)
        return 2
    try:
        root = run_root()
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    step = Path(opts.step)
    step = step if step.is_absolute() else Path.cwd() / step
    if not step.is_file():
        print(f"run.py: REFUSED — --step {opts.step} is not a file", file=sys.stderr)
        return 2
    # Resolved once: gate 5 names the run by the file the door exports, so
    # the envelope the step's arguments are held to is named by it too.
    step_file = step.resolve()
    out_root = ""
    if opts.out_root is not None:
        folder = Path(opts.out_root)
        folder = folder if folder.is_absolute() else Path.cwd() / folder
        if not opts.out_root or not folder.is_dir():
            print(
                f"run.py: REFUSED — --out-root {opts.out_root!r} is not an "
                "existing folder. The run is filed under it, and the door never "
                "makes the folder a run is filed under: a folder made silently "
                "is a run filed where nobody looks",
                file=sys.stderr,
            )
            return 2
        out_root = str(folder.resolve())

    run_date = opts.date or datetime.now(UTC).strftime("%Y-%m-%d")
    from mcgyvr.fleet.roots import FolderError

    try:
        envelope = gatelib.envelope_of(
            out_root=out_root,
            run_date=run_date,
            campaign=opts.campaign,
            run_id=gatelib.run_id_of(run_date, opts.campaign, step_file, opts.suffix),
        )
    except (FolderError, RuntimeError) as unnamed:
        print(
            f"run.py: REFUSED — the data folder cannot be named: {unnamed}",
            file=sys.stderr,
        )
        return 2
    escape = _check_step_args(step_args, envelope, root)
    if escape is not None:
        print(f"run.py: REFUSED — {escape}", file=sys.stderr)
        return 2
    try:
        gates = callers_gates("step", opts.gates)
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
        RUN_CAMPAIGN=opts.campaign,
        RUN_STEP_FILE=str(step_file),
        RUN_HOST=opts.host,
        RUN_SUFFIX=opts.suffix,
        # Read off the clock once: the envelope above was named by it, and
        # gate 5 files under it.
        RUN_DATE=run_date,
        RUN_COMMAND=_command("step", argv),
    )
    # Each of the four only when it is given: a step run has no defaults.
    for name, value in (
        ("RUN_MODEL", opts.model),
        ("RUN_PARALLEL", opts.parallel),
        ("RUN_CTX_PER_SLOT", opts.ctx_per_slot),
        ("RUN_UBATCH", opts.ubatch),
    ):
        if value is not None:
            env[name] = str(value)
    if out_root:
        env[gatelib.OUT_ROOT_VAR] = out_root
    return _through_step(STEP_SEQUENCE, STEP_PHASES, env, gates, step_args)


def main(argv: list[str] | None = None) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    if given[:1] == ["serve"]:
        return _serve(given[1:])
    if given[:1] == ["read"]:
        return _read(given[1:])
    if given[:1] == ["link"]:
        return _link(given[1:])
    if given[:1] == ["step"]:
        return _step(given[1:])
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run",
        description="the one access point to the rigs",
        epilog=(
            "The verbs, each with its own --help: `serve "
            "up|down|sleep|wake|fetch` starts, stops, sleeps or wakes a "
            "ladder on a rig, or fetches weights onto it; `read` reads a rig; "
            "`link` times a link on one; and, advanced, `step` runs one script "
            "of your own on a rig under the door's fixed gates (the lease, the "
            "rig's reading, its daemon, the envelope, then teardown and parse), "
            "filed under the door's log or --out-root"
        ),
    )
    parser.add_argument("verb", nargs="?", choices=("serve", "read", "link", "step"))
    parser.parse_args(given)
    parser.print_help()
    return 0


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
    and counts as its refusal. One the signal reaches while the door is
    starting it is not ended and can run on past the lease release; the door
    cannot tell the two apart, and its message says either may be so. INT
    and TERM are set to end a caller's gate
    only while it runs, and set aside again before the door says how it
    ended; a signal that lands in between is caught and they are set aside
    again (:func:`_aside`), so it neither stops the next gate nor escapes the
    door. One more signal landing in the few instructions between catching a
    signal and setting them aside can still escape. The claim gate 5 took on
    the RUN_ID is released last, on every path out of here.
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
            status: int | None = None
            refused: RefusedError | None = None
            ended = False
            try:
                try:
                    for sig in UNSTOPPABLE:
                        signal.signal(sig, _sigterm)
                    status = _run_entry(entry, env)
                except RefusedError as refusal:
                    refused = refusal
                except KeyboardInterrupt:
                    ended = True
                finally:
                    _aside()
            except KeyboardInterrupt:
                # One more signal, landed before INT and TERM were set aside.
                _aside()
                ended = ended or (status is None and refused is None)
            if refused is not None:
                print(f"run.py: REFUSED — {refused.rule}", file=sys.stderr)
                after = refused.status
            elif ended:
                print(
                    _printable(
                        f"run.py: {entry.script} is refused: a signal reached "
                        "the door while it ran or was being started (one the "
                        "door was waiting on is ended with its process group; "
                        f"one being started may still run) — {entry.why}"
                    ),
                    file=sys.stderr,
                )
                after = entry.status
            elif status:
                print(
                    _printable(
                        f"run.py: {entry.script} ({_ended(status)}) — {entry.why}"
                    ),
                    file=sys.stderr,
                )
                after = entry.status
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        _release_claim(env)
    return after


def _aside() -> None:
    """Set INT and TERM to be ignored, whatever signal lands while it does so.

    A signal that arrives while a handler is still the door's raises
    KeyboardInterrupt; it is caught and the setting done again, so once this
    returns neither signal raises.
    """
    while True:
        try:
            for sig in UNSTOPPABLE:
                signal.signal(sig, signal.SIG_IGN)
        except KeyboardInterrupt:
            continue
        return


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
        _printable(
            f"run.py: REFUSED at {entry.script} ({_ended(status)}) — {entry.why}"
        ),
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
