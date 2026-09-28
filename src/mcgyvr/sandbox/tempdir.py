"""The temp-directory sandbox: the weaker mode, for installs without Docker.

Docker is the default, not a hard requirement — nobody is locked out for the
lack of it. This mode runs the worker's output and the gate in an ephemeral git
workspace and executes commands **on the host**. It is explicitly weaker and
says so once at open (:data:`base._WEAKER_MODE_NOTE`), because the isolation a
container gives — process, network, resource — is the host's here.

Almost nothing lives in this file. The workspace, its git base, reset and
teardown are all inherited from :class:`~mcgyvr.sandbox.base.Sandbox`; the
only thing a temp directory does differently from a container is *where* a
command runs, so :meth:`run` is the whole of it. That is what lets the two
modes share one test suite rather than having two (#30).

Two properties are still held, weaker mode or not:

- **Credentials stay out.** The command environment is the host's minus every
  credential-shaped variable (:func:`~mcgyvr.sandbox.base.safe_env`), rather
  than the empty base a container starts from — the host env is needed for a
  command to find its own tools, but a key is never among what it keeps. The
  host HOME is not kept either: each command gets a fresh empty one, with the
  toolchain homes (cargo, rustup, uv's cache) pinned to the host's.
- **Nothing survives.** The ephemeral directory is removed on success,
  failure and interrupt by the shared context manager, and each command runs in
  its own session, killed whole when the command ends — so a child it left in
  the background neither outlives it nor holds its verdict open.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, ClassVar

from mcgyvr.sandbox.base import (
    TIMEOUT_EXIT,
    CommandResult,
    Sandbox,
    command_timeout,
    merge_env,
)

# Conventional shell exit codes for a command that never ran: 127 when the
# binary is not found, 126 when it is found but cannot be executed. Both let a
# caller tell "did not run" apart from "ran and exited non-zero".
_COMMAND_NOT_FOUND = 127
_COMMAND_NOT_EXECUTABLE = 126

_HOME_PREFIX = "mcgyvr-home-"

#: Host variables that point a command back into the host HOME's dot files.
#: Unset, each falls back to its default under the command's own HOME.
_HOME_DERIVED = frozenset(
    {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"}
)


def host_tool_homes() -> dict[str, str]:
    """Where the host's toolchains live, resolved as each tool resolves it.

    A variable the host sets is kept as set; an unset one is the tool's own
    default under the host HOME (uv's cache honours ``XDG_CACHE_HOME``).
    """
    env = os.environ
    home = Path.home()
    xdg_cache = env.get("XDG_CACHE_HOME")
    cache = Path(xdg_cache) if xdg_cache else home / ".cache"
    return {
        "CARGO_HOME": env.get("CARGO_HOME") or str(home / ".cargo"),
        "RUSTUP_HOME": env.get("RUSTUP_HOME") or str(home / ".rustup"),
        "UV_CACHE_DIR": env.get("UV_CACHE_DIR") or str(cache / "uv"),
    }


class TempDirSandbox(Sandbox):
    """Run a task in an ephemeral host directory. The weaker isolation mode."""

    isolation: ClassVar[str] = "process"

    def _start(self) -> None:
        # The workspace and its git base are prepared by the base class;
        # there is nothing to stand up on the host.
        pass

    def _stop(self) -> None:
        # Teardown is just the workspace removal the base class does.
        pass

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        # A fresh empty HOME per command, outside the workspace so nothing
        # written there reaches the gated diff, and removed when it returns.
        with tempfile.TemporaryDirectory(
            prefix=_HOME_PREFIX, ignore_cleanup_errors=True
        ) as home:
            return self._run(tuple(command), timeout, env, home)

    def _run(
        self,
        argv: tuple[str, ...],
        timeout: float | None,
        env: Mapping[str, str] | None,
        home: str,
    ) -> CommandResult:
        # Host env minus credentials, plus the caller's vetted extras. The
        # container mode starts from nothing; here the host env is what lets a
        # command find its own toolchain, and the credential filter is what
        # keeps a key from riding along. The host HOME is not kept: its dot
        # files are where credentials live. Tool homes stay where the host
        # resolves them, so a toolchain found through HOME still works.
        host = {k: v for k, v in os.environ.items() if k not in _HOME_DERIVED}
        full_env = merge_env(host, env, {**host_tool_homes(), "HOME": home})
        # Output goes to files rather than pipes: a child the command left in
        # the background holds a pipe open, and waiting for it to close would
        # report a command that exited as one that timed out.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=self.workspace,
                    env=full_env,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
            except OSError as unrunnable:
                # The binary is missing (FileNotFoundError) or present but not
                # executable (PermissionError, NotADirectoryError). Either way
                # it never ran; report the shell code rather than raising, so
                # the gate sees a command outcome like any other.
                code = (
                    _COMMAND_NOT_FOUND
                    if isinstance(unrunnable, FileNotFoundError)
                    else _COMMAND_NOT_EXECUTABLE
                )
                return CommandResult(
                    command=argv, exit_code=code, stdout="", stderr=str(unrunnable)
                )
            timed_out = False
            try:
                exit_code = proc.wait(timeout=command_timeout(timeout))
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = TIMEOUT_EXIT
            finally:
                # The command's whole session goes when it ends, on a timeout,
                # an exit or an interrupt: nothing it started outlives it.
                _kill_session(proc)
            return CommandResult(
                command=argv,
                exit_code=exit_code,
                stdout=_read(out),
                stderr=_read(err),
                timed_out=timed_out,
            )


def _kill_session(proc: subprocess.Popen[bytes]) -> None:
    """SIGKILL every process in ``proc``'s session and reap ``proc``.

    A process that left the session (``setsid``, a daemon) is not reached:
    this mode's process isolation is the host's.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _read(stream: IO[bytes]) -> str:
    stream.seek(0)
    return stream.read().decode("utf-8", "replace")
