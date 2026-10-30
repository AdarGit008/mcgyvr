"""Setup's start step names what it starts, and on macOS and Windows says why
no firewall asks.

On Linux the interactive setup starts the serving containers, word for word as
before. On a Mac or a Windows machine the units of this machine run as the
pinned native llama.cpp build (``launcher: native``), so the question names
native servers and, before it, two notes say what the first start does: it
fetches the pinned build and checks its sha256 (clearing macOS's quarantine
flag), and a native server listens on 127.0.0.1 alone, the rig agent relaying
to it, so neither system's firewall asks. Remote rigs stay containers.
"""

from __future__ import annotations

import pytest

from mcgyvr.cli.commands.setup import _native_notes, _start_question
from mcgyvr.serving import llamacpp
from tests.hostos_fakes import as_system


def test_linux_starts_the_serving_containers_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "linux")
    assert (
        _start_question(("localhost", "rig-b"))
        == "Start the serving containers on localhost, rig-b? [y/N] "
    )
    assert _native_notes(("localhost",)) == ()


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_this_mac_or_windows_machine_starts_native_servers(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    assert (
        _start_question(("localhost",))
        == "Start the native llama.cpp servers on localhost? [y/N] "
    )


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_remote_rigs_beside_this_machine_stay_containers(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    assert _start_question(("localhost", "rig-b")) == (
        "Start the servers (native here, containers on rig-b) on "
        "localhost, rig-b? [y/N] "
    )
    assert (
        _start_question(("rig-b",)) == "Start the serving containers on rig-b? [y/N] "
    )
    assert _native_notes(("rig-b",)) == ()


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_the_notes_say_the_pinned_build_and_the_loopback(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    notes = " ".join(_native_notes(("localhost",)))
    assert llamacpp.TAG in notes
    assert "sha256" in notes
    assert "127.0.0.1" in notes
    assert "relay" in notes
    assert "firewall" in notes
    assert ("quarantine" in notes) == (system == "darwin")
    assert "--host" not in notes
