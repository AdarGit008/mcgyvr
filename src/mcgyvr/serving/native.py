"""Run a llama.cpp unit natively: the pinned build, kept up by mcgyvr, no container.

A launch spec whose services carry ``x-mcgyvr-launcher: native`` (``emit``
writes it for a unit with ``launcher: native``) is started here instead of by
``docker compose``. Each unit gets a supervisor of its own,
``python -m mcgyvr.serving.native supervise <spec>``, started detached so it
outlives the step that started it (:func:`mcgyvr.hostos.popen_detached_kwargs`).
The supervisor:

- holds ``<unit>.lock`` under the data folder's ``native/`` for as long as it
  lives, which is how anything else asks whether the unit is supervised (a
  lock dies with its holder, a pid file does not);
- runs the program of the pinned build (:mod:`mcgyvr.serving.llamacpp`), fetched
  and verified on first use (:mod:`mcgyvr.serving.release`) under
  ``$MCGYVR_HOME/bin/llama.cpp/<tag>/<build>/``, with the spec's argv and
  environment, its output appended to ``logs/<unit>.log`` in the data folder;
- keeps it in its own process group on POSIX, and on Windows in a Job Object
  that ends it when the supervisor ends however it ends
  (:func:`mcgyvr.hostos.kill_on_close_job`);
- writes ``<unit>.json``: the supervisor's and the server's pid, each with its
  start time and program, the port, the restarts and the state;
- restarts a server that exits on its own, as docker's ``unless-stopped``
  does, after a pause that doubles from ``backoff_s`` up to ``backoff_max_s``;
  a server that stays up ``reset_after_s`` starts the count again, and one
  that exits ``max_restarts`` times running is given up on;
- reads the server's Metal start-up log for ``recommendedMaxWorkingSetSize``,
  which llama.cpp prints as
  ``"%s: recommendedMaxWorkingSetSize  = %8.2f MB\\n"`` of
  ``max_working_set_size / 1e6``
  (https://github.com/ggml-org/llama.cpp/blob/b11960/ggml/src/ggml-metal/ggml-metal-device.m#L1364),
  and files it as a reading (:func:`metal_working_set`);
- on ``TERM`` stops the server and exits (POSIX). Windows sends a process
  with no console no signal it can catch: :func:`down` ends the supervisor
  with ``TerminateProcess`` there, and its Job Object ends the server.

:func:`down` asks the supervisor to stop through its group and, when it does
not within :data:`STOP_S`, ends it and its server by force, each only while
its pid still has the start time the record holds. :func:`running` and
:func:`status` read the locks and records.

Which build runs (pin K5): :func:`mcgyvr.serving.llamacpp.backend_for`, from
this machine's system, architecture and ``nvidia-smi``'s driver version;
``$MCGYVR_NATIVE_BACKEND`` (``metal``, ``cuda``, ``vulkan`` or ``cpu``) names
one instead. Vulkan is picked only where the Vulkan loader is installed:
"for Vulkan version 1.X on Windows the library filename is vulkan-1.dll",
typically "in the windows\\system32" folder; on Linux the "versioned SONAME,
currently libvulkan.so.1"
(https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderApplicationInterface.md).
A CUDA server is given the unit's cards (``CUDA_VISIBLE_DEVICES`` with
``CUDA_DEVICE_ORDER=PCI_BUS_ID``, the order the reader numbers them in). A
Vulkan server is given every device: Vulkan numbers devices in its own order,
an integrated GPU among them, so a card's index is not its Vulkan index.

Native units run on the machine this code runs on: the door reaches a native
rig through its local transport (:func:`mcgyvr.serving.gatelib.local_transport`).
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
import types
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mcgyvr import hostos
from mcgyvr.config import LAUNCHER_NATIVE
from mcgyvr.hubwire import FIGURE_READING
from mcgyvr.serving import (
    CARDS_KEY,
    LAUNCHER_KEY,
    PROGRAM_KEY,
    SLEEPER_PROFILE,
    llamacpp,
    release,
    rigscan,
)

#: The folders under the data folder: supervisors' locks, specs and records;
#: the units' logs.
STATE = "native"
LOGS = "logs"
#: Where the pinned builds are unpacked, under the mcgyvr home.
BIN = Path("bin") / "llama.cpp"
#: A unit name a file is made from: what a container name may hold.
UNIT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
#: How long :func:`up` waits for a supervisor to say its server started, how
#: long :func:`down` gives one to stop before it is ended by force, and how
#: often each looks.
START_S = 30.0
STOP_S = 20.0
POLL_S = 0.2
#: How often, and how far apart, a record is renamed into place on Windows
#: while a reader holds it.
REPLACE_TRIES = 20
REPLACE_PAUSE_S = 0.05
#: How long a server asked to stop is given before it is killed.
SERVER_GRACE_S = 10.0
#: How long one health probe waits for its answer.
ASK_S = 5.0
#: The restart policy a spec carries; :func:`start` and :func:`up` take
#: overrides (``{"max_restarts": 0}`` for an engine that must not come back).
RESTART = {
    "max_restarts": 5,
    "backoff_s": 1.0,
    "backoff_max_s": 30.0,
    "reset_after_s": 60.0,
}
#: The variable that names the backend instead of reading the machine for one.
BACKEND_ENV = "MCGYVR_NATIVE_BACKEND"
#: The Metal start-up line, and how much of a start's log is searched for it.
METAL_LINE = re.compile(
    rb"recommendedMaxWorkingSetSize\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*MB"
)
METAL_SCAN_BYTES = 4 << 20
#: How long into a start the Metal line is looked for: it is printed while
#: the backend initialises, before the model loads.
METAL_SCAN_S = 120.0
#: The reading of it, beside the records.
METAL_FILE = "metal.json"
#: The states a record says a unit is in.
RUNNING = "running"
BACKOFF = "backoff"
GAVE_UP = "gave_up"
STOPPED = "stopped"
FAILED = "failed"
#: How long ``nvidia-smi`` is given to name its driver.
PROBE_S = 10.0


class NativeError(Exception):
    """A native unit could not be started, stopped or read."""


@dataclass(frozen=True)
class NativeUnit:
    """One native service of a launch spec, as :func:`parse` reads it."""

    name: str
    container: str
    program: str
    argv: tuple[str, ...]
    env: dict[str, str]
    port: int
    cards: tuple[int, ...]
    depends_on: tuple[str, ...]
    asleep: bool


# --- where things are --------------------------------------------------------


def state_dir() -> Path:
    """The supervisors' folder: locks, specs, records and the Metal reading."""
    from mcgyvr.fleet.roots import data_home

    return data_home() / STATE


def log_path(unit: str) -> Path:
    """Where `unit`'s server output goes: ``logs/<unit>.log`` in the data folder."""
    from mcgyvr.fleet.roots import data_home

    return data_home() / LOGS / f"{_checked(unit)}.log"


def bin_root() -> Path:
    """Where the pinned tag's builds are unpacked, under the mcgyvr home."""
    from mcgyvr.fleet.roots import home

    return home() / BIN / llamacpp.TAG


def _checked(unit: str) -> str:
    if not UNIT_NAME.fullmatch(unit):
        raise NativeError(f"{unit!r} cannot name a native unit's files")
    return unit


def _private(path: Path) -> Path:
    """`path`, made if missing, as a folder of this user's alone, or NativeError."""
    from mcgyvr.userdir import private_dir

    if private_dir(path, make=True) is None:
        raise NativeError(
            f"{path} is not this user's own folder (a link, another user's, or "
            "writable by others); nothing is started from it"
        )
    hostos.chmod_private(path, directory=True)
    return path


def _paths(unit: str) -> tuple[Path, Path, Path]:
    """The unit's lock, record and spec files."""
    base = state_dir() / _checked(unit)
    return (
        base.with_suffix(".lock"),
        base.with_suffix(".json"),
        base.with_suffix(".spec.json"),
    )


# --- the launch spec ---------------------------------------------------------


def parse(compose_file: Path) -> tuple[NativeUnit, ...]:
    """The native services of a launch spec, in file order."""
    try:
        doc = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NativeError(f"{compose_file}: cannot be read: {exc}") from exc
    services = doc.get("services") if isinstance(doc, dict) else None
    if not isinstance(services, dict):
        raise NativeError(f"{compose_file}: carries no `services:` mapping")
    found = []
    for name, block in services.items():
        if not isinstance(block, dict) or block.get(LAUNCHER_KEY) != LAUNCHER_NATIVE:
            continue
        command = [str(part) for part in block.get("command") or ()]
        program = str(block.get(PROGRAM_KEY) or llamacpp.SERVER)
        if program not in llamacpp.EXECUTABLES:
            raise NativeError(f"{compose_file}: {name}: no program {program!r}")
        try:
            port = int(command[command.index("--port") + 1])
        except (ValueError, IndexError):
            raise NativeError(f"{compose_file}: {name} names no --port") from None
        env = block.get("environment") or {}
        depends = block.get("depends_on") or ()
        found.append(
            NativeUnit(
                name=str(name),
                container=_checked(str(block.get("container_name") or "")),
                program=program,
                argv=tuple(command),
                env={str(k): str(v) for k, v in dict(env).items()},
                port=port,
                cards=tuple(int(card) for card in block.get(CARDS_KEY) or ()),
                depends_on=tuple(str(d) for d in depends),
                asleep=SLEEPER_PROFILE in (block.get("profiles") or ()),
            )
        )
    return tuple(found)


# --- which build -------------------------------------------------------------


def nvidia_driver() -> str | None:
    """The NVIDIA driver's version ``nvidia-smi`` reads, or None without one.

    The tool is the one the reader runs (:func:`mcgyvr.serving.rigscan.nvidia_smi`),
    so on Windows it is found by its full path alone, never in the working folder.
    """
    smi = rigscan.nvidia_smi()
    if smi is None:
        return None
    try:
        done = subprocess.run(
            [smi, "--query-gpu=driver_version", "--format=csv,noheader"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=PROBE_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = done.stdout.strip().splitlines() if done.returncode == 0 else []
    return lines[0].strip() if lines and lines[0].strip() else None


def vulkan_loader() -> bool:
    """Whether this machine has a Vulkan loader for a Vulkan build to use."""
    if hostos.os_name() == hostos.WINDOWS:
        system = os.environ.get("SYSTEMROOT") or r"C:\Windows"
        return (Path(system) / "System32" / "vulkan-1.dll").is_file()
    if hostos.os_name() == hostos.LINUX:
        # Looked up, not loaded: the door's own process loads no driver.
        import ctypes.util

        return ctypes.util.find_library("vulkan") is not None
    return False


def pick() -> llamacpp.Build:
    """The pinned build for this machine (K5), or for ``$MCGYVR_NATIVE_BACKEND``.

    The system and its architecture are the reader's (:func:`rigscan.host`):
    the machine's, so an Apple silicon Mac under an x86_64 interpreter still
    gets its Metal build. A machine whose arch the reader does not name has
    no build.
    """
    host = rigscan.host()
    os_name, arch = str(host["os"]), host["arch"]
    if arch is None:
        raise NativeError(
            f"this machine's arch ({platform.machine()!r}) is not one a pinned "
            f"llama.cpp build is made for: {', '.join(llamacpp.ARCHES)}"
        )
    driver = nvidia_driver()
    named = os.environ.get(BACKEND_ENV, "").strip().lower()
    if named and named not in llamacpp.BACKENDS:
        raise NativeError(
            f"${BACKEND_ENV}={named!r} names no backend; it is one of "
            f"{', '.join(llamacpp.BACKENDS)}"
        )
    backend = named or llamacpp.backend_for(
        os_name, arch, nvidia_driver=driver, vulkan=vulkan_loader()
    )
    try:
        return llamacpp.build_for(os_name, arch, backend, nvidia_driver=driver)
    except llamacpp.NoBuildError as exc:
        raise NativeError(str(exc)) from exc


def binaries(build: llamacpp.Build) -> Path:
    """The folder holding `build`'s programs, fetched and verified on first use."""
    try:
        return release.install(
            llamacpp.RELEASE,
            build.assets,
            bin_root() / build.name,
            executables=llamacpp.EXECUTABLES,
        )
    except release.ReleaseError as exc:
        raise NativeError(str(exc)) from exc


def device_env(backend: str, cards: Sequence[int]) -> dict[str, str]:
    """The variables that give a server exactly the unit's cards."""
    listed = ",".join(str(card) for card in cards)
    if not listed:
        return {}
    if backend == llamacpp.CUDA:
        return {"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": listed}
    return {}


# --- up and down --------------------------------------------------------------


def up(
    compose_file: Path,
    names: Iterable[str] = (),
    *,
    folder: Callable[[llamacpp.Build], Path] = binaries,
    build: Callable[[], llamacpp.Build] = pick,
    restart: Mapping[str, float] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Start the spec's native units (the named ones, else every awake one).

    A unit already supervised is left as it is. A unit that waits on another
    (``depends_on``) starts once that one answers ``/v1/models``. The build is
    picked and fetched once. Returns status 0 when every supervisor reported
    its server started, else 1 with what went wrong on stderr.
    """
    units = parse(compose_file)
    named = set(names)
    chosen = (
        [u for u in units if u.name in named]
        if named
        else [u for u in units if not u.asleep]
    )
    if not chosen:
        return subprocess.CompletedProcess(
            ["native"], 0, "no native unit to start\n", ""
        )
    try:
        picked = build()
        programs = folder(picked)
    except NativeError as exc:
        return subprocess.CompletedProcess(["native"], 1, "", f"{exc}\n")
    by_name = {u.name: u for u in units}
    said: list[str] = []
    failed: list[str] = []
    for unit in _in_order(chosen, by_name):
        for ahead in unit.depends_on:
            # A unit started here a moment ago is still loading its weights,
            # which takes minutes; one this call did not start either answers
            # now or is not coming.
            budget = START_S * 20 if by_name.get(ahead) in chosen else ASK_S
            if ahead in by_name and not wait_answers(by_name[ahead].port, budget):
                failed.append(f"{unit.container}: {ahead} never answered")
                break
        else:
            outcome = start(unit, picked, programs, restart=restart)
            (said if outcome is None else failed).append(
                f"{unit.container}: started" if outcome is None else outcome
            )
    return subprocess.CompletedProcess(
        ["native"],
        1 if failed else 0,
        "".join(f"{s}\n" for s in said),
        "".join(f"{f}\n" for f in failed),
    )


def _in_order(
    chosen: Sequence[NativeUnit], by_name: dict[str, NativeUnit]
) -> list[NativeUnit]:
    """`chosen` with every unit after the units it waits on."""
    placed: list[NativeUnit] = []
    seen: set[str] = set()

    def visit(unit: NativeUnit, trail: tuple[str, ...]) -> None:
        if unit.name in seen or unit.name in trail:
            return
        for ahead in unit.depends_on:
            if ahead in by_name and by_name[ahead] in chosen:
                visit(by_name[ahead], (*trail, unit.name))
        seen.add(unit.name)
        placed.append(unit)

    for unit in chosen:
        visit(unit, ())
    return placed


def start(
    unit: NativeUnit,
    build: llamacpp.Build,
    programs: Path,
    *,
    restart: Mapping[str, float] | None = None,
) -> str | None:
    """Start `unit`'s supervisor: None once its server runs, else why not."""
    spec_file = _paths(unit.container)[2]
    _private(state_dir())
    _private(log_path(unit.container).parent)
    spec = {
        "unit": unit.container,
        "program": str(programs / hostos.exe(unit.program)),
        "argv": list(unit.argv),
        "env": {**unit.env, **device_env(build.backend, unit.cards)},
        "port": unit.port,
        "backend": build.backend,
        "build": build.name,
        "tag": llamacpp.TAG,
        "log": str(log_path(unit.container)),
        **RESTART,
        # A caller whose engine must not come back on its own (a pooled
        # session's) passes `{"max_restarts": 0}`.
        **(restart or {}),
    }
    if supervised(unit.container):
        try:
            same = json.loads(spec_file.read_text(encoding="utf-8")) == spec
        except (OSError, ValueError):
            same = False
        if same:
            return None
        # The spec changed under a running unit: it is started again from the
        # new one, as `docker compose up` recreates a changed container.
        if not stop(unit.container):
            return f"{unit.container}: its old server would not stop"
    else:
        # A server whose supervisor was killed outright (POSIX has no Job
        # Object) may still hold the port: it is ended, by its record, first.
        left = (read_record(unit.container) or {}).get("server")
        orphan = matches(left)
        if orphan is not None:
            hostos.end_pid(orphan, force=True)
            _wait(lambda: matches(left) is None, STOP_S)
    _write_json(spec_file, spec)
    argv = [sys.executable, "-m", __name__, "supervise", str(spec_file)]
    proc = _spawn(argv)
    deadline = time.monotonic() + START_S
    while time.monotonic() < deadline:
        found = read_record(unit.container) or {}
        if (
            found.get("state") == RUNNING
            and (found.get("supervisor") or {}).get("pid") == proc.pid
            and supervised(unit.container)
        ):
            return None
        if proc.poll() is not None:
            return (
                f"{unit.container}: its supervisor exited {proc.returncode} "
                f"(see {log_path(unit.container)})"
            )
        time.sleep(POLL_S)
    return f"{unit.container}: no server started in {START_S:g}s"


def _spawn(argv: list[str]) -> subprocess.Popen[bytes]:
    """Start a supervisor detached; out of the starter's job where it may leave it."""
    common: dict[str, Any] = {
        "env": supervisor_env(os.environ),
        "cwd": str(state_dir()),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    try:
        return subprocess.Popen(argv, **common, **hostos.popen_detached_kwargs())
    except PermissionError:
        # A job that forbids breaking away refuses the start (Windows).
        return subprocess.Popen(
            argv, **common, **hostos.popen_detached_kwargs(breakaway=False)
        )


def supervisor_env(env: Mapping[str, str]) -> dict[str, str]:
    """The environment a supervisor, and through it a server, starts with.

    The door's own vocabulary (``RUN_*``, its proof among it, and
    ``DOCKER_*``) stays with the door, which a supervisor outlives; the
    door's shims leave PATH; and ``LLAMA_ARG_*``, llama-server's own settings,
    come from the unit's spec alone, so a variable in the operator's shell
    cannot widen where a unit listens.
    """
    from mcgyvr.serving.gatelib import SHIM_DIR

    kept = {
        key: value
        for key, value in env.items()
        if not key.startswith(("RUN_", "DOCKER_", "LLAMA_ARG_"))
    }
    if "PATH" in kept:
        kept["PATH"] = os.pathsep.join(
            entry
            for entry in kept["PATH"].split(os.pathsep)
            if entry and Path(entry) != SHIM_DIR
        )
    return kept


def down(names: Iterable[str]) -> subprocess.CompletedProcess[str]:
    """Stop the named native units; status 0 when none is left supervised.

    Answered as the finished ``docker compose`` call the serve steps read.
    """
    left: list[str] = []
    said: list[str] = []
    for unit in names:
        if stop(unit):
            said.append(f"{unit}: stopped")
        else:
            left.append(f"{unit}: still up")
    return subprocess.CompletedProcess(
        ["native"],
        1 if left else 0,
        "".join(f"{s}\n" for s in said),
        "".join(f"{f}\n" for f in left),
    )


def stop(unit: str) -> bool:
    """Stop `unit`'s supervisor and server; True once neither is left."""
    found = read_record(unit) or {}
    supervisor = matches(found.get("supervisor"))
    server = matches(found.get("server"))
    if supervisor is not None and supervised(unit):
        # The supervisor heads the group its server runs in (POSIX), so the
        # group hears it; on Windows the supervisor is ended outright, and
        # its Job Object ends the server.
        hostos.end_pid(supervisor, group=True)
        if not _wait(lambda: not supervised(unit), STOP_S):
            # Asked again by its start time before the kill: the pid may be
            # another process's by now.
            if matches(found.get("supervisor")) is not None:
                hostos.end_pid(supervisor, force=True, group=True)
            _wait(lambda: not supervised(unit), STOP_S)
    if server is not None and matches(found.get("server")) is not None:
        hostos.end_pid(server, force=True)
        _wait(lambda: matches(found.get("server")) is None, STOP_S)
    gone = not supervised(unit) and matches(found.get("server")) is None
    if found and gone:
        _write_json(_paths(unit)[1], {**found, "state": STOPPED})
    return gone


def matches(entry: object) -> int | None:
    """The pid in a record's entry while it still names that process, else None.

    A record entry is ``{pid, start, program}``. A pid is taken as the one the
    record names only while it has the start time recorded, which a reused
    pid cannot have; the program is recorded for a reader, not compared (no
    hostos reader of a pid's program exists yet).
    """
    if not isinstance(entry, dict):
        return None
    pid = entry.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return None
    start = entry.get("start")
    if start is None or hostos.process_start_time(pid) != start:
        return None
    # Windows answers a start time for an exited process while a handle to it
    # is open somewhere; the process must also be running.
    return pid if hostos.pid_alive(pid) else None


def _wait(done: Callable[[], bool], budget: float) -> bool:
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if done():
            return True
        time.sleep(POLL_S)
    return done()


def wait_answers(port: int, budget: float = START_S * 20) -> bool:
    """Whether the server on the loopback `port` lists its models within `budget`."""
    return _wait(lambda: answers(port), budget)


def answers(port: int, path: str = "/v1/models") -> bool:
    """Whether the server on the loopback `port` answers `path` with 200."""
    from mcgyvr.serving import localrig

    status, _body = localrig.ask(f"http://127.0.0.1:{port}{path}", timeout=ASK_S)
    return status == 200


# --- reading ----------------------------------------------------------------


def supervised(unit: str) -> bool:
    """Whether a supervisor holds `unit`'s lock right now."""
    lock = _paths(unit)[0]
    try:
        fd = hostos.open_nofollow(lock, os.O_RDONLY)
    except OSError:
        return False
    try:
        try:
            hostos.lock(fd, blocking=False)
        except BlockingIOError:
            return True
        hostos.unlock(fd)
        return False
    finally:
        os.close(fd)


def read_record(unit: str) -> dict[str, Any] | None:
    """`unit`'s record as its supervisor last wrote it, or None."""
    try:
        found = json.loads(_paths(unit)[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def units() -> list[str]:
    """Every unit a record names."""
    try:
        listed = sorted(state_dir().glob("*.json"))
    except OSError:
        return []
    return [
        p.name[: -len(".json")]
        for p in listed
        if not p.name.endswith(".spec.json") and p.name != METAL_FILE
    ]


def running() -> dict[str, str]:
    """The supervised units, as an id (``native-<server pid>``) to the unit's name."""
    up_now: dict[str, str] = {}
    for unit in units():
        if supervised(unit):
            server = (read_record(unit) or {}).get("server") or {}
            up_now[f"native-{server.get('pid', 0)}"] = unit
    return up_now


def status() -> list[dict[str, Any]]:
    """One row per recorded unit: its state, pids, port, restarts and log."""
    rows = []
    for unit in units():
        found = read_record(unit) or {}
        state = found.get("state", "unknown")
        if state in (RUNNING, BACKOFF) and not supervised(unit):
            state = "gone"
        rows.append(
            {
                "unit": unit,
                "state": state,
                "port": found.get("port"),
                "restarts": found.get("restarts", 0),
                "server_pid": (found.get("server") or {}).get("pid"),
                "backend": found.get("backend"),
                "log": found.get("log"),
            }
        )
    return rows


def metal_working_set() -> dict[str, Any] | None:
    """The last ``recommendedMaxWorkingSetSize`` a native server's log read.

    ``bytes`` is the figure, a reading (``figure``: ``reading``) of this
    machine's Metal device by llama.cpp, not an estimate.
    """
    try:
        found = json.loads((state_dir() / METAL_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def metal_reading(log: bytes) -> int | None:
    """The working set, in bytes, a Metal start-up log states, or None."""
    match = METAL_LINE.search(log)
    if match is None:
        return None
    return round(float(match.group(1)) * 1e6)


def held() -> dict[str, str]:
    """What holds this machine, as gates 2 and 7 read a rig: units, card holders."""
    ids = ";".join(sorted(running()))
    return {"gpu_procs": _card_holders(), "containers": ids or "none"}


def _card_holders() -> str:
    smi = rigscan.nvidia_smi()
    if smi is None:
        return "none"
    try:
        done = subprocess.run(
            [
                smi,
                "--query-compute-apps=pid,used_memory,process_name",
                "--format=csv,noheader,nounits",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=PROBE_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unread"
    if done.returncode != 0:
        return "unread"
    rows = []
    for line in done.stdout.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) >= 3 and fields[0].isdigit():
            name = re.sub(r"[\s,;]+", "_", Path(fields[2]).name) or "unnamed"
            mib = fields[1] if fields[1].isdigit() else "unread"
            rows.append(f"{fields[0]},{name},{mib}MiB")
    return ";".join(rows) or "none"


def _write_json(path: Path, body: dict[str, Any]) -> None:
    """Write `body` to `path` whole: a private temporary file renamed over it.

    Windows refuses the rename while a reader holds `path` open, which a
    record read at the same moment does; the rename is tried again then.
    """
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hostos.chmod_private(part)
    for _ in range(REPLACE_TRIES - 1):
        try:
            os.replace(part, path)
            return
        except PermissionError:
            time.sleep(REPLACE_PAUSE_S)
    os.replace(part, path)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- the supervisor -----------------------------------------------------------


def supervise(spec_file: Path) -> int:
    """Keep the spec's server up until asked to stop; the supervisor's whole life.

    Exit 0 once stopped, 1 after giving up or when the server cannot be
    started at all (said in the log and the record), 3 when another
    supervisor already holds the unit.
    """
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    unit = _checked(str(spec["unit"]))
    lock, record_file, _spec = _paths(unit)
    fd = hostos.open_nofollow(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        hostos.lock(fd, blocking=False)
    except BlockingIOError:
        os.close(fd)
        return 3
    stopping: list[int] = []

    def ask_stop(signum: int, _frame: types.FrameType | None) -> None:
        stopping.append(signum)

    for signum in (*hostos.stop_signals(), signal.SIGINT):
        signal.signal(signum, ask_stop)

    base = {
        "unit": unit,
        "port": spec["port"],
        "backend": spec.get("backend"),
        "build": spec.get("build"),
        "tag": spec.get("tag"),
        "log": spec["log"],
        "supervisor": {
            "pid": os.getpid(),
            "start": hostos.process_start_time(os.getpid()),
            "program": sys.executable,
        },
    }
    env = {
        **supervisor_env(os.environ),
        **{str(k): str(v) for k, v in spec["env"].items()},
    }
    program = Path(spec["program"])
    log_file = Path(spec["log"])
    restarts = 0
    with log_file.open("ab") as log:

        def record(state: str, **more: object) -> None:
            # A record that cannot be written is said in the log; the server
            # it describes is not stopped for it.
            try:
                _write_json(record_file, {**base, "state": state, **more})
            except OSError as exc:
                log.write(f"--- mcgyvr: {unit}: record not written: {exc}\n".encode())
                log.flush()

        while True:
            log.write(f"--- mcgyvr: {unit} starts at {_now()}\n".encode())
            log.flush()
            offset = log.tell()
            started = time.monotonic()
            try:
                # Run from the build's own folder: ggml looks for its backend
                # libraries beside the program and in the working directory.
                proc = subprocess.Popen(
                    [str(program), *spec["argv"]],
                    env=env,
                    cwd=str(program.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    **hostos.popen_no_window_kwargs(),
                )
            except OSError as exc:
                log.write(f"--- mcgyvr: {unit} could not start: {exc}\n".encode())
                record(FAILED, restarts=restarts, why=str(exc))
                return 1
            job = hostos.kill_on_close_job(proc)
            server = {
                "pid": proc.pid,
                "start": hostos.process_start_time(proc.pid),
                "program": str(program),
            }
            record(
                RUNNING,
                server=server,
                restarts=restarts,
                since=_now(),
                job=job is not None,
            )
            # Only a Metal build prints the working set, early in its start.
            scanned = spec.get("backend") != llamacpp.METAL
            while proc.poll() is None and not stopping:
                if not scanned:
                    scanned = _scan_metal(log_file, offset, unit, spec) or (
                        time.monotonic() - started > METAL_SCAN_S
                    )
                time.sleep(POLL_S)
            if stopping:
                _end_server(proc)
                record(STOPPED, server=server, restarts=restarts)
                return 0
            if not scanned:
                _scan_metal(log_file, offset, unit, spec)
            if time.monotonic() - started >= float(spec["reset_after_s"]):
                restarts = 0
            if restarts >= int(spec["max_restarts"]):
                record(GAVE_UP, server=server, restarts=restarts, exit=proc.returncode)
                log.write(
                    f"--- mcgyvr: {unit} exited {proc.returncode}; given up after "
                    f"{restarts} restarts\n".encode()
                )
                return 1
            restarts += 1
            pause = min(
                float(spec["backoff_s"]) * 2 ** (restarts - 1),
                float(spec["backoff_max_s"]),
            )
            record(BACKOFF, server=server, restarts=restarts, exit=proc.returncode)
            log.write(
                f"--- mcgyvr: {unit} exited {proc.returncode}; restart {restarts} "
                f"in {pause:g}s\n".encode()
            )
            log.flush()
            if _wait(lambda: bool(stopping), pause):
                record(STOPPED, restarts=restarts)
                return 0


def _end_server(proc: subprocess.Popen[bytes]) -> None:
    """Ask the server to end, then kill it if it has not within the grace."""
    with contextlib.suppress(OSError):
        proc.terminate()
    try:
        proc.wait(timeout=SERVER_GRACE_S)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            proc.kill()
        proc.wait()


def _scan_metal(log_file: Path, offset: int, unit: str, spec: dict[str, Any]) -> bool:
    """Find the Metal line in this start's log: True once filed or out of reach."""
    try:
        with log_file.open("rb") as handle:
            handle.seek(offset)
            seen = handle.read(METAL_SCAN_BYTES)
    except OSError:
        return False
    found = metal_reading(seen)
    if found is None:
        return len(seen) >= METAL_SCAN_BYTES
    _write_json(
        state_dir() / METAL_FILE,
        {
            "bytes": found,
            "figure": FIGURE_READING,
            "source": "llama-server's Metal start-up log, recommendedMaxWorkingSetSize",
            "unit": unit,
            "tag": spec.get("tag"),
            "read_at": _now(),
        },
    )
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """``supervise SPEC`` (the supervisor) or ``status`` (one JSON row per unit)."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "supervise":
        return supervise(Path(args[1]))
    if args == ["status"]:
        print(json.dumps(status(), indent=2))
        return 0
    print(
        "usage: python -m mcgyvr.serving.native supervise SPEC | status",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
