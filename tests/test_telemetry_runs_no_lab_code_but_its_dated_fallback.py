"""Telemetry runs no code from the lab, except one dated fallback, fenced here.

A row is told what run it belongs to by ``$MCGYVR_RUN_TAGS``
(``tests/test_a_row_carries_the_run_tags_its_environment_names.py``). Before
that, :mod:`mcgyvr.telemetry` found the development checkout around the package
and executed its ``tools/bench/product.py`` to stamp each row with a round. That
path stays for one step, so the lab can set the variable first (borders plan 2a,
2026-10-08), and it is the only place in the module allowed to load a file by
path or to name ``tools/`` or the bench.

Two tests, read from the module's syntax rather than its prose:

* the guard: every such reference sits inside the fallback — the slot constant,
  ``_checkout``, ``_bench_product``, ``_product_revision`` and the
  ``importlib`` import — and the fallback is reached only from ``_identity``;
* a strict, dated xfail: the module has no such reference at all. It turns
  green when the fallback is deleted, and the marker comes off then, with the
  guard.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TELEMETRY = Path(__file__).resolve().parents[1] / "src" / "mcgyvr" / "telemetry.py"

#: The fallback: the top-level statements allowed to reach the checkout.
FALLBACK = frozenset(
    {"_PRODUCT_SLOT", "_checkout", "_bench_product", "_product_revision"}
)

#: The one caller allowed to reach into :data:`FALLBACK`, and what it may name.
CALLER = "_identity"
CALLED = "_product_revision"

#: What loading code by path is spelled with.
_LOADERS = frozenset(
    {"importlib", "exec_module", "spec_from_file_location", "module_from_spec"}
)

#: A string that names the lab's trees or the bench's module.
_LAB_WORDS = re.compile(r"tools|bench|product\.py")


def _docstrings(tree: ast.Module) -> set[int]:
    """The ids of every docstring node: prose, not code."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _name(statement: ast.stmt) -> str | None:
    """The name a top-level statement defines, or ``None``."""
    if isinstance(statement, ast.FunctionDef | ast.ClassDef):
        return statement.name
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
        return target.id if isinstance(target, ast.Name) else None
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return statement.target.id
    return None


def _reaches(node: ast.AST, prose: set[int]) -> str | None:
    """What ``node`` names that reaches the checkout, or ``None``."""
    if isinstance(node, ast.Import | ast.ImportFrom):
        names = [alias.name for alias in node.names]
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        hit = [n for n in names if n.split(".")[0] in _LOADERS]
        return f"import {hit[0]}" if hit else None
    if isinstance(node, ast.Name) and (node.id in _LOADERS or node.id in FALLBACK):
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in _LOADERS:
        return node.attr
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in prose
        and _LAB_WORDS.search(node.value)
    ):
        return repr(node.value)
    return None


def _references() -> list[tuple[str | None, int, str]]:
    """Every reference to the checkout: ``(top-level name, line, what)``."""
    tree = ast.parse(TELEMETRY.read_text(encoding="utf-8"))
    prose = _docstrings(tree)
    found: list[tuple[str | None, int, str]] = []
    for statement in tree.body:
        owner = _name(statement)
        if owner in FALLBACK:
            found.append((owner, statement.lineno, f"defines {owner}"))
        for node in ast.walk(statement):
            what = _reaches(node, prose)
            if what is not None:
                found.append((owner, getattr(node, "lineno", 0), what))
    return found


def _allowed(owner: str | None, what: str) -> bool:
    if owner in FALLBACK:
        return True
    if owner == CALLER:
        return what == CALLED
    # The import the fallback loads with, at the top of the module.
    return owner is None and what == "import importlib.util"


def test_only_the_dated_fallback_reaches_the_checkout() -> None:
    stray = [
        f"telemetry.py:{line} ({owner or 'module'}): {what}"
        for owner, line, what in _references()
        if not _allowed(owner, what)
    ]
    assert not stray, (
        "telemetry reaches the checkout outside its dated fallback; a row's "
        "run is named by $MCGYVR_RUN_TAGS, not looked up:\n" + "\n".join(stray)
    )


def test_the_guard_sees_the_fallback() -> None:
    """The guard is not passing because it reads nothing."""
    seen = {what for _, _, what in _references()}
    assert {"import importlib.util", "exec_module", "'tools'", CALLED} <= seen, seen


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "2026-10-08: owed — borders plan 2a. The checkout fallback "
        "(_bench_product, which executes tools/bench/product.py) stays one "
        "step so the lab can set $MCGYVR_RUN_TAGS first. Delete it, and this "
        "marker and the guard above come off."
    ),
)
def test_telemetry_reaches_no_checkout_at_all() -> None:
    found = [f"telemetry.py:{line}: {what}" for _, line, what in _references()]
    assert not found, "\n".join(found)
