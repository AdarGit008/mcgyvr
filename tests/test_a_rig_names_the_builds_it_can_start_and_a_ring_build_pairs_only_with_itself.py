"""A rig names the builds it can start, and a ring build pairs only with itself.

A hello may list the llama.cpp builds a rig can start for a session
(``capabilities.runtimes``, feature ``runtime_select``): each an id, the
build's name, its RPC protocol and whether it is a ring build. A head and a
worker run builds that pair (``hubwire.runtimes_pair``): a ring build only
with the same ring build, any other build by its protocol as heads and
workers always have, and a rig that names no build stands for the one its
``runtime`` and ``rpc_proto`` describe. A hello without builds is the hello
it always was. A start may name the build (``runtime_id``, an id of the
rig's own) and whether a ring build's ring may be used (``head_start.ring``);
the agent reads both, and refuses an id not of its shape, as the schema does.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import protocol, sessionwire
from tests import rig_schema

UPSTREAM = hubwire.RpcProto(major=8, minor=0)
OLDER = hubwire.RpcProto(major=8, minor=1)
RING = hubwire.RpcProto(major=7, minor=3)
RING_NEXT = hubwire.RpcProto(major=7, minor=4)
RING_BUILD = "example/llama.cpp@r1"


def _build(
    proto: hubwire.RpcProto | None,
    *,
    ring: bool = False,
    runtime: str = "example/llama.cpp@b1",
    id_: str = "upstream",
) -> hubwire.Runtime:
    return hubwire.Runtime(id=id_, runtime=runtime, rpc_proto=proto, ring=ring)


def _ring(proto: hubwire.RpcProto = RING, runtime: str = RING_BUILD) -> hubwire.Runtime:
    return _build(proto, ring=True, runtime=runtime, id_="ring")


@pytest.mark.parametrize(
    ("head", "worker", "pairs"),
    [
        # Builds that are no ring build pair as heads and workers always have.
        (_build(UPSTREAM), _build(UPSTREAM), True),
        (_build(OLDER), _build(UPSTREAM), True),
        (_build(UPSTREAM), _build(OLDER), False),
        (_build(UPSTREAM), _build(RING), False),
        (_build(None), _build(None), True),
        (_build(UPSTREAM), _build(None), False),
        (_build(None), _build(UPSTREAM), False),
        # Their names do not matter: an owner's image and the pinned release.
        (_build(UPSTREAM, runtime="example.org/own:1"), _build(UPSTREAM), True),
        # A ring build pairs with the same ring build alone.
        (_ring(), _ring(), True),
        (_ring(), _build(RING, ring=True, runtime=RING_BUILD, id_="other"), True),
        (_ring(), _ring(runtime="example/llama.cpp@r2"), False),
        (_ring(), _ring(proto=RING_NEXT), False),
        (_ring(proto=RING_NEXT), _ring(), False),
        (_ring(), _build(RING, runtime=RING_BUILD), False),
        (_build(RING, runtime=RING_BUILD), _ring(), False),
        (_ring(), _build(UPSTREAM), False),
        (_build(UPSTREAM), _ring(), False),
        (_ring(), _build(None), False),
        (_build(None), _ring(), False),
    ],
)
def test_the_pairing_rule(
    head: hubwire.Runtime, worker: hubwire.Runtime, pairs: bool
) -> None:
    assert hubwire.runtimes_pair(head, worker) is pairs


def test_a_ring_build_that_names_no_build_or_protocol_pairs_with_none() -> None:
    nameless = hubwire.Runtime(id=None, runtime=None, rpc_proto=RING, ring=True)
    blind = hubwire.Runtime(id="ring", runtime=RING_BUILD, rpc_proto=None, ring=True)
    assert not hubwire.runtimes_pair(nameless, nameless)
    assert not hubwire.runtimes_pair(blind, blind)


def test_a_rig_that_names_no_build_stands_for_the_one_it_describes() -> None:
    implied = hubwire.implied_runtime("example.org/own:1", UPSTREAM)
    assert implied == hubwire.Runtime(
        id=None, runtime="example.org/own:1", rpc_proto=UPSTREAM, ring=False
    )
    assert hubwire.rig_runtimes(
        (), runtime="example.org/own:1", rpc_proto=UPSTREAM
    ) == (implied,)
    named = (_build(UPSTREAM), _ring())
    assert hubwire.rig_runtimes(named, runtime="x", rpc_proto=None) == named
    # Two rigs from before it pair as they always did.
    old = hubwire.implied_runtime(None, None)
    assert hubwire.runtimes_pair(old, old)
    assert hubwire.runtimes_pair(_build(UPSTREAM), implied)


@pytest.mark.parametrize(
    "id_",
    [
        "",
        "../ring",
        "a/b",
        "ring.1",
        "Ring",
        "1ring",
        "ring\n",
        "ri\x00ng",
        "ring\u202e",
        "r" * 33,
        None,
        7,
    ],
)
def test_a_build_whose_id_is_not_of_its_shape_is_refused(id_: Any) -> None:
    with pytest.raises(ValueError, match="id"):
        hubwire.Runtime(id=id_, runtime=RING_BUILD).validate()


def test_a_build_the_wire_may_not_carry_is_refused() -> None:
    hubwire.Runtime(id="r" * 32, runtime=RING_BUILD).validate()
    for bad, field in [
        (hubwire.Runtime(id="ring", runtime=None), "runtime"),
        (hubwire.Runtime(id="ring", runtime="a b"), "runtime"),
        (hubwire.Runtime(id="ring", runtime="x" * 201), "runtime"),
        (
            hubwire.Runtime(
                id="ring",
                runtime=RING_BUILD,
                rpc_proto=hubwire.RpcProto(major=256, minor=0),
            ),
            "major",
        ),
        (hubwire.Runtime(id="ring", runtime=RING_BUILD, ring=1), "ring"),  # type: ignore[arg-type]
        (hubwire.Runtime(id="ring", runtime=RING_BUILD, ring=True), "rpc_proto"),
    ]:
        with pytest.raises(ValueError, match=field):
            bad.validate()


def test_a_hello_names_at_most_the_bound_of_builds_each_id_once() -> None:
    builds = [_build(UPSTREAM, id_=f"b{i}") for i in range(hubwire.MAX_RUNTIMES)]
    hubwire.runtimes_fit(builds)
    hubwire.runtimes_fit([])
    with pytest.raises(ValueError, match="more than"):
        hubwire.runtimes_fit([*builds, _build(UPSTREAM, id_="extra")])
    with pytest.raises(ValueError, match="twice"):
        hubwire.runtimes_fit([_build(UPSTREAM), _build(None)])
    with pytest.raises(ValueError, match="id"):
        hubwire.runtimes_fit([_build(UPSTREAM), hubwire.implied_runtime("x", None)])


def _offer(**changes: Any) -> protocol.Offer:
    fields: dict[str, Any] = {
        "roles": ("head", "worker"),
        "runtime": "example.org/own:1",
        "endpoints": (("192.0.2.1", 51820, "lan"),),
        "models": (),
        "sessions": (),
        "features": ("probe",),
        "rpc_proto": UPSTREAM,
    }
    fields.update(changes)
    return protocol.Offer(**fields)


def _hello(offer: protocol.Offer) -> str:
    return protocol.hello(
        "h1",
        machine_id="rig-1",
        agent_version="1",
        ram_total_mb=1,
        ram_free_mb=None,
        cards=(),
        offer=offer,
    )


def test_a_hello_without_builds_is_the_hello_it_always_was() -> None:
    frame = json.loads(_hello(_offer()))
    assert hubwire.RUNTIMES_FIELD not in frame["body"]["capabilities"]
    assert _hello(_offer(runtimes=())) == _hello(_offer())


def test_a_hello_names_its_builds_default_first_valid_against_the_schema() -> None:
    builds = (
        _build(UPSTREAM, runtime="example/llama.cpp@b1"),
        _build(None, runtime="example.org/own:1", id_="own"),
        _ring(),
    )
    frame = json.loads(
        _hello(
            _offer(
                runtimes=builds,
                features=("probe", hubwire.RUNTIME_SELECT_FEATURE),
            )
        )
    )
    rig_schema.validate(frame, rig_schema.load(), "#/$defs/AgentMessage")
    assert frame["body"]["capabilities"][hubwire.RUNTIMES_FIELD] == [
        {
            "id": "upstream",
            "runtime": "example/llama.cpp@b1",
            "rpc_proto": {"major": 8, "minor": 0},
            "ring": False,
        },
        {"id": "own", "runtime": "example.org/own:1", "ring": False},
        {
            "id": "ring",
            "runtime": RING_BUILD,
            "rpc_proto": {"major": 7, "minor": 3},
            "ring": True,
        },
    ]


def test_the_agent_writes_no_build_the_wire_may_not_carry() -> None:
    for runtimes in [
        (_build(UPSTREAM), _build(None)),
        (hubwire.Runtime(id="../x", runtime=RING_BUILD),),
        (hubwire.Runtime(id="ring", runtime=RING_BUILD, ring=True),),
        tuple(_build(None, id_=f"b{i}") for i in range(hubwire.MAX_RUNTIMES + 1)),
    ]:
        with pytest.raises(ValueError, match=f"capabilities.{hubwire.RUNTIMES_FIELD}"):
            _hello(_offer(runtimes=runtimes))


def test_the_wire_names_are_the_schemas() -> None:
    schema = rig_schema.load()
    defs = schema["$defs"]
    assert hubwire.RUNTIME_SELECT_FEATURE in schema["x-features"]
    listed = defs["Capabilities"]["properties"][hubwire.RUNTIMES_FIELD]
    assert listed["maxItems"] == hubwire.MAX_RUNTIMES
    assert listed["items"] == {"$ref": "#/$defs/Runtime"}
    build = defs["Runtime"]["properties"]
    assert build["id"]["pattern"] == f"^{hubwire.RUNTIME_ID.pattern}$"
    assert build["runtime"]["pattern"] == f"^{hubwire.RUNTIME.pattern}$"
    assert build["ring"] == {"default": False, "title": "Ring", "type": "boolean"}
    assert set(defs["Runtime"]["required"]) == {"id", "runtime"}
    for start in ("WorkerStartBody", "HeadStartBody"):
        named = defs[start]["properties"][hubwire.RUNTIME_ID_FIELD]["anyOf"][0]
        assert named["pattern"] == f"^{hubwire.RUNTIME_ID.pattern}$"
        assert hubwire.RUNTIME_ID_FIELD not in defs[start]["required"]
    ring = defs["HeadStartBody"]["properties"][hubwire.HEAD_RING_FIELD]
    assert ring["anyOf"] == [{"type": "boolean"}, {"type": "null"}]
    assert hubwire.HEAD_RING_FIELD not in defs["HeadStartBody"]["required"]


def _worker_start(**changes: Any) -> dict[str, Any]:
    body = {"session_id": "s1", "cards": [{"card_index": 0, "port": 50052}]}
    return {"type": "worker_start", "body": {**body, **changes}}


def _head_start(**changes: Any) -> dict[str, Any]:
    body = {
        "session_id": "s1",
        "model": {"name": "m.gguf"},
        "ctx": 256,
        "devices": [
            {"kind": "local", "card_index": 0},
            {"kind": "rpc", "host": "198.51.100.1", "port": 50052},
        ],
        "tensor_split": [1, 1],
    }
    return {"type": "head_start", "body": {**body, **changes}}


def _read(frame: dict[str, Any]) -> Any:
    message = {"v": 1, "id": "c1", **frame}
    envelope = protocol.decode(json.dumps(message))
    return getattr(sessionwire, f"read_{frame['type']}")(envelope)


def _allowed(frame: dict[str, Any]) -> None:
    rig_schema.validate(
        {"v": 1, "id": "c1", **frame}, rig_schema.load(), "#/$defs/HubMessage"
    )


def test_a_start_that_names_no_build_starts_the_default_as_always() -> None:
    for frame in (_worker_start(), _head_start()):
        _allowed(frame)
        assert _read(frame).runtime_id is None
    null = _head_start(runtime_id=None, ring=None)
    _allowed(null)
    head = _read(null)
    assert head.runtime_id is None and head.ring is None
    assert _read(_head_start()).ring is None


@pytest.mark.parametrize("ring", [True, False])
def test_a_start_names_its_build_and_a_head_whether_its_ring_is_used(
    ring: bool,
) -> None:
    worker = _worker_start(runtime_id="ring")
    head = _head_start(runtime_id="ring", ring=ring)
    for frame in (worker, head):
        _allowed(frame)
    assert _read(worker).runtime_id == "ring"
    read = _read(head)
    assert read.runtime_id == "ring" and read.ring is ring


@pytest.mark.parametrize(
    "runtime_id",
    [
        "",
        "../ring",
        "/opt/llama",
        "a/b",
        "ring.1",
        "Ring",
        "ring\n",
        "r\x00",
        "r" * 33,
        7,
    ],
)
def test_a_start_naming_a_build_id_not_of_its_shape_is_refused(
    runtime_id: Any,
) -> None:
    for frame in (
        _worker_start(runtime_id=runtime_id),
        _head_start(runtime_id=runtime_id),
    ):
        with pytest.raises(rig_schema.SchemaError):
            _allowed(frame)
        with pytest.raises(protocol.ProtocolError) as refused:
            _read(frame)
        assert refused.value.code == "bad_message"
        assert hubwire.RUNTIME_ID_FIELD in str(refused.value)


@pytest.mark.parametrize("ring", ["false", 0, 1, [], {}])
def test_a_head_start_whose_ring_is_not_true_or_false_is_refused(ring: Any) -> None:
    frame = _head_start(ring=ring)
    with pytest.raises(rig_schema.SchemaError):
        _allowed(frame)
    with pytest.raises(protocol.ProtocolError) as refused:
        _read(frame)
    assert refused.value.code == "bad_message"
