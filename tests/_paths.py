"""Where this repository is, derived once and derived by marker.

Every test file that wanted the checkout's root used to walk up from its own
``__file__`` by a counted number of parents — ``parent.parent`` for a file
directly under ``tests/``, ``parents[2]`` for one a directory further down.
That count is not a fact about the repository; it is a fact about where the
file happened to sit. Move the file one directory down and the expression
still evaluates, still returns a directory, and returns the wrong one: the
test then looks for ``src/mcgyvr`` inside ``tests/`` and reports that the
package is missing. The same goes for the files that reached sideways for
``tests/fixtures/`` by way of their own parent.

So the places are derived here, once, from a **marker** rather than a depth:
the nearest ancestor holding both a ``Makefile`` and a ``pyproject.toml``,
which is by definition the directory ``make check`` is run from. That answer
does not depend on where the caller sits, and it does not depend on where this
module sits either — which is the point, since a module that had to stay put
to stay correct would have moved the problem rather than removed it.
"""

from __future__ import annotations

from pathlib import Path

#: The files that mark a checkout's root. Both, because ``pyproject.toml``
#: alone also marks a directory that is not a checkout root.
_MARKERS = ("Makefile", "pyproject.toml")


def root_above(start: Path) -> Path:
    """The nearest directory at or above ``start`` that holds every marker."""
    for candidate in (start, *start.parents):
        if all((candidate / marker).is_file() for marker in _MARKERS):
            return candidate
    raise RuntimeError(
        f"no checkout root at or above {start}: no ancestor holds all of "
        f"{', '.join(_MARKERS)}"
    )


#: The checkout's root — where ``make check`` is run from.
REPO = root_above(Path(__file__).resolve().parent)

#: This suite's own directory: where ``fixtures/`` is, and where it stays when
#: the test files around it move into levels.
TESTS = REPO / "tests"

#: The package under test, as source on disk. A test that reads the installed
#: package asks the package (``Path(mcgyvr.__file__).parent``) instead.
SRC = REPO / "src" / "mcgyvr"
