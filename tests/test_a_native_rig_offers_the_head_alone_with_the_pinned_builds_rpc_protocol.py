"""A native rig offers the head alone, and names the pinned build's RPC protocol.

On macOS or Windows a rig lending with ``launcher: native`` needs no image: it
runs the pinned llama.cpp build, names it as its runtime, offers the head role
alone (its helper serves no rpc worker yet) and drops ``traversal`` until its
helper's UDP is known to pass the host firewall unasked. It offers it only
once it names the hosts its tunnel is reached on and a helper is pinned for
the machine, so the hub never pairs a rig that could not run the session. Any
rig running the pinned build — natively, or as the pinned image — names that
build's llama.cpp RPC protocol in its hello under ``hubwire.RPC_PROTO_FIELD``,
read from the pin module (b11960 speaks 8.0); a rig on another image names
none. On Linux the launcher changes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import protocol, session, sharing, userwg, wgpin
from mcgyvr.serving import llamacpp
from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.native_pool_fakes import as_native_system


def _offer(share: sharing.Sharing, tmp_path: Path) -> protocol.Offer:
    return session.offer(share, fakes.inventory(tmp_path), (fakes.LAN_ADDRESS,), ())


def _hello(offer: protocol.Offer) -> dict[str, Any]:
    frame = json.loads(
        protocol.hello(
            "a" * 32,
            machine_id="rig-example",
            agent_version="0.0.0",
            ram_total_mb=65536,
            ram_free_mb=60000,
            cards=fakes.report().cards,
            offer=offer,
        )
    )
    rig_schema.validate(frame, rig_schema.load(), "#/$defs/AgentMessage")
    body: dict[str, Any] = frame["body"]
    return body


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_a_native_mac_or_windows_rig_offers_the_head_on_the_pinned_build(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_native_system(monkeypatch, system)
    share = fakes.sharing(tmp_path, launcher="native", image=None)
    assert share.native_here()
    offer = _offer(share, tmp_path)
    assert offer.roles == ("head",)
    assert offer.runtime == llamacpp.RUNTIME
    assert f"{llamacpp.REPO}@{llamacpp.TAG}" == llamacpp.RUNTIME
    assert session.TRAVERSAL_FEATURE not in offer.features
    assert set(offer.features) == set(session.FEATURES) - {session.TRAVERSAL_FEATURE}
    capabilities = _hello(offer)["capabilities"]
    assert capabilities[hubwire.RPC_PROTO_FIELD] == {"major": 8, "minor": 0}


def test_the_rpc_protocol_named_is_the_pin_modules() -> None:
    assert hubwire.RpcProto(major=8, minor=0) == llamacpp.RPC_PROTO
    llamacpp.RPC_PROTO.validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"roles": ("worker",)},
        {"models_dir": None},
        {"enabled": False},
        {"endpoints": ()},
    ],
)
def test_a_native_rig_offers_nothing_it_could_not_run(
    changes: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_native_system(monkeypatch, "darwin")
    share = fakes.sharing(tmp_path, launcher="native", image=None, **changes)
    assert share.offered_roles() == ()


def test_a_native_rig_with_no_helper_pinned_for_it_offers_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_native_system(monkeypatch, "windows")
    monkeypatch.setattr(wgpin, "pinned_here", lambda: False)
    share = fakes.sharing(tmp_path, launcher="native", image=None)
    assert share.offered_roles() == ()
    assert _offer(share, tmp_path).roles == ()


def test_a_rig_on_the_pinned_image_names_its_protocol_and_another_image_none(
    tmp_path: Path,
) -> None:
    pinned = _hello(_offer(fakes.sharing(tmp_path, image=llamacpp.IMAGE), tmp_path))
    assert pinned["capabilities"][hubwire.RPC_PROTO_FIELD] == {"major": 8, "minor": 0}
    other = _hello(_offer(fakes.sharing(tmp_path), tmp_path))
    assert hubwire.RPC_PROTO_FIELD not in other["capabilities"]
    assert other["capabilities"]["runtime"] == "engine:rpc"
    assert session.TRAVERSAL_FEATURE in other["capabilities"]["features"]


def test_on_linux_the_native_launcher_changes_nothing_a_session_sees(
    tmp_path: Path,
) -> None:
    share = fakes.sharing(tmp_path, launcher="native")
    assert not share.native_here()
    assert share.offered_roles() == ("head", "worker")
    assert _offer(share, tmp_path) == _offer(fakes.sharing(tmp_path), tmp_path)
    no_image = fakes.sharing(tmp_path, launcher="native", image=None)
    assert no_image.offered_roles() == ()


@pytest.mark.parametrize(
    ("system", "native_host"), [("linux", False), ("darwin", True), ("windows", True)]
)
def test_the_agent_has_a_native_host_on_a_mac_or_windows_alone(
    system: str, native_host: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import verbs

    as_native_system(monkeypatch, system)
    found = verbs.native_host(4242)
    assert isinstance(found, userwg.NativeHost) is native_host


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_the_shipped_pin_table_offers_no_native_session_yet(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the system's name is faked: the helper table is the shipped one,
    which pins no archive yet. The release that adds rows changes this test."""
    from mcgyvr import hostos

    monkeypatch.setattr(hostos, "os_name", lambda: system)
    share = fakes.sharing(tmp_path, launcher="native", image=None)
    assert share.native_here()
    assert share.offered_roles() == ()
