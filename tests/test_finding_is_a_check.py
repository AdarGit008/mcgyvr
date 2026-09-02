"""Closing a finding without fixing it is a dated, strict xfail.

ADR-0037 (#323) bound prose to predicate in two places and this file was the
predicate for both. **Rule 3 is gone with its corpus.** It walked
``docs/decisions/0*.md`` and required every ``tests/<file>::<test>`` a record
named to resolve to a real function. The decision records were archived on
2026-08-25 (``archive/docs/archive/decisions/``) and no longer govern anything, so a
check that enforced their prose would be the archive governing by the back
door. The resolver, its population guard and its canary went with it.

Rule 2 stands, because it is a property of this suite rather than of a
record: every ``xfail`` under ``tests/`` is
``pytest.mark.xfail(strict=True, reason="YYYY-MM-DD: ...")``. ``strict`` keeps
the check live -- an accidental fix turns XPASS and fails the suite until the
marker comes off -- and the dated reason is the record of why. The canaries
below are the proof it can refuse.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
TESTS = _REPO / "tests"

_CHECK_REF = re.compile(r"tests/(test_[a-z0-9_]+\.py)::(test_[a-z0-9_]+)")
_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}: ")


def _xfail_markers(tests: Path) -> list[tuple[str, int, dict[str, ast.expr]]]:
    """Every xfail under ``tests/`` — decorator, bare decorator, or call — with
    its file, line and keyword arguments (empty for a bare decorator)."""
    markers: list[tuple[str, int, dict[str, ast.expr]]] = []

    def _is_xfail(node: ast.expr) -> bool:
        name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        return name == "xfail"

    for module in sorted(tests.glob("test_*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_xfail(node.func):
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                markers.append((module.name, node.lineno, kw))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for deco in node.decorator_list:
                    if not isinstance(deco, ast.Call) and _is_xfail(deco):
                        markers.append((module.name, deco.lineno, {}))
    return markers


def _undisciplined_xfails(tests: Path) -> set[tuple[str, int, str]]:
    """xfail markers that are not strict or carry no dated reason."""
    bad: set[tuple[str, int, str]] = set()
    for file, line, kw in _xfail_markers(tests):
        strict = kw.get("strict")
        if not (isinstance(strict, ast.Constant) and strict.value is True):
            bad.add((file, line, "strict=True is missing"))
        reason = kw.get("reason")
        if not (
            isinstance(reason, ast.Constant)
            and isinstance(reason.value, str)
            and _DATED.match(reason.value)
        ):
            bad.add((file, line, "reason does not begin with an ISO date"))
    return bad


def test_every_xfail_in_the_suite_is_strict_and_carries_a_dated_reason() -> None:
    bad = _undisciplined_xfails(TESTS)
    assert not bad, (
        "ADR-0037 rule 2: an xfail is strict and its reason begins with the "
        f"date it was parked: {sorted(bad)}"
    )


def test_canary_an_undated_xfail_is_refused(tmp_path: Path) -> None:
    (tmp_path / "test_parked.py").write_text(
        "import pytest\n\n\n"
        '@pytest.mark.xfail(strict=True, reason="2026-08-21: owed — why")\n'
        "def test_disciplined() -> None:\n    assert False\n\n\n"
        '@pytest.mark.xfail(reason="2026-08-21: decided — not strict")\n'
        "def test_lax() -> None:\n    assert False\n\n\n"
        '@pytest.mark.xfail(strict=True, reason="someday")\n'
        "def test_undated() -> None:\n    assert False\n\n\n"
        "@pytest.mark.xfail\n"
        "def test_bare() -> None:\n    assert False\n",
        encoding="utf-8",
    )
    bad = _undisciplined_xfails(tmp_path)
    assert {(line, why) for _, line, why in bad} == {
        (9, "strict=True is missing"),
        (14, "reason does not begin with an ISO date"),
        (19, "strict=True is missing"),
        (19, "reason does not begin with an ISO date"),
    }


def test_canary_a_bare_xfail_decorator_is_refused(tmp_path: Path) -> None:
    (tmp_path / "test_bare.py").write_text(
        "import pytest\n\n\n@pytest.mark.xfail\n"
        "def test_bare() -> None:\n    assert False\n",
        encoding="utf-8",
    )
    assert _undisciplined_xfails(tmp_path) == {
        ("test_bare.py", 4, "strict=True is missing"),
        ("test_bare.py", 4, "reason does not begin with an ISO date"),
    }
