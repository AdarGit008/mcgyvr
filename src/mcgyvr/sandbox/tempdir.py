"""The temp-directory sandbox: a contract's commands run as ordinary host
processes inside the throwaway git workspace the base class builds, each under
a temporary HOME that is deleted when the call returns.

There is no container here, so process, network and resource isolation are the
host's. What this module does provide: the child environment is the host's own
minus everything that names a home, plus the caller's variables, plus the
throwaway HOME and the host's package caches, and the merged result is scrubbed
for credentials on the way through — so no key the host holds reaches a command.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, ClassVar

from mcgyvr import hostos
from mcgyvr.sandbox.base import (
    TIMEOUT_EXIT,
    CommandResult,
    Sandbox,
    command_timeout,
    merge_env,
    workdir,
)

# Exit codes a POSIX shell reports when the program named could not be run at
# all, as opposed to running and failing; used when the spawn itself fails so a
# caller sees the same numbers a shell would have given it.
_COMMAND_NOT_FOUND = 127
_COMMAND_NOT_EXECUTABLE = 126

_HOME_PREFIX = "mcgyvr-home-"

#: Variables whose values point into a home directory. The host's values are
#: dropped, so a command resolves them against the throwaway HOME instead.
_HOME_DERIVED = frozenset(
    {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"}
)


def host_tool_homes() -> dict[str, str]:
    """The host's cargo, rustup and uv cache locations, read from the
    environment when set (so a non-default one is honoured) and otherwise
    spelled as the conventional path under the real home.
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
    """A sandbox whose commands run on the host, inside the throwaway git
    workspace, with no container around them.

    It adds nothing to the workspace the base class builds: there is no session
    to start or stop. `isolation` is `process` because the only thing between a
    command and the host is a separate process with a scrubbed environment and
    its own HOME.
    """

    isolation: ClassVar[str] = "process"

    def _start(self) -> None:
        # Nothing to start: the workspace is already there, and every command
        # is spawned directly by `run`.
        pass

    def _stop(self) -> None:
        # Nothing to stop: every command is reaped inside `_run`.
        pass

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        where = self.workspace.joinpath(*workdir(cwd).parts)
        # A throwaway HOME for this one call, removed when it returns, so
        # whatever a command writes under its home does not survive the run.
        with tempfile.TemporaryDirectory(
            prefix=_HOME_PREFIX, ignore_cleanup_errors=True
        ) as home:
            return self._run(tuple(command), timeout, env, home, where)

    def _run(
        self,
        argv: tuple[str, ...],
        timeout: float | None,
        env: Mapping[str, str] | None,
        home: str,
        where: Path,
    ) -> CommandResult:
        # The child gets the host environment minus every variable that names a
        # home, so `CARGO_HOME` and its neighbours cannot point a command back
        # at the real one. The caller's variables layer on next and the
        # throwaway HOME plus the host's tool caches last, later layers winning,
        # and `merge_env` scrubs the merged result for credentials, so a key the
        # host holds is not passed on even when the caller asked for it.
        host = {k: v for k, v in os.environ.items() if k not in _HOME_DERIVED}
        full_env = merge_env(host, env, {**host_tool_homes(), "HOME": home})
        # Real files rather than pipes: a command that writes more than a pipe
        # buffer holds would block on a pipe nobody is reading until it exits,
        # and these are read back only after it has.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=where,
                    env=full_env,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    **hostos.popen_group_kwargs(),
                )
            except OSError as unrunnable:
                # The program could not be spawned at all — not found, or found
                # but not executable — which is not the same as a program that
                # ran and failed. It is reported with the exit code a shell
                # would give it and the OS error as stderr, rather than raised.
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
                # Kill the whole session, not just the process, so children the
                # command left running do not outlive the call.
                _kill_session(proc)
            return CommandResult(
                command=argv,
                exit_code=exit_code,
                stdout=_read(out),
                stderr=_read(err),
                timed_out=timed_out,
            )


def _kill_session(proc: subprocess.Popen[bytes]) -> None:
    """Kill the process group the leader `proc` heads, then reap the leader.

    The group is signalled because `_run` starts the process in its own
    session, which makes it a group leader, so the command's children are in
    that group and would otherwise survive. A group that is already gone or is
    not ours is not an error; the wait afterwards reaps the leader so no zombie
    is left behind.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        hostos.kill_group(proc)
    proc.wait()


def _read(stream: IO[bytes]) -> str:
    stream.seek(0)
    return stream.read().decode("utf-8", "replace")
