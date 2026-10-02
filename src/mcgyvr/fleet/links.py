"""What kind of link two cards share, decided by what any machine has.

Two cards in one machine talk over that machine's bus; two machines talk over
the network between them. That is all a link's class says, and it is decided by
whether the two cards sit in one machine, never by a machine's name, so a
machine nobody here has seen is classed the same way. The numbers of each class
(its bandwidth and latency) are estimates shipped with mcgyvr that the user's
own setting or reading replaces; they live in :mod:`mcgyvr.derived`, keyed by
the classes named here.

This module imports nothing from mcgyvr: :mod:`mcgyvr.derived` imports it, to
take :data:`LINK_CLASSES` as the key space of the link numbers.
"""

from __future__ import annotations

#: Two cards in one machine: the link is that machine's bus.
PCIE = "pcie"
#: Two cards in two machines: the link is the network between them.
NETWORK = "network"
#: Every class a link can be in; each link number states a value for each.
LINK_CLASSES: tuple[str, ...] = (PCIE, NETWORK)


def link_class(host_a: str, host_b: str) -> str:
    """The class of the link between a card on ``host_a`` and a card on ``host_b``.

    A link is classed by what any machine has (two cards in one machine talk
    over the bus; two machines talk over the network), never by a machine's
    name. Host names are the names a scan and an address use, so they are
    compared without regard to case: a name is the same machine however it is
    capitalised.
    """
    return PCIE if host_a.casefold() == host_b.casefold() else NETWORK
