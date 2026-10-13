"""A test file does not know where it sits, so it does not count its parents.

``Path(__file__).resolve().parent.parent`` is not an expression about this
repository; it is an expression about the file that holds it. Every file that
carried its own copy was pinned to its own depth under ``tests/`` — and a
suite about to be reorganised into ``unit/``, ``integration/`` and ``e2e/``
is a suite where that depth changes. The failure would not be loud: the
expression still returns a directory, so the test would look for
``src/mcgyvr`` inside ``tests/`` and report that the package is missing. The
files that reached sideways for ``tests/fixtures/`` by way of their own parent
had the same fault one directory over.

So the places are derived in one module, from a marker (:mod:`tests._paths`),
and this file is the check that it stays the only derivation.

Four files are outside the rule, and none of them is a test file the levels
reorganise.

* :mod:`tests._paths` is the derivation.
* ``tests/uninvented_machines.py`` and ``tests/hub_borders.py`` are run **by
  their path** — ``python tests/uninvented_machines.py --compare`` is what CI
  runs — and each puts the checkout on ``sys.path`` only inside its
  ``__main__`` block. A module-level ``from tests._paths import ...`` would
  therefore fail exactly when CI runs them, so each keeps a derivation of its
  own. Neither is collected, and neither moves.
* ``tests/rig_schema.py`` is **copied into a throw-away tree and run from
  there** (``test_a_re_pin_rewrites_every_copy_and_its_digests``), so its
  ``FIXTURES`` must be the fixtures beside *the copy*. Derived from a marker,
  the copy reaches back for the committed fixtures and re-pins them: the first
  run of this change rewrote ``tests/fixtures/hub_protocol_v1.schema.json``
  and ``hub_rider_v1.schema.json`` in place, and 24 contract tests then failed
  on the digest. Counting from its own file is the correct answer for a module
  whose whole purpose is to be moved and still act locally.

Two shapes stay and should. A file that asks where *it* is, to read its own
source or to name itself in a node id, is not deriving a place — it is the
only honest way to say "me". And a climb from an imported package's file,
``Path(mcgyvr.__file__).parent``, asks where the **package** is; moving the
test that asks does not change the answer, and six tests ask it on purpose.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests._paths import REPO, SRC, TESTS, root_above

#: The files allowed their own derivation, and why in the docstring above.
_EXEMPT = frozenset(
    {"_paths.py", "uninvented_machines.py", "hub_borders.py", "rig_schema.py"}
)


def _depth_counted_places(tests: Path) -> set[tuple[str, int]]:
    """Every place a file under ``tests`` climbs from its own ``__file__``."""
    found: set[tuple[str, int]] = set()
    for module in sorted(tests.rglob("*.py")):
        if module.name in _EXEMPT:
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute | ast.Subscript):
                continue
            attribute = node.attr if isinstance(node, ast.Attribute) else ""
            if isinstance(node, ast.Subscript):
                value = node.value
                attribute = value.attr if isinstance(value, ast.Attribute) else ""
            if attribute not in {"parent", "parents"}:
                continue
            # A bare ``__file__``, not ``some_module.__file__``: a climb from
            # an imported package's file asks where the *package* is, which
            # moving this file does not change.
            if "Name(id='__file__'" in ast.dump(node):
                found.add((str(module.relative_to(tests)), node.lineno))
    return found


def test_the_shared_places_are_this_checkout() -> None:
    """The derived places are the ones the gate is run against."""
    assert (REPO / "Makefile").is_file()
    assert (REPO / "pyproject.toml").is_file()
    assert TESTS == REPO / "tests"
    assert (SRC / "__init__.py").is_file()
    assert (TESTS / "_paths.py").is_file()


def test_no_test_file_derives_its_places_from_its_own_depth() -> None:
    counted = _depth_counted_places(TESTS)
    assert not counted, (
        "a file under tests/ walks up from its own __file__, so moving it "
        "would silently move its idea of the repository; import REPO, TESTS "
        f"or SRC from tests._paths instead: {sorted(counted)}"
    )


def test_the_root_is_the_same_answer_from_any_depth(tmp_path: Path) -> None:
    """An invented checkout, asked from three depths, gives one root."""
    root = tmp_path / "repo"
    (root / "tests" / "unit" / "serving").mkdir(parents=True)
    (root / "Makefile").write_text("check:\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert root_above(root / "tests") == root
    assert root_above(root / "tests" / "unit") == root
    assert root_above(root / "tests" / "unit" / "serving") == root


def test_canary_a_checkout_inside_a_checkout_stops_at_the_inner_root(
    tmp_path: Path,
) -> None:
    """A file under a checkout that sits inside another answers the inner one.

    Both markers are demanded rather than ``pyproject.toml`` alone, which many
    a directory that is not a checkout root also holds.
    """
    root = tmp_path / "outer"
    inner = root / "inner" / "tests"
    inner.mkdir(parents=True)
    for place in (root, root / "inner"):
        (place / "Makefile").write_text("check:\n", encoding="utf-8")
        (place / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert root_above(inner) == root / "inner"


def test_canary_a_tree_with_no_markers_is_refused(tmp_path: Path) -> None:
    lonely = tmp_path / "nowhere" / "deep"
    lonely.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no checkout root at or above"):
        root_above(lonely)


def test_canary_a_file_that_counts_parents_is_refused(tmp_path: Path) -> None:
    (tmp_path / "test_counts.py").write_text(
        "from pathlib import Path\n\n"
        "REPO = Path(__file__).resolve().parent.parent\n"
        "ALSO = Path(__file__).resolve().parents[2]\n"
        "NEAR = Path(__file__).parent / 'fixtures'\n"
        "FINE = Path('/x').parent\n"
        "ME = Path(__file__)\n"
        "PACKAGE = Path(mcgyvr.__file__).resolve().parent\n",
        encoding="utf-8",
    )
    assert _depth_counted_places(tmp_path) == {
        ("test_counts.py", 3),
        ("test_counts.py", 4),
        ("test_counts.py", 5),
    }


def test_canary_an_exempt_file_is_not_read(tmp_path: Path) -> None:
    """The three exemptions are by file name, and the check proves it skips."""
    for name in sorted(_EXEMPT):
        (tmp_path / name).write_text(
            "from pathlib import Path\n\nREPO = Path(__file__).resolve().parent\n",
            encoding="utf-8",
        )
    assert _depth_counted_places(tmp_path) == set()
