"""A kept file is renamed into place by ``mcgyvr.atomic`` alone.

``atomic.write`` stages a file and renames it over its target, and
``atomic.replace`` is that rename for a staged file or folder built some other
way (a resumed download, an unpacked build). The rename is tried again while
Windows holds the target, so a writer that renames by hand would lose that
retry. These pin that no module of the package calls ``os.replace`` or
``Path.replace`` but atomic, and that each ``rename`` outside it is one named
here with why it is not a replace.
"""

from __future__ import annotations

import ast
import functools

from tests._paths import REPO

PACKAGE = REPO / "src" / "mcgyvr"

#: The renames that are not a kept file put in place, by file: each moves a
#: file of its own aside or publishes a folder that must not overwrite one.
RENAMES = {
    # A lock marker is published under its final name while its lock is held.
    "pressure.py": 1,
    # A built fleet folder must not overwrite one that appeared meanwhile:
    # os.rename refuses an existing target on Windows, which replace would not.
    "fleet/promote.py": 1,
    # A stamp folder, the same way.
    "fleet/stamp.py": 1,
    # An artifact a step wrote is moved aside, and moved back when not rewritten.
    "serving/gate-scripts/05-envelope.py": 1,
    "serving/gate-scripts/08-parse.py": 1,
}


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    """``os.<name>(a, b)`` and ``<path>.<name>(a)`` calls in `tree`; a str's
    ``replace`` takes two arguments, so one argument is a path's."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != name or node.keywords:
            continue
        owner = node.func.value
        by_os = isinstance(owner, ast.Name) and owner.id == "os"
        if by_os or len(node.args) == 1:
            found.append(node)
    return found


@functools.cache
def _modules() -> dict[str, ast.AST]:
    """Every module of the package, parsed once, by its path in the package."""
    return {
        path.relative_to(PACKAGE).as_posix(): ast.parse(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(PACKAGE.rglob("*.py"))
    }


def test_no_module_but_atomic_replaces_a_file_by_hand() -> None:
    by_hand = {
        f"{name}:{call.lineno}"
        for name, tree in _modules().items()
        if name != "atomic.py"
        for call in _calls(tree, "replace")
    }

    assert by_hand == set(), "rename through mcgyvr.atomic.write or atomic.replace"


def test_each_rename_outside_atomic_is_one_named_here() -> None:
    renames = {
        name: len(found)
        for name, tree in _modules().items()
        if (found := _calls(tree, "rename"))
    }

    assert renames == RENAMES
