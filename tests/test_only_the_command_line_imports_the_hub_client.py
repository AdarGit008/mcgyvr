"""Only the command line imports the hub client.

``src/mcgyvr/rig/`` is the agent that publishes this machine as a rig of a hub.
The product is offline and for one user; the hub is an option it can join, and
``mcgyvr rig`` is the one way in. So the rest of the package — everything an
install runs with no hub — imports nothing under ``mcgyvr.rig``:
:data:`~tests.test_the_seam_holds.THE_COMMAND_LINE_ENTRYPOINT` dispatches ``mcgyvr
rig`` and is the one module outside ``rig/`` that may.

One edge breaks that today, and it is written down as data rather than
exempted by module name: :data:`NOT_YET_MOVED`. It may only shrink. An entry
leaves the list in the change that removes the import, and
:func:`test_every_edge_not_yet_moved_is_still_in_the_tree` fails until it does,
so the list cannot keep a slot a later import would fill in silence.

The import walk is the seam test's own (:func:`tests.test_the_seam_holds._imports_in`):
every spelling, wherever the import sits, deferred ones included. The last test
hands the rule a synthetic crossing, to show it catches one.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.test_the_seam_holds import (
    THE_COMMAND_LINE_ENTRYPOINT,
    _imports_in,
    _mcgyvr_imports,
    _the_tree,
)

#: The hub client: the rig agent and everything it holds.
HUB_CLIENT = "mcgyvr.rig"

#: ``(importer, imported)`` edges into the hub client from outside it that the
#: tree still has. Entries may only be removed, never added.
#:
#: * ``sandbox.pooled`` is the sandbox a hub's pooled session runs in, and is
#:   itself imported only from ``rig/``; it reads the WireGuard key shape from
#:   ``rig.sessionwire``. It moves into ``rig/`` (borders plan, step 2d), and
#:   this entry goes with it.
NOT_YET_MOVED: frozenset[tuple[str, str]] = frozenset(
    {
        ("mcgyvr.sandbox.pooled", "mcgyvr.rig.sessionwire"),
    }
)


def _in_hub_client(dotted: str) -> bool:
    return dotted == HUB_CLIENT or dotted.startswith(f"{HUB_CLIENT}.")


def _edges_into_the_hub_client(
    imports: Callable[[str], set[str]] = _mcgyvr_imports,
    modules: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Every ``(importer, imported)`` edge into ``mcgyvr.rig`` from a module
    outside it, the command line left out."""
    edges: set[tuple[str, str]] = set()
    for module in sorted(_the_tree() if modules is None else modules):
        if module == THE_COMMAND_LINE_ENTRYPOINT or _in_hub_client(module):
            continue
        edges.update(
            (module, imported)
            for imported in imports(module)
            if _in_hub_client(imported)
        )
    return edges


def test_nothing_but_the_command_line_imports_the_hub_client() -> None:
    new = sorted(_edges_into_the_hub_client() - NOT_YET_MOVED)
    assert not new, (
        "only mcgyvr.cli may import mcgyvr.rig; these modules reach into the "
        "hub client and must not (NOT_YET_MOVED only shrinks): "
        + ", ".join(f"{a} imports {b}" for a, b in new)
    )


def test_every_edge_not_yet_moved_is_still_in_the_tree() -> None:
    gone = sorted(NOT_YET_MOVED - _edges_into_the_hub_client())
    assert not gone, (
        "these edges no longer exist; take them off NOT_YET_MOVED so the list "
        "stays as short as the tree: " + ", ".join(f"{a} imports {b}" for a, b in gone)
    )


def test_the_command_line_does_import_the_hub_client() -> None:
    """The one sanctioned importer is real: ``mcgyvr rig`` is wired in."""
    assert any(_in_hub_client(m) for m in _mcgyvr_imports(THE_COMMAND_LINE_ENTRYPOINT))


# A core module reaching into the hub client the way the one real edge does,
# and in the `from mcgyvr import rig` spelling a rule that read only module
# paths would walk past.
_CORE_REACHING_IN = '''
def dispatch(endpoint, args):
    """A rung that asks the hub before it dispatches."""
    from mcgyvr.rig import rungs
    from mcgyvr import rig

    return rungs, rig
'''


def test_the_rule_catches_a_core_module_that_reaches_into_the_hub_client() -> None:
    imported = _imports_in(_CORE_REACHING_IN)
    edges = _edges_into_the_hub_client(
        imports=lambda _module: imported,
        modules={"mcgyvr.runner", "mcgyvr.cli", "mcgyvr.rig.verbs"},
    )
    assert edges == {
        ("mcgyvr.runner", "mcgyvr.rig"),
        ("mcgyvr.runner", "mcgyvr.rig.rungs"),
    }
