"""Behaviors mcgyvr has, stated as tests, not as designs.

Every test in this package says *what must be observably true*, never *how to make
it true*: a test that asserted a call sequence would freeze one implementation.

So the assertions are outcomes a person could check by hand — what a file on disk
holds, what a refusal says, what a record carries, what a prompt contains. None of
them names a private function, and none asserts that something *was called*.

**Naming a seam.** A test has to call something. The entry point is resolved
through :func:`required`, whose failure message is the behavior statement itself —
so an entry point that cannot be imported reads as a missing behavior rather than
an import error.

**Why the failure is deliberate rather than an error.** ``pytest.fail(pytrace=False)``
rather than a bare import at module scope, because a module-level ImportError is a
collection error: it takes the whole file down, reports no behavior, and hides
every other test in it. One test, one missing behavior, one sentence.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""


def required(behavior: str, resolve: Callable[[], Any]) -> Any:
    """The capability this test needs, or a failure naming the behavior.

    ``behavior`` is the sentence a reader should see when the test fails. It is
    phrased as a capability of mcgyvr ("must be able to ...") rather than as a
    missing module, because the capability is the requirement.
    """
    try:
        return resolve()
    except (ImportError, AttributeError, ModuleNotFoundError) as absent:
        pytest.fail(
            f"mcgyvr must be able to: {behavior}\n  unreachable: {absent}",
            pytrace=False,
        )


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising with stderr on failure."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository with one commit and one target file.

    Real rather than mocked: every behavior in this package is about what git and
    the filesystem end up holding, and a fake git would let a wrong answer pass.
    """
    work = tmp_path / "work"
    (work / "src" / "pkg").mkdir(parents=True)
    (work / "src" / "pkg" / "fetch.py").write_text("def fetch(url):\n    return url\n")
    git(work.parent, "init", "-q", str(work))
    git(work, "config", "user.email", "test@example.invalid")
    git(work, "config", "user.name", "test")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "base")
    return work


@pytest.fixture
def contract() -> Any:
    """The same contract every test in this package works against."""
    from mcgyvr.contract import loads

    return loads(CONTRACT)
