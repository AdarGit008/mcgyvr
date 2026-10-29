"""A native rig offers the head alone, and names the pinned build's RPC protocol.

On macOS or Windows a rig lending with ``launcher: native`` needs no image: it
runs the pinned llama.cpp build, names it as its runtime, offers the head role
alone (its helper serves no rpc worker yet) and drops ``traversal`` until its
helper's UDP is known to pass the host firewall unasked. Any rig running the
pinned build — natively, or as the pinned image — names that build's llama.cpp
RPC protocol in its hello under ``hubwire.RPC_PROTO_FIELD``, read from the pin
module (b11960 speaks 8.0), so the hub pairs heads and workers by
``hubwire.rpc_compatible``; a rig on another image names none. On Linux the
launcher changes nothing. The setting round-trips through the lending file
and is left out of it while it is the default.

The helper itself is pinned like llama.cpp: one archive name per system and
architecture, made in one place, and nothing fetched that is not pinned. A
native head binds the loopback alone, whatever the session planned.
"""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import (
    pooled,
    protocol,
    session,
    sharing,
    tunnel,
    userwg,
    wghelper,
    wgpin,
)
from mcgyvr.serving import llamacpp, native
from mcgyvr.serving.release import Release, ReleaseError
from tests import hostos_fakes, rig_schema
from tests import rig_pool_fakes as fakes


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
    hostos_fakes.as_system(monkeypatch, system)
    share = fakes.sharing(tmp_path, launcher="native", image=None)
    assert share.native_here()
    offer = _offer(share, tmp_path)
    assert offer.roles == ("head",)
    assert offer.runtime == llamacpp.RUNTIME == "ggml-org/llama.cpp@b11960"
    assert "traversal" not in offer.features
    assert set(offer.features) == set(session.FEATURES) - {"traversal"}
    capabilities = _hello(offer)["capabilities"]
    assert capabilities[hubwire.RPC_PROTO_FIELD] == {"major": 8, "minor": 0}


def test_the_rpc_protocol_named_is_the_pin_modules() -> None:
    assert hubwire.RpcProto(major=8, minor=0) == llamacpp.RPC_PROTO
    llamacpp.RPC_PROTO.validate()


def test_a_native_rig_lends_no_worker_and_no_head_without_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostos_fakes.as_system(monkeypatch, "darwin")
    worker = fakes.sharing(tmp_path, launcher="native", roles=("worker",))
    assert worker.offered_roles() == ()
    no_models = fakes.sharing(None, launcher="native", image=None)
    assert no_models.offered_roles() == ()
    off = fakes.sharing(tmp_path, launcher="native", enabled=False)
    assert off.offered_roles() == ()


def test_a_rig_on_the_pinned_image_names_its_protocol_and_another_image_none(
    tmp_path: Path,
) -> None:
    pinned = _hello(_offer(fakes.sharing(tmp_path, image=llamacpp.IMAGE), tmp_path))
    assert pinned["capabilities"][hubwire.RPC_PROTO_FIELD] == {"major": 8, "minor": 0}
    other = _hello(_offer(fakes.sharing(tmp_path), tmp_path))
    assert hubwire.RPC_PROTO_FIELD not in other["capabilities"]
    assert other["capabilities"]["runtime"] == "engine:rpc"
    assert "traversal" in other["capabilities"]["features"]


def test_on_linux_the_native_launcher_changes_nothing_a_session_sees(
    tmp_path: Path,
) -> None:
    share = fakes.sharing(tmp_path, launcher="native")
    assert not share.native_here()
    assert share.offered_roles() == ("head", "worker")
    assert _offer(share, tmp_path) == _offer(fakes.sharing(tmp_path), tmp_path)
    no_image = fakes.sharing(tmp_path, launcher="native", image=None)
    assert no_image.offered_roles() == ()


def test_the_launcher_round_trips_and_the_default_stays_unwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    written = sharing.save(sharing.Sharing(enabled=True, launcher="native"))
    assert json.loads(written.read_text())["launcher"] == "native"
    assert sharing.load().launcher == "native"
    sharing.save(sharing.Sharing(enabled=True))
    assert "launcher" not in json.loads(written.read_text())
    assert sharing.load().launcher == "docker"
    with pytest.raises(sharing.SharingError, match="launcher"):
        sharing.read({"launcher": "podman"})
    with pytest.raises(sharing.SharingError, match="launcher"):
        sharing.read({"launcher": ["native"]})


@pytest.mark.parametrize(
    ("system", "arch", "name"),
    [
        ("darwin", "arm64", "mcgyvr-wg-v0.1.0-darwin-arm64.tar.gz"),
        ("windows", "x86_64", "mcgyvr-wg-v0.1.0-windows-x86_64.zip"),
        ("linux", "arm64", "mcgyvr-wg-v0.1.0-linux-arm64.tar.gz"),
    ],
)
def test_each_helper_archive_is_named_once_by_system_and_architecture(
    system: str, arch: str, name: str
) -> None:
    assert wgpin.asset_name(system, arch) == name


def test_every_pinned_helper_archive_is_named_by_the_rule_with_its_digest() -> None:
    names = {
        wgpin.asset_name(system, arch)
        for system in hubwire.HOST_OS
        for arch in hubwire.HOST_ARCH
    }
    for asset in wgpin.RELEASE.assets:
        assert asset.name in names
        assert len(asset.sha256) == 64 and asset.sha256 == asset.sha256.lower()
        assert asset.bytes > 0
    assert wgpin.RELEASE.tag == wgpin.TAG and wgpin.RELEASE.repo == wgpin.REPO


def test_no_helper_is_fetched_for_a_system_nothing_is_pinned_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(wgpin, "RELEASE", Release(wgpin.REPO, wgpin.TAG, ()))
    with pytest.raises(ReleaseError, match="no pinned mcgyvr-wg"):
        wgpin.helper("darwin", "arm64")
    with pytest.raises(ReleaseError):
        wgpin.asset_name("plan9", "arm64")
    assert not (tmp_path / "home").exists()


def test_a_native_prepare_with_no_pinned_helper_fails_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.native_pool_fakes import make_native_pool

    rig = make_native_pool(tmp_path, monkeypatch)
    monkeypatch.setattr(rig.host, "_helper", userwg.pinned_helper)
    monkeypatch.setattr(native, "machine_arch", lambda: "arm64")
    try:
        assert (
            rig.pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
        )
        rig.pool.wait_for("session_status", "failed")
        status = rig.pool.box.of_type("session_status")[-1]["body"]
        assert status["error_code"] == "tunnel_failed"
        assert "no pinned mcgyvr-wg" in status["log_excerpt"]
    finally:
        rig.pool.sessions.close()
        rig.echo.close()


def _head_spec(bind: str) -> pooled.HeadSpec:
    return pooled.HeadSpec(
        session_id="s1",
        image=llamacpp.RUNTIME,
        binary="/app/llama-server",
        gpus=(0,),
        models_dir=Path("/models"),
        model="m.gguf",
        name="m.gguf",
        ctx=4096,
        n_gpu_layers=99,
        devices=("CUDA0",),
        tensor_split=(1,),
        rpc=(),
        bind=bind,
        memory_mb=8192,
    )


@pytest.mark.parametrize("bind", ["198.51.100.2", "0.0.0.0"])
def test_a_native_head_never_binds_other_than_the_loopback(
    bind: str, tmp_path: Path
) -> None:
    engine = userwg.Engine(program=tmp_path / "llama-server", backend=llamacpp.CUDA)
    host = userwg.NativeHost(agent_pid=1, helper=lambda: [], engine=lambda: engine)
    host._runs["s1"] = userwg._Run(
        session_id="s1",
        helper=wghelper.Helper(["/x"], log=tmp_path / "h.log"),
        api_port=18080,
    )
    with pytest.raises(pooled.PoolError, match=r"binds 127\.0\.0\.1"):
        host.start_head(_head_spec(bind))


def test_an_operators_listening_address_is_refused_by_the_native_units_rule() -> None:
    with pytest.raises(pooled.PoolError, match=r"127\.0\.0\.1 alone"):
        userwg._native_block("mcgyvr-pool-x-head", ["--host", "0.0.0.0"], {}, (0,))
    block = userwg._native_block("mcgyvr-pool-x-head", ["-m", "m.gguf"], {}, (0,))
    command = block["command"]
    assert command[command.index("--host") + 1] == "127.0.0.1"


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_a_mac_or_windows_rig_reads_no_interface_with_linuxs_ioctl(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostos_fakes.as_system(monkeypatch, system)
    assert tunnel.read_interfaces() == ()


def test_a_native_hello_names_the_loopback_as_its_tunnel_address() -> None:
    assert ipaddress.IPv4Interface(userwg.HELLO_ADDRESS).ip.is_loopback


@pytest.mark.parametrize(
    ("system", "native_host"), [("linux", False), ("darwin", True), ("windows", True)]
)
def test_the_agent_has_a_native_host_on_a_mac_or_windows_alone(
    system: str, native_host: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import verbs

    hostos_fakes.as_system(monkeypatch, system)
    found = verbs.native_host(4242)
    assert isinstance(found, userwg.NativeHost) is native_host
