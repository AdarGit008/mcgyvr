#!/usr/bin/env python3
"""The one access point to the rigs.

    python -m mcgyvr.serving.run serve|read|link ...

Nothing else opens an ssh to a rig or starts a container on one. ``serve``
starts, stops, sleeps or wakes the units of a launch spec on a rig, or fetches
weights onto it; ``read`` reads a rig; ``link`` times a link on one. Each runs
a fixed sequence of the door's own gates, and no flag adds a gate, skips one
or moves one. The door runs no code but its own: no variable, flag or
argument names a check, a step or a gate of a caller's.

THE SERVE RUN is the run: the config gate, the rig's lease and reading, its
daemon, the envelope, then the serve step, then gates 7 and 8 whatever the
step did, and the lease released last (:data:`SERVE_SEQUENCE`). Its envelope
is the run's own folder of the door's log under the data folder
(``<data folder>/door/<date>/<RUN_ID>/``).

HOW THE DOOR IS THE ONLY WAY IN. The environment a gate or a step runs under
has ``gate-scripts/bin`` first on PATH, where ``ssh`` and ``docker`` are shims
that admit exactly the host the door was opened for and refuse any process
the door did not start (:func:`mcgyvr.serving.gatelib.under_door` reads the
parent chain from /proc, which nothing can set). ``docker`` under the door is
the RIG's daemon (``-H ssh://<host>``), never the operator's. And the door
refuses to start under an ambient ``RUN_*`` or ``DOCKER_*`` variable: it mints
its own vocabulary, and a value inherited from the shell is one no gate set.

THE ACCEPTED LIMITS, in two sentences. The proof every gate and step applies
is an ancestor's command line plus RUN_HOST, both of which an operator
can forge with ``bash -c ... x/mcgyvr/serving/run.py``, so the seal is against
every code path in this repository and not against an operator impersonating
the door. And a step is code run under the door: one that calls
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

THE RUN ROOT. The door's gates run from the tree its own file sits in
(:data:`ROOT`) and see it as ``RUN_ROOT``; the door also exports its shim
directory as ``RUN_BIN``, so a step derives neither from the other.

GATE ORDER IS THE POINT, NOT AN IMPLEMENTATION DETAIL. Gates 1-4 write nothing:
gate 1 reaches no rig, gate 2 takes the rig's lease (a rig another live run
holds is refused, untouched) and reads the rig, gates 3-4 only read, and none
launches anything,
so a machine that is not what it claims leaves no artifact to clean up. Gate 5
stamps the lease and makes the envelope. Gates 7-8 run after the step whatever
it did.

ONE MODE, THE USER'S. The rig is held to the user's own rig file
(``<rig-file folder>/<rig>.json``, :mod:`mcgyvr.serving.rigfile`, written by
``mcgyvr scan --rig``). Each run reads the rig again, says what moved, and
refuses only when the fleet no longer fits. Every gate is the same on every
run: the config and the live fleet's lock, the lease, the daemon that answers
and is the machine that was read, the envelope, the step, and the
stray-container check. A serve run is filed under the data folder's
``door/<date>/<run_id>/`` (command, rig reading before and after, compose
text, units up, step exit), and a container or a card holder mcgyvr did not
start is reported and left as it is.

THE CONTRACT WITH A GATE SCRIPT. The door's own gates are executables under
``gate-scripts/``. A gate reads the run from the environment (:data:`EXPORTED`),
writes anything it learned as ``KEY=VALUE`` lines on the descriptor
``RUN_EXPORT_FD`` names, and exits 0 to admit or non-zero having said why. It
is not imported: a gate that could be imported could be monkeypatched, and the
seam that lets a test stub a gate is the seam that lets a caller do it.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
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
#: The files beside the gates that a gate READS rather than spawns.
#: `rigscan.py` is the one reader of a machine: gate 2 ships it to the rig and
#: gate 7 compares against what it printed. It is not an entry in SEQUENCE, so
#: it would not be on the manifest — and a check that covers only the entries
#: someone remembered is the absence the manifest exists to turn into a
#: refusal: a reader that is gone is a gate 2 that dies on a traceback, which
#: is a gate that stopped running without anyone deciding it should.
#: `rig-units.sh` is the runtime reader gates 2 and 7 and the read run ship
#: beside it: what holds the rig, not what the rig is.
#: `linktime.py` is the one timer the link run ships to a rig
#: (gate-scripts/link-01-time.py), and `fetcher.py` the one downloader a
#: `serve fetch` ships (gate-scripts/serve-fetch.py).
READERS = (
    HERE / "rigscan.py",
    GATE_SCRIPTS / "rig-units.sh",
    HERE / "linktime.py",
    HERE / "fetcher.py",
)
#: The door's own serve steps, one per direction, shipped beside the gates.
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
#: The tree this file sits in, four levels up (src/mcgyvr/serving/run.py): the
#: run root, where the door's gates run from. Read from the file's own location
#: and never from the caller's cwd. From an installed wheel it is
#: ``site-packages/``.
ROOT = HERE.parents[2]


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
#: configurable. The step is gate 6's payload and appears nowhere else in this
#: list.
SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "01-round.py",
        "gate 1: the run knows which config it is under, and a `serve up` "
        "held to the live fleet's lock starts only units it names",
        exports=("RUN_CONFIG",),
    ),
    Entry(
        "02-rig.py",
        "gate 2: the rig is leased to this run — refused, untouched, if "
        "another live run holds it; a dead run's lease is reclaimed — and read "
        f"again, and held to your rig file ({RIGS_SHOWN}/<rig>.json, written "
        "by `mcgyvr scan --rig`): what moved is said, and the run is refused "
        "only when the fleet no longer fits",
        exports=("RUN_LEASE", "RUN_PRE_RIG"),
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
            "RUN_SUPERSEDED",
        ),
    ),
    Entry(
        "06-step.py",
        "gate 6: the step, with the run exported to it. Its stdout and stderr "
        "are the operator's; the door adds nothing",
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
#: --compose FILE`). The whole of :data:`SEQUENCE`: config, rig, daemon,
#: envelope, then the serve step, then gates 7 and 8. A live ladder is started
#: and LEFT RUNNING, which gate 7 reads in its own serve vocabulary; `serve
#: fetch --weights FILE` runs the same sequence: it leases the rig it downloads
#: onto, and gate 7 names any container that is up after it and was not before.
SERVE_SEQUENCE: tuple[Entry, ...] = SEQUENCE

#: THE READ RUN (`python -m mcgyvr.serving.run read --host H [--probe UNIT...
#: [--load WxN]]`). A second fixed sequence: the config is settled, then one
#: reader goes to the rig, is compared with the rig's
#: file, and is filed. A plain read starts nothing on the rig; `--probe`
#: and `--load` run the lock's harness there against idle units. There is no
#: lease, no envelope, no teardown and no gate 7 or 8 in it.
READ_SEQUENCE: tuple[Entry, ...] = (
    Entry(
        "read-01-config.py",
        "read, config: the read knows which config it is under, as gate 1 settles it",
        exports=("RUN_CONFIG",),
    ),
    Entry(
        "read-02-rig.py",
        "read, rig: one reader on the rig, its facts held to the user's rig "
        "file and the rest filed under the read fleet's journal; nothing "
        "leased, nothing torn down, and a busy rig read as it is",
    ),
)
#: THE LINK RUN (`python -m mcgyvr.serving.run link --host H (--peer A B |
#: --sink ADDR PORT | --send ADDR PORT)`). A third fixed sequence, and the
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
    # The run root (:data:`ROOT`) and the door's own shim directory. Two
    # variables because they are two places: the root is where the door's
    # gates run, the shims are part of the code, and a step that derived one
    # from the other found no shims under a run root that was not a checkout.
    "RUN_ROOT",
    "RUN_BIN",
    "RUN_STEP_FILE",
    "RUN_HOST",
    "RUN_SUFFIX",
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
    # The command line it was opened with, and, once a serve run's step has
    # ended, how it ended: what the run files in its log.
    "RUN_COMMAND",
    "RUN_STEP_EXIT",
    *(name for entry in (*SEQUENCE, *ALWAYS) for name in entry.exports),
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


def _command(verb: str, argv: list[str]) -> str:
    """The command line a run was opened with, as its log files it."""
    return shlex.join(["python", "-m", DOOR_MODULE, *([verb] if verb else []), *argv])


#: What ``--host`` says on every run.
HOST_HELP = f"the rig, as your ssh names it: its name in {RIGS_SHOWN}/"


def check_manifest() -> None:
    """Every entry exists and is executable, BEFORE anything runs.

    Checked as a set rather than lazily at each step, so a run cannot get four
    gates in — past the config check, past the rig comparison — and then stop
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


def run_entry(entry: Entry, env: dict[str, str]) -> int:
    """Spawn one door entry, fold its exports into ``env``, return its status.

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
    script = GATE_SCRIPTS / entry.script
    read_fd, write_fd = os.pipe()
    try:
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=ROOT,
                env=dict(env, RUN_EXPORT_FD=str(write_fd)),
                pass_fds=(write_fd,),
            )
        except (OSError, ValueError) as escape:
            _refuse(2, f"{entry.script} could not be started: {escape}")
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


def _rel(path: Path, base: Path = ROOT) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


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


def serve(argv: list[str]) -> int:
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

    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env.update(
        RUN_ROOT=str(ROOT),
        RUN_BIN=str(BIN),
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
    return _serve_run(env)


def _serve_run(env: dict[str, str]) -> int:
    """:data:`SERVE_SEQUENCE`, to completion, under the ``env`` :func:`serve`
    built.

    Each entry in order; the step's own failure is a result, not a refusal,
    so the run goes on past it. Then gates 7 and 8 (:func:`_always`),
    whatever the step did, and gate 5's claim and the rig's lease released on
    every way out.
    """
    interrupted = False
    step_status = 0
    try:
        try:
            check_manifest()
            for entry in SERVE_SEQUENCE:
                status = run_entry(entry, env)
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

        env["RUN_STEP_EXIT"] = "interrupted" if interrupted else str(step_status)
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
            "loads (MCGYVR_CONFIG, else the live fleet folder) instead of the "
            "live fleet: no lock, rows "
            "filed locked=false, probe figures unjudged, card and load peak "
            "judged against room_mib"
        ),
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="the id the read's rows are filed under (default: minted)",
    )
    return parser.parse_args(argv)


def read(argv: list[str]) -> int:
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
    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    try:
        pin_config(env)
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env.update(
        RUN_ROOT=str(ROOT),
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
            status = run_entry(entry, env)
            if status == 2:
                return _stop(entry, status, env)
            if status != 0:
                return status
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


def link(argv: list[str]) -> int:
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
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    env = dict(os.environ)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH') or os.defpath}"
    env.update(
        RUN_ROOT=str(ROOT),
        RUN_BIN=str(BIN),
        RUN_HOST=opts.host,
        RUN_LINK=" ".join(timer),
        RUN_COMMAND=_command("link", argv),
    )
    try:
        check_manifest()
        for entry in LINK_SEQUENCE:
            status = run_entry(entry, env)
            if status != 0:
                return status
    except RefusedError as refusal:
        print(f"run.py: REFUSED — {refusal.rule}", file=sys.stderr)
        return refusal.status
    except KeyboardInterrupt:
        return 130
    return 0


def main(argv: list[str] | None = None) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    verbs = {"serve": serve, "read": read, "link": link}
    if given[:1] and given[0] in verbs:
        return verbs[given[0]](given[1:])
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.serving.run",
        description="the one access point to the rigs",
        epilog=(
            "The verbs, each with its own --help: `serve "
            "up|down|sleep|wake|fetch` starts, stops, sleeps or wakes a "
            "ladder on a rig, or fetches weights onto it; `read` reads a rig; "
            "and `link` times a link on one. Each runs the door's own fixed "
            "gates; nothing adds, skips or moves one"
        ),
    )
    parser.add_argument("verb", nargs="?", choices=("serve", "read", "link"))
    parser.parse_args(given)
    parser.print_help()
    return 0


#: What the ALWAYS phase will not be stopped by.
UNSTOPPABLE = (signal.SIGINT, signal.SIGTERM)


def _always(env: dict[str, str]) -> int:
    """Gates 7 and 8, to completion, whatever signal arrives.

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
                if run_entry(entry, env) != 0:
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


def _release_lease(env: dict[str, str]) -> None:
    """Release the rig's lease, if gate 2 took one for this run.

    Through a script and not in-process: the door itself is not *under* the
    door — the shims prove an ancestor — so its own ssh would be refused,
    and rightly. Signals are ignored for the duration, as for gates 7 and
    8: a Ctrl-C that landed on the release would leave a lease a rig cannot
    tell from a live one. Released once: the variable is dropped after.
    """
    if not env.get(gatelib.LEASE_VAR):
        return
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in UNSTOPPABLE}
    try:
        run_entry(LEASE_RELEASE, env)
    except RefusedError as refusal:
        print(f"run.py: {refusal.rule}", file=sys.stderr)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        env.pop(gatelib.LEASE_VAR, None)


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
