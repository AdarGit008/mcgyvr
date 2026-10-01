"""The local orchestrator unit: when a local-only setup must provision one.

The use-case plan distinguishes two deployment models. **Hybrid** drives mcgyvr
from an API-tier orchestrator in the user's session; there is no local
orchestrator to provision. **Local-only** makes mcgyvr the backend, so a
non-chat use case needs an orchestrator *inside* the fleet: a heavy, capable
model with a generous context window, resident first, whose width (slot count)
equals the number of users.

Two rulings decide the answer, both read straight from the plan:

* ``chat`` is a raw un-gated endpoint, so it needs no orchestrator — local-only
  chat is just the ladder serving text.
* local-only for a **non-chat** use case provisions a local orchestrator with
  ``width == users``. Because that unit is resident first and consumes the
  VRAM/RAM the ladder rungs would otherwise use, a single-user setup is
  **flagged, not refused**: the operator is told the trade-off, never blocked.

"Single-user hardware" is read here as ``users == 1`` — the one count the
decision can act on without a hardware model. The flag is a warning to surface,
not a refusal to carry.

This module states the *decision*; the config key that carries ``users`` and
the init/serving mechanics that act on it are built on top, so the policy has
one home and is testable without a fleet.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The one use case that needs no orchestrator: chat is a raw endpoint.
CHAT = "chat"


@dataclass(frozen=True)
class LocalOrchestrator:
    """What a setup must provision to serve the orchestrator role locally."""

    #: Whether a local orchestrator unit is required at all.
    provision: bool
    #: Its width (slot count). ``None`` when no unit is provisioned.
    width: int | None = None
    #: Warn the operator about single-user contention; never a refusal.
    flag_single_user: bool = False


def local_orchestrator(
    *, use_case: str, local_only: bool, users: int
) -> LocalOrchestrator:
    """The local orchestrator a ``use_case`` needs, under a deployment model.

    ``local_only`` is whether every laddered unit is served without a
    credential (:attr:`mcgyvr.config.Config.is_local_only`); the hybrid model
    has an API orchestrator and provisions nothing here.
    """
    if not local_only:
        return LocalOrchestrator(provision=False)
    if use_case == CHAT:
        return LocalOrchestrator(provision=False)
    if users < 1:
        raise ValueError(
            f"users must be at least 1 to provision a local orchestrator, got {users}"
        )
    return LocalOrchestrator(
        provision=True,
        width=users,
        flag_single_user=users == 1,
    )
