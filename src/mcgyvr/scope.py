"""The one canonical path matcher.

Scope is the check that makes autonomy safe: a worker may only touch what its
contract allows. That guarantee is only as trustworthy as the matcher behind
it, so there is exactly **one** matcher, and it is imported wherever a path is
tested against a contract's scope — the gate, deterministic tool resolution,
and output application. A second, subtly different matcher elsewhere is a
defect, not an optimization (see #34).

Semantics, stated once so every caller shares them:

* A **literal** segment matches itself exactly.
* ``*`` (single-segment wildcard) matches any run of characters *within one
  path segment* — it never crosses a ``/``.
* ``**`` (recursive wildcard) matches across segments. ``src/**`` matches
  everything under ``src/``; ``**/*.py`` matches a ``.py`` file at any depth,
  including the repository root.
* **Forbidden** patterns override **allowed** ones. A path that a forbid
  pattern matches is out of scope even if an allow pattern also matches it —
  the safe direction for an autonomous gate.
* An empty allow list permits nothing. Scope fails closed: a contract that
  declares no writable surface grants none.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Scope:
    """A contract's writable surface: what a worker may touch, and may not.

    ``allow`` and ``forbid`` are glob patterns with the semantics documented
    in this module. Construct once from a contract and thread it into every
    check; instances are immutable and hashable.
    """

    allow: tuple[str, ...]
    forbid: tuple[str, ...] = ()

    @classmethod
    def of(
        cls,
        allow: Iterable[str],
        forbid: Iterable[str] = (),
    ) -> Scope:
        """Build a scope from any iterables of patterns."""
        return cls(allow=tuple(allow), forbid=tuple(forbid))

    def permits(self, path: str) -> bool:
        """Whether ``path`` is inside this scope.

        A path is permitted when some allow pattern matches it and no forbid
        pattern does. Forbid wins ties by construction.
        """
        norm = _normalize(path)
        if any(_matches(pattern, norm) for pattern in self.forbid):
            return False
        return any(_matches(pattern, norm) for pattern in self.allow)

    def forbidden(self, path: str) -> bool:
        """Whether ``path`` is explicitly forbidden, regardless of allows."""
        norm = _normalize(path)
        return any(_matches(pattern, norm) for pattern in self.forbid)

    def violations(self, paths: Iterable[str]) -> tuple[str, ...]:
        """The paths that fall outside this scope, in the order given.

        This is what the gate reports: a change outside allowed scope fails by
        name, so every offending path is named rather than a single boolean.
        """
        return tuple(p for p in paths if not self.permits(p))


def _normalize(path: str) -> str:
    """Repo-relative, forward-slashed, no leading ``./`` — the matcher's domain.

    Paths reaching scope come from the change set (already in this form) and
    from contracts (authored by hand, so tolerated loosely). Backslashes are
    folded to forward slashes so a Windows-style pattern or path still matches.
    """
    p = path.replace("\\", "/").lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    return p


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    """Translate a glob pattern to an anchored regex, compiled once.

    The cache matters: a gate run tests every changed path against every
    pattern, and the pattern set is tiny and reused, so compilation is paid
    once per distinct pattern per process.
    """
    return re.compile(_glob_to_regex(_normalize(pattern)))


def _glob_to_regex(pattern: str) -> str:
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            # Zero or more leading segments: `**/foo` matches `foo` and `a/b/foo`.
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            # `src/**` -> `src/.*`: everything at or below this point.
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


# --- where a named path lands on disk ---------------------------------------


class OutsideTreeError(ValueError):
    """A repository-relative name that would read or write outside its tree."""


def enters_git_dir(path: str) -> bool:
    """Whether ``path`` has a ``.git`` component, in any case.

    A ``.git`` directory is not content: host git reads it as its own
    configuration and hooks, so bytes landing there are commands host git
    runs. Case-folded because a case-insensitive filesystem reads ``.GIT`` as
    the same directory.
    """
    return any(part.lower() == ".git" for part in PurePosixPath(path).parts)


def inside(root: Path, named: str) -> Path:
    """``named`` as a path under ``root``, refused if it could land anywhere else.

    Every host-side read or write of a worker's target goes through this, in
    the sandbox workspace and in the repository a delivery commits into alike.
    Three ways a name reaches somewhere else are refused before anything is
    touched:

    * it is absolute, or ``..`` walks it out of ``root``;
    * it is, or crosses, a symlink. ``git archive`` recreates tracked symlinks,
      and ``.resolve()`` follows them, so a tracked ``target -> ~/.bashrc``
      would steer the write into the user's shell profile. The literal
      components are walked with ``lstat`` semantics (``Path.is_symlink``)
      instead;
    * it enters a ``.git`` directory (:func:`enters_git_dir`).
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
