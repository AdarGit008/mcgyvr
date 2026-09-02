"""``tests/sweeprows.py`` is a shim over ``tools/runs/rows.py``, not a second parser.

The parser moved: the door (``tools/runs/run.sh``) reads back every artifact a
step wrote with ``rows.read()`` before it exits 0 (BRIEF.md gate 8), and a
parser that lived under ``tests/`` was one that ran only in CI, post-hoc, over
one hard-coded directory. The twelve behaviour tests keep importing
``tests.sweeprows`` — so it stays, as a re-export.

What must not happen is the obvious drift: two files, both called the parser,
one read by the door and one read by the tests, agreeing on 2026-09-02 and on
nothing after. So the shim is held to the module it fronts — every public name,
the same object — rather than trusted to be a copy.
"""

from __future__ import annotations

import importlib
import types

from tests import sweeprows


def _rows() -> types.ModuleType:
    """Imported by name at call time; the ImportError is this test's failure."""
    return importlib.import_module("tools.runs.rows")


def _public(module: types.ModuleType) -> list[str]:
    declared = getattr(module, "__all__", None)
    if declared:
        return sorted(declared)
    return sorted(
        name
        for name, value in vars(module).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    )


def test_read_is_one_function_in_one_place() -> None:
    rows = _rows()
    assert sweeprows.read is rows.read, (
        "tests.sweeprows.read and tools.runs.rows.read are two functions; the "
        "door and the tests would be reading artifacts through different parsers"
    )


def test_the_shim_re_exports_every_public_name_as_the_same_object() -> None:
    rows = _rows()
    names = _public(rows)
    assert names, "tools/runs/rows.py exports nothing public"
    for owed in ("read", "workload_digest", "WORKLOAD_DIGEST", "RIG_FIELDS", "Row"):
        assert owed in names, f"tools/runs/rows.py does not export {owed}"
    missing = [name for name in names if not hasattr(sweeprows, name)]
    assert not missing, f"tests/sweeprows.py does not re-export {missing}"
    different = [
        name for name in names if getattr(sweeprows, name) is not getattr(rows, name)
    ]
    assert not different, (
        f"tests/sweeprows.py carries its own {different} rather than "
        "tools.runs.rows'; a shim re-exports, it does not redefine"
    )
