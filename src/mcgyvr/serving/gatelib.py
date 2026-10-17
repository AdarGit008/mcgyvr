#
""

from __future__ import annotations

import base64
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

#
#
DOOR = "python -m mcgyvr.serving.run serve|read|link --host H ..."

#
#
#
DOOR_FILE = "mcgyvr/serving/run.py"
DOOR_MODULE = "mcgyvr.serving.run"

#
#
#
#
NO_SLEEP_ROUTE = 3

#
#
SSH_TAKES_VALUE = frozenset("bcDeEFiIJlLmoOpPQRSwW")


def export(key: str, value: object) -> None:
    ""
    raw = os.environ.get("RUN_EXPORT_FD")
    if not raw:
        refuse(
            f"{key} cannot be exported: RUN_EXPORT_FD is unset, so this script "
            "was started outside mcgyvr.serving.run, where no door reads what "
            "a gate learned and nothing is guarded"
        )
    #
    #
    os.write(int(raw), f"{key}={value}\n".encode())


def refuse(rule: str, status: int = 2) -> NoReturn:
    ""
    sys.stderr.write(f"{Path(sys.argv[0]).name}: {rule}\n")
    raise SystemExit(status)


def need(key: str) -> str:
    ""
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


#
#
#
USER_MODE = "user"
#
DOOR_LOG = "door"


def step_name(step_file: Path) -> str:
    ""
    return re.sub(r"^\d+-", "", step_file.stem)


def run_id_of(run_date: str, host: str, step_file: Path, suffix: str) -> str:
    ""
    return f"{run_date}-{host}-{step_name(step_file)}" + (
        f"-{suffix}" if suffix else ""
    )


def envelope_of(run_date: str, run_id: str) -> Path:
    ""
    from mcgyvr.fleet.roots import data_home

    return data_home() / DOOR_LOG / run_date / run_id


def is_door(argv: list[str]) -> bool:
    ""
    for index, arg in enumerate(argv):
        if arg.endswith(DOOR_FILE):
            return True
        if arg == "-m" and index + 1 < len(argv) and argv[index + 1] == DOOR_MODULE:
            return True
    return False


def under_door() -> bool:
    ""
    pid = os.getpid()
    for _ in range(128):
        try:
            record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            #
            #
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
    ""
    if not under_door():
        refuse(
            f"{what} refused: this process was not started by the door — it "
            "was started outside mcgyvr.serving.run, and nothing reaches a rig "
            "or reads a run outside it (a RUN_* variable set by hand does not "
            f"stand in for the door). Start the run as `{DOOR}`"
        )


def door_required(what: str) -> None:
    ""
    _require_door(what)
    if not (os.environ.get("RUN_EXPORT_FD") or os.environ.get("RUN_ID")):
        refuse(
            f"{what} refused: an ancestor is the door but neither RUN_EXPORT_FD "
            "nor RUN_ID is set, so no gate exported this run to it — it was "
            f"not started by the door's sequence. Start the run as `{DOOR}`"
        )


def _admit(what: str, host: str | None) -> str:
    ""
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
    ""
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


#
#
#
#
_SCAN_READ_SUFFIX = " | base64 -d | python3 -I -B -"

#
_HEADER_READ_MIDDLE = " | base64 -d | python3 - "


def _header_read_blob() -> str:
    ""
    from mcgyvr.serving import ggufscan

    source = Path(ggufscan.__file__)
    return base64.b64encode(source.read_bytes()).decode("ascii")


def _scan_read_blob() -> str:
    ""
    from mcgyvr.serving import rigscan

    source = Path(rigscan.__file__)
    return base64.b64encode(source.read_bytes()).decode("ascii")


def _single_quote(token: str) -> str:
    ""
    if "'" in token:
        raise ValueError(
            "a read-only path or directory with an embedded single quote "
            "cannot be proven safe; refuse rather than ship it"
        )
    return f"'{token}'"


def scan_read_command() -> str:
    ""
    return f"echo {_scan_read_blob()}{_SCAN_READ_SUFFIX}"


def cards_read_command() -> str:
    ""
    return f"echo {_scan_read_blob()}{_SCAN_READ_SUFFIX} --cards"


def header_read_command(path: str) -> str:
    ""
    return f"echo {_header_read_blob()}{_HEADER_READ_MIDDLE}{_single_quote(path)}"


def _read_only_command(command: str) -> bool:
    ""
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
    ""
    if not _read_only_command(command):
        refuse(
            "ssh_read_only refused: the command is not a sanctioned read-only "
            "detection line (only the shipped reader, the *.gguf discovery and "
            "the shipped-reader header read are "
            f"admitted), not {shlex.quote(command)[:80]}"
        )
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


def ssh_or_refuse(host: str, command: str, what: str, timeout: float = 120.0) -> str:
    ""
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


#
#
#


def artifact_escape(path: Path, envelope: Path) -> str | None:
    ""
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
    ""
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
    ""
    return out_dir / f".{run_id}.running"


def claim(out_dir: Path, run_id: str) -> Path:
    ""
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
    ""
    claim_path(out_dir, run_id).unlink(missing_ok=True)


#
#
#

#
#
#
LEASE_DIR = "~/.mcgyvr"
LEASE_FILE = f"{LEASE_DIR}/lease"
#
#
LEASE_TOKEN = re.compile(r"[A-Za-z0-9._@:+/-]+")
#
#
LEASE_VAR = "RUN_LEASE"
#
#
#
LEASE_SHELL = "bash -s -- lease"

#
#
Transport = Callable[[str, str, "str | None"], "subprocess.CompletedProcess[str]"]


def _over_ssh(
    host: str, command: str, stdin: str | None
) -> subprocess.CompletedProcess[str]:
    return ssh(host, command, input=stdin)


def os_machine_id() -> str:
    ""
    from mcgyvr.serving import rigscan

    return rigscan.machine_id() or socket.gethostname()


def process_start(pid: int) -> str | None:
    ""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        start = stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None
    return start if start.isdigit() else None


@dataclass(frozen=True)
class Lease:
    ""

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
        ""
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
        ""
        if not self.has_id or self.machine != os_machine_id() or self.pid <= 0:
            return False
        try:
            os.kill(self.pid, 0)
        except (ProcessLookupError, OverflowError):
            return True  #
        except PermissionError:
            pass  #
        if self.pid_start == "none":
            return False
        now = process_start(self.pid)
        return now is not None and now != self.pid_start


def whoami() -> str:
    ""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = f"uid{os.getuid()}"
    return f"{user}@{socket.gethostname()}"


def new_lease(step: str, pid: int) -> Lease:
    ""
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
    ""
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
    via: Transport, host: str, script: str
) -> subprocess.CompletedProcess[str]:
    try:
        return via(host, LEASE_SHELL, script)
    except subprocess.TimeoutExpired:
        refuse(
            f"lease: {host} did not answer for its lease. A rig whose lease "
            "cannot be read is not entered"
        )


#
#
#
_READ = f"cat {LEASE_FILE} 2>/dev/null || true\n"
_TAKE_FREE = "mkdir -p {dir} || exit 4\nset -C\nprintf '%s\\n' '{line}' > {file}\n"
#
#
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


def lease_read(host: str, *, via: Transport | None = None) -> Lease | None:
    ""
    done = _lease_script(via or _over_ssh, host, _READ)
    if done.returncode != 0:
        refuse(
            f"lease: the lease on {host} could not be read: "
            f"{done.stderr.strip()[:300] or '(no stderr)'}. A rig whose lease "
            "cannot be read is not entered"
        )
    return Lease.parse(done.stdout)


def lease_take(host: str, lease: Lease, *, held: Lease | None) -> Lease | None:
    ""
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
            return None  #
        held_id = ""  #
    elif held.is_stale():
        held_id = held.lease_id
    else:
        refuse(f"lease: {held_by(host, held)}")
    done = _lease_script(
        _over_ssh,
        host,
        _TAKE_STALE.format(
            dir=LEASE_DIR, file=LEASE_FILE, held=held_id, line=lease.line()
        ),
    )
    if done.returncode == 0:
        return None
    now = lease_read(host)
    if now is not None and now.lease_id == lease.lease_id:
        return None  #
    if done.returncode == 3 and now is not None:
        return now  #
    refuse(
        f"lease: the lease on {host} could not be written (exit "
        f"{done.returncode}): {done.stderr.strip()[:300] or '(no stderr)'}"
    )


def lease_stamp(host: str, lease: Lease, run_id: str) -> Lease:
    ""
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
        return stamped  #
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
    ""
    try:
        done = (via or _over_ssh)(
            host, LEASE_SHELL, _RELEASE.format(file=LEASE_FILE, held=lease_id)
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def lease_of_run() -> Lease | None:
    ""
    raw = os.environ.get(LEASE_VAR, "")
    return Lease.parse(raw) if raw else None


#
#
#
#


def _ssh_options(argv: list[str]) -> tuple[list[tuple[str, str, bool]], int]:
    ""
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
    ""
    _, index = _ssh_options(argv)
    if index >= len(argv):
        return None
    return argv[index].rpartition("@")[2]


#
#
#
#
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
    ""
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
    ""
    own = skip.resolve()
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        directory = Path(entry or ".")
        try:
            if directory.resolve() == own:
                continue
        except OSError:
            continue
        candidate = directory / name
        #
        #
        #
        try:
            found = candidate.is_file() and os.access(candidate, os.X_OK)
        except OSError:
            continue
        if found:
            return str(candidate)
    return None


def shim_ssh(argv: list[str], *, own: Path) -> NoReturn:
    ""
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
    os.execv(real, [real, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *argv])


def docker_names_a_daemon(argv: list[str]) -> list[str]:
    ""
    named: list[str] = []
    for arg in argv:
        if not arg.startswith("-"):
            break  #
        if arg in ("-H", "--host", "--context", "-c") or arg.startswith(
            ("-H=", "--host=", "--context=", "-c=")
        ):
            named.append(arg)
    return named


def shim_docker(argv: list[str], *, own: Path) -> NoReturn:
    ""
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
    os.execv(real, [real, "-H", f"ssh://{host}", *argv])
