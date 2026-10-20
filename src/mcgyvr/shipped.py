"""Where a shipped data file is read from: the package's copy, else a checkout's.

A built wheel carries each shipped file inside the package, under
``mcgyvr/data``; a source checkout, which has no such copy, keeps it in the
repository's own ``data/`` directory beside ``src/``. The packaged copy is
looked for first, so an installed mcgyvr finds the file inside itself.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

#: Where a checkout keeps its shipped files: the repository root's data folder.
CHECKOUT_DATA = Path(__file__).resolve().parents[2] / "data"


def packaged(name: str) -> Path:
    """Where the package's own copy of `name` is, whether or not it exists."""
    return Path(str(resources.files("mcgyvr") / "data" / name))


def shipped_file(name: str, *, checkout: Path | None = None) -> Path | None:
    """The shipped file `name`: the packaged copy, else the checkout's, else None.

    `checkout` is the checkout's data folder, :data:`CHECKOUT_DATA` when not
    given; a caller that keeps its own patchable copy of it passes that.
    """
    inside = packaged(name)
    if inside.is_file():
        return inside
    there = (checkout if checkout is not None else CHECKOUT_DATA) / name
    return there if there.is_file() else None
