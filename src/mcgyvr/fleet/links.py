"""The two classes of link a pair of cards can talk over, and how a pair is classed.

A link joins two cards. Two cards in one machine talk over that machine's bus
(PCIE) and two cards in different machines talk over the network (NETWORK).
Which class a link is depends only on whether the two hosts are one machine,
so a host nobody has seen is classed the same way, and a host name's capitals
do not make it another machine.
"""

from __future__ import annotations

#: The class of a link whose two cards sit in one machine and talk over its bus.
PCIE = "pcie"
#: The class of a link whose two cards sit in two machines and talk over the network.
NETWORK = "network"
#: Every class a link can be in, in the order they are offered and named in messages.
LINK_CLASSES: tuple[str, ...] = (PCIE, NETWORK)


def link_class(host_a: str, host_b: str) -> str:
    """The class of the link between two cards, given the hosts they sit on.

    The two hosts are one machine, and so the link is a bus link, exactly when
    their names match once case is folded; any other pair is a network link.
    """
    return PCIE if host_a.casefold() == host_b.casefold() else NETWORK
