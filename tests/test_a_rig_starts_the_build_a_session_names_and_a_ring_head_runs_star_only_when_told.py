"""A rig starts the build a session names, and a ring head runs star only when told.

A rig offers the builds it can start (``capabilities.runtimes``, feature
``runtime_select``) only when one is the ring build
(:data:`mcgyvr.serving.llamacpp.RING`): the ring pin ships empty, so a rig
offers nothing new and its hello is the one it always sent. With the pin
filled in, a native rig offers it when the pin has an archive for it, and a
container rig when its owner names the ring build's image by the pin's own
digest (``ring_image``); any other reference names no build the rig knows,
and a start of the ring build is refused naming why. A start that names a
build runs that build (its image and programs, or its archives, fetched only
then); a start naming a build the rig does not offer is refused. A ring
build's head runs star only (``GGML_RPC_STAR_ONLY=1``) when ``head_start``
says ``ring`` false, and nothing changes for another build. A native ring
head names each worker as the other workers reach it
(``GGML_RPC_PEER_ENDPOINTS``), since it reaches them through loopback forwards.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.hostos import WINDOWS
from mcgyvr.rig import pooled, protocol, session, sharing, userwg
from mcgyvr.serving import llamacpp, native, rigscan
from mcgyvr.serving.release import Asset, Release
from tests import native_pool_fakes as native_fakes
from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.rig_pool_fakes import Pool, make_pool, prepared

RING_DIGEST = "sha256:" + "a" * 64
RING_IMAGE = f"registry.example/llama-ring@{RING_DIGEST}"
MIRROR = f"mirror.example/ring@{RING_DIGEST}"
RING_HEAD = "/opt/ring/llama-server"
RING_WORKER = "/opt/ring/ggml-rpc-server"
RING_ARCHIVE = "llama-r1-bin-win-cuda-13.4-x64.zip"


def _pin(**changes: Any) -> llamacpp.Pin:
    fields: dict[str, Any] = {
        "id": llamacpp.RING_ID,
        "repo": "example/llama-ring",
        "tag": "r1",
        "rpc_proto": (7, 3),
        "ring": True,
        "release": Release(
            repo="example/llama-ring",
            tag="r1",
            assets=(Asset(RING_ARCHIVE, 10, "0" * 64),),
        ),
        "builds": (
            llamacpp._build(
                WINDOWS, llamacpp.X86_64, llamacpp.CUDA, RING_ARCHIVE, tag="r1"
            ),
        ),
        "image": RING_IMAGE,
        "head_binary": RING_HEAD,
        "worker_binary": RING_WORKER,
    }
    fields.update(changes)
    return llamacpp.Pin(**fields)


@pytest.fixture
def ring(monkeypatch: pytest.MonkeyPatch) -> llamacpp.Pin:
    pin = _pin()
    monkeypatch.setattr(llamacpp, "RING", pin)
    return pin


def _offer(tmp_path: Path, **changes: Any) -> Any:
    return session.offer(
        fakes.sharing(tmp_path, **changes),
        fakes.inventory(tmp_path),
        (fakes.LAN_ADDRESS,),
        (),
        fakes.report(),
    )


# --- what a rig offers ---------------------------------------------------------------


def test_the_ring_pin_ships_empty_so_no_rig_offers_a_ring_build(tmp_path: Path) -> None:
    assert llamacpp.RING is None
    for changes in ({}, {"ring_image": RING_IMAGE}, {"image": llamacpp.IMAGE}):
        offer = _offer(tmp_path, **changes)
        assert offer.runtimes == ()
        assert session.RUNTIME_SELECT_FEATURE not in offer.features
    assert session.RUNTIME_SELECT_FEATURE not in session.FEATURES


def test_a_rig_with_todays_sharing_file_offers_what_it_always_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for changes in ({}, {"image": llamacpp.IMAGE}, {"ring_links": True}):
        before = _offer(tmp_path, **changes)
        monkeypatch.setattr(llamacpp, "RING", _pin())
        assert _offer(tmp_path, **changes) == before
        monkeypatch.setattr(llamacpp, "RING", None)


def test_a_container_rig_offers_the_ring_build_its_owner_names_by_digest(
    tmp_path: Path, ring: llamacpp.Pin
) -> None:
    for named in (RING_IMAGE, MIRROR):
        offer = _offer(tmp_path, ring_image=named)
        assert offer.runtimes == (
            hubwire.Runtime(id=llamacpp.IMAGE_ID, runtime="engine:rpc"),
            hubwire.Runtime(
                id=llamacpp.RING_ID,
                runtime="example/llama-ring@r1",
                rpc_proto=hubwire.RpcProto(major=7, minor=3),
                ring=True,
            ),
        )
        assert offer.features[-1] == session.RUNTIME_SELECT_FEATURE
        assert offer.rpc_proto is None  # the default build's: an owner's image
    pinned = _offer(tmp_path, image=llamacpp.IMAGE, ring_image=RING_IMAGE)
    assert pinned.runtimes[0] == hubwire.Runtime(
        id=llamacpp.UPSTREAM_ID,
        runtime=llamacpp.RUNTIME,
        rpc_proto=session.PINNED_RPC_PROTO,
    )
    assert pinned.rpc_proto == session.PINNED_RPC_PROTO
    frame = rig_schema.load()
    hello = protocol.hello(
        "h1",
        machine_id="rig-1",
        agent_version="1",
        ram_total_mb=1,
        ram_free_mb=None,
        cards=(),
        offer=pinned,
    )
    import json

    rig_schema.validate(json.loads(hello), frame, "#/$defs/AgentMessage")


def test_an_image_that_is_the_ring_pins_own_is_the_ring_build_alone(
    tmp_path: Path, ring: llamacpp.Pin
) -> None:
    offer = _offer(tmp_path, image=MIRROR)
    assert [r.id for r in offer.runtimes] == [llamacpp.RING_ID]
    assert offer.rpc_proto == hubwire.RpcProto(major=7, minor=3)


@pytest.mark.parametrize(
    "named",
    [
        "registry.example/llama-ring:r1",
        f"registry.example/llama-ring@sha256:{'b' * 64}",
        "registry.example/llama-ring@md5:abc",
    ],
)
def test_a_ring_image_of_another_digest_names_no_build_and_says_why(
    tmp_path: Path, ring: llamacpp.Pin, named: str
) -> None:
    share = fakes.sharing(tmp_path, ring_image=named)
    assert session.rig_builds(share) == ()
    fault = session.ring_image_fault(share)
    assert fault is not None and named in fault and RING_IMAGE in fault
    found = session.chosen_build(share, llamacpp.RING_ID)
    assert isinstance(found, str) and named in found


def test_a_ring_pin_without_an_image_or_programs_is_offered_by_no_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for changes in ({"image": None}, {"head_binary": None}, {"worker_binary": None}):
        monkeypatch.setattr(llamacpp, "RING", _pin(**changes))
        assert _offer(tmp_path, ring_image=RING_IMAGE).runtimes == ()


# --- what a container rig starts ----------------------------------------------------


@pytest.fixture
def pool(tmp_path: Path, ring: llamacpp.Pin) -> Iterator[Pool]:
    made = make_pool(tmp_path, ring_image=MIRROR)
    yield made
    made.sessions.close()


def _worker_up(pool: Pool) -> None:
    prepared(pool, role="worker")
    pool.up("t1", **fakes.tunnel_up_body())


def _worker_start(pool: Pool, **changes: Any) -> dict[str, Any] | None:
    body: dict[str, Any] = {
        "session_id": "s1",
        "cards": [{"card_index": 0, "port": 50052}],
        **changes,
    }
    return pool.ask("worker_start", "w1", **body)


def _container(pool: Pool, part: str) -> list[str]:
    """The argv of the session's container whose name holds ``part``."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for name in pool.docker.of_session("s1"):
            if part in name:
                return list(pool.docker.containers[name].argv)
        time.sleep(0.01)
    raise AssertionError(f"no {part}: {pool.docker.calls}")


@pytest.mark.parametrize(
    ("runtime_id", "image", "binary"),
    [
        (llamacpp.RING_ID, MIRROR, RING_WORKER),
        (llamacpp.IMAGE_ID, "engine:rpc", sharing.DEFAULT_WORKER_BINARY),
        (None, "engine:rpc", sharing.DEFAULT_WORKER_BINARY),
    ],
)
def test_a_worker_runs_the_build_its_start_names(
    pool: Pool, runtime_id: str | None, image: str, binary: str
) -> None:
    _worker_up(pool)
    named = {} if runtime_id is None else {"runtime_id": runtime_id}
    answer = _worker_start(pool, **named)
    assert answer is not None and answer["type"] == "ack", answer
    argv = _container(pool, "worker")
    at = argv.index("--entrypoint")
    assert argv[at + 2] == image
    assert binary in argv


@pytest.mark.parametrize("runtime_id", ["upstream", "nope"])
def test_a_start_naming_a_build_the_rig_does_not_offer_is_refused(
    pool: Pool, runtime_id: str
) -> None:
    _worker_up(pool)
    answer = _worker_start(pool, runtime_id=runtime_id)
    assert answer is not None and answer["type"] == "error"
    assert answer["body"]["code"] == "not_capable"
    assert runtime_id in answer["body"]["message"]
    assert pool.docker.of_session("s1") == [pooled.container_name("s1", "tunnel")]


def test_a_rig_that_offers_no_build_refuses_any_a_start_names(tmp_path: Path) -> None:
    made = make_pool(tmp_path)
    try:
        _worker_up(made)
        answer = _worker_start(made, runtime_id=llamacpp.RING_ID)
        assert answer is not None and answer["body"]["code"] == "not_capable"
        assert "no ring build is pinned" in answer["body"]["message"]
    finally:
        made.sessions.close()


def _head_up(pool: Pool) -> None:
    prepared(pool, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)


def _head_start(pool: Pool, **changes: Any) -> dict[str, Any] | None:
    body: dict[str, Any] = {
        "session_id": "s1",
        "model": {"name": fakes.MODEL},
        "ctx": 4096,
        "devices": [
            {"kind": "rpc", "host": fakes.SELF, "port": 50052},
            {"kind": "local", "card_index": 0},
        ],
        "tensor_split": [1, 1],
        **changes,
    }
    return pool.ask("head_start", "h1", **body)


STAR = f"{pooled.STAR_ONLY_ENV}=1"


@pytest.mark.parametrize(
    ("changes", "image", "binary", "star"),
    [
        ({"runtime_id": "ring", "ring": False}, MIRROR, RING_HEAD, True),
        ({"runtime_id": "ring", "ring": True}, MIRROR, RING_HEAD, False),
        ({"runtime_id": "ring"}, MIRROR, RING_HEAD, False),
        (
            {"runtime_id": "image", "ring": False},
            "engine:rpc",
            sharing.DEFAULT_HEAD_BINARY,
            False,
        ),
        ({"ring": False}, "engine:rpc", sharing.DEFAULT_HEAD_BINARY, False),
    ],
)
def test_a_ring_head_runs_star_only_when_told_and_no_other_build_changes(
    pool: Pool, changes: dict[str, Any], image: str, binary: str, star: bool
) -> None:
    _head_up(pool)
    answer = _head_start(pool, **changes)
    assert answer is not None and answer["type"] == "ack", answer
    argv = _container(pool, "head")
    assert argv[argv.index("--entrypoint") + 2] == image
    assert binary in argv
    assert (STAR in argv) is star
    assert not any(pooled.STAR_ONLY_ENV in word for word in argv if word != STAR)


def test_a_head_spec_of_no_ring_build_starts_as_it_always_did() -> None:
    spec = pooled.HeadSpec(
        session_id="s1",
        image="engine:rpc",
        binary="/app/llama-server",
        gpus=(0,),
        models_dir=Path("/m"),
        model="m.gguf",
        name="m.gguf",
        ctx=4096,
        n_gpu_layers=999,
        devices=("CUDA0",),
        tensor_split=(1,),
        rpc=(),
        bind="10.0.0.2",
        memory_mb=1024,
    )
    owner = pooled.Owner(uid=1000, gid=1000, agent_pid=1)
    from dataclasses import replace

    plain = pooled.head_argv(spec, owner)
    assert pooled.head_argv(replace(spec, build="image", ring=False), owner) == plain
    star = pooled.head_argv(replace(spec, ring=True, star_only=True), owner)
    assert [w for w in star if w not in ("--env", STAR)] == [
        w for w in plain if w != "--env"
    ]


# --- what a native rig offers and starts --------------------------------------------


def test_a_native_rig_offers_the_ring_build_only_where_its_pin_has_an_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ring: llamacpp.Pin
) -> None:
    native_fakes.as_native_system(monkeypatch, "windows")
    share = fakes.sharing(tmp_path, launcher="native", image=None)
    monkeypatch.setattr(session, "native_pin_here", lambda pin: False)
    assert (
        session.offer(share, fakes.inventory(tmp_path), (), (), fakes.report()).runtimes
        == ()
    )
    monkeypatch.setattr(session, "native_pin_here", lambda pin: pin == ring)
    offer = session.offer(share, fakes.inventory(tmp_path), (), (), fakes.report())
    assert [(r.id, r.ring) for r in offer.runtimes] == [
        (llamacpp.UPSTREAM_ID, False),
        (llamacpp.RING_ID, True),
    ]
    assert offer.runtimes[0].runtime == offer.runtime == llamacpp.RUNTIME
    assert offer.rpc_proto == session.PINNED_RPC_PROTO
    assert session.RUNTIME_SELECT_FEATURE in offer.features


def test_a_ring_pin_is_picked_on_the_upstream_builds_backend_and_kept_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ring: llamacpp.Pin
) -> None:
    monkeypatch.setattr(rigscan, "host", lambda: {"os": WINDOWS, "arch": "x86_64"})
    monkeypatch.setattr(native, "nvidia_driver", lambda: "590.1")
    monkeypatch.setattr(native, "vulkan_loader", lambda: True)
    monkeypatch.delenv(native.BACKEND_ENV, raising=False)
    assert native.pick(ring).assets == (RING_ARCHIVE,)
    assert native.pick().backend == native.pick(ring).backend == llamacpp.CUDA
    monkeypatch.setattr(native, "nvidia_driver", lambda: None)  # vulkan: none for ring
    with pytest.raises(native.NativeError, match="r1"):
        native.pick(ring)
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    assert native.pin_root() == native.pin_root(llamacpp.UPSTREAM) == native.bin_root()
    assert native.pin_root(ring) == tmp_path / "home" / native.BIN / "ring" / "r1"


@pytest.fixture
def ring_control() -> dict[str, Any]:
    """How the fake ring fetch behaves: ``fails`` (a reason it raises with),
    ``backend`` (the build's), ``gate`` (an Event it waits on first)."""
    return {"fails": None, "backend": "cuda", "gate": None}


@pytest.fixture
def ring_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ring: llamacpp.Pin,
    ring_control: dict[str, Any],
) -> Iterator[tuple[native_fakes.NativePool, list[str]]]:
    fetched: list[str] = []
    program = native_fakes.write_engine(tmp_path / "ring-engine")

    def ring_engine() -> userwg.Engine:
        fetched.append("ring")
        if ring_control["gate"] is not None:
            assert ring_control["gate"].wait(10.0)
        if ring_control["fails"] is not None:
            raise pooled.PoolError(ring_control["fails"])
        return userwg.Engine(program=program, backend=ring_control["backend"])

    monkeypatch.setattr(userwg, "ring_engine", ring_engine)
    monkeypatch.setattr(session, "native_pin_here", lambda pin: pin == ring)
    made = native_fakes.make_native_pool(tmp_path, monkeypatch)
    yield made, fetched
    made.pool.sessions.close()
    made.echo.close()


def _native_head(rig: native_fakes.NativePool, **changes: Any) -> dict[str, Any]:
    answer = _native_head_start(rig, **changes)
    assert answer is not None and answer["type"] == "ack", answer
    return rig.head_said()


def _native_head_start(
    rig: native_fakes.NativePool, **changes: Any
) -> dict[str, Any] | None:
    assert rig.pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
    rig.pool.wait_for("session_prepared")
    rig.pool.up("t1", **fakes.tunnel_up_body())
    rpc = {
        "kind": "rpc",
        "host": native_fakes.RPC_DEVICE[0],
        "port": native_fakes.RPC_DEVICE[1],
    }
    answer = rig.pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[rpc, {"kind": "local", "card_index": 0}],
        tensor_split=[1, 1],
        **changes,
    )
    return answer


def test_a_native_ring_head_names_each_worker_as_the_others_reach_it(
    ring_rig: tuple[native_fakes.NativePool, list[str]],
) -> None:
    rig, fetched = ring_rig
    said = _native_head(rig, runtime_id=llamacpp.RING_ID)
    (local,) = said["argv"][said["argv"].index("--rpc") + 1].split(",")
    worker = f"{native_fakes.RPC_DEVICE[0]}:{native_fakes.RPC_DEVICE[1]}"
    env = said["rpc_env"]
    assert env[userwg.PEER_ENDPOINTS_ENV] == f"{local}={worker}"
    assert env["GGML_RPC_NO_RDMA"] == "1"
    assert "GGML_RPC_NO_COMM" not in env and pooled.STAR_ONLY_ENV not in env
    assert fetched == ["ring"]


def test_a_native_ring_head_told_no_ring_runs_star_only_and_names_no_peer(
    ring_rig: tuple[native_fakes.NativePool, list[str]],
) -> None:
    rig, _ = ring_rig
    env = _native_head(rig, runtime_id=llamacpp.RING_ID, ring=False)["rpc_env"]
    assert env[pooled.STAR_ONLY_ENV] == "1"
    assert userwg.PEER_ENDPOINTS_ENV not in env


@pytest.mark.parametrize("changes", [{}, {"runtime_id": "upstream", "ring": False}])
def test_a_native_upstream_head_runs_as_it_always_did_and_fetches_no_ring_build(
    ring_rig: tuple[native_fakes.NativePool, list[str]], changes: dict[str, Any]
) -> None:
    rig, fetched = ring_rig
    env = _native_head(rig, **changes)["rpc_env"]
    assert {k: env[k] for k in userwg.HEAD_FIXED_ENV} == userwg.HEAD_FIXED_ENV
    assert userwg.PEER_ENDPOINTS_ENV not in env
    assert pooled.STAR_ONLY_ENV not in env
    assert fetched == []


def test_the_peer_mapping_is_the_forks_spelling() -> None:
    assert userwg.PEER_ENDPOINTS_ENV == "GGML_RPC_PEER_ENDPOINTS"
    assert userwg.peer_endpoints(()) == {}
    assert userwg.peer_endpoints(
        [
            ("127.0.0.1:50101", "192.0.2.10:50052"),
            ("127.0.0.1:50102", "192.0.2.11:50052"),
        ]
    ) == {
        "GGML_RPC_PEER_ENDPOINTS": (
            "127.0.0.1:50101=192.0.2.10:50052,127.0.0.1:50102=192.0.2.11:50052"
        )
    }


# --- the owner's settings -----------------------------------------------------------


def test_the_ring_image_is_unwritten_until_set_and_refused_when_no_reference() -> None:
    assert "ring_image" not in sharing.as_data(sharing.Sharing())
    kept = sharing.read({"ring_image": RING_IMAGE})
    assert kept.ring_image == RING_IMAGE
    assert sharing.as_data(kept)["ring_image"] == RING_IMAGE
    for bad in ("../x", "a b", 7, "x" * 201):
        with pytest.raises(sharing.SharingError):
            sharing.read({"ring_image": bad})


def test_share_names_the_ring_image_and_turns_the_ring_links_on_and_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli

    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    assert cli.main(["rig", "share", "--ring-image", RING_IMAGE, "--ring-links"]) == 0
    kept = sharing.load()
    assert kept.ring_image == RING_IMAGE and kept.ring_links
    said = capsys.readouterr().out
    assert f"ring:    {RING_IMAGE} (no ring build is pinned" in said
    assert "ring:    links on" in said
    assert cli.main(["rig", "share", "--ring-image", "none", "--no-ring-links"]) == 0
    kept = sharing.load()
    assert kept.ring_image is None and not kept.ring_links


def _pairs(n: int) -> list[tuple[str, str]]:
    return [(f"127.0.0.1:{50100 + i}", f"10.0.0.{i + 1}:50052") for i in range(n)]


def test_the_peer_mapping_holds_every_bound_the_forks_head_aborts_on() -> None:
    most = userwg.PEER_ENDPOINTS_MAX_PAIRS
    full = userwg.peer_endpoints(_pairs(most))
    assert full is not None
    value = full[userwg.PEER_ENDPOINTS_ENV]
    assert len(value.split(",")) == most <= 16
    assert len(value) <= userwg.PEER_ENDPOINTS_MAX_BYTES
    for pair in value.split(","):
        local, peer = pair.split("=")
        assert len(local) <= 255 and len(peer) <= 255
    assert userwg.peer_endpoints(_pairs(most + 1)) is None
    twice_local = [
        ("127.0.0.1:50100", "10.0.0.1:50052"),
        ("127.0.0.1:50100", "10.0.0.2:1"),
    ]
    twice_peer = [
        ("127.0.0.1:50100", "10.0.0.1:50052"),
        ("127.0.0.1:50101", "10.0.0.1:50052"),
    ]
    assert userwg.peer_endpoints(twice_local) is None
    assert userwg.peer_endpoints(twice_peer) is None
    for bad in (
        "worker.example:50052",
        "[2001:db8::1]:50052",
        "10.0.0.1",
        "10.0.0.1:0",
        "10.0.0.1:65536",
        "10.0.0.1:050052",
        "10.0.0.1:5005a",
        "10.0.0.1:50052,10.0.0.2:50052",
        "10.0.0.1=1:50052",
    ):
        assert userwg.peer_endpoints([("127.0.0.1:50100", bad)]) is None, bad
        assert userwg.peer_endpoints([(bad, "10.0.0.1:50052")]) is None, bad


def _ring_spec(rpc: int, **changes: Any) -> pooled.HeadSpec:
    return pooled.HeadSpec(
        session_id="s1",
        image=llamacpp.RUNTIME,
        binary="/app/llama-server",
        gpus=(),
        models_dir=Path("/m"),
        model="m.gguf",
        name="m.gguf",
        ctx=4096,
        n_gpu_layers=999,
        devices=tuple(f"RPC{i}" for i in range(rpc)),
        tensor_split=(1,) * rpc,
        rpc=tuple(peer for _, peer in _pairs(rpc)),
        bind="127.0.0.1",
        memory_mb=1024,
        build=llamacpp.RING_ID,
        ring=True,
        **changes,
    )


def test_a_ring_head_whose_forwards_the_mapping_cannot_name_runs_star_only() -> None:
    most = userwg.PEER_ENDPOINTS_MAX_PAIRS
    env = userwg.head_build_env(_ring_spec(most), _pairs(most))
    assert userwg.PEER_ENDPOINTS_ENV in env and pooled.STAR_ONLY_ENV not in env
    many = userwg.head_build_env(_ring_spec(most + 1), _pairs(most + 1))
    assert many == {"GGML_RPC_NO_RDMA": "1", pooled.STAR_ONLY_ENV: "1"}
    named = userwg.head_build_env(_ring_spec(1), [("127.0.0.1:50100", "host:50052")])
    assert named == many
    from dataclasses import replace

    plain = replace(_ring_spec(most + 1), ring=False, build=None)
    upstream = userwg.head_build_env(plain, _pairs(most + 1))
    assert upstream == userwg.HEAD_FIXED_ENV


def test_the_ring_pin_when_filled_in_is_named_as_the_rig_starts_it() -> None:
    pin = llamacpp.RING
    if pin is not None:  # the shipped pin: its id and kind are what a start names
        assert pin.id == llamacpp.RING_ID and pin.ring
        assert pin.image is None or session._digest(pin.image) is not None
    assert _pin().id == llamacpp.RING_ID


# --- review round: what a ring fetch holds up, and what a ring head inherits ---------


def _failed(rig: native_fakes.NativePool) -> dict[str, Any]:
    rig.pool.wait_for("session_status", "failed")
    (failed,) = [
        f
        for f in rig.pool.box.of_type("session_status")
        if f["body"]["state"] == "failed"
    ]
    body: dict[str, Any] = failed["body"]
    return body


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {"fails": "llama-r1-bin-win-cuda-13.4-x64.zip: sha256 mismatch"},
            "sha256 mismatch",
        ),
        ({"backend": "vulkan"}, "the ring build runs vulkan"),
    ],
)
def test_a_ring_build_that_cannot_be_fetched_or_runs_elsewhere_fails_its_start(
    ring_rig: tuple[native_fakes.NativePool, list[str]],
    ring_control: dict[str, Any],
    changes: dict[str, Any],
    reason: str,
) -> None:
    rig, fetched = ring_rig
    ring_control.update(changes)
    answer = _native_head_start(rig, runtime_id=llamacpp.RING_ID)
    assert answer is not None and answer["type"] == "ack", answer
    failed = _failed(rig)
    assert failed["error_code"] == "start_failed"
    assert reason in json.dumps(failed)
    assert fetched == ["ring"]
    assert "spawn" not in rig.verbs()  # no head was started
    assert not (rig.tmp / "head-said.json").exists()


def test_a_ring_fetch_holds_up_no_other_sessions_prepare(
    ring_rig: tuple[native_fakes.NativePool, list[str]],
    ring_control: dict[str, Any],
) -> None:
    import threading

    rig, fetched = ring_rig
    gate = threading.Event()
    ring_control["gate"] = gate
    try:
        answer = _native_head_start(rig, runtime_id=llamacpp.RING_ID)
        assert answer is not None and answer["type"] == "ack", answer
        deadline = time.monotonic() + 5.0
        while fetched != ["ring"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert fetched == ["ring"]  # the fetch is under way, and held
        asked = rig.pool.ask("session_prepare", "p2", session_id="s2", role="head")
        assert asked is None
        rig.pool.wait_for("session_prepared", count=2)  # while the fetch is held
    finally:
        gate.set()
    rig.head_said()


@pytest.mark.parametrize("ring_on", [True, False])
def test_a_ring_head_takes_no_peer_mapping_or_star_switch_from_the_agent(
    ring_rig: tuple[native_fakes.NativePool, list[str]], ring_on: bool
) -> None:
    rig, _ = ring_rig
    rig.host._env[userwg.PEER_ENDPOINTS_ENV] = "not=a,mapping"
    rig.host._env[pooled.STAR_ONLY_ENV] = "0"
    env = _native_head(rig, runtime_id=llamacpp.RING_ID, ring=ring_on)["rpc_env"]
    if ring_on:
        assert env[userwg.PEER_ENDPOINTS_ENV] != "not=a,mapping"
        assert pooled.STAR_ONLY_ENV not in env
    else:
        assert env[pooled.STAR_ONLY_ENV] == "1"
        assert userwg.PEER_ENDPOINTS_ENV not in env


def test_an_upstream_head_still_takes_the_agents_gpu_settings_as_it_always_did(
    ring_rig: tuple[native_fakes.NativePool, list[str]],
) -> None:
    rig, _ = ring_rig
    rig.host._env[userwg.PEER_ENDPOINTS_ENV] = "kept=as,before"
    env = _native_head(rig)["rpc_env"]
    assert env[userwg.PEER_ENDPOINTS_ENV] == "kept=as,before"


def test_a_ring_pin_whose_image_names_no_digest_is_offered_by_no_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llamacpp, "RING", _pin(image="registry.example/r:tag"))
    for named in ("anything:latest", "registry.example/r:tag"):
        share = fakes.sharing(tmp_path, ring_image=named)
        fault = session.ring_image_fault(share)
        assert fault is not None and "not pinned by its digest" in fault
        assert session.rig_builds(share) == ()
        assert session.rig_builds(fakes.sharing(tmp_path, image=named)) == ()


def test_once_the_pin_is_filled_an_image_that_pins_its_digest_runs_as_the_ring_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one rig whose unchanged sharing file offers something new once the
    ring pin is filled in: its image is the ring build's, so its hello names
    that build and its protocol, and its head and worker run the pin's
    programs, not the file's head_binary and worker_binary."""
    changes = {"image": MIRROR, "head_binary": "/own/head", "worker_binary": "/own/w"}
    before = _offer(tmp_path, **changes)
    assert before.runtimes == () and before.rpc_proto is None
    monkeypatch.setattr(llamacpp, "RING", _pin())
    after = _offer(tmp_path, **changes)
    assert [r.id for r in after.runtimes] == [llamacpp.RING_ID]
    assert after.rpc_proto == hubwire.RpcProto(major=7, minor=3)
    assert after.features == (*before.features, session.RUNTIME_SELECT_FEATURE)
    (build,) = session.rig_builds(fakes.sharing(tmp_path, **changes))
    assert (build.image, build.head_binary, build.worker_binary) == (
        MIRROR,
        RING_HEAD,
        RING_WORKER,
    )
