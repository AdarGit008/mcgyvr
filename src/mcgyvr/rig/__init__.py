""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcgyvr.rig.agent import Channel

__all__ = ["Channel"]


def __getattr__(name: str) -> type[Channel]:
    if name == "Channel":
        from mcgyvr.rig.agent import Channel

        return Channel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
