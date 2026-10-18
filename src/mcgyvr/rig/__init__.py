"""Package root for the rig side of mcgyvr.

Nothing is imported eagerly here: importing any ``mcgyvr.rig`` submodule runs
this file first, so an eager import of ``mcgyvr.rig.agent`` (and the commands,
hardware, protocol and websocket modules it pulls in) would be paid on every
one of those imports. ``Channel`` is instead resolved lazily by the module
``__getattr__`` below, so ``from mcgyvr.rig import Channel`` works unchanged
while the agent module is only imported when that name is first accessed, and
not while the agent module is in the middle of importing from this package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcgyvr.rig.agent import Channel

__all__ = ["Channel"]


def __getattr__(name: str) -> type[Channel]:
    """Import and return ``Channel`` on first attribute access; raise for any
    other name.

    Only ``"Channel"`` is resolvable here; every other name raises
    ``AttributeError`` naming the module, as normal module attribute lookup
    would.
    """
    if name == "Channel":
        from mcgyvr.rig.agent import Channel

        return Channel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
