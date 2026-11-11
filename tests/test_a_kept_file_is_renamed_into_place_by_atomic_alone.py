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
    # publish_dir: a new folder (a promoted fleet, a stamp) must not overwrite
    # one that appeared meanwhile: os.rename refuses an existing target on
    # Windows, which replace would not.
    "atomic.py": 1,
    # A lock marker is published under its final name while its lock is held.
    "pressure.py": 1,
    # An artifact a step wrote is moved aside, and moved back when not rewritten.
    "serving/gate-scripts/05-envelope.py": 1,
    "serving/gate-scripts/08-parse.py": 1,
}


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    """The calls in `tree` that rename by `name` (``replace`` or ``rename``).

    ``os.<name>(...)`` however its arguments are given; the bare `name`, or the
    name it is bound to, after ``from os import <name>``; and
    ``<path>.<name>(a)`` with one argument and no keyword, which a str's or a
    datetime's ``replace`` never is. Not seen: ``shutil.move`` and
    ``os.renames``, which the package does not call.
    """
    bound = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "os"
        for alias in node.names
        if alias.name == name
    }
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in bound:
            found.append(node)
        elif isinstance(func, ast.Attribute) and func.attr == name:
            owner = func.value
            by_os = isinstance(owner, ast.Name) and owner.id == "os"
            if by_os or (len(node.args) == 1 and not node.keywords):
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


def test_the_scan_sees_a_rename_however_it_is_spelled() -> None:
    tree = ast.parse(
        "import os\n"
        "from os import replace as swap\n"
        "os.replace(a, dst=b)\n"
        "swap(a, b)\n"
        "staged.replace(target)\n"
        "text.replace('old', 'new')\n"
        "stamp.replace(tzinfo=None)\n"
    )

    assert [call.lineno for call in _calls(tree, "replace")] == [3, 4, 5]
