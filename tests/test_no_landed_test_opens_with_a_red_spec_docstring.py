"""No landed test still opens with a RED spec docstring.

A RED spec docstring declares that the behaviour it pins does not exist yet.
Once the behaviour lands the declaration is stale: the assertions are live
guards and stay, and the RED paragraph goes
(``mcgyvr-lab/records/plans/fleet-identity.md`` §10).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent

#: A RED spec opens a line with the word ``RED`` (any punctuation after it).
RED_SPEC = re.compile(r"^[ \t]*RED\b", re.MULTILINE)


def _opens_with_red_spec(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring = ast.get_docstring(tree, clean=False) or ""
    return RED_SPEC.search(docstring) is not None


def test_no_landed_test_still_opens_with_a_red_spec_docstring() -> None:
    stale = sorted(
        str(path.relative_to(TESTS))
        for path in TESTS.rglob("*.py")
        if _opens_with_red_spec(path)
    )
    assert not stale, (
        f"{len(stale)} test module(s) still open with a RED spec docstring. "
        f"Drop the RED paragraph, keep the assertions: {stale}"
    )
