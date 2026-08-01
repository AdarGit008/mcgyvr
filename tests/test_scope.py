"""Scope is the matcher that makes worker autonomy safe.

These tests pin the semantics every caller shares: single-segment vs recursive
wildcards, forbid beating allow, and fail-closed behaviour on an empty allow
list. A regression here is a hole in the property the gate depends on — that a
worker cannot touch what its contract did not grant.
"""

from __future__ import annotations

import pytest

from mcgyvr.scope import Scope


def test_literal_paths_match_exactly() -> None:
    scope = Scope.of(["src/app.py"])
    assert scope.permits("src/app.py")
    assert not scope.permits("src/app_test.py")
    assert not scope.permits("src/app.pyc")


def test_single_segment_wildcard_does_not_cross_slash() -> None:
    scope = Scope.of(["src/*.py"])
    assert scope.permits("src/app.py")
    assert not scope.permits("src/nested/app.py"), "* must stop at a path segment"


def test_recursive_wildcard_crosses_segments() -> None:
    scope = Scope.of(["src/**"])
    assert scope.permits("src/app.py")
    assert scope.permits("src/a/b/c/deep.py")
    assert not scope.permits("tests/app.py")


def test_leading_recursive_wildcard_matches_any_depth_including_root() -> None:
    scope = Scope.of(["**/*.py"])
    assert scope.permits("app.py"), "root-level file must match **/"
    assert scope.permits("src/pkg/app.py")
    assert not scope.permits("src/app.txt")


def test_forbid_overrides_allow() -> None:
    """A path matched by both an allow and a forbid is out of scope."""
    scope = Scope.of(allow=["src/**"], forbid=["src/secrets/**"])
    assert scope.permits("src/app.py")
    assert not scope.permits("src/secrets/keys.py")
    assert scope.forbidden("src/secrets/keys.py")


def test_forbid_wins_even_for_an_exact_allow() -> None:
    scope = Scope.of(allow=["config.py"], forbid=["config.py"])
    assert not scope.permits("config.py")


def test_empty_allow_permits_nothing() -> None:
    """Fail closed: no declared surface grants no writable surface."""
    scope = Scope.of([])
    assert not scope.permits("anything.py")


def test_violations_names_every_offender_in_order() -> None:
    scope = Scope.of(allow=["src/**"], forbid=["src/gen/**"])
    changed = ["src/a.py", "docs/readme.md", "src/gen/out.py", "src/b.py"]
    assert scope.violations(changed) == ("docs/readme.md", "src/gen/out.py")


def test_paths_are_normalized_before_matching() -> None:
    scope = Scope.of(["src/**"])
    assert scope.permits("./src/app.py")
    assert scope.permits("src\\app.py"), "backslash paths fold to forward slashes"


def test_star_matches_within_but_not_across_a_dotfile_segment() -> None:
    scope = Scope.of(["*.py"])
    assert scope.permits("app.py")
    assert not scope.permits("pkg/app.py")


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("**", "a/b/c.py", True),
        ("**", "top.py", True),
        ("tests/**/*.py", "tests/unit/test_x.py", True),
        ("tests/**/*.py", "tests/test_x.py", True),
        ("tests/**/*.py", "src/test_x.py", False),
        ("a/*/c.py", "a/b/c.py", True),
        ("a/*/c.py", "a/b/d/c.py", False),
    ],
)
def test_wildcard_matrix(pattern: str, path: str, expected: bool) -> None:
    assert Scope.of([pattern]).permits(path) is expected
