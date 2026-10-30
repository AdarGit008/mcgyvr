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
    wanted = shipped.imports("mcgyvr.serving.rigscan", ("mcgyvr.hostos",))
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


def test_an_import_of_something_not_carried_is_refused_unless_the_door_alone_runs_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ("mcgyvr.serving.native", "parse", "yaml") in shipped.DOOR_ONLY
    monkeypatch.setattr(shipped, "DOOR_ONLY", frozenset())
    with pytest.raises(shipped.ShipError, match="imports yaml, which is not shipped"):
        shipped.native()


def test_the_native_launcher_carries_the_loopback_names_not_the_door() -> None:
    assert "mcgyvr.serving.gatelib" not in shipped.NATIVE_MODULES
    wanted = shipped.imports("mcgyvr.serving.native", shipped.NATIVE_MODULES)
    assert wanted == {"mcgyvr.serving.gatelib": ["LOCAL_RIGS"]}
    namespace: dict[str, object] = {}
    exec(shipped.constants("mcgyvr.serving.gatelib", ["LOCAL_RIGS"]), namespace)
    assert namespace["LOCAL_RIGS"] == gatelib.LOCAL_RIGS


def test_an_argument_holding_a_nul_or_a_quote_is_refused_not_shipped() -> None:
    with pytest.raises(ValueError, match="NUL"):
        gatelib.ship(gatelib.WINDOWS, b"", ("a\0b",))
    with pytest.raises(ValueError, match="NUL"):
        gatelib.ship(gatelib.LINUX, b"", ("a\0b",))
    with pytest.raises(ValueError, match="single quote"):
        gatelib.ship(gatelib.DARWIN, b"", ("it's",))


def test_a_door_only_import_is_allowed_by_its_full_name_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = ("mcgyvr.serving.native", "parse", "mcgyvr.config.LAUNCHER_NATIVE")
    assert entry in shipped.DOOR_ONLY
    monkeypatch.setattr(shipped, "DOOR_ONLY", shipped.DOOR_ONLY - {entry})
    with pytest.raises(shipped.ShipError, match=r"mcgyvr\.config\.LAUNCHER_NATIVE"):
        shipped.native()


def test_a_door_only_import_in_another_function_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = shipped.source

    def source(name: str) -> str:
        text = real(name)
        if name == "mcgyvr.serving.native":
            text += (
                "\n\ndef _on_the_rig() -> None:\n"
                "    from mcgyvr.serving import CARDS_KEY  # noqa: F401\n"
            )
        return text

    monkeypatch.setattr(shipped, "source", source)
    with pytest.raises(shipped.ShipError, match=r"mcgyvr\.serving\.CARDS_KEY"):
        shipped.native()


@pytest.mark.parametrize(
    ("system", "command", "keepalive"),
    [
        ("linux", "python3 - mcgyvr-fetch", False),
        ("darwin", "python3 -I -B - mcgyvr-fetch", True),
        ("windows", gatelib.WINDOWS_SHIP, True),
    ],
)
def test_a_fetch_keeps_ssh_alive_on_a_mac_or_windows_rig_and_linux_as_it_was(
    system: str, command: str, keepalive: bool
) -> None:
    from mcgyvr.serving import fetchlist

    sent = fetchlist.shipment(
        system, system, (), "https://hub.example", "HF_TOKEN", "s3cret"
    )
    assert (sent.command, sent.keepalive) == (command, keepalive)
    assert "s3cret" not in sent.command
    if system == "linux":
        assert sent.stdin == fetchlist.payload(
            (), "https://hub.example", "HF_TOKEN", "s3cret"
        )


def test_a_fetch_onto_this_windows_machine_is_the_posix_line_it_runs_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import hostos
    from mcgyvr.serving import fetchlist

    monkeypatch.setattr(hostos, "os_name", lambda: "windows")
    sent = fetchlist.shipment(
        gatelib.shipping_os("localhost"),
        gatelib.rig_system("localhost"),
        (),
        "https://hub.example",
        "HF_TOKEN",
        None,
    )
    assert sent.command == fetchlist.REMOTE_COMMAND
