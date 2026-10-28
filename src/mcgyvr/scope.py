"""Path scope matching and tree-containment checks.

`Scope` holds two glob pattern lists and answers whether a repository-relative
path is writable: a path is permitted only when it matches an allow pattern and
matches no forbid pattern, so an empty allow list permits nothing (fail closed).

Patterns are normalized (`\\` folded to `/`, leading `/` and `./` dropped) and
compiled to anchored regular expressions, cached per pattern, where `**/`
matches zero or more segments, `**` matches anything, and `*` stops at a `/`.

The same module also guards filesystem access: `enters_git_dir` reports paths
that touch a `.git` component, and `inside` validates a named path against a
root directory, raising `OutsideTreeError` for absolute paths, `.git` entries,
symlink crossings, and paths that climb out of the root.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Scope:
    """Immutable allow/forbid glob lists deciding which paths a contract grants."""

    allow: tuple[str, ...]
    forbid: tuple[str, ...] = ()

    @classmethod
    def of(
        cls,
        allow: Iterable[str],
        forbid: Iterable[str] = (),
    ) -> Scope:
        """Build a `Scope`, freezing both pattern iterables into tuples."""
        return cls(allow=tuple(allow), forbid=tuple(forbid))

    def permits(self, path: str) -> bool:
        """Return True only if `path` matches an allow pattern and no forbid pattern."""
        norm = _normalize(path)
        if any(_matches(pattern, norm) for pattern in self.forbid):
            return False
        return any(_matches(pattern, norm) for pattern in self.allow)

    def forbidden(self, path: str) -> bool:
        """Return True if `path` matches any forbid pattern, ignoring the allow list."""
        norm = _normalize(path)
        return any(_matches(pattern, norm) for pattern in self.forbid)

    def violations(self, paths: Iterable[str]) -> tuple[str, ...]:
        """Return the paths that `permits` rejects, in the order they were given."""
        return tuple(p for p in paths if not self.permits(p))

    def meets(self, other: Scope) -> bool:
        """Whether some path may be written under both scopes, as far as can be told.

        A literal allow entry of either is asked of both. Two globs are taken to
        meet, since whether two globs share a path is not worked out here, and
        a wrong "they meet" costs no more than two contracts run one after the
        other rather than at once.
        """
        for one, two in ((self, other), (other, self)):
            for entry in one.allow:
                if (
                    not _GLOB.search(entry)
                    and one.permits(entry)
                    and two.permits(entry)
                ):
                    return True
        return any(_GLOB.search(e) for e in self.allow) and any(
            _GLOB.search(e) for e in other.allow
        )


def _normalize(path: str) -> str:
    """Fold backslashes to slashes and strip leading slashes and `./` prefixes."""
    p = path.replace("\\", "/").lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    return p


#: What makes an allow entry a glob rather than one path: `*` is the only
#: character `_glob_to_regex` does not match literally.
_GLOB = re.compile(r"\*")


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    """Return the anchored regex for `pattern`, compiled once per normalized pattern."""
    return re.compile(_glob_to_regex(_normalize(pattern)))


def _glob_to_regex(pattern: str) -> str:
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            # Recursive prefix: zero or more whole segments, so `**/x` also matches `x`.
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            # Recursive wildcard: any run of characters, crossing segment boundaries.
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return f"^{''.join(out)}$"


def _matches(pattern: str, path: str) -> bool:
    return _compiled(pattern).match(path) is not None


# Containment helpers: `enters_git_dir` and `inside` keep reads and writes within
# a root directory, rejecting `.git` components, symlinks, and `..` escapes.


class OutsideTreeError(ValueError):
    """A path names something outside the tree rooted at the given directory."""


def enters_git_dir(path: str) -> bool:
    """Return True if any path component is `.git`, compared case-insensitively."""
    return any(part.lower() == ".git" for part in PurePosixPath(path).parts)


def inside(root: Path, named: str) -> Path:
    """Resolve `named` relative to `root`, raising `OutsideTreeError` if it escapes.

    The returned path is joined onto the resolved root; the final component is
    not resolved, but every prefix walked is checked with `is_symlink`.
    """
    if PurePosixPath(named).is_absolute() or Path(named).is_absolute():
        raise OutsideTreeError(
            f"{named!r} is absolute; a path in the tree is relative to it"
        )
    if enters_git_dir(named):
        raise OutsideTreeError(
            f"{named!r} is inside a .git directory, which host git reads as "
            f"configuration and hooks; nothing is written there"
        )
    anchor = root.resolve()
    walked = anchor
    for part in Path(named).parts:
        if part in ("", "."):
            continue
        if part == "..":
            walked = walked.parent
            continue
        walked = walked / part
        if walked.is_symlink():
            raise OutsideTreeError(
                f"{named!r} crosses the symlink {part!r}; a symlink is not a "
                f"file the tree holds, so nothing is read or written through it"
            )
    if anchor not in walked.parents:
        raise OutsideTreeError(f"{named!r} is outside the tree")
    return walked
