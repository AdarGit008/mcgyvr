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

import os
import shlex
import stat
import subprocess
import sys
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
    """The only way anything in this repository reaches a rig.

    Refuses — exit 2, naming the door — unless this process descends from
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
        if candidate.is_file() and os.access(candidate, os.X_OK):
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
    _admit(f"ssh to {host}", host)
    real = next_on_path("ssh", skip=own)
    if real is None:
        refuse("ssh refused: no ssh on PATH beyond the door's own shim")
    os.execv(real, [real, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *argv])


def shim_docker(argv: list[str], *, own: Path) -> NoReturn:
    """``bin/docker``: admit, then become the real docker AT the door's host.

    ``-H ssh://<RUN_HOST>`` is prepended so every docker call a gate or a step
    makes reaches the rig's daemon and not the operator's — and the ssh that
    docker opens for it goes through ``bin/ssh``, which admits the same host.
    A caller naming a daemon of its own is refused: the door names it.
    """
    named = [
        arg
        for arg in argv
        if arg in ("-H", "--host", "--context")
        or arg.startswith(("-H=", "--host=", "--context="))
    ]
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
    os.execv(real, [real, "-H", f"ssh://{host}", *argv])
