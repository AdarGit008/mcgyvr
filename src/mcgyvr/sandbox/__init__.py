"""The sandbox: the throwaway workspace a task's commands are run in.

A contract's acceptance commands run without a shell, each in whatever program
it names, on the host unless a container holds it. This package holds no logic
of its own. It re-exports the pieces a caller
composes so one import is enough: `open_sandbox` builds a `Sandbox` — a
container-backed one, or the weaker temp-directory one — over a source
repository, and raises `SandboxError` when the requested mode or network
cannot be honoured; `CommandResult` is what `Sandbox.run` hands back. Alongside
them come the stack detection a sandbox needs to install a repository's
dependencies: `detect_stack` inspects the manifests present and returns a
`Stack` of `StackComponent`s, one per detected language, with the install
commands, base image, checker installs and the notes explaining what it could
not pin.
"""

from __future__ import annotations

from mcgyvr.sandbox.base import (
    CommandResult,
    Sandbox,
    SandboxError,
    open_sandbox,
)
from mcgyvr.sandbox.stack import Stack, StackComponent, detect_stack

__all__ = [
    "CommandResult",
    "Sandbox",
    "SandboxError",
    "Stack",
    "StackComponent",
    "detect_stack",
    "open_sandbox",
]
