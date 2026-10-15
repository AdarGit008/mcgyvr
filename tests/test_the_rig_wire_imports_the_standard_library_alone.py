"""The rig wire modules import the standard library alone.

``rig/websocket.py`` and ``rig/udpwire.py`` are staged into the tunnel's
container as text and run there with ``python3 -I`` (isolated mode), and also
run in-process beside the door. Either way they must not drag in mcgyvr, so a
dependency that reached the package would break the door's staging contract
silently. This pins the invariant the way the timer's test does, as an import
rule rather than a comment.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from tests._paths import SRC

WIRE = (
    SRC / "rig" / "websocket.py",
    SRC / "rig" / "udpwire.py",
)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }


def test_the_wire_modules_import_the_standard_library_alone() -> None:
    for path in WIRE:
        assert path.is_file(), path
        assert _imported_roots(path) <= set(sys.stdlib_module_names) | {
            "__future__"
        }, f"{path.name} imports beyond the standard library"
