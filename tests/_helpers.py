"""Helpers shared across the test files that needed a copy of their own.

Each function here was copy-pasted into the test files that used it. They are
lifted so that a change to one body is one change, not a change in every file.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold


def by_path(name: str, path: Path) -> types.ModuleType:
    """A module loaded by path through its shared ``sys.modules`` slot."""
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising with stderr on failure."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def _records(journal: Path) -> list[dict[str, Any]]:
    return [
        record for path in sorted(journal.glob("*.jsonl")) for record in fold(path=path)
    ]


def _rows(journal: Path) -> list[dict[str, Any]]:
    return sorted(
        (r for r in _records(journal) if r.get("record_kind") == ATTEMPT_KIND),
        key=lambda record: str(record["attempt_id"]),
    )


def _orphans(journal: Path) -> list[dict[str, Any]]:
    return [r for r in _records(journal) if r.get("record_kind") == CORRECTION_KIND]
