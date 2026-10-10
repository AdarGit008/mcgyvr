"""``rigscan`` is shipped to a rig as bytes, so it may depend on nothing.

The remote scan ships to the far end as ``echo <blob> | base64 -d | python3 -``:
the interpreter there is whatever the rig has -- no venv, no ``mcgyvr``, no
``PYTHONPATH``. An import added to the file therefore fails on the rig and
nowhere else. The same rule as ``tests/test_ggufscan_self_contained.py``, for
the one other file that crosses the wire as ``python3 -``.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCANNER = REPO / "src" / "mcgyvr" / "serving" / "rigscan.py"

#: What a bare ``python3`` on a rig is guaranteed to have: the file's own
#: import line, and nothing that has ever been added to it.
STDLIB_ONLY = {
    "hashlib",
    "json",
    "os",
    "platform",
    "shutil",
    "subprocess",
    "time",
    "typing",
    "re",
}


def _tree() -> ast.Module:
    return ast.parse(SCANNER.read_text(encoding="utf-8"), filename=str(SCANNER))


def _imported_names(tree: ast.Module) -> set[str]:
    """Top-level names of every import, at any depth -- a lazy one counts too."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    return names


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    left = node.test.left
    right = node.test.comparators
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and len(right) == 1
        and isinstance(right[0], ast.Constant)
        and right[0].value == "__main__"
    )


def test_the_scanner_imports_nothing_a_rig_lacks() -> None:
    extra = sorted(_imported_names(_tree()) - STDLIB_ONLY)
    assert not extra, (
        f"{SCANNER.relative_to(REPO)} imports {extra}; it runs on the rig as "
        f"`python3 -` with nothing installed, so only {sorted(STDLIB_ONLY)} "
        "are available there"
    )


def test_the_scanner_keeps_its_main_guard() -> None:
    assert any(_is_main_guard(node) for node in _tree().body), (
        f'{SCANNER.relative_to(REPO)} has no `if __name__ == "__main__":` guard'
    )


def test_the_scanner_runs_isolated_and_prints_the_scan_shape() -> None:
    """The exact transport the remote scan uses, with no argument.

    ``-I`` isolates the child from this environment -- no site-packages, no
    ``PYTHONPATH``, no current directory on ``sys.path`` -- so a dependency the
    AST walk somehow missed fails here rather than on the rig. The scanner
    prints one JSON document in the shape ``Scan.from_json`` reads.
    """
    done = subprocess.run(
        [sys.executable, "-I", "-"],
        input=SCANNER.read_bytes(),
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    raw = done.stdout
    payload = json.loads(raw)
    for key in (
        "machine",
        "gpus",
        "memory",
        "cpu",
        "bandwidth",
        "disk",
        "models_on_disk",
        "notes",
        "facts",
    ):
        assert key in payload, key
