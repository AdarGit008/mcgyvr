"""Telemetry runs no code from the lab: it loads nothing by path and names no lab tree.

A row is told what run it belongs to by ``$MCGYVR_RUN_TAGS``
(``tests/test_a_row_carries_the_run_tags_its_environment_names.py``). Before
that, :mod:`mcgyvr.telemetry` found the development checkout around the package
and executed the bench's product module in it to stamp each row with a round.
That fallback was deleted once the lab set the variable itself (borders plan
2a, 2026-10-08), and this holds the module to having no way back to it: no
loader, no builtin that runs text as code, no walk up from a ``__file__`` to
the tree around the package, and no string naming the lab's trees or the
bench's module. Read from the module's syntax rather than its prose.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TELEMETRY = Path(__file__).resolve().parents[1] / "src" / "mcgyvr" / "telemetry.py"

#: What loading or running code by path is spelled with: modules, and the
#: functions read off them, seen as a name, an attribute or an import.
_LOADERS = frozenset(
    {
        "importlib",
        "runpy",
        "exec_module",
        "spec_from_file_location",
        "module_from_spec",
        "import_module",
        "run_path",
        "run_module",
    }
)

#: The builtins that run code from text, seen as a bare name only: an
#: attribute named ``compile`` is ``re.compile`` as often as not.
_BUILTIN_LOADERS = frozenset({"exec", "eval", "compile", "__import__"})

#: What walks up from a module's own file to the tree around it.
_UPWARD = frozenset({"parent", "parents"})

#: A string that names the lab's trees or the bench's module. ``bench`` is
#: bounded by letters only, so ``bench_product`` is caught and ``workbench`` not.
_LAB_WORDS = re.compile(r"\btools\b|(?<![A-Za-z])bench(?![A-Za-z])|\bproduct\.py\b")


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


def _names_file(node: ast.AST) -> bool:
    """Whether ``node`` reads a ``__file__``: bare, or off a module."""
    return any(
        (isinstance(n, ast.Name) and n.id == "__file__")
        or (isinstance(n, ast.Attribute) and n.attr == "__file__")
        for n in ast.walk(node)
    )


def _reaches(node: ast.AST, prose: set[int]) -> str | None:
    """What ``node`` names that reaches the checkout, or ``None``."""
    if isinstance(node, ast.Import | ast.ImportFrom):
        names = [alias.name for alias in node.names]
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        hit = [n for n in names if n.split(".")[0] in _LOADERS]
        return f"import {hit[0]}" if hit else None
    if isinstance(node, ast.Name) and (
        node.id in _LOADERS or node.id in _BUILTIN_LOADERS
    ):
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in _LOADERS:
        return node.attr
    # A file's own path walked up is the tree around the package: data read
    # from there needs no loader and no lab word to be the checkout's.
    if (
        isinstance(node, ast.Attribute)
        and node.attr in _UPWARD
        and _names_file(node.value)
    ):
        return f"{node.attr} of __file__"
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in prose
        and _LAB_WORDS.search(node.value)
    ):
        return repr(node.value)
    return None


def _references(source: str) -> list[tuple[int, str]]:
    """Every reference to the checkout in ``source``: ``(line, what)``."""
    tree = ast.parse(source)
    prose = _docstrings(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        what = _reaches(node, prose)
        if what is not None:
            found.append((getattr(node, "lineno", 0), what))
    return found


def test_the_lab_words_are_words() -> None:
    """``bench_product`` is the bench's; ``workbench`` is nobody's."""
    assert _LAB_WORDS.search("bench_product")
    assert not _LAB_WORDS.search("workbench")


def test_the_scan_sees_a_loader_by_path() -> None:
    """The scan is not passing because it reads nothing: the deleted shape is seen,
    and the same words in prose are not."""
    lab = "tools"
    seen = {
        what
        for _, what in _references(
            f'"""prose naming {lab}, a bench and product.py is not read"""\n'
            "import importlib.util\n"
            'SLOT = "bench_product"\n'
            "def load(source):\n"
            f'    """And {lab} here is prose too."""\n'
            "    spec = importlib.util.spec_from_file_location(SLOT, source)\n"
            "    spec.loader.exec_module(importlib.util.module_from_spec(spec))\n"
            f'    return source / "{lab}"\n'
            "ROOT = Path(mcgyvr.__file__).resolve().parents[2]\n"
            "HERE = Path(__file__).parent\n"
            "BLOBS = sink.parent\n"
        )
    }
    assert seen == {
        "import importlib.util",
        "importlib",
        "spec_from_file_location",
        "module_from_spec",
        "exec_module",
        "'bench_product'",
        "'tools'",
        "parents of __file__",
        "parent of __file__",
    }, seen


def test_telemetry_reaches_no_checkout_at_all() -> None:
    found = [
        f"telemetry.py:{line}: {what}"
        for line, what in _references(TELEMETRY.read_text(encoding="utf-8"))
    ]
    assert not found, (
        "telemetry reaches the development checkout; a row's run is named by "
        "$MCGYVR_RUN_TAGS, not looked up:\n" + "\n".join(found)
    )
