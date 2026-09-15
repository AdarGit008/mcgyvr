"""Per-task sandbox: one task, one throwaway workspace, torn down after.

Acceptance commands are arbitrary shell from a contract, running on someone
else's machine — so a task never runs directly on the host. This package
provides the isolation those commands run in, in two modes that share one
interface (:mod:`mcgyvr.sandbox.base`):

- ``docker`` (:mod:`mcgyvr.sandbox.docker`): one container per task, built
  from an image that carries the repository's own dependencies
  (:mod:`mcgyvr.sandbox.image`), torn down afterwards.
- ``tempdir`` (:mod:`mcgyvr.sandbox.tempdir`): the explicitly weaker
  fallback for installs without Docker — an ephemeral directory with a git
  repository, commands executed on the host.

What the target repository needs to run its own checks is detected once
(:mod:`mcgyvr.sandbox.stack`). Provider credentials never enter either mode
(see ``SECURITY.md``).
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
