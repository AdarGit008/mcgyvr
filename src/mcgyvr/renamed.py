"""Names a file may still carry from before a rename, read for one release.

A key or value that was renamed is read under its old name for one release,
so a file written before the rename still loads, and each read says so with a
:class:`RenamedWarning` naming the old and the new spelling: rewrite the file
before the release after, which refuses the old name. Nothing else is read
under an old name; a name that was retired outright is refused where it is
read.
"""

from __future__ import annotations

import warnings


class RenamedWarning(UserWarning):
    """A file was read under a name it should no longer use."""


def warn_renamed(where: str, old: str, new: str) -> None:
    """Warn that `where` says `old`, read as `new` for this release only."""
    warnings.warn(
        f"{where}: `{old}` is now `{new}`; the old name is read for this "
        f"release only, so write `{new}`",
        RenamedWarning,
        stacklevel=3,
    )
