""

from __future__ import annotations

#
PCIE = "pcie"
#
NETWORK = "network"
#
LINK_CLASSES: tuple[str, ...] = (PCIE, NETWORK)


def link_class(host_a: str, host_b: str) -> str:
    ""
    return PCIE if host_a.casefold() == host_b.casefold() else NETWORK
