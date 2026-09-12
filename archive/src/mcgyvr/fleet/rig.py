"""A rig is its host, hardware and system.

Any hardware or system change renames the rig on purpose: a new name makes
every lock on the old one lapse, loudly, rather than carrying artifacts that
are internally consistent and wrong.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.fleet import ids


def rig_id(host: str, hw: dict[str, Any], system: dict[str, Any]) -> str:
    """``rig-`` plus a digest of the host, hardware and system."""
    return ids.digest("rig-", {"host": host, "hw": hw, "system": system})
