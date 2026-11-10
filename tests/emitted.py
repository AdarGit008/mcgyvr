"""The compose document ``mcgyvr emit`` writes for one unit, read back.

A test of how one unit is rendered asks :func:`mcgyvr.emit.emit_all`, the entry
the product writes launch specs with, into a directory of its own, so what it
reads is what a rig would be handed; a unit that is refused raises the
``EmitError`` the entry raises, before anything is written.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mcgyvr.emit import emit_all
from mcgyvr.serving import Unit


def compose_of(unit: Unit, *, sleep_mode: bool = False) -> str:
    """The one compose file ``emit_all`` writes for ``unit``, as text."""
    with tempfile.TemporaryDirectory() as root:
        (path,) = emit_all((unit,), Path(root), sleep_mode=sleep_mode)
        return path.read_text(encoding="utf-8")
