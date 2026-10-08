"""What the tests of a caller's gate list drive the door with.

A caller hands the door ``--gates FILE`` on ``serve`` and ``read``: a JSON
object naming a ``root`` folder and a list of gates, each with a ``path``, a
``why``, a ``phase`` (``before``, ``after`` or ``always``) and the names it
``exports``. These helpers write such lists and the gates in them, and two
kinds of door to run them through:

* :func:`fake_door` swaps the door's own gate scripts for stand-ins that write
  one line each to a log and export what the door declares for them, so a
  test reads the whole order of a run, the lease release included, with no
  machine anywhere. The door is run in-process through ``run.main``.
* :func:`stub_machine` puts an ``ssh`` and a ``docker`` of the test's own
  behind the door's shims. Each writes every call it receives to a log and
  answers nothing, so a door run with its real gates shows whether anything
  was sent to a machine at all.

Every host, folder and container here is invented for the test.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import stat
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import run

#: The host every door run here is opened for. A name no resolver answers.
HOST = "gatelist-box.invalid"

#: What a stand-in door gate exports for a name its entry declares, when the
#: value matters to the door itself: a RUN_ID and a lease send the door
#: through its always phase and its lease release.
FAKE_VALUES = {"RUN_ID": "run-gatelist", "RUN_LEASE": "lease_id=gatelist"}


def executable(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` and make it executable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def log_lines(log: Path) -> list[str]:
    """The lines a run wrote to ``log``, in order; none when it wrote none."""
    if not log.is_file():
        return []
    return log.read_text(encoding="utf-8").splitlines()


def gate_text(
    log: Path,
    tag: str,
    *,
    exports: dict[str, str] | None = None,
    show: tuple[str, ...] = (),
    status: int = 0,
) -> str:
    """A gate that logs ``tag`` with its RUN_ROOT, exports, and exits.

    ``show`` names variables whose value (or ``-`` when unset) the gate adds
    to its log line, so a test reads what the gate was handed.
    """
    return "\n".join(
        [
            "#!/usr/bin/env python3",
            "import os, sys",
            "seen = ' '.join(",
            f"    f'{{k}}={{os.environ.get(k, \"-\")}}' for k in {list(show)!r}",
            ")",
            f'line = f\'{tag} root={{os.environ.get("RUN_ROOT", "-")}} {{seen}}\'',
            f"with open({str(log)!r}, 'a', encoding='utf-8') as out:",
            "    out.write(line.rstrip() + '\\n')",
            *(
                [
                    "fd = int(os.environ['RUN_EXPORT_FD'])",
                    *(
                        f"os.write(fd, {f'{key}={value}\n'!r}.encode())"
                        for key, value in (exports or {}).items()
                    ),
                ]
                if exports
                else []
            ),
            f"sys.exit({status})",
            "",
        ]
    )


def fake_door(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    log: Path,
    *,
    show: tuple[str, ...] = (),
    statuses: dict[str, int] | None = None,
) -> Path:
    """Replace every gate the door spawns with a stand-in that logs its name.

    Each stand-in exports what the door declares for its entry, so the run
    goes as far as a run whose every gate admits. ``show`` is handed to each
    stand-in as :func:`gate_text` takes it, and ``statuses`` names a stand-in
    that exits with another status than 0. The door's shims are copied beside
    them, since the door will not start without its shims.
    """
    where = tmp_path / "door-gates"
    where.mkdir()
    (where / "bin").mkdir()
    for shim in run.SHIMS:
        executable(where / "bin" / shim, (run.BIN / shim).read_text("utf-8"))
    entries = (
        *run.SEQUENCE,
        *run.ALWAYS,
        *run.READ_SEQUENCE,
        *run.LINK_SEQUENCE,
        run.LEASE_RELEASE,
    )
    for entry in entries:
        values = {
            key: FAKE_VALUES.get(key, str(tmp_path / "out") if "DIR" in key else "x")
            for key in entry.exports
        }
        executable(
            where / entry.script,
            gate_text(
                log,
                f"door:{entry.script}",
                exports=values,
                show=show,
                status=(statuses or {}).get(entry.script, 0),
            ),
        )
    monkeypatch.setattr(run, "GATE_SCRIPTS", where)
    monkeypatch.setattr(run, "BIN", where / "bin")
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(door_root(tmp_path)))
    return where


def door_root(tmp_path: Path) -> Path:
    """The run root the door is opened with: a folder of the test's own."""
    root = tmp_path / "door-root"
    root.mkdir(exist_ok=True)
    return root


def write_list(where: Path, root: object, gates: list[dict[str, Any]]) -> Path:
    """Write a gate list to ``where`` and return its path."""
    where.write_text(json.dumps({"root": root, "gates": gates}), encoding="utf-8")
    return where


def entry(
    path: str, phase: str, exports: list[str] | None = None, why: str = "a test gate"
) -> dict[str, Any]:
    """One gate of a list."""
    return {"path": path, "why": why, "phase": phase, "exports": exports or []}


def compose_file(where: Path) -> Path:
    """A compose file of two invented units, as `serve` reads one."""
    where.write_text(
        "services:\n"
        "  alpha:\n"
        "    container_name: gatelist-alpha\n"
        "    command: [--port, '47011']\n"
        "  beta:\n"
        "    container_name: gatelist-beta\n"
        "    command: [--port, '47012']\n",
        encoding="utf-8",
    )
    return where


def serve_argv(compose: Path, *extra: str) -> list[str]:
    """``serve down`` of the invented units on :data:`HOST`."""
    return ["serve", "down", "--host", HOST, "--compose", str(compose), *extra]


def read_argv(*extra: str) -> list[str]:
    """A plain ``read`` of :data:`HOST`."""
    return ["read", "--host", HOST, *extra]


def clean_door_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every variable the door refuses to inherit."""
    for name in list(os.environ):
        if name.startswith(run.MINTED_PREFIXES):
            monkeypatch.delenv(name)


def stub_machine(tmp_path: Path) -> tuple[Path, Path]:
    """An ``ssh`` and a ``docker`` that log every call and answer nothing.

    Returns the folder to put on PATH and the log they write to.
    """
    stubs = tmp_path / "stubs"
    calls = tmp_path / "machine-calls.log"
    for name in run.SHIMS:
        executable(
            stubs / name,
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"with open({str(calls)!r}, 'a', encoding='utf-8') as out:\n"
            f"    out.write({name!r} + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "sys.exit(255)\n",
        )
    return stubs, calls


def round_stub(root: Path) -> None:
    """The round module gate 1 loads from a run root, invented: it admits."""
    executable(
        root / "tools" / "bench" / "product.py",
        "class ProductError(Exception):\n"
        "    pass\n"
        "\n"
        "\n"
        "def ensure_open():\n"
        "    return 'round-gatelist', '0' * 64\n",
    )


def door_process(
    argv: list[str], *, stubs: Path, run_root: Path, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """``python -m mcgyvr.serving.run ARGV`` with its real gates, over the stubs."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(run.MINTED_PREFIXES)
    }
    env["PATH"] = f"{stubs}{os.pathsep}{env.get('PATH', os.defpath)}"
    env["MCGYVR_RUN_ROOT"] = str(run_root)
    return subprocess.run(
        [sys.executable, "-m", "mcgyvr.serving.run", *argv],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


#: The checkout the tests run from, for a door started as its own process.
REPO = Path(__file__).resolve().parent.parent

#: The door as a process over :func:`fake_door`'s stand-ins, with the signal
#: handlers the door installs when it runs as ``python -m``. Arguments: the
#: folder to build in, the order log, the door's argv as JSON, and
#: ``subreaper`` or nothing. A ``lease-release.py`` in that folder stands in
#: for the lease release, and a ``hook.py`` there is run in the door's process
#: before the door starts, with ``run`` in its namespace. With ``subreaper``
#: the door adopts every process orphaned below it (a child subreaper), as a
#: door running as PID 1 does.
DRIVER = """
import ctypes, json, signal, sys
from pathlib import Path
import pytest
sys.path.insert(0, {repo!r})
from mcgyvr.serving import run
from tests import callergates as cg
work, log, argv = Path(sys.argv[1]), Path(sys.argv[2]), json.loads(sys.argv[3])
if sys.argv[4:] == ["subreaper"]:
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        sys.exit("cannot become a child subreaper")
mp = pytest.MonkeyPatch()
cg.clean_door_env(mp)
gates = cg.fake_door(work, mp, log)
release = work / "lease-release.py"
if release.is_file():
    cg.executable(gates / run.LEASE_RELEASE.script, release.read_text("utf-8"))
hook = work / "hook.py"
if hook.is_file():
    exec(hook.read_text("utf-8"), {{"run": run}})
signal.signal(signal.SIGTERM, run._sigterm)
signal.signal(signal.SIGINT, run._sigterm)
sys.exit(run.main(argv))
"""


#: A parent for the door that adopts every process orphaned below it (a
#: child subreaper) and reaps each one only ``delay`` seconds after it died,
#: so a killed process stays in its process group, as a zombie, for that
#: long. Arguments: the delay, then the command to run.
SLOW_REAPER = """
import ctypes, os, subprocess, sys, time
delay = float(sys.argv[1])
if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
    sys.exit("cannot become a child subreaper")
door = subprocess.Popen(sys.argv[2:])
first = {}
while door.poll() is None:
    try:
        info = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        info = None
    now = time.monotonic()
    if info is not None and info.si_pid != door.pid:
        if now - first.setdefault(info.si_pid, now) >= delay:
            os.waitpid(info.si_pid, 0)
    time.sleep(0.02)
end = time.monotonic() + 10
while time.monotonic() < end:
    try:
        if os.waitpid(-1, os.WNOHANG) == (0, 0):
            time.sleep(0.05)
    except ChildProcessError:
        break
sys.exit(door.returncode)
"""


def driven_door(
    work: Path,
    log: Path,
    argv: list[str],
    *,
    reap_after: float | None = None,
    subreaper: bool = False,
) -> subprocess.Popen[str]:
    """Start the door over stand-in gates as a process of its own.

    With ``reap_after``, the door runs under :data:`SLOW_REAPER`: a process
    orphaned below it is reaped only that many seconds after it died. With
    ``subreaper``, the door itself adopts the processes orphaned below it.
    The door starts in a session of its own, so :func:`stop_door` can end it
    and whatever runs in its process group.
    """
    door = [
        sys.executable,
        "-c",
        DRIVER.format(repo=str(REPO)),
        str(work),
        str(log),
        json.dumps(argv),
        *(["subreaper"] if subreaper else []),
    ]
    if reap_after is not None:
        door = [sys.executable, "-c", SLOW_REAPER, str(reap_after), *door]
    return subprocess.Popen(
        door,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def stop_door(door: subprocess.Popen[str], pids: Iterable[int] = ()) -> None:
    """Kill a driven door's process group, when it still runs, and ``pids``.

    A caller's gate runs in a session of its own, outside the door's group,
    so a test names the gate's processes to leave nothing running.
    """
    if door.poll() is None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(door.pid, signal.SIGKILL)
        door.wait()
    for pid in pids:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)


def alive(pid: int) -> bool:
    """Whether a process of that id still runs."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def step_argv(where: Path, *extra: str) -> list[str]:
    """``step`` of a script of the test's own on :data:`HOST`."""
    script = executable(
        where / "own-step.sh", "#!/usr/bin/env bash\n# RUN_ARTIFACTS: out.json\n"
    )
    return ["step", "--host", HOST, "--campaign", "own", "--step", str(script), *extra]


def link_argv(*extra: str) -> list[str]:
    """A ``link --peer`` of two cards of :data:`HOST`."""
    return ["link", "--host", HOST, "--peer", "0", "1", *extra]
