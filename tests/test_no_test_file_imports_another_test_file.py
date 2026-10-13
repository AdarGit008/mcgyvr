"""A test module is a leaf: nothing imports it.

Forty-four test modules lent helpers to seventy others by importing the test
module they sat in -- ``from tests.test_drive import _driven``. That holds
only while both files are in one package under one name, and it binds a file
that is about to move into ``unit/``, ``integration/`` or ``e2e/`` to a file
that may move somewhere else. It also asks pytest for something it does not
promise: a test module imported under its own name as well as collected is a
module whose collection-time code runs twice.

A helper two tests share belongs in a module that is not a test. The ones
this rule evicted went to a module named for their topic -- ``tests/doors.py``,
``tests/fleetlocks.py``, ``tests/reads.py``, ``tests/relays.py``,
``tests/rungs.py``, ``tests/drives.py`` and the rest beside them.

A pytest fixture is a case of its own: pytest names it, so a fixture that
moved would leave behind an import that no reader of the code ever names.
What a shared fixture builds moved; each module declares the fixture.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests._paths import REPO

#: The one import of a test module that is not a borrowed helper: the subject
#: under test. ``test_the_docgen_guard_never_writes_the_committed_setup``
#: runs the docgen guard and watches what it does to the checkout, and it
#: reaches it through its module on purpose, so the guard is free to change
#: how it plants its sentinel without that file following it.
SUBJECTS_UNDER_TEST = frozenset(
    {("test_the_docgen_guard_never_writes_the_committed_setup.py", "tests.test_docgen")}
)


def _imports_of_tests(tests: Path) -> set[tuple[str, int, str]]:
    """Every import, anywhere under ``tests``, of a module named ``test_*``."""
    found: set[tuple[str, int, str]] = set()
    for module in sorted(tests.rglob("*.py")):
        relative = str(module.relative_to(tests))
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(p.startswith("test_") for p in alias.name.split(".")):
                        found.add((relative, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                where = node.module or ""
                if any(p.startswith("test_") for p in where.split(".")):
                    found.add((relative, node.lineno, where))
                for alias in node.names:
                    if alias.name.startswith("test_"):
                        found.add((relative, node.lineno, f"{where}.{alias.name}"))
    return {
        (where, line, what)
        for where, line, what in found
        if (where, what) not in SUBJECTS_UNDER_TEST
    }


def test_no_file_under_tests_imports_a_test_module() -> None:
    imported = _imports_of_tests(REPO / "tests")
    assert not imported, (
        "a test module is imported by another file; move the shared helper "
        "into a module named for its topic (tests/doors.py, tests/rungs.py) "
        f"or into a conftest fixture: {sorted(imported)}"
    )


def test_the_one_module_imported_as_a_subject_is_still_imported_that_way() -> None:
    """The exemption is for an import that exists; it is not a spare licence."""
    for where, what in sorted(SUBJECTS_UNDER_TEST):
        text = (REPO / "tests" / where).read_text(encoding="utf-8")
        head, _, tail = what.rpartition(".")
        assert f"from {head} import {tail}" in text, (
            f"{where} no longer imports {what}; drop it from "
            "SUBJECTS_UNDER_TEST rather than leaving the hole open"
        )


def test_canary_each_shape_of_importing_a_test_module_is_refused(
    tmp_path: Path,
) -> None:
    (tmp_path / "test_borrows.py").write_text(
        "import tests.test_drive\n"
        "from tests.test_drive import _driven\n"
        "from tests import test_drive\n"
        "from tests import drives\n"
        "from tests._paths import REPO\n",
        encoding="utf-8",
    )
    assert _imports_of_tests(tmp_path) == {
        ("test_borrows.py", 1, "tests.test_drive"),
        ("test_borrows.py", 2, "tests.test_drive"),
        ("test_borrows.py", 3, "tests.test_drive"),
    }
