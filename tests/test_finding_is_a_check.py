"""A finding is a check, and the record that names a check names a real one.

ADR-0037 (#323) binds prose to predicate in two places, and this file is the
predicate for both.

Rule 3: an append-only record names the check that enforces it, in the form
``tests/<file>::<test>``. A name that resolves to nothing is the defect the
rule exists to prevent — prose asserting a guard that is not there. The
resolver walks ``docs/decisions/0*.md`` only (the ADR prices that choice),
finds every ``tests/test_*.py::test_*`` reference, and requires each to name
a function defined in that file, found by parsing the module rather than by
grepping it, so a name inside a comment or a string does not count as a test.

Rule 2: closing a finding without fixing it is
``pytest.mark.xfail(strict=True, reason="YYYY-MM-DD: ...")``. ``strict`` is
what keeps the check live — an accidental fix turns XPASS and fails the
suite until the marker comes off — and the dated reason is the record of
why. Every ``xfail`` under ``tests/`` is held to both. At the time of
writing there are none, so the canary is the only proof the check can
reject; the first ``xfail`` to land (#328's conflicts) is this check's first
real member.

Populations are read through an injectable directory, the
tests/test_decisions.py idiom: each check takes its corpus as an argument,
and a canary hands it a synthetic one to show that the check can refuse.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
DECISIONS = _REPO / "docs" / "decisions"
TESTS = _REPO / "tests"

_CHECK_REF = re.compile(r"tests/(test_[a-z0-9_]+\.py)::(test_[a-z0-9_]+)")
_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}: ")


def _named_checks(decisions: Path) -> dict[str, set[tuple[str, str]]]:
    """Every ``tests/<file>::<test>`` a decision record names, by record."""
    found: dict[str, set[tuple[str, str]]] = {}
    for record in sorted(decisions.glob("0*.md")):
        refs = set(_CHECK_REF.findall(record.read_text(encoding="utf-8")))
        if refs:
            found[record.name] = refs
    return found


def _test_functions(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    }


def _unresolved(decisions: Path, tests: Path) -> set[tuple[str, str, str]]:
    """(record, file, test) triples that name a test which does not exist."""
    missing: set[tuple[str, str, str]] = set()
    cache: dict[str, set[str]] = {}
    for record, refs in _named_checks(decisions).items():
        for file, test in refs:
            if file not in cache:
                path = tests / file
                cache[file] = _test_functions(path) if path.exists() else set()
            if test not in cache[file]:
                missing.add((record, file, test))
    return missing


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


def test_every_check_a_decision_record_names_resolves_to_a_test_in_the_suite() -> None:
    missing = _unresolved(DECISIONS, TESTS)
    assert not missing, (
        "a decision record names a check that does not exist — ADR-0037 rule 3 "
        f"binds prose to a real predicate: {sorted(missing)}"
    )


def test_the_resolver_has_a_population() -> None:
    # ADR-0037 is the first record to name a check in the `::` form; a
    # resolver over an empty population proves nothing.
    named = _named_checks(DECISIONS)
    assert any(name.startswith("0037-") for name in named), sorted(named)


def test_canary_a_record_naming_a_missing_check_is_refused(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions"
    tests = tmp_path / "tests"
    decisions.mkdir()
    tests.mkdir()
    (tests / "test_real.py").write_text(
        "def test_present() -> None:\n    pass\n\n\n"
        "def helper() -> None:\n    '''tests/test_real.py::test_in_a_docstring'''\n",
        encoding="utf-8",
    )
    (decisions / "0001-honest.md").write_text(
        "Checks: tests/test_real.py::test_present\n", encoding="utf-8"
    )
    (decisions / "0002-stale.md").write_text(
        "Checks: tests/test_real.py::test_renamed_away and "
        "tests/test_gone.py::test_present and "
        "tests/test_real.py::test_in_a_docstring\n",
        encoding="utf-8",
    )
    assert _unresolved(decisions, tests) == {
        ("0002-stale.md", "test_real.py", "test_renamed_away"),
        ("0002-stale.md", "test_gone.py", "test_present"),
        ("0002-stale.md", "test_real.py", "test_in_a_docstring"),
    }


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
