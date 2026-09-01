"""D4 — an auto-import is only written for a dependency that actually resolves.

``_module_of`` derives a module name from a dependency's path and the repair
writes ``from <module> import <name>`` for it, without ever checking that the
file exists. A contract that declares a dependency whose file is missing — a
typo, a path the worker was supposed to create but did not — gets an import
that raises ``ModuleNotFoundError`` at run time: the rejection becomes an
acceptance plus a crash nobody asked for.

The fix skips a declared dependency whose file is not in the repository, the
same way it already skips a path it cannot name a module for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.contract import loads
from mcgyvr.repair import repair
from tests.red_port.conftest import git

DEPS_CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
deps:
  - path: src/pkg/backoff.py
    signature: "def sleep_backoff(attempt: int) -> None"
    note: The backoff the retry loop must wait with.
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""


def test_no_import_is_written_for_a_declared_dependency_that_does_not_exist(
    repo: Path,
) -> None:
    """A declared dependency whose file is missing must not get an import."""
    contract: Any = loads(DEPS_CONTRACT)
    base = git(repo, "rev-parse", "HEAD").strip()
    target = repo / "src" / "pkg" / "fetch.py"
    target.write_text(
        "def fetch(url):\n"
        "    for attempt in range(3):\n"
        "        sleep_backoff(attempt)\n"
        "    return url\n"
    )

    repair(repo=repo, contract=contract, base=base)

    written = target.read_text()
    assert "from pkg.backoff import sleep_backoff" not in written, (
        f"repair wrote an import for a dependency whose file does not exist, "
        f"turning the undefined name into a ModuleNotFoundError: {written!r}"
    )
