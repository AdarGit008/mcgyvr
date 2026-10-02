"""A link is classed by whether its two cards share a machine, never by a name.

Two cards in one machine talk over its bus and two machines over the network.
Which a link is depends only on whether the two hosts are one host, so a
machine nobody has seen is classed the same way, and a host name's spelling in
capitals does not make it another machine.
"""

from __future__ import annotations

import pytest

from mcgyvr.fleet import links
from tests import machine_shapes as shapes


def test_two_cards_on_one_host_are_a_bus_link() -> None:
    assert links.link_class("box-a.example", "box-a.example") == links.PCIE


def test_two_cards_on_two_hosts_are_a_network_link() -> None:
    assert links.link_class("box-a.example", "box-b.example") == links.NETWORK
    assert links.link_class("box-b.example", "box-a.example") == links.NETWORK


@pytest.mark.parametrize(
    ("a", "b"),
    [("Box-A.Example", "box-a.example"), ("BOX-B.EXAMPLE", "box-b.example")],
)
def test_a_host_names_capitals_do_not_make_it_another_machine(a: str, b: str) -> None:
    assert links.link_class(a, b) == links.PCIE


@pytest.mark.parametrize("machine", shapes.shapes(), ids=lambda m: m.label)
def test_every_invented_machine_is_classed_the_same_way(machine: shapes.Shape) -> None:
    assert links.link_class(machine.host, machine.host) == links.PCIE
    assert links.link_class(machine.host, f"other-{machine.host}") == links.NETWORK


def test_the_classes_are_the_two_a_link_can_be_in() -> None:
    assert set(links.LINK_CLASSES) == {links.PCIE, links.NETWORK}
