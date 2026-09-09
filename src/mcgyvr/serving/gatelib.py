#!/usr/bin/env python3
"""What every gate script needs and nothing else.

Importable, unlike the scripts under ``gate-scripts/``: this holds the plumbing
each gate repeats, and ONE rule — :func:`ssh` opens a connection only for a
process the door started, and only to the host the door was opened for. That
rule lives here and not in a gate because it guards the gates themselves: a
gate that could reach a rig by hand would be a gate that reads a machine
nobody compared with its declaration. :func:`door_required` is the same rule
for a whole script: every gate and every driver calls it before anything
else, so a hand-set ``RUN_*`` environment admits nothing. Everything else
that decides whether a run may proceed belongs in a gate, where the door can
see it in :data:`~mcgyvr.serving.run.SEQUENCE`.

Nothing here runs at import. A product module imports this, and a module that
read the environment or touched a descriptor on import would make "import
gatelib" an action.
"""

from __future__ import annotations

import getpass
import os
import re
import secrets
import shlex
import socket
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

#: How a run is started. Named in every refusal, because the operator reading
#: one is the operator most inclined to work around it.
DOOR = "python -m mcgyvr.serving.run --host H --campaign C --step PATH --model M"

#: What an ancestor's command line carries when it is the door: the module
#: file by path (matched on its suffix, so a copy of the door in a test tree
#: is the door too) or the `-m` pair.
DOOR_FILE = "mcgyvr/serving/run.py"
DOOR_MODULE = "mcgyvr.serving.run"

#: ssh options that consume the next argument (OpenSSH's getopt string, the
#: letters followed by a colon). Anything else beginning with `-` is a flag.
SSH_TAKES_VALUE = frozenset("bcDeEFiIJlLmoOpPQRSwW")


def export(key: str, value: object) -> None:
    """Hand one named fact back to the door. Declared in SEQUENCE or refused.

    The door hands facts back on a pipe whose descriptor number it names in
    RUN_EXPORT_FD — not a hardcoded 3, because `pass_fds` keeps a descriptor
    at the number it already has, so a gate writing to a fixed 3 writes to
    whatever happened to be there. Read here and not at import: a module that
    read the environment on import could not be imported without a door.
    """
    raw = os.environ.get("RUN_EXPORT_FD")
    if not raw:
        refuse(
            f"{key} cannot be exported: RUN_EXPORT_FD is unset, so this script "
            "was started outside mcgyvr.serving.run, where no door reads what "
            "a gate learned and nothing is guarded"
        )
    # The descriptor was named and is not writable: that is a broken door,
    # not a gate run by hand, so an OSError here is not swallowed.
    os.write(int(raw), f"{key}={value}\n".encode())


def refuse(rule: str, status: int = 2) -> NoReturn:
    """Say which rule refused, then stop. Never returns.

    The message is the whole product of a refusal: an operator reads it at the
    moment they are most inclined to work around it, so it names what was
    checked and what to do, not merely that something failed.
    """
    sys.stderr.write(f"{Path(sys.argv[0]).name}: {rule}\n")
    raise SystemExit(status)


def need(key: str) -> str:
    """A variable the door promised. Absent means the gate ran out of order."""
    value = os.environ.get(key)
    if not value:
        refuse(
            f"{key} is not set. A gate reads the run from the environment the "
            "door exports; an empty one means this script was started outside "
            "mcgyvr.serving.run, where no gate has run and nothing is guarded"
        )
    return value


def root() -> Path:
    return Path(need("RUN_ROOT"))


def is_door(argv: list[str]) -> bool:
    """Whether one command line is the door's."""
    for index, arg in enumerate(argv):
        if arg.endswith(DOOR_FILE):
            return True
        if arg == "-m" and index + 1 < len(argv) and argv[index + 1] == DOOR_MODULE:
            return True
    return False


def under_door() -> bool:
    """Whether some ancestor of this process is ``mcgyvr.serving.run``.

    Read from ``/proc``, which a process cannot lie to: an environment
    variable saying "the door started me" is set by whoever wants it set,
    while a parent chain is what actually happened. Walked to pid 1, bounded
    so a corrupt reading cannot loop.

    THE ACCEPTED LIMIT, in one sentence: the proof is an ancestor's command
    line plus RUN_HOST, both of which an operator can forge with
    ``bash -c ... x/mcgyvr/serving/run.py``, so the seal is against every code
    path in this repository — none reaches a rig without the door — and not
    against an operator impersonating the door.
    """
    pid = os.getpid()
    for _ in range(128):
        try:
            record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            # `pid (comm) state ppid ...`, and comm may hold spaces or parens,
            # so the fields are taken after the LAST closing paren.
            ppid = int(record.rsplit(")", 1)[1].split()[1])
            if ppid <= 1:
                return False
            raw = Path(f"/proc/{ppid}/cmdline").read_bytes()
        except (OSError, ValueError, IndexError):
            return False
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        if is_door(argv):
            return True
        pid = ppid
    return False


def _require_door(what: str) -> None:
    """Refuse unless an ancestor is the door. The one message for that."""
    if not under_door():
        refuse(
            f"{what} refused: this process was not started by the door — it "
            "was started outside mcgyvr.serving.run, and nothing reaches a rig "
            "or reads a run outside it (a RUN_* variable set by hand does not "
            f"stand in for the door). Start the run as `{DOOR}` "
            "(okf/must-read/touching-rigs.md)"
        )


def door_required(what: str) -> None:
    """Refuse — exit 2, naming the door and ``what`` — unless this is a door run.

    A gate script's ``main()`` calls this FIRST, before any subprocess; a
    driver calls it at startup. Two things are required: an ancestor that is
    the door (:func:`under_door`, read from /proc), AND the door's own mark on
    the environment — ``RUN_EXPORT_FD`` for a gate, which the door sets per
    entry, or ``RUN_ID`` for a step or a driver, which gate 5 exported. The
    environment alone was never enough: every ``RUN_*`` can be typed into a
    shell, and a caller that guarded itself on those alone reached a real
    ``ssh srv1`` by hand, with no shim on PATH to stop it.
    """
    _require_door(what)
    if not (os.environ.get("RUN_EXPORT_FD") or os.environ.get("RUN_ID")):
        refuse(
            f"{what} refused: an ancestor is the door but neither RUN_EXPORT_FD "
            "nor RUN_ID is set, so no gate exported this run to it — it was "
            "not started by the door's sequence. Start the run as "
            f"`{DOOR}` (okf/must-read/touching-rigs.md)"
        )


def _admit(what: str, host: str | None) -> str:
    """The one rule: under the door, and to the host the door was opened for.

    Returns the door's host. ``host`` is None for a caller that has no host
    of its own to name (the docker shim, which takes the door's).
    """
    _require_door(what)
    expected = need("RUN_HOST")
    if host is not None and host != expected:
        refuse(
            f"{what} refused: the door was opened for {expected} and a run "
            f"reaches exactly the host it named, not {host}. Open a door for "
            f"{host} instead: `{DOOR}`"
        )
    return expected


def ssh(
    host: str,
    command: str,
    timeout: float = 120.0,
    *,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """How everything in this repository reaches a rig.

    The one other ssh spawn is the shims' own lease check
    (:func:`_direct_ssh`), which applies the same rule. Refuses — exit 2,
    naming the door — unless this process descends from
    ``mcgyvr.serving.run`` and ``host`` is the one it was opened for.
    ``BatchMode=yes`` so a host that wants a password fails in seconds instead
    of hanging on a prompt nobody is watching, and a timeout because a rig that
    hard-locks takes the ssh pipe with it — three of those on srv1 in one
    campaign, each ending mid-log-stream. ``input`` is piped to the remote
    command's stdin (how a reader is shipped without landing on the rig's disk).
    """
    _admit(f"ssh to {host}", host)
    return subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            command,
        ],
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def ssh_or_refuse(host: str, command: str, what: str, timeout: float = 120.0) -> str:
    """``ssh``, refusing on a non-zero exit. A rig that cannot answer is not read."""
    try:
        done = ssh(host, command, timeout=timeout)
    except subprocess.TimeoutExpired:
        refuse(
            f"{what}: ssh to {host} did not answer within {timeout:.0f}s "
            f"({shlex.quote(command)[:80]}). A rig that cannot be read is not "
            "compared, and nothing is measured on it"
        )
        raise
    if done.returncode != 0:
        refuse(
            f"{what}: ssh to {host} exited {done.returncode}: "
            f"{done.stderr.strip()[:400] or '(no stderr)'}"
        )
    return done.stdout


# --------------------------------------------------------------------------
# the envelope: what a declared artifact is, and the claim on a RUN_ID
# --------------------------------------------------------------------------


def artifact_escape(path: Path, envelope: Path) -> str | None:
    """Why ``path`` is not one regular file of ``envelope``, or None if it is.

    Gates 5, 7 and 8 ask this of every declared artifact before they read,
    stamp or parse it, because a step is operator code and the envelope is
    the one directory it may write: a step once planted ``ln -sf <other
    envelope>/sizing.tsv $RUN_OUT_DIR/probe.tsv`` after gate 5 and wrote
    through it, so committed evidence elsewhere was overwritten and gate 8
    parsed the victim as this run's green artifact. A symlink is therefore
    named with its target and where that lands; a file with a second name on
    disk (a hard link) is named with the count, because a write under one
    name lands under the other; anything but a regular file is named; and a
    path that resolves outside the resolved envelope is named with where it
    resolves. The envelope itself must not be a symlink — see
    :func:`envelope_escape`, which this checks first.

    A path that does not exist is NOT an escape: the caller says what an
    absent artifact means (gate 8: not green; gate 5: not yet written).
    """
    escape = envelope_escape(envelope)
    if escape is not None:
        return escape
    if path.is_symlink():
        target = os.readlink(path)
        try:
            lands = str(path.resolve(strict=True))
        except OSError:
            lands = "nowhere (the link dangles)"
        return f"{path} is a symlink to {target}, landing at {lands}"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return f"{path} is not a regular file"
    if info.st_nlink > 1:
        return (
            f"{path} has {info.st_nlink} names on disk (a hard link), so what is "
            "written under this name lands under another too"
        )
    real, home = path.resolve(strict=True), envelope.resolve(strict=True)
    if real.parent != home:
        return f"{path} resolves to {real}, outside the envelope {home}"
    return None


def envelope_escape(envelope: Path) -> str | None:
    """Why ``envelope`` is not a directory of its own, or None if it is."""
    if envelope.is_symlink():
        target = os.readlink(envelope)
        try:
            lands = str(envelope.resolve(strict=True))
        except OSError:
            lands = "nowhere (the link dangles)"
        return (
            f"the envelope {envelope} is a symlink to {target}, landing at "
            f"{lands}; the envelope is a directory the door made, never a link"
        )
    return None


def claim_path(out_dir: Path, run_id: str) -> Path:
    """Where a run's claim on its RUN_ID sits while the run is in progress."""
    return out_dir / f".{run_id}.running"


def claim(out_dir: Path, run_id: str) -> Path:
    """Claim ``run_id`` for this run, atomically, or refuse (exit 2).

    Two door invocations of one step on one day mint one RUN_ID, and before
    this both passed write-once because neither had written yet. The claim is
    ``O_CREAT | O_EXCL`` on one file in the envelope, so exactly one of two
    concurrent runs gets it; the door releases it (:func:`release`) on every
    exit path, including an interrupt. A claim that is still there names a
    run that is in progress, or one that died without the door — and the
    door cannot tell which, so the operator decides.
    """
    path = claim_path(out_dir, run_id)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        refuse(
            f"gate 5: a run with this RUN_ID ({run_id}) is in progress or died "
            f"without releasing it; wait, or remove {path} if you know it is "
            "dead. Two door invocations never share a run id: a same-day "
            "re-run takes --suffix"
        )
    os.write(fd, f"{os.getpid()}\n".encode())
    os.close(fd)
    return path


def release(out_dir: Path, run_id: str) -> None:
    """Release the claim :func:`claim` took. Absent is fine: nothing to release."""
    claim_path(out_dir, run_id).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# the rig lease: one run on a rig at a time, and live outranks dev
# --------------------------------------------------------------------------

#: Where a rig keeps the lease on itself. ON the rig, because the rig is the
#: contended resource: a laptop and srv1 both reach it, and a file on either
#: of them would be a lock only one of them could see.
LEASE_DIR = "~/.mcgyvr"
LEASE_FILE = f"{LEASE_DIR}/lease"
#: The profile that yields (owner's ruling R1, 2026-09-06: live outranks dev).
DEV = "dev"
#: What a lease value may be: one whitespace-free token that survives a
#: single-quoted shell line and a `k=v` stamp as-is. Matched whole.
LEASE_TOKEN = re.compile(r"[A-Za-z0-9._@:+/-]+")
#: The environment variables a run carries its own lease in and the lease it
#: displaced (gate 2 exports both), read by the shims, gate 5 and gate 7.
LEASE_VAR = "RUN_LEASE"
DISPLACED_VAR = "RUN_DISPLACED"
#: How every lease script reaches the rig: a POSIX shell is pinned, as the
#: snapshot pins one, so `set -C` and `>` mean what the lease needs them to
#: mean whatever the rig's login shell is. The script goes on stdin.
LEASE_SHELL = "bash -s -- lease"

#: How a lease script runs on the rig: ``(host, command, stdin) ->`` a
#: completed process. The gates hand in :func:`ssh`; a shim hands in the real
#: ssh directly, because the shim IS what ``ssh`` on PATH resolves to.
Transport = Callable[[str, str, "str | None"], "subprocess.CompletedProcess[str]"]


def _over_ssh(
    host: str, command: str, stdin: str | None
) -> subprocess.CompletedProcess[str]:
    return ssh(host, command, input=stdin)


def machine_id() -> str:
    """What tells this machine from another with the same hostname.

    systemd's machine id where there is one — two cloud images or containers
    are both `ubuntu` and a lease judged stale by hostname alone would let a
    dev run take a live run's rig — and the hostname where there is not.
    """
    try:
        raw = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
    except OSError:
        raw = ""
    return (
        raw[:12] if LEASE_TOKEN.fullmatch(raw or "-") and raw else socket.gethostname()
    )


@dataclass(frozen=True)
class Lease:
    """One run's hold on one rig, as the line at ``~/.mcgyvr/lease`` says it.

    ``lease_id`` is minted per run and is what makes a lease *this* run's:
    the file is compared by it before it is released or rewritten, so a run
    never removes a lease another run took from it. ``holder`` is
    ``user@host`` for a person; ``machine`` and ``pid`` — the door's pid on
    that machine — are the only way to tell a dead run's lease from a live
    one's, and only from the machine the pid is on. ``run_id`` is ``none``
    until gate 5 mints one. ``raw`` is the line as read off the rig, kept so a
    lease the door did not write can still be named and handed on whole.
    """

    lease_id: str
    profile: str
    holder: str
    machine: str
    pid: int
    started_at: str
    campaign: str
    step: str
    run_id: str = "none"
    raw: str = ""

    def line(self) -> str:
        pairs = (
            ("lease_id", self.lease_id),
            ("profile", self.profile),
            ("holder", self.holder),
            ("machine", self.machine),
            ("pid", str(self.pid)),
            ("started_at", self.started_at),
            ("campaign", self.campaign),
            ("step", self.step),
            ("run_id", self.run_id),
        )
        for key, value in pairs:
            if not LEASE_TOKEN.fullmatch(value):
                refuse(
                    f"the lease cannot be written: {key}={value!r} is not one "
                    "plain token, and a lease line is shipped to the rig inside "
                    "a quoted shell command"
                )
        return " ".join(f"{k}={v}" for k, v in pairs)

    @classmethod
    def parse(cls, text: str) -> Lease | None:
        """The lease a file's text describes, or ``None`` for an empty file.

        A line the door did not write — a field missing, a pid that is not a
        number — is still a lease: something holds the rig, and it is handed
        back with what could be read (and the raw line) so a refusal can
        name it and a live run can hand it on to gate 7 whole.
        """
        line = text.strip().splitlines()[0].strip() if text.strip() else ""
        if not line:
            return None
        fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
        try:
            pid = int(fields.get("pid", "0"))
        except ValueError:
            pid = 0
        return cls(
            lease_id=fields.get("lease_id", "?"),
            profile=fields.get("profile", "?"),
            holder=fields.get("holder", "?"),
            machine=fields.get("machine", "?"),
            pid=pid,
            started_at=fields.get("started_at", "?"),
            campaign=fields.get("campaign", "?"),
            step=fields.get("step", "?"),
            run_id=fields.get("run_id", "none"),
            raw=line,
        )

    def describe(self) -> str:
        return (
            f"{self.holder} (pid {self.pid} on {self.machine}, profile "
            f"{self.profile}, {self.campaign}/{self.step}, run {self.run_id}, "
            f"since {self.started_at})"
        )

    @property
    def has_id(self) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{16}", self.lease_id))

    def is_stale(self) -> bool:
        """Whether the holder is a door on THIS machine that is gone.

        Decidable only here: a pid on another machine cannot be asked. A
        lease from elsewhere is therefore never stale by this test, and is
        honoured (a dev run refuses, a live run displaces) — the operator on
        that machine is the one who can tell. A pid that is alive but is not
        the door — the number reused by something else since — is gone too.
        """
        if self.machine != machine_id() or self.pid <= 0:
            return False
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass  # alive, somebody else's; judged by its command line below
        try:
            raw = Path(f"/proc/{self.pid}/cmdline").read_bytes()
        except OSError:
            return False  # cannot tell: honoured
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        return not is_door(argv)


def whoami() -> str:
    """``user@host`` for this door, as a lease names its holder."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = f"uid{os.getuid()}"
    return f"{user}@{socket.gethostname()}"


def new_lease(profile: str, campaign: str, step: str, pid: int) -> Lease:
    return Lease(
        lease_id=secrets.token_hex(8),
        profile=profile,
        holder=whoami(),
        machine=machine_id(),
        pid=pid,
        started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        campaign=campaign,
        step=step,
    )


def _lease_script(
    via: Transport, host: str, script: str
) -> subprocess.CompletedProcess[str]:
    try:
        return via(host, LEASE_SHELL, script)
    except subprocess.TimeoutExpired:
        refuse(
            f"lease: {host} did not answer for its lease. A rig whose lease "
            "cannot be read is not entered"
        )


#: The scripts, on the rig's own bash. A written lease lands whole: staged
#: beside the file and moved over it, so a reader never sees a line half
#: written and a crash mid-write leaves the old lease, not an empty file.
_READ = f"cat {LEASE_FILE} 2>/dev/null || true\n"
_TAKE_FREE = "mkdir -p {dir} || exit 4\nset -C\nprintf '%s\\n' '{line}' > {file}\n"
_TAKE_OVER = (
    "mkdir -p {dir} || exit 4\nf={file}\n"
    "[ -z '{held}' ] || grep -qs -- 'lease_id={held} ' \"$f\" || exit 3\n"
    'printf \'%s\\n\' \'{line}\' > "$f.$$" && mv -f "$f.$$" "$f"\n'
)
_STAMP = (
    "f={file}\n"
    "grep -qs -- 'lease_id={held} ' \"$f\" || exit 3\n"
    'printf \'%s\\n\' \'{line}\' > "$f.$$" && mv -f "$f.$$" "$f"\n'
)
_RELEASE = 'f={file}\ngrep -qs -- \'lease_id={held} \' "$f" && rm -f "$f"\ntrue\n'


def lease_read(host: str, *, via: Transport | None = None) -> Lease | None:
    """The lease on ``host`` now, or ``None`` when the rig is free (or the
    file is empty — a write that never finished holds nothing)."""
    done = _lease_script(via or _over_ssh, host, _READ)
    if done.returncode != 0:
        refuse(
            f"lease: the lease on {host} could not be read: "
            f"{done.stderr.strip()[:300] or '(no stderr)'}. A rig whose lease "
            "cannot be read is not entered"
        )
    return Lease.parse(done.stdout)


def lease_take(host: str, lease: Lease, *, held: Lease | None) -> Lease | None:
    """Write ``lease`` on ``host``. Returns the lease that stands in the way, if any.

    ``held`` is what the caller read: ``None`` for a free rig, and the write
    is then ``set -C`` (noclobber) — the rig's shell refuses to overwrite, so
    of two runs arriving at once exactly one holds the rig, and the other is
    handed back what it found. A held lease is written over — what a live
    run does (R1), and what a stale one earns — but only if the rig still
    holds exactly that lease (compare-and-swap on its id): a holder that
    changed meanwhile comes back for the caller to judge again. An empty
    file, and a file with no id to compare, are taken outright: nothing a
    run can be told to wait for is in them.
    """
    if held is None:
        done = _lease_script(
            _over_ssh,
            host,
            _TAKE_FREE.format(dir=LEASE_DIR, file=LEASE_FILE, line=lease.line()),
        )
        if done.returncode == 0:
            return None
        now = lease_read(host)
        if now is not None and now.lease_id != lease.lease_id:
            return now
        if now is not None:
            return None  # written, and only the exit was lost
        held_id = ""  # exists and empty: a write that never finished
    else:
        held_id = held.lease_id if held.has_id else ""
    done = _lease_script(
        _over_ssh,
        host,
        _TAKE_OVER.format(
            dir=LEASE_DIR, file=LEASE_FILE, held=held_id, line=lease.line()
        ),
    )
    if done.returncode == 0:
        return None
    now = lease_read(host)
    if now is not None and now.lease_id == lease.lease_id:
        return None  # written, and only the exit was lost
    if done.returncode == 3 and now is not None:
        return now  # the holder changed under the read; judged again
    refuse(
        f"lease: the lease on {host} could not be written (exit "
        f"{done.returncode}): {done.stderr.strip()[:300] or '(no stderr)'}"
    )


def lease_stamp(host: str, lease: Lease, run_id: str) -> Lease:
    """Add the RUN_ID gate 5 minted to this run's lease on the rig.

    Rewritten only if the lease there is still this run's; if it is not, the
    run is refused here rather than allowed to start a step under a lease it
    no longer holds — named with what stands there now, or with the fact
    that nothing does.
    """
    stamped = replace(lease, run_id=run_id)
    done = _lease_script(
        _over_ssh,
        host,
        _STAMP.format(file=LEASE_FILE, held=lease.lease_id, line=stamped.line()),
    )
    if done.returncode == 0:
        return stamped
    now = lease_read(host)
    if now is not None and now.lease_id == lease.lease_id:
        return stamped  # written, and only the exit was lost
    refuse(
        f"gate 5: the lease on {host} is no longer this run's — "
        + (
            f"held by {now.describe()}: another run took the rig, and this "
            "one yields (owner's ruling R1, 2026-09-06)"
            if now is not None
            else "it is gone: removed by hand, or the rig's home was reset"
        )
        + ". Nothing is minted"
    )


def lease_release(host: str, lease_id: str, *, via: Transport | None = None) -> bool:
    """Remove the lease on ``host`` if it is still ``lease_id``'s.

    False when the rig could not be reached; the caller says so.
    """
    try:
        done = (via or _over_ssh)(
            host, LEASE_SHELL, _RELEASE.format(file=LEASE_FILE, held=lease_id)
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def lease_of_run() -> Lease | None:
    """The lease this process's run holds, from the environment gate 2 exported."""
    raw = os.environ.get(LEASE_VAR, "")
    return Lease.parse(raw) if raw else None


def displaced_by_run() -> Lease | None:
    """The lease this run displaced at gate 2, if any."""
    raw = os.environ.get(DISPLACED_VAR, "")
    return Lease.parse(raw) if raw else None


def yield_if_displaced(host: str, *, via: Transport, what: str) -> None:
    """Refuse — the run yields — when the rig's lease is no longer this run's.

    Called by the shims before they reach the rig, for the calls that spend
    it. ``via`` is the real ssh: the shim is what ``ssh`` on PATH resolves
    to, and a check that went through PATH would be checking itself. A rig
    that cannot be reached for its lease is not refused here — the call
    about to be made will fail on its own, and say so.
    """
    mine = lease_of_run()
    if mine is None:
        return
    try:
        done = via(host, LEASE_SHELL, _READ)
    except (subprocess.TimeoutExpired, OSError):
        return
    if done.returncode != 0:
        return
    held = Lease.parse(done.stdout)
    if held is not None and held.lease_id == mine.lease_id:
        return
    refuse(
        f"{what} refused: the lease on {host} is no longer this run's "
        f"({mine.lease_id}) — "
        + (f"held by {held.describe()}" if held is not None else "it is gone")
        + ". Another run took the rig; this one yields (owner's ruling R1, "
        "2026-09-06: live outranks dev, enforced by the machine), and nothing "
        "more is started on it"
    )


#: The docker verbs that spend a rig: anything that starts a process on it.
#: `ps`, `inspect`, `logs`, `rm`, `info`, and `compose down` read or clean and
#: are let through, so a displaced run can still tear down and gate 7 can
#: still look.
DOCKER_SPENDS = frozenset({"run", "create", "start", "restart", "exec"})
COMPOSE_SPENDS = frozenset({"up", "start", "run", "restart", "exec"})


def docker_spends(argv: list[str]) -> bool:
    """Whether a docker command line starts something on the rig.

    Read from the non-option words, so a global option's value (`--log-level
    info run`) cannot hide the verb and `container run` reads as `run`.
    """
    words = [arg for arg in argv if not arg.startswith("-")]
    for index, word in enumerate(words):
        if word in DOCKER_SPENDS:
            return True
        if word == "container" and index + 1 < len(words):
            return words[index + 1] in DOCKER_SPENDS
        if word == "compose":
            return any(later in COMPOSE_SPENDS for later in words[index + 1 :])
    return False


#: The same verbs in a docker line shipped over plain ssh (the drivers' way).
#: A launch that never says `docker` — a bare server, another engine, a
#: script piped to `bash -s` — is the stated limit: the seal is against every
#: code path in this repository, all of which launch through docker.
#: Read token by token within one shell command (`;`, `&&`, `|` end it), so
#: `x-run` in a container name is never the verb `run`.
SSH_SPENDS = re.compile(
    r"\bdocker(?:\s+(?![;&|])\S+)*?\s+"
    r"(?:(?:container\s+)?(?:run|create|start|restart|exec)"
    r"|compose(?:\s+(?![;&|])\S+)*?\s+(?:up|start|run|restart|exec))(?=\s|$)"
)


def ssh_spends(argv: list[str]) -> bool:
    return SSH_SPENDS.search(" ".join(argv)) is not None


def _direct_ssh(real: str) -> Transport:
    """The real ssh, for a shim's own lease check — admitted like any other.

    Under the door and to the door's host, or refused: this is the second
    ssh spawn in the repository beside :func:`ssh`, and it applies the same
    rule, so a caller that reached it without a door is told so.
    """

    def via(
        host: str, command: str, stdin: str | None
    ) -> subprocess.CompletedProcess[str]:
        _admit("the lease check", host)
        return subprocess.run(
            [real, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    return via


# --------------------------------------------------------------------------
# the shims under gate-scripts/bin/: what `ssh` and `docker` resolve to on
# the PATH the door exports, so a step reaches only the door's host
# --------------------------------------------------------------------------


def ssh_target(argv: list[str]) -> str | None:
    """The host an ssh command line names, or None if it names none.

    The first argument that is not an option, with the value-taking options
    skipped (attached, `-p22`, or detached, `-p 22`) and `--` ending option
    parsing. A leading `user@` is not part of the host.
    """
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            index += 1
            break
        if arg.startswith("-") and len(arg) > 1:
            if arg[1] in SSH_TAKES_VALUE and len(arg) == 2:
                index += 2  # `-o VALUE`
            else:
                index += 1  # `-oVALUE`, `-tt`, `-v`
            continue
        break
    if index >= len(argv):
        return None
    return argv[index].rpartition("@")[2]


#: ssh options that send the connection somewhere other than the host on the
#: line, or open a tunnel through it: a jump host, a stdio forward, another
#: config file, a control socket, a port forward, and the `-o` keys that do
#: the same. Compared case-insensitively, the way ssh reads them.
SSH_REDIRECT_FLAGS = frozenset("JWFSLRDG")
SSH_REDIRECT_KEYS = frozenset(
    k.lower()
    for k in (
        "ProxyCommand",
        "ProxyJump",
        "ProxyUseFdpass",
        "Hostname",
        "HostName",
        "HostKeyAlias",
        "LocalCommand",
        "PermitLocalCommand",
        "RemoteCommand",
        "ControlPath",
        "ControlMaster",
        "LocalForward",
        "RemoteForward",
        "DynamicForward",
        "Include",
        "Match",
        "Host",
    )
)


def ssh_redirects(argv: list[str]) -> list[str]:
    """The options before the host that would carry the connection elsewhere.

    ``ssh_target`` admits the positional host; ``-J srv2``, ``-W srv2:22``,
    ``-o Hostname=srv2`` and ``-o ProxyCommand=…`` all keep that host on the
    line and connect somewhere else. An adversarial pass found them; the shim
    refuses them by name. Options after the host are the remote command's.
    """
    found: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--" or not arg.startswith("-") or len(arg) == 1:
            break
        flag, attached = arg[1], arg[2:]
        value = (
            attached if attached else (argv[index + 1] if index + 1 < len(argv) else "")
        )
        if flag in SSH_REDIRECT_FLAGS:
            found.append(arg)
        elif (
            flag == "o" and value.partition("=")[0].strip().lower() in SSH_REDIRECT_KEYS
        ):
            found.append(arg if attached else f"{arg} {value}")
        index += 1 if attached or flag not in SSH_TAKES_VALUE else 2
    return found


def next_on_path(name: str, *, skip: Path) -> str | None:
    """The first executable ``name`` on PATH outside the directory ``skip``.

    The shims are ``ssh`` and ``docker`` themselves, so the real one is the
    next hit on PATH — never the shim's own directory, whatever PATH says.
    """
    own = skip.resolve()
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        directory = Path(entry or ".")
        try:
            if directory.resolve() == own:
                continue
        except OSError:
            continue
        candidate = directory / name
        # A PATH entry the caller cannot stat (another user's ~/.local/bin, a
        # dead mount) is not the real binary; it is skipped, not a crash --
        # the first door run on a rig died here at gate 2 on /root/.local/bin.
        try:
            found = candidate.is_file() and os.access(candidate, os.X_OK)
        except OSError:
            continue
        if found:
            return str(candidate)
    return None


def shim_ssh(argv: list[str], *, own: Path) -> NoReturn:
    """``bin/ssh``: admit the door's host, then become the real ssh."""
    host = ssh_target(argv)
    if host is None:
        refuse(
            f"ssh refused: `ssh {shlex.join(argv)}` names no host, and the "
            "door admits exactly the host it was opened for"
        )
    redirected = ssh_redirects(argv)
    if redirected:
        refuse(
            f"ssh refused: {shlex.join(redirected)} would carry the connection "
            f"somewhere other than {host}, and the door admits exactly the host "
            "it was opened for — no jump host, no forward, no other config, no "
            "control socket"
        )
    _admit(f"ssh to {host}", host)
    real = next_on_path("ssh", skip=own)
    if real is None:
        refuse("ssh refused: no ssh on PATH beyond the door's own shim")
    if ssh_spends(argv):
        yield_if_displaced(host, via=_direct_ssh(real), what="ssh")
    os.execv(real, [real, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *argv])


def docker_names_a_daemon(argv: list[str]) -> list[str]:
    """The GLOBAL docker options in ``argv`` that name a daemon or context.

    Only the tokens before the subcommand are docker's own; everything after
    ``run … IMAGE`` belongs to the container. The first door run on srv2 was
    refused because llama-server's ``--host 0.0.0.0`` was read as docker's.
    """
    named: list[str] = []
    for arg in argv:
        if not arg.startswith("-"):
            break  # the subcommand: what follows is its business
        if arg in ("-H", "--host", "--context", "-c") or arg.startswith(
            ("-H=", "--host=", "--context=", "-c=")
        ):
            named.append(arg)
    return named


def shim_docker(argv: list[str], *, own: Path) -> NoReturn:
    """``bin/docker``: admit, then become the real docker AT the door's host.

    ``-H ssh://<RUN_HOST>`` is prepended so every docker call a gate or a step
    makes reaches the rig's daemon and not the operator's — and the ssh that
    docker opens for it goes through ``bin/ssh``, which admits the same host.
    A caller naming a daemon of its own is refused: the door names it.
    """
    named = docker_names_a_daemon(argv)
    if named:
        refuse(
            f"docker refused: {shlex.join(named)} names a daemon, and under the "
            "door the daemon is the rig's — `docker` reaches ssh://RUN_HOST "
            "and nothing else"
        )
    host = _admit("docker", None)
    real = next_on_path("docker", skip=own)
    if real is None:
        refuse("docker refused: no docker on PATH beyond the door's own shim")
    if docker_spends(argv):
        real_ssh = next_on_path("ssh", skip=own)
        if real_ssh is not None:
            yield_if_displaced(host, via=_direct_ssh(real_ssh), what="docker")
    os.execv(real, [real, "-H", f"ssh://{host}", *argv])
