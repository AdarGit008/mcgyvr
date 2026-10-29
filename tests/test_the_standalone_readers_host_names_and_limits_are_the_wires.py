"""The standalone reader's host names and limits are the wire's.

The machine reader ships alone to a rig and cannot import the product, so it
spells the wire's host systems, architectures, version length and resource
name length again, and the share of memory a unified GPU is sized with. Each
spelling is held equal to the one the product defines (`mcgyvr.hubwire`,
`mcgyvr.estimate`), and the system the product's own host seam answers with is
one the reader and the wire know.
"""

from __future__ import annotations

import pytest

from mcgyvr import estimate, hubwire
from mcgyvr.serving import rigscan


def test_the_reader_spells_the_wires_systems_and_architectures() -> None:
    assert tuple(rigscan.SYSTEMS) == hubwire.HOST_OS
    assert set(rigscan.ARCHES.values()) == set(hubwire.HOST_ARCH)
    assert set(rigscan.WINDOWS_ARCHES.values()) == set(hubwire.HOST_ARCH)


def test_the_reader_holds_the_wires_lengths() -> None:
    assert rigscan.VERSION_MAX == hubwire.HOST_VERSION_MAX
    assert rigscan.RESOURCE_NAME_MAX == hubwire.RESOURCE_NAME_MAX


def test_the_reader_sizes_a_unified_gpu_with_the_products_share() -> None:
    assert rigscan.UNIFIED_SHARE == estimate.UNIFIED_SHARE


def test_the_host_seam_answers_with_a_system_the_reader_and_the_wire_know() -> None:
    # The seam (mcgyvr.hostos) arrives with its own pull request; until then
    # there is nothing here to hold.
    hostos = pytest.importorskip("mcgyvr.hostos")
    assert hostos.os_name() in hubwire.HOST_OS
    assert hostos.os_name() in rigscan.SYSTEMS
