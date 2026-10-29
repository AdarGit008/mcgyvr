"""A shipped program carries the modules and the names it imports, and nothing else.

``mcgyvr.serving.shipped`` builds a program from its main module, the whole
modules named, and the names the main module imports from any other ``mcgyvr``
module, read off its own import lines: those go as that module's plain
constants alone (no annotation, no call), so the wire's names reach the reader
from ``mcgyvr.hubwire`` itself, and a constant that could mean something else
outside its module is refused at ship time. On the rig nothing installed is
imported in their place: the packages are registered empty. The same checkout
builds the same bytes, and the wire's system names are the ones the door tells
rigs apart by.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from mcgyvr import hubwire
from mcgyvr.serving import gatelib, shipped


def test_the_reader_takes_the_wire_names_rigscan_imports() -> None:
    wanted = shipped.names_imported("mcgyvr.serving.rigscan", ("mcgyvr.hostos",))
    assert {"HOST_OS", "HOST_VERSION_MAX", "RESOURCE_NAME_MAX"} <= set(
        wanted["mcgyvr.hubwire"]
    )
    assert set(wanted["mcgyvr.fleet.roots"]) == {"HOME_DIR", "HOME_ENV"}


def test_a_constant_ships_as_its_value_alone() -> None:
    text = shipped.constants("mcgyvr.hubwire", ["HOST_OS", "RESOURCE_KINDS"])
    namespace: dict[str, object] = {}
    exec(text, namespace)
    assert namespace["HOST_OS"] == hubwire.HOST_OS
    assert namespace["RESOURCE_KINDS"] == hubwire.RESOURCE_KINDS
    assert "tuple[" not in text  # the annotation stays home


def test_a_constant_that_is_not_plain_is_refused() -> None:
    with pytest.raises(shipped.ShipError, match="not built from literals"):
        shipped.constants("mcgyvr.hubwire", ["RESOURCE_NAME"])  # a re.compile
    with pytest.raises(shipped.ShipError, match="assigns no constant"):
        shipped.constants("mcgyvr.hubwire", ["NOT_THERE"])


def test_nothing_installed_is_imported_in_a_shipped_programs_place() -> None:
    program = shipped.program(
        "mcgyvr.hubwire", modules=("mcgyvr.hostos",), tail="import mcgyvr.config\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-"],
        input=shipped.packed(program),
        capture_output=True,
        check=False,
    )
    assert b"ModuleNotFoundError" in done.stderr
    assert b"mcgyvr.config" in done.stderr


def test_one_checkout_builds_the_same_bytes() -> None:
    assert shipped.packed(shipped.reader()) == shipped.packed(shipped.reader())
    assert shipped.native() == shipped.native()


def test_the_door_tells_rigs_apart_by_the_wires_system_names() -> None:
    assert (gatelib.LINUX, gatelib.DARWIN, gatelib.WINDOWS) == hubwire.HOST_OS
