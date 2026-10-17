""

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
    workdir,
)

#
#
#
_COMMAND_NOT_FOUND = 127
_COMMAND_NOT_EXECUTABLE = 126

_HOME_PREFIX = "mcgyvr-home-"

#
#
_HOME_DERIVED = frozenset(
    {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"}
)


def host_tool_homes() -> dict[str, str]:
    ""
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
    ""

    isolation: ClassVar[str] = "process"

    def _start(self) -> None:
        #
        #
        pass

    def _stop(self) -> None:
        #
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
        #
        #
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
        #
        #
        #
        #
        #
        #
        host = {k: v for k, v in os.environ.items() if k not in _HOME_DERIVED}
        full_env = merge_env(host, env, {**host_tool_homes(), "HOME": home})
        #
        #
        #
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=where,
                    env=full_env,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
            except OSError as unrunnable:
                #
                #
                #
                #
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
                #
                #
                _kill_session(proc)
            return CommandResult(
                command=argv,
                exit_code=exit_code,
                stdout=_read(out),
                stderr=_read(err),
                timed_out=timed_out,
            )


def _kill_session(proc: subprocess.Popen[bytes]) -> None:
    ""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _read(stream: IO[bytes]) -> str:
    stream.seek(0)
    return stream.read().decode("utf-8", "replace")
