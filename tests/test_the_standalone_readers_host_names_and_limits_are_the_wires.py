"""The standalone reader's host names and limits are the wire's.

The machine reader ships to a rig as one program assembled from the modules it
imports (`mcgyvr.serving.shipped`), the wire's names among them, so it takes the
host systems, architectures, version length and resource name length from the
product's wire module (`mcgyvr.hubwire`) and the host seam (`mcgyvr.hostos`)
takes the systems from it too. Each is held to the wire's here, and the system
the host seam answers with is one the reader and the wire know. The share of
memory a unified GPU is sized with is the reader's alone
(`rigscan.UNIFIED_SHARE`).
"""

from __future__ import annotations

import pytest

from mcgyvr import hubwire
from mcgyvr.serving import rigscan


def test_the_reader_spells_the_wires_systems_and_architectures() -> None:
    assert tuple(rigscan.HOST_OS) == hubwire.HOST_OS
    assert set(rigscan.ARCHES.values()) == set(hubwire.HOST_ARCH)
    assert set(rigscan.WINDOWS_ARCHES.values()) == set(hubwire.HOST_ARCH)


def test_the_reader_holds_the_wires_lengths() -> None:
    assert rigscan.HOST_VERSION_MAX == hubwire.HOST_VERSION_MAX
    assert rigscan.RESOURCE_NAME_MAX == hubwire.RESOURCE_NAME_MAX


def test_the_host_seam_answers_with_a_system_the_reader_and_the_wire_know() -> None:
    # The seam (mcgyvr.hostos) arrives with its own pull request; until then
    # there is nothing here to hold.
    hostos = pytest.importorskip("mcgyvr.hostos")
    assert hostos.os_name() in hubwire.HOST_OS
    assert hostos.os_name() in rigscan.HOST_OS
