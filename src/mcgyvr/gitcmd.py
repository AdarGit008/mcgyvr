"""Running git in a repository and refusing its failure in the caller's own error.

Every git a module runs to read or write a repository goes through
:func:`run_git`: output captured as bytes, extra environment merged over the
current one, and a non-zero exit raised as the caller's error carrying git's
stderr. A probe that reads only git's exit status runs git itself.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path


def run_git(
    root: Path,
    *args: str,
    error: Callable[[str], Exception],
    env: Mapping[str, str] | None = None,
    input: bytes | None = None,
    message: str | None = None,
) -> bytes:
    """Run ``git -C root *args`` and return its stdout.

    `env` is merged over the current environment (a scratch ``GIT_INDEX_FILE``
    or a commit identity reaches git this way); `input` is sent on stdin. A
    non-zero exit raises ``error(message)``, or, with no `message`, an error
    naming the subcommand, `root` and git's stderr.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input,
        capture_output=True,
        env={**os.environ, **env} if env else None,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise error(message or f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout
