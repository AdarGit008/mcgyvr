"""The temp-directory sandbox: the weaker mode, for installs without Docker.

Docker is the default, not a hard requirement — nobody is locked out for the
lack of it (ADR-0001 §5). This mode runs the worker's output and the gate in
an ephemeral git workspace and executes commands **on the host**. It is
explicitly weaker and says so once at open (:data:`base._WEAKER_MODE_NOTE`),
because the isolation a container gives — process, network, resource — is the
host's here.

Almost nothing lives in this file. The workspace, its git base, reset and
teardown are all inherited from :class:`~mcgyvr.sandbox.base.Sandbox`; the
only thing a temp directory does differently from a container is *where* a
command runs, so :meth:`run` is the whole of it. That is what lets the two
modes share one test suite rather than having two (#30).

Two properties are still held, weaker mode or not:

- **Credentials stay out.** The command environment is the host's minus every
  credential-shaped variable (:func:`~mcgyvr.sandbox.base.safe_env`), rather
  than the empty base a container starts from — the host env is needed for a
  command to find its own tools, but a key is never among what it keeps.
- **Nothing survives.** The ephemeral directory is removed on success,
  failure and interrupt by the shared context manager.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from typing import ClassVar

from mcgyvr.sandbox.base import CommandResult, Sandbox, merge_env

# Conventional shell exit codes for a command that never ran: 127 when the
# binary is not found, 126 when it is found but cannot be executed. Both let a
# caller tell "did not run" apart from "ran and exited non-zero".
_COMMAND_NOT_FOUND = 127
_COMMAND_NOT_EXECUTABLE = 126


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
        argv = tuple(command)
        # Host env minus credentials, plus the caller's vetted extras. The
        # container mode starts from nothing; here the host env is what lets a
        # command find its own toolchain, and the credential filter is what
        # keeps a key from riding along.
        full_env = merge_env(os.environ, env)
        try:
            done = subprocess.run(
                argv,
                cwd=self.workspace,
                env=full_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as expired:
            return CommandResult(
                command=argv,
                exit_code=-1,
                stdout=_as_text(expired.stdout),
                stderr=_as_text(expired.stderr),
                timed_out=True,
            )
        except OSError as unrunnable:
            # The binary is missing (FileNotFoundError) or present but not
            # executable (PermissionError, NotADirectoryError). Either way it
            # never ran; report the shell code rather than raising, so the gate
            # sees a command outcome like any other.
            code = (
                _COMMAND_NOT_FOUND
                if isinstance(unrunnable, FileNotFoundError)
                else _COMMAND_NOT_EXECUTABLE
            )
            return CommandResult(
                command=argv,
                exit_code=code,
                stdout="",
                stderr=str(unrunnable),
            )
        return CommandResult(
            command=argv,
            exit_code=done.returncode,
            stdout=done.stdout,
            stderr=done.stderr,
        )


def _as_text(stream: str | bytes | None) -> str:
    """Coerce captured output — bytes on a timeout under some Pythons — to text."""
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", "replace")
    return stream
