"""Only the command line imports the hub client.

``src/mcgyvr/rig/`` is the agent that publishes this machine as a rig of a hub.
The product is offline and for one user; the hub is an option it can join, and
``mcgyvr rig`` is the one way in. So the offline core
(:func:`tests.hub_borders.in_core`: everything under ``src/mcgyvr/`` but
``cli.py`` and ``rig/``) reaches nothing under ``mcgyvr.rig``, and nothing of
``mcgyvr.cli`` either, which imports it and would carry it in. Every tracked
Python file of the core is read: the modules, and the scripts under
``serving/gate-scripts/`` that no import reaches but that run on their own.
Two ways in are read:

* an import, by the seam test's own walk
  (:func:`tests.test_the_seam_holds._imports_in`): every spelling, wherever it
  sits, deferred ones included;
* a string that is nothing but a dotted name under one of them, the shape
  ``importlib.import_module`` and ``python -m`` are handed. A name inside
  prose (a docstring's ``:mod:`` reference) is not one.

No edge breaks the rule today, and none is exempted by module name. The
edges that did were written down as data,
:data:`tests.hub_borders.IMPORTS_NOT_YET_MOVED`, which may only shrink and is
now empty: an entry left the list in the change that removed the import, and
:func:`test_every_edge_not_yet_moved_is_still_in_the_tree` failed until it did.
That a pull request did not add to the list is CI's to see
(``tests/hub_borders.py --compare``).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable

from tests.hub_borders import (
    HUB_CLIENT,
    IMPORTS_NOT_YET_MOVED,
    SRC,
    core_files,
)
from tests.test_the_seam_holds import (
    THE_COMMAND_LINE_ENTRYPOINT,
    _dotted_name,
    _imports_in,
    _mcgyvr_imports,
)

#: What the core may not reach: the hub client, and the command line that
#: imports it.
OUT_OF_BOUNDS = (HUB_CLIENT, THE_COMMAND_LINE_ENTRYPOINT)

_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")


def _out_of_bounds(dotted: str) -> bool:
    return any(dotted == p or dotted.startswith(f"{p}.") for p in OUT_OF_BOUNDS)


def _reached(source: str, package: str) -> set[str]:
    """What ``source`` imports, and the dotted names it holds as whole strings."""
    named = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _DOTTED.fullmatch(node.value)
    }
    return _imports_in(source, package=package) | named


def _edges(files: Iterable[tuple[str, str, str]]) -> set[tuple[str, str]]:
    """``(importer, reached)`` for each ``(importer, package, source)`` that
    reaches out of bounds."""
    return {
        (importer, reached)
        for importer, package, source in files
        for reached in _reached(source, package)
        if _out_of_bounds(reached)
    }


def _the_core() -> list[tuple[str, str, str]]:
    """Every tracked Python file of the core: a module by its dotted name and
    the package its relative imports resolve in, a script by its path."""
    found = []
    for rel in core_files():
        if not rel.endswith(".py"):
            continue
        path = SRC / rel
        source = path.read_text(encoding="utf-8")
        dotted = _dotted_name(path)
        if dotted is None:
            found.append((rel, "mcgyvr", source))
            continue
        package = dotted if path.name == "__init__.py" else dotted.rpartition(".")[0]
        found.append((dotted, package, source))
    return found


def test_nothing_but_the_command_line_imports_the_hub_client() -> None:
    new = sorted(_edges(_the_core()) - IMPORTS_NOT_YET_MOVED)
    assert not new, (
        "only mcgyvr.cli may import mcgyvr.rig, and nothing of the core may "
        "import mcgyvr.cli; these reach out of bounds "
        "(IMPORTS_NOT_YET_MOVED only shrinks): "
        + ", ".join(f"{a} reaches {b}" for a, b in new)
    )


def test_every_edge_not_yet_moved_is_still_in_the_tree() -> None:
    gone = sorted(IMPORTS_NOT_YET_MOVED - _edges(_the_core()))
    assert not gone, (
        "these edges no longer exist; take them off IMPORTS_NOT_YET_MOVED so "
        "the list stays as short as the tree: "
        + ", ".join(f"{a} reaches {b}" for a, b in gone)
    )


def test_the_rule_holds_with_no_exception() -> None:
    """Only the command line imports the hub client: no edge of the core is
    excused, not even one written down."""
    assert not IMPORTS_NOT_YET_MOVED
    assert _edges(_the_core()) == set()


def test_the_core_read_holds_the_scripts_no_import_reaches() -> None:
    read = {importer for importer, _, _ in _the_core()}
    assert "serving/gate-scripts/serve-fetch.py" in read
    assert "mcgyvr.runner" in read
    assert not any(_out_of_bounds(name) for name in read)


def test_the_command_line_does_import_the_hub_client() -> None:
    """The one sanctioned importer is real: ``mcgyvr rig`` is wired in."""
    imported = _mcgyvr_imports(THE_COMMAND_LINE_ENTRYPOINT)
    assert any(
        name == HUB_CLIENT or name.startswith(f"{HUB_CLIENT}.") for name in imported
    )


# A core module reaching into the hub client the way the last real edge did,
# in the `from mcgyvr import rig` spelling a rule that read only module paths
# would walk past, by name for importlib, and through the command line.
_CORE_REACHING_IN = '''
"""A docstring may name :mod:`mcgyvr.rig.rungs` and :mod:`mcgyvr.cli`."""
import importlib


def dispatch(endpoint, args):
    """A rung that asks the hub before it dispatches."""
    from mcgyvr.rig import rungs
    from mcgyvr import rig
    from mcgyvr.cli import main

    return rungs, rig, main, importlib.import_module("mcgyvr.rig.verbs")
'''


def test_the_rule_catches_each_way_into_the_hub_client() -> None:
    edges = _edges([("serving/gate-scripts/x.py", "mcgyvr", _CORE_REACHING_IN)])
    assert edges == {
        ("serving/gate-scripts/x.py", "mcgyvr.rig"),
        ("serving/gate-scripts/x.py", "mcgyvr.rig.rungs"),
        ("serving/gate-scripts/x.py", "mcgyvr.rig.verbs"),
        ("serving/gate-scripts/x.py", "mcgyvr.cli"),
    }
