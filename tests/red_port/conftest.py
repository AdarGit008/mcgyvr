"""Behaviors mcgyvr must have and does not yet — stated as tests, not as designs.

Every test in this package says *what must be observably true*, never *how to make
it true*. The distinction is load-bearing here because these tests are written
before the code: a test that asserted a call sequence would freeze an
implementation nobody has chosen yet, and the first honest design would have to
delete it.

So the assertions are outcomes a person could check by hand — what a file on disk
holds, what a refusal says, what a record carries, what a prompt contains. None of
them names a private function, and none asserts that something *was called*.

**Naming a seam.** A test has to call something. Where a lever has no code at all,
the entry point is resolved through :func:`required`, whose failure message is the
behavior statement itself — so a RED run reads as a list of missing behaviors
rather than a list of import errors. The dotted path handed to it is a
**placeholder**: rename it freely while porting and these tests still say the same
thing. What must not drift is what is asserted after it resolves.

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
    """The capability this test needs, or a RED failure naming the behavior.

    ``behavior`` is the sentence a reader should see when the test fails. It is
    phrased as a capability of mcgyvr ("must be able to ...") rather than as a
    missing module, because the module is a guess and the capability is the
    requirement.
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
