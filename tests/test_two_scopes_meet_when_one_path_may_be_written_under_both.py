"""`Scope.meets`: whether two contracts could write one file, as far as can be told.

`delegate --run --jobs` never runs two contracts at once whose scopes meet, so
the second starts from what the first landed. A literal path is asked of both
scopes; two globs are taken to meet, which costs only running the two one
after the other.
"""

from __future__ import annotations

import pytest

from mcgyvr.scope import Scope


@pytest.mark.parametrize(
    ("one", "two", "meet"),
    [
        (Scope.of(["pkg/a.py"]), Scope.of(["pkg/a.py"]), True),
        (Scope.of(["pkg/a.py"]), Scope.of(["pkg/b.py"]), False),
        (Scope.of(["pkg/a.py", "pkg/c.py"]), Scope.of(["pkg/b.py", "pkg/c.py"]), True),
        (Scope.of(["pkg/a.py"]), Scope.of(["pkg/*.py"]), True),
        (Scope.of(["pkg/*.py"]), Scope.of(["pkg/a.py"]), True),
        (Scope.of(["lib/a.py"]), Scope.of(["pkg/*.py"]), False),
        (Scope.of(["pkg/a.py"]), Scope.of(["pkg/*.py"], ["pkg/a.py"]), False),
        (Scope.of(["pkg/*.py"]), Scope.of(["lib/**"]), True),
        (Scope.of([]), Scope.of(["pkg/a.py"]), False),
    ],
)
def test_two_scopes_meet_when_some_path_may_be_written_under_both(
    one: Scope, two: Scope, meet: bool
) -> None:
    assert one.meets(two) is meet
    assert two.meets(one) is meet
