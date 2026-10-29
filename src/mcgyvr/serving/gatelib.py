#!/usr/bin/env python3
# What the door and its gate scripts share, and the shims a run's PATH answers with.
"""What the door and each gate script under it are written against.

The door (`mcgyvr.serving.run`) starts a gate script as a subprocess and hands it
the run as environment variables and one `RUN_EXPORT_FD` pipe, and the script
imports this module rather than spelling either. `need()` and `root()` read the
run back, `export()` answers on the pipe, `refuse()` ends the script with a rule
and a status, `ssh()` and `ssh_read_only()` are the only ways a run reaches a
rig, `envelope_of()` with the claim and escape helpers guards where a run's
artifacts may land, and the lease functions keep one live run on a rig at a time.

The same module is the code behind the `ssh` and `docker` shims the door puts
first on PATH: each reads the command line it was handed, admits only the host
the run was opened for, and executes the real tool.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import getpass
import hashlib
import hmac
import json
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

#: The door's command line as every refusal here spells it out for a person who
#: started a script by hand: the three verbs, and the host they all take.
DOOR = "python -m mcgyvr.serving.run serve|read|link --host H ..."

#: How a process is recognized as the door while its ancestors' command lines are
#: walked: the file the door is, and the module that `-m` names. Both are spelled
#: here so the rest of the tree does not spell the door's path again.
DOOR_FILE = "mcgyvr/serving/run.py"
DOOR_MODULE = "mcgyvr.serving.run"

#: The door's own `ssh` and `docker`, put first on a run's PATH (the shims), and
#: the Windows launchers beside them that a program looking a command up by
#: PATHEXT finds (`docker` looking up `ssh` for an ssh:// daemon).
SHIM_DIR = Path(__file__).resolve().parent / "gate-scripts" / "bin"
WINDOWS_LAUNCHER = ".cmd"
#: The interpreter the door runs on, which a Windows launcher and a shim that
#: cannot import mcgyvr hand themselves to.
PYTHON_VAR = "RUN_PYTHON"


def tool(name: str) -> list[str]:
    """The argv that runs the door's `name` (`ssh` or `docker`) under a run.

    POSIX: the bare name, which PATH resolves to the shim the door put first.
    Windows, where a program is found by its `.exe` and a shim is a Python
    file: the shim itself, run on this interpreter.
    """
    if sys.platform == "win32":
        return [sys.executable, str(SHIM_DIR / name)]
    return [name]


#: The rig names that are this machine, and the variable that says how the
#: door reaches it: `direct` (no ssh) or `ssh`.
LOCAL_RIGS = frozenset({"localhost", "127.0.0.1", "::1"})
LOCAL_TRANSPORT_ENV = "MCGYVR_LOCAL_TRANSPORT"
TRANSPORT_DIRECT = "direct"
TRANSPORT_SSH = "ssh"
#: Where an sshd listens when this machine runs one, and how long it is asked.
SSHD = ("127.0.0.1", 22)
SSHD_S = 1.0


def local_transport(host: str) -> bool:
    """Whether the door reaches `host` without ssh, by running its steps here.

    Only for this machine (`LOCAL_RIGS`): always on macOS and Windows, which
    run no sshd unless asked to; on Linux when nothing listens on port 22.
    `$MCGYVR_LOCAL_TRANSPORT` (`direct` or `ssh`) decides instead. Every other
    rig is reached over ssh.
    """
    if host not in LOCAL_RIGS:
        return False
    chosen = os.environ.get(LOCAL_TRANSPORT_ENV, "").strip().lower()
    if chosen in (TRANSPORT_DIRECT, TRANSPORT_SSH):
        return chosen == TRANSPORT_DIRECT
    if sys.platform in ("darwin", "win32"):
        return True
    return not _sshd_listens()


@functools.cache
def _sshd_listens() -> bool:
    try:
        with socket.create_connection(SSHD, timeout=SSHD_S):
            return True
    except OSError:
        return False


#: The status a `sleep` step answers with when one of its units has no sleep
#: route: nothing was asked of any unit and the card can only be stopped. It sits
#: here, rather than in the gate that returns it, so the caller that reads it as
#: proof a card is not asleep compares against one number.
NO_SLEEP_ROUTE = 3

#: The single-letter ssh flags that take the next argument as their value, which
#: `_ssh_options()` must know to tell an option's value from the host it ends at.
SSH_TAKES_VALUE = frozenset("bcDeEFiIJlLmoOpPQRSwW")


def export(key: str, value: object) -> None:
    """Answer on the door's pipe with one `KEY=VALUE` line from this gate.

    The door reads the pipe back and accepts only the keys the gate declares, so
    this is how a gate says what it settled and nothing else. With no
    `RUN_EXPORT_FD` in the environment there is no door reading what this script
    learned, which means it was started outside `mcgyvr.serving.run`.
    """
    raw = os.environ.get("RUN_EXPORT_FD")
    if not raw:
        refuse(
            f"{key} cannot be exported: RUN_EXPORT_FD is unset, so this script "
            "was started outside mcgyvr.serving.run, where no door reads what "
            "a gate learned and nothing is guarded"
        )
    # One line, written in a single call so the door never reads half of it: the
    # door refuses a line of any shape but `KEY=VALUE`.
    os.write(_export_fd(raw), f"{key}={value}\n".encode())


@functools.cache
def _export_fd(raw: str) -> int:
    """The descriptor the door's `RUN_EXPORT_FD` names in this process.

    POSIX: the number itself. Windows: the pipe's handle, opened as a
    descriptor once (`mcgyvr.hostos.inherited_fd`).
    """
    if sys.platform != "win32":
        return int(raw)
    from mcgyvr import hostos

    return hostos.inherited_fd(raw)


def refuse(rule: str, status: int = 2) -> NoReturn:
    """Say `rule` on stderr as one line and exit with `status`.

    The line is prefixed with this script's own name, so a refusal reads as a
    statement about the script that made it. The default status, 2, is the one
    the door takes as a gate's refusal.
    """
    sys.stderr.write(f"{Path(sys.argv[0]).name}: {rule}\n")
    raise SystemExit(status)


def need(key: str) -> str:
    """The variable `key` the door exported, refused when it is unset or empty.

    A gate reads its run from this environment and nowhere else, so an empty
    value means the script was started outside `mcgyvr.serving.run`, where no
    gate has run and nothing is guarded.
    """
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


#: The mode a person's run is recorded under: gate 5 writes `USER_MODE` into the
#: header of the envelope it mints, beside the command and the compose file the
#: person ran.
USER_MODE = "user"
#: The directory under the data home that holds the door's envelopes, by run date.
DOOR_LOG = "door"


def step_name(step_file: Path) -> str:
    """The step's name: the stem of `step_file` with its `NN-` prefix removed.

    `05-envelope.py` is the step `envelope`, which is what a run id and a lease
    both carry.
    """
    return re.sub(r"^\d+-", "", step_file.stem)


def run_id_of(run_date: str, host: str, step_file: Path, suffix: str) -> str:
    """The run id for a step: `<date>-<host>-<step>`, plus `-<suffix>` if given.

    `suffix` is what a same-day re-run adds, so two runs of one step on one host
    never share an id.
    """
    return f"{run_date}-{host}-{step_name(step_file)}" + (
        f"-{suffix}" if suffix else ""
    )


def envelope_of(run_date: str, run_id: str) -> Path:
    """The envelope a run keeps its artifacts in: `<data home>/door/<date>/<id>`.

    The data home is resolved in the call, so this module does not import the
    fleet's roots until an envelope is actually named.
    """
    from mcgyvr.fleet.roots import data_home

    return data_home() / DOOR_LOG / run_date / run_id


def is_door(argv: list[str]) -> bool:
    """Whether a command line is the door's own, by its script or by its module.

    A script is the door when its path ends in the door's file, and a `-m`
    invocation when the module it names is the door's.
    """
    for index, arg in enumerate(argv):
        if arg.endswith(DOOR_FILE):
            return True
        if arg == "-m" and index + 1 < len(argv) and argv[index + 1] == DOOR_MODULE:
            return True
    return False


#: Where `/proc` answers for this process, which makes the ancestry walk the proof.
PROC_SELF = Path("/proc/self/stat")
#: The variable the door hands its one-time proof down in, and the folder, under
#: the data folder, the proof's file waits in while the door lives.
PROOF_VAR = "RUN_DOOR_PROOF"
PROOF_DIR = Path("door") / ".proof"


def under_door() -> bool:
    """Whether this process descends from a live door.

    Linux (`/proc` answers): the ancestry walk, :func:`_door_ancestor`.
    Elsewhere: the door's one-time proof, :func:`_proof_holds`.

    Threat note. What is sealed is every code path in this repository: a gate,
    a step or a shim started by hand, or by code that was not started under the
    door, is refused even with every `RUN_*` variable set right. It is not a
    seal against an operator impersonating the door: the operator runs as the
    same user and can forge either proof, a command line plus `RUN_HOST` with
    ``bash -c ...``, or a running door's proof file read off disk. The proof
    keeps the property the walk has: it exists only while a door process lives
    (its file names the door's pid and start time and is removed when the door
    ends), it is handed down only through the environment the door builds, so
    only its descendants carry it, and it is a 256-bit secret that no file on
    disk spells (the file holds only its sha256), so a process that was not
    handed it cannot present it. Its file is the user's own (0600 in a 0700
    folder, where modes say so), opened without following a link.
    """
    if PROC_SELF.exists():
        return _door_ancestor()
    return _proof_holds()


def mint_proof() -> tuple[str, Path]:
    """The door's one-time proof for its descendants: the secret, and its file.

    The file is created exclusively in the user's proof folder, named by the
    secret's digest, and holds the digest with the door's pid and start time;
    the door removes it when it ends (:func:`drop_proof`).
    """
    from mcgyvr import hostos

    secret = secrets.token_hex(32)
    digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
    folder = _proof_dir()
    folder.mkdir(parents=True, exist_ok=True)
    hostos.chmod_private(folder, directory=True)
    path = folder / digest[:32]
    fd = hostos.open_nofollow(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        body = {
            "digest": digest,
            "pid": os.getpid(),
            "start": hostos.process_start_time(os.getpid()),
        }
        os.write(fd, json.dumps(body).encode("ascii"))
    finally:
        os.close(fd)
    return secret, path


def drop_proof(path: Path | None) -> None:
    """Remove the door's proof file; a door that ended proves nothing."""
    if path is not None:
        with contextlib.suppress(OSError):
            path.unlink()


def _proof_dir() -> Path:
    from mcgyvr.fleet.roots import data_home

    return data_home() / PROOF_DIR


def _proof_holds() -> bool:
    """Whether this process was handed a live door's proof (see :func:`under_door`)."""
    secret = os.environ.get(PROOF_VAR, "")
    if not re.fullmatch(r"[0-9a-f]{64}", secret):
        return False
    try:
        from mcgyvr import hostos

        digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
        path = _proof_dir() / digest[:32]
        found = os.lstat(path)
        if (
            not stat.S_ISREG(found.st_mode)
            or hostos.is_link(found)
            or not hostos.owned_by_current_user(found)
            or hostos.others_mode_bits(found)
        ):
            return False
        fd = hostos.open_nofollow(path, os.O_RDONLY)
        try:
            body = json.loads(os.read(fd, 4096).decode("ascii"))
        finally:
            os.close(fd)
        pid = body["pid"]
        return (
            hmac.compare_digest(str(body["digest"]), digest)
            and isinstance(pid, int)
            and pid > 0
            and body.get("start") is not None
            and hostos.process_start_time(pid) == body["start"]
        )
    except (ImportError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def _door_ancestor() -> bool:
    """Whether some ancestor of this process is the door, read off `/proc`.

    The walk reads each ancestor's command line from `/proc` — up to 128 of them
    — and answers False as soon as it reaches pid 1 or a process whose files
    cannot be read. A `RUN_*` variable set by hand does not stand in for this.
    """
    pid = os.getpid()
    for _ in range(128):
        try:
            record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            # The parent's pid follows the parenthesised command name, which may
            # hold spaces and brackets, so the record is split at its last `)`.
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
    """Refuse `what` unless this process descends from the door.

    Every reach for a rig and every read of a run comes through here, so a
    script started by hand is refused even when its `RUN_*` variables are set
    correctly: what is admitted is the door as a process, not the variables.
    """
    if not under_door():
        refuse(
            f"{what} refused: this process was not started by the door — it "
            "was started outside mcgyvr.serving.run, and nothing reaches a rig "
            "or reads a run outside it (a RUN_* variable set by hand does not "
            f"stand in for the door). Start the run as `{DOOR}`"
        )


def door_required(what: str) -> None:
    """Refuse `what` unless an ancestor is the door and it exported this run.

    `_require_door()` proves the ancestry; this also demands that the door's
    export pipe or a run id came down to this process, which is what tells a
    gate in the door's sequence from one merely started under it.
    """
    _require_door(what)
    if not (os.environ.get("RUN_EXPORT_FD") or os.environ.get("RUN_ID")):
        refuse(
            f"{what} refused: an ancestor is the door but neither RUN_EXPORT_FD "
            "nor RUN_ID is set, so no gate exported this run to it — it was "
            f"not started by the door's sequence. Start the run as `{DOOR}`"
        )


def _admit(what: str, host: str | None) -> str:
    """Refuse `what` unless the door was opened for `host`, and return that host.

    `host` None checks nothing beyond the door's ancestry, for a caller that has
    no host of its own to name. The returned `RUN_HOST` is the one host the door
    named, which is what a caller sends its traffic to.
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
    timeout: float | None = 120.0,
    *,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `command` on `host` over ssh, once the door has admitted the host.

    `BatchMode=yes` keeps the call from prompting for a password nobody is there
    to give, `ConnectTimeout=10` bounds the connect itself, and `timeout` bounds
    the whole call. `input` is fed to the remote command's stdin, and the exit
    status is left to the caller (`check=False`).
    """
    _admit(f"ssh to {host}", host)
    if local_transport(host):
        from mcgyvr.serving import localrig

        return localrig.run(command, input=input, timeout=timeout)
    return subprocess.run(
        [
            *tool("ssh"),
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


#: A read-only command ships the reader's own source, base64-encoded, and decodes
#: it into python3 on the rig, so the rig runs the file this checkout has and
#: nothing has to be installed there. `_SCAN_READ_SUFFIX` is that tail for the
#: scanner, run isolated (`-I`) and without writing bytecode (`-B`) on the rig.
_SCAN_READ_SUFFIX = " | base64 -d | python3 -I -B -"

#: The same tail for the header reader, which is followed by the path it reads.
_HEADER_READ_MIDDLE = " | base64 -d | python3 - "


def _header_read_blob() -> str:
    """The header reader's source from this checkout, base64-encoded to ship.

    `ggufscan` is imported in the call, so the bytes encoded are the file as it
    stands when the command is built.
    """
    from mcgyvr.serving import ggufscan

    source = Path(ggufscan.__file__)
    return base64.b64encode(source.read_bytes()).decode("ascii")


def _scan_read_blob() -> str:
    """The rig scanner's source from this checkout, base64-encoded to ship.

    `rigscan` is imported in the call, so the bytes encoded are the file as it
    stands when the command is built.
    """
    from mcgyvr.serving import rigscan

    source = Path(rigscan.__file__)
    return base64.b64encode(source.read_bytes()).decode("ascii")


def _single_quote(token: str) -> str:
    """Wrap a path or directory in single quotes, refusing one holding a quote.

    A token with an embedded single quote cannot be quoted safely for the shell
    line it is shipped in, so it is refused rather than escaped.
    """
    if "'" in token:
        raise ValueError(
            "a read-only path or directory with an embedded single quote "
            "cannot be proven safe; refuse rather than ship it"
        )
    return f"'{token}'"


def scan_read_command() -> str:
    """The read-only command that runs the shipped scanner on a rig."""
    return f"echo {_scan_read_blob()}{_SCAN_READ_SUFFIX}"


def cards_read_command() -> str:
    """The same shipped scanner, asked only for the rig's cards (`--cards`)."""
    return f"echo {_scan_read_blob()}{_SCAN_READ_SUFFIX} --cards"


def header_read_command(path: str) -> str:
    """The read-only command that reads the header of `path` on a rig.

    `path` is the file as the rig spells it, single-quoted by `_single_quote()`
    so it cannot break out of the shell line.
    """
    return f"echo {_header_read_blob()}{_HEADER_READ_MIDDLE}{_single_quote(path)}"


def _read_only_command(command: str) -> bool:
    """Whether `command` is one of the read-only lines this module builds.

    Three shapes pass: the shipped scanner's run, the `find` that discovers
    `*.gguf` files one level down a quoted directory, and the shipped header read
    with one quoted path. Each blob is compared against the one this checkout
    builds, so anything else — a hand-edited line included — is not traffic a
    read is allowed to make.
    """
    if command.startswith("echo ") and command.endswith(_SCAN_READ_SUFFIX):
        blob = command[len("echo ") : -len(_SCAN_READ_SUFFIX)]
        return blob == _scan_read_blob()

    prefix = "find "
    suffix = " -maxdepth 1 -name '*.gguf' -print"
    if command.startswith(prefix) and command.endswith(suffix):
        directory = command[len(prefix) : -len(suffix)]
        return (
            len(directory) >= 2
            and directory[0] == "'"
            and directory[-1] == "'"
            and "'" not in directory[1:-1]
            and bool(directory[1:-1])
        )

    if not command.startswith("echo ") or _HEADER_READ_MIDDLE not in command:
        return False
    blob, _sep, tail = command[len("echo ") :].partition(_HEADER_READ_MIDDLE)
    if len(tail) < 2 or tail[0] != "'" or tail[-1] != "'":
        return False
    if "'" in tail[1:-1] or not tail[1:-1]:
        return False
    return blob == _header_read_blob()


def ssh_read_only(
    host: str,
    command: str,
    timeout: float | None = 120.0,
) -> subprocess.CompletedProcess[str]:
    """Run one sanctioned read-only command on `host`, or refuse the command.

    What is admitted is the command — the three shapes `_read_only_command()`
    recognizes — so nothing but a read reaches a rig down this channel. The ssh
    options are those of `ssh()`, and the exit status is left to the caller.
    """
    if not _read_only_command(command):
        refuse(
            "ssh_read_only refused: the command is not a sanctioned read-only "
            "detection line (only the shipped reader, the *.gguf discovery and "
            "the shipped-reader header read are "
            f"admitted), not {shlex.quote(command)[:80]}"
        )
    if local_transport(host):
        from mcgyvr.serving import localrig

        return localrig.run(command, input=None, timeout=timeout)
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
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# Where a run's artifacts may land: inside the envelope. These two checks say why
# a path is not — the envelope is a link, or the artifact is a link, a hard link,
# not a regular file, or resolves elsewhere.


def artifact_escape(path: Path, envelope: Path) -> str | None:
    """Why `path` cannot be trusted as an artifact name in `envelope`, or None.

    None means the path is absent, or a regular file of one name whose real
    parent is the envelope's real path. Anything else is returned as the reason:
    a symlink, with the target and where it lands; a non-regular file; a hard
    link, whose writes would land under another name too; or a path that
    resolves outside the envelope. The envelope is checked first, because a link
    standing in for it makes every name under it suspect.
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
    """Why `envelope` is no fit directory for a run's artifacts, or None.

    The envelope is a directory the door makes, never a link; a link is reported
    with its target and where it lands.
    """
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
    """Where the claim file for `run_id` sits in `out_dir`: `.<run id>.running`."""
    return out_dir / f".{run_id}.running"


def claim(out_dir: Path, run_id: str) -> Path:
    """Claim `run_id` in `out_dir` by creating its claim file, or refuse.

    The file is created exclusively and holds this process's pid, so a second
    invocation that finds one refuses rather than share the id: two door
    invocations never share a run id, and a same-day re-run takes `--suffix`.
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
    """Drop the claim on `run_id`, if one is still there."""
    claim_path(out_dir, run_id).unlink(missing_ok=True)


# The lease: the one file on a rig that says which run is on it, and what keeps
# two live runs off one rig. The holder is named by pid and that process's start
# time, so a recycled pid is not mistaken for the run that took the lease.

#: Where the lease lives on the rig, spelled for the shell that reads and writes
#: it: a directory the lease scripts make when it is missing, and the file inside
#: it.
LEASE_DIR = "~/.mcgyvr"
LEASE_FILE = f"{LEASE_DIR}/lease"
#: What one field of a lease line may hold: one plain token, since a lease line is
#: shipped to the rig inside a quoted shell command.
LEASE_TOKEN = re.compile(r"[A-Za-z0-9._@:+/-]+")
#: The variable a run's lease is handed down to it in, so a step releases the rig
#: from what the door exported instead of reading the lease back off the rig.
LEASE_VAR = "RUN_LEASE"
#: How every lease operation reaches the rig: bash reads the script from stdin and
#: `lease` becomes argv[0], so a process listing on the rig says what the shell is
#: for.
LEASE_SHELL = "bash -s -- lease"

#: What a lease operation is sent through in place of ssh: the host and the script
#: for its stdin, answering with the finished call.
Transport = Callable[[str, str, "str | None"], "subprocess.CompletedProcess[str]"]


def _over_ssh(
    host: str, command: str, stdin: str | None
) -> subprocess.CompletedProcess[str]:
    return ssh(host, command, input=stdin)


def os_machine_id() -> str:
    """This machine's id, from the shipped reader, else its hostname.

    The lease records it for the machine its holder runs on, and `is_stale()`
    compares against it to tell a lease taken here from one taken elsewhere.
    """
    from mcgyvr.serving import rigscan

    return rigscan.machine_id() or socket.gethostname()


def process_start(pid: int) -> str | None:
    """When `pid` started (`mcgyvr.hostos.process_start_time`; on Linux field 22
    of `/proc/<pid>/stat`), or None.

    It is ever only compared with the same field read later, so a pid recycled
    by a new process is not mistaken for the one that took a lease. None means
    the field could not be read, or was not a number.
    """
    from mcgyvr import hostos

    return hostos.process_start_time(pid)


@dataclass(frozen=True)
class Lease:
    """One rig's lease: who holds the rig, from where, and since when.

    A lease is one line of `key=value` fields on the rig, which `line()` builds
    and `parse()` reads back, and every field is one token because that line is
    shipped inside a quoted shell command. `lease_id` names this taking of the
    rig, so a hold can be told from any other; `pid` and `pid_start` identify the
    holding process on `machine`; `step` says what the run is doing; `run_id` is
    `none` until the run has one; and `raw` keeps the line as it was read.
    """

    lease_id: str
    holder: str
    machine: str
    pid: int
    started_at: str
    step: str
    run_id: str = "none"
    pid_start: str = "none"
    raw: str = ""

    def line(self) -> str:
        pairs = (
            ("lease_id", self.lease_id),
            ("holder", self.holder),
            ("machine", self.machine),
            ("pid", str(self.pid)),
            ("pid_start", self.pid_start),
            ("started_at", self.started_at),
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
        """The lease on the first line of `text`, or None when there is none.

        Fields the line does not carry take placeholder values — `?`, `0`,
        `none` — so a lease read off a rig is never mistaken for a well-formed
        one: an id that is not 16 hex characters fails `has_id`. The line itself
        is kept in `raw`.
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
            holder=fields.get("holder", "?"),
            machine=fields.get("machine", "?"),
            pid=pid,
            started_at=fields.get("started_at", "?"),
            step=fields.get("step", "?"),
            run_id=fields.get("run_id", "none"),
            pid_start=fields.get("pid_start", "none"),
            raw=line,
        )

    def describe(self) -> str:
        return (
            f"{self.holder} (pid {self.pid} on {self.machine}, "
            f"step {self.step}, run {self.run_id}, "
            f"since {self.started_at})"
        )

    @property
    def has_id(self) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{16}", self.lease_id))

    def is_stale(self) -> bool:
        """Whether the process that took this lease is gone from this machine.

        Only a lease with a well-formed id, taken on this machine, for a positive
        pid can be stale; anything else answers False, because a lease taken
        elsewhere cannot be checked from here. The pid is probed with signal 0:
        no such process is a stale lease, a process this user may not signal is
        taken as alive, and — when the lease recorded a start time — a pid whose
        start time has changed is a recycled pid, so the lease is stale too.
        """
        if not self.has_id or self.machine != os_machine_id() or self.pid <= 0:
            return False
        from mcgyvr import hostos

        try:
            if not hostos.pid_alive(self.pid):
                return True  # no such process: the holder is gone
        except OverflowError:
            return True
        if self.pid_start == "none":
            return False
        now = process_start(self.pid)
        return now is not None and now != self.pid_start


def whoami() -> str:
    """`user@hostname` for the person running this, as a lease records them.

    A user that cannot be read falls back to the numeric uid.
    """
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = f"uid{os.getuid()}"
    return f"{user}@{socket.gethostname()}"


def new_lease(step: str, pid: int) -> Lease:
    """Mint a lease for `step` held by `pid` on this machine, with no run id.

    `lease_id` is 16 hex characters from `secrets`, `pid_start` is the pid's
    start time, and `started_at` is UTC as `%Y-%m-%dT%H:%M:%SZ`. The run id is
    put on by `lease_stamp()` once the run has one.
    """
    return Lease(
        lease_id=secrets.token_hex(8),
        holder=whoami(),
        machine=os_machine_id(),
        pid=pid,
        pid_start=process_start(pid) or "none",
        started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        step=step,
    )


def held_by(host: str, held: Lease) -> str:
    """The refusal a run gets while another live lease holds `host`.

    The sentence names the holder, its run, pid and start time, and what can be
    done about it — including that a lease left by a run that died on another
    machine is removed by hand.
    """
    who = f" of {held.holder}" if held.holder != "?" else ""
    run = (
        f"run {held.run_id}{who}"
        if held.run_id != "none"
        else f"a {held.step} run{who} that has no run id yet"
    )
    return (
        f"{host} is held by {run} (pid {held.pid}, since {held.started_at}), "
        "and no run takes a rig another live run holds. Wait for that run to "
        "end, or end it, then run this again; a run that died on another "
        f"machine leaves its lease to be removed by hand ({LEASE_FILE} on {host})"
    )


def _lease_script(
    via: Transport | None, host: str, op: str, **fields: str
) -> subprocess.CompletedProcess[str]:
    try:
        return _lease_op(host, op, via=via, **fields)
    except subprocess.TimeoutExpired:
        refuse(
            f"lease: {host} did not answer for its lease. A rig whose lease "
            "cannot be read is not entered"
        )


#: The lease scripts, run on the rig as `bash -s -- lease` with their fields
#: filled in. Each answers with its status: 0 the lease now reads as this run
#: wrote it, 3 the lease is not the one expected, 4 no lease directory.
_READ = f"cat {LEASE_FILE} 2>/dev/null || true\n"
_TAKE_FREE = "mkdir -p {dir} || exit 4\nset -C\nprintf '%s\\n' '{line}' > {file}\n"
#: Replacing a lease is the same write behind a check: it only goes through while
#: the file still holds the lease the caller was told about, or holds nothing.
_TAKE_STALE = (
    "mkdir -p {dir} || exit 4\nf={file}\n"
    "if [ -z '{held}' ]; then grep -qs -- '[^[:space:]]' \"$f\" && exit 3; "
    "else grep -qs -- 'lease_id={held} ' \"$f\" || exit 3; fi\n"
    'printf \'%s\\n\' \'{line}\' > "$f.$$" && mv -f "$f.$$" "$f"\n'
)
_STAMP = (
    "f={file}\n"
    "grep -qs -- 'lease_id={held} ' \"$f\" || exit 3\n"
    'printf \'%s\\n\' \'{line}\' > "$f.$$" && mv -f "$f.$$" "$f"\n'
)
_RELEASE = 'f={file}\ngrep -qs -- \'lease_id={held} \' "$f" && rm -f "$f"\ntrue\n'
#: Each lease operation by name, as the script the rig's shell runs.
_LEASE_SCRIPTS = {
    "read": _READ,
    "take_free": _TAKE_FREE,
    "take_stale": _TAKE_STALE,
    "stamp": _STAMP,
    "release": _RELEASE,
}


def _lease_op(
    host: str, op: str, *, via: Transport | None = None, **fields: str
) -> subprocess.CompletedProcess[str]:
    """Run the lease operation `op` on `host`, answering as its shell script does.

    Over ssh (or `via`) it is the script; on a rig the door reaches through its
    local transport it is :func:`_local_lease`, the same operation on the same
    file in Python, so no shell is needed there.
    """
    if via is None and local_transport(host):
        return _local_lease(op, **fields)
    script = _LEASE_SCRIPTS[op].format(dir=LEASE_DIR, file=LEASE_FILE, **fields)
    return (via or _over_ssh)(host, LEASE_SHELL, script)


def _local_lease(op: str, **fields: str) -> subprocess.CompletedProcess[str]:
    """The lease scripts' operation `op` on this machine's lease file.

    Statuses as the scripts give them: 0 done, 1 a free take found a lease
    there, 3 the lease is not the one expected, 4 no lease folder. Each
    operation holds `lease.lock` beside the file, so two on this machine do not
    interleave. Every write goes through a temporary file renamed over the
    lease, as the scripts' `mv -f` does; a free take creates it exclusively, as
    `set -C` does.
    """
    from mcgyvr import hostos

    folder = Path.home() / ".mcgyvr"
    lease = folder / "lease"

    def answer(code: int, out: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["lease", op], code, out, "")

    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return answer(4)
    fd = hostos.open_nofollow(folder / "lease.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        hostos.lock(fd)
        try:
            now = lease.read_text(encoding="utf-8")
        except FileNotFoundError:
            now = ""
        held = f"lease_id={fields.get('held', '')} "
        if op == "read":
            return answer(0, now)
        if op == "release":
            if held in now:
                lease.unlink(missing_ok=True)
            return answer(0)
        line = fields["line"] + "\n"
        if op == "take_free":
            try:
                out = hostos.open_nofollow(
                    lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                )
            except FileExistsError:
                return answer(1)
            with os.fdopen(out, "w", encoding="utf-8") as handle:
                handle.write(line)
            return answer(0)
        if op == "take_stale" and not fields.get("held"):
            if now.strip():
                return answer(3)
        elif held not in now:
            return answer(3)
        part = folder / f"lease.{os.getpid()}"
        part.write_text(line, encoding="utf-8")
        os.replace(part, lease)
        return answer(0)
    finally:
        hostos.unlock(fd)
        os.close(fd)


def lease_read(host: str, *, via: Transport | None = None) -> Lease | None:
    """The lease `host` holds right now, or None when it holds none.

    A lease that cannot be read at all is a refusal: a rig whose lease cannot be
    read is not entered. `via` sends the script by something other than ssh.
    """
    done = _lease_script(via, host, "read")
    if done.returncode != 0:
        refuse(
            f"lease: the lease on {host} could not be read: "
            f"{done.stderr.strip()[:300] or '(no stderr)'}. A rig whose lease "
            "cannot be read is not entered"
        )
    return Lease.parse(done.stdout)


def lease_take(host: str, lease: Lease, *, held: Lease | None) -> Lease | None:
    """Take `host`'s lease for `lease`, and say what got in the way.

    None means the lease on the rig now reads as this run's. A `Lease` is
    another run's, come back with the answer for the caller to report. With
    `held` None only a rig carrying no lease is taken, so a lease that appeared
    meanwhile is not overwritten; with `held` a lease this machine has found
    stale, only a file still holding that same lease is replaced. A lease a live
    run holds is a refusal.
    """
    if held is None:
        done = _lease_script(None, host, "take_free", line=lease.line())
        if done.returncode == 0:
            return None
        now = lease_read(host)
        if now is not None and now.lease_id != lease.lease_id:
            return now
        if now is not None:
            return None  # the write landed: the lease already carries our id
        held_id = ""  # nothing to match: only a file with nothing in it is replaced
    elif held.is_stale():
        held_id = held.lease_id
    else:
        refuse(f"lease: {held_by(host, held)}")
    done = _lease_script(None, host, "take_stale", held=held_id, line=lease.line())
    if done.returncode == 0:
        return None
    now = lease_read(host)
    if now is not None and now.lease_id == lease.lease_id:
        return None  # the write landed after all: the lease carries our id
    if done.returncode == 3 and now is not None:
        return now  # another run took the lease between the check and the write
    refuse(
        f"lease: the lease on {host} could not be written (exit "
        f"{done.returncode}): {done.stderr.strip()[:300] or '(no stderr)'}"
    )


def lease_stamp(host: str, lease: Lease, run_id: str) -> Lease:
    """Put `run_id` on this run's lease on `host`, and return the lease written.

    The write only goes through while the file still holds this lease id, so a
    lease removed by hand and taken by another run is caught and is a refusal:
    nothing is minted on a rig this run no longer holds.
    """
    stamped = replace(lease, run_id=run_id)
    done = _lease_script(None, host, "stamp", held=lease.lease_id, line=stamped.line())
    if done.returncode == 0:
        return stamped
    now = lease_read(host)
    if now is not None and now.lease_id == lease.lease_id:
        return stamped  # the stamp landed: the lease carries our id and the run's
    refuse(
        f"gate 5: the lease on {host} is no longer this run's — "
        + (
            f"held by {now.describe()}: it was removed by hand and another run "
            "took the free rig"
            if now is not None
            else "it is gone: removed by hand, or the rig's home was reset"
        )
        + ". Nothing is minted"
    )


def lease_release(host: str, lease_id: str, *, via: Transport | None = None) -> bool:
    """Remove this run's lease from `host`, and say whether it is gone.

    The script removes the file only while it still holds `lease_id`, so a lease
    another run has taken since is left alone. False means the release could not
    be confirmed — a shell that timed out or exited non-zero.
    """
    try:
        done = _lease_op(host, "release", via=via, held=lease_id)
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def lease_of_run() -> Lease | None:
    """The lease the door handed this run in `LEASE_VAR`, or None without one."""
    raw = os.environ.get(LEASE_VAR, "")
    return Lease.parse(raw) if raw else None


# Reading the ssh command line a shim was handed: which options it carries, which
# of them take a value, and where the host and the remote command begin. A shim
# cannot call ssh's own parser, and it has to be sure it read what ssh will read,
# so the walk here is the left-to-right one ssh itself makes.


def _ssh_options(argv: list[str]) -> tuple[list[tuple[str, str, bool]], int]:
    """The options in an ssh argv, and the index where the host begins.

    Each option is `(flag, value, attached)`: the single letter, the value it
    took — the rest of the argument, the next argument, or `""` — and whether
    that value came attached to its flag. The walk stops at `--`, at the first
    argument that is no option, or when the arguments run out.
    """
    options: list[tuple[str, str, bool]] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            index += 1
            break
        if not arg.startswith("-") or len(arg) == 1:
            break
        index += 1
        for pos in range(1, len(arg)):
            flag = arg[pos]
            if flag not in SSH_TAKES_VALUE:
                options.append((flag, "", False))
                continue
            attached = arg[pos + 1 :]
            if attached:
                options.append((flag, attached, True))
            else:
                value = argv[index] if index < len(argv) else ""
                options.append((flag, value, False))
                index += 1
            break
    return options, index


def ssh_target(argv: list[str]) -> str | None:
    """The host an ssh argv ends at, with any `user@` stripped, or None.

    None means the command line names no host at all.
    """
    _, index = _ssh_options(argv)
    if index >= len(argv):
        return None
    return argv[index].rpartition("@")[2]


#: What would carry an ssh connection somewhere other than the host on the command
#: line: the flags themselves (`-J`, `-W`, `-F`, `-S`, ...), and the `-o` keys that
#: name a proxy, a jump, another host name, another config file, a control socket
#: or a forward. A shim refuses a command line carrying any of them.
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
    """Every option in an ssh argv that would redirect the connection, as text.

    Each is spelled the way it was given — `-Jhost`, `-J host`, `-oKey=Value` —
    so a refusal can quote what it found. An empty list means the argv reaches
    only the host it names.
    """
    found: list[str] = []
    for flag, value, attached in _ssh_options(argv)[0]:
        if flag in SSH_REDIRECT_FLAGS:
            found.append(f"-{flag}{value}" if attached else f"-{flag}")
        elif (
            flag == "o" and value.partition("=")[0].strip().lower() in SSH_REDIRECT_KEYS
        ):
            found.append(f"-o{value}" if attached else f"-o {value}")
    return found


def next_on_path(name: str, *, skip: Path) -> str | None:
    """The first `name` on PATH outside the `skip` directory, or None.

    This is how a shim finds the real tool: its own directory is skipped, so a
    shim never executes itself. A candidate has to be a file this process may
    execute, and a directory that cannot be resolved is passed over.
    """
    own = skip.resolve()
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        directory = Path(entry or ".")
        try:
            if directory.resolve() == own:
                continue
        except OSError:
            continue
        candidate = directory / _program_name(name)
        # `is_file()` and `access()` are asked inside the guard: an entry that
        # vanished or cannot be stat'ed is passed over, rather than ending the
        # search for the real tool.
        try:
            found = candidate.is_file() and os.access(candidate, os.X_OK)
        except OSError:
            continue
        if found:
            return str(candidate)
    return None


def _program_name(name: str) -> str:
    """`name` as a program file is named here (`ssh.exe` on Windows).

    `mcgyvr.hostos.exe`'s rule, spelled here because a shim may load this
    module where mcgyvr itself cannot be imported.
    """
    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


def become(real: str, argv: list[str]) -> NoReturn:
    """Be the program `real` with `argv`: an exec on POSIX, a child on Windows.

    Windows has no exec that keeps the process: `os.execv` starts a new one and
    ends this one at once, so whoever waits on the shim would see it end before
    the tool did. There the tool is run and waited for, and its status is this
    shim's.
    """
    if sys.platform == "win32":
        raise SystemExit(subprocess.run([real, *argv[1:]], check=False).returncode)
    os.execv(real, argv)


def shim_ssh(argv: list[str], *, own: Path) -> NoReturn:
    """Become ssh for a command line that reaches only the door's host.

    The host is read off the argv and admitted against `RUN_HOST`, and any option
    that would redirect the connection — a jump host, a forward, another config,
    a control socket — is refused. The real ssh is then found on PATH past the
    shim and executed with `BatchMode=yes` and `ConnectTimeout=10` in front of the
    caller's arguments. This function does not return.
    """
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
    become(real, [real, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *argv])


def docker_names_a_daemon(argv: list[str]) -> list[str]:
    """The leading docker options that name a daemon or a context of their own.

    Only the options before the subcommand are read — the walk stops at the first
    argument that is no option — and `-H`, `--host`, `--context` and `-c` are
    taken, attached or apart, since any of them points the client at a daemon
    other than the one the door sends it to.
    """
    named: list[str] = []
    for arg in argv:
        if not arg.startswith("-"):
            break  # the subcommand: what follows is its business, not a daemon
        if arg in ("-H", "--host", "--context", "-c") or arg.startswith(
            ("-H=", "--host=", "--context=", "-c=")
        ):
            named.append(arg)
    return named


def shim_docker(argv: list[str], *, own: Path) -> NoReturn:
    """Become docker pointed at the rig the door was opened for.

    A command line that names a daemon of its own is refused, so the client
    cannot be pointed anywhere but `ssh://RUN_HOST`. The real docker is then
    found on PATH past the shim and executed with `-H ssh://<RUN_HOST>` in front
    of the caller's arguments, or as it is when the rig is this machine reached
    through the local transport. This function does not return.
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
    if local_transport(host):
        # The rig is this machine, reached without ssh: its daemon is the one
        # the client already talks to, and no other is named.
        become(real, [real, *argv])
    become(real, [real, "-H", f"ssh://{host}", *argv])
