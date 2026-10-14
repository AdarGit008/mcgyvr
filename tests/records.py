"""A machine recorded the way the product records one: as its rig file.

The one record of a machine is its rig file (:mod:`mcgyvr.serving.rigfile`),
which keeps one reading of it whole. A test that hands ``emit`` or the door a
machine it has measured writes that machine's rig file with :func:`rig_file`,
into the folder ``MCGYVR_RIGS`` names (:data:`RIGS_ENV`).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcgyvr.scan import Scan

#: The variable that names the folder of rig files.
RIGS_ENV = "MCGYVR_RIGS"


def rig_file(scan: Scan, rig: str = "") -> str:
    """The text of a rig file whose one reading is ``scan``, under ``rig``
    (the machine's own host name unless said)."""
    from mcgyvr.serving import rigfile

    name = rig or scan.machine.host or "rig"
    reading = json.loads(scan.to_json())
    return rigfile.from_reading(name, reading, "2026-10-14T00:00:00Z").to_json()
