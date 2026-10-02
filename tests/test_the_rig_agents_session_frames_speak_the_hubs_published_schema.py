"""The rig agent's session and relay frames speak the hub's published schema.

The hub's schema is the one definition of the wire, and it grew the session
commands, the relay and the hello's offer. So the agent's limits for them
(peers, devices, the relay's chunk, body, answer, window and time, the log
excerpt), its shapes (model names, digests, keys, hosts, addresses, content
types), its closed sets (session states, relay outcomes, the relayed
endpoint) and its error codes are the schema's; every frame the agent writes
for a session or a relay, at its edges, is valid against it; every session
command the schema allows is read, and one it refuses is refused.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import pytest

from tests import rig_schema


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return rig_schema.load()


def _props(schema: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = schema["$defs"][name]["properties"]
    return found


def _branch(node: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in node:
        return next(b for b in node["anyOf"] if b.get("type") != "null")
    return node


def test_the_agents_session_limits_shapes_and_sets_are_the_schemas(
    schema: dict[str, Any],
) -> None:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    assert schema["x-relay-max-chunk-bytes"] == w.RELAY_MAX_CHUNK_BYTES
    assert schema["x-relay-max-request-bytes"] == w.RELAY_MAX_REQUEST_BYTES
    assert schema["x-relay-max-response-bytes"] == w.RELAY_MAX_RESPONSE_BYTES
    assert schema["x-relay-max-window"] == w.RELAY_MAX_WINDOW
    assert schema["x-relay-max-timeout-s"] == w.RELAY_MAX_TIMEOUT_S
    assert schema["x-log-excerpt-max-chars"] == w.LOG_EXCERPT_MAX_CHARS
    assert set(schema["x-error-codes"]) == {c.value for c in p.ErrorCode} | {
        value for name, value in vars(w.SessionCode).items() if name.isupper()
    }

    hello = _props(schema, "HelloBody")
    assert hello["models"]["maxItems"] == p.MAX_MODELS
    assert hello["endpoints"]["maxItems"] == p.MAX_ENDPOINTS == w.MAX_ENDPOINTS
    assert hello["sessions"]["maxItems"] == p.MAX_SESSIONS_REPORTED
    model = _props(schema, "ModelInfo")
    assert model["name"]["pattern"] == f"^{p.MODEL_NAME.pattern}$"
    assert model["size_bytes"]["maximum"] == p.MAX_MODEL_BYTES
    assert _branch(model["digest"])["pattern"] == f"^{p.DIGEST.pattern}$"
    assert _branch(model["arch"])["pattern"] == f"^{p.SHORT_TAG.pattern}$"
    assert _branch(model["n_layers"])["maximum"] == p.MAX_LAYERS
    assert _branch(model["n_ctx_train"])["maximum"] == p.MAX_COUNT
    assert _branch(model["kv_bytes_per_token"])["maximum"] == p.MAX_KV_BYTES_PER_TOKEN
    capabilities = _props(schema, "Capabilities")
    assert _branch(capabilities["runtime"])["pattern"] == f"^{p.RUNTIME.pattern}$"
    assert capabilities["roles"]["items"]["enum"] == list(p.ROLES)
    assert _props(schema, "Endpoint")["host"]["pattern"] == f"^{w.HOST.pattern}$"

    peer = _props(schema, "TunnelPeer")
    assert peer["public_key"]["pattern"] == f"^{w.WIREGUARD_KEY.pattern}$"
    assert peer["allowed_ips"]["maxItems"] == w.MAX_ALLOWED_IPS
    assert peer["allowed_ips"]["items"]["pattern"] == f"^{w.IPV4_CIDR.pattern}$"
    assert (peer["keepalive_s"]["maximum"], peer["keepalive_s"]["default"]) == (
        w.MAX_KEEPALIVE_S,
        w.DEFAULT_KEEPALIVE_S,
    )
    assert _props(schema, "TunnelUpBody")["peers"]["maxItems"] == w.MAX_PEERS
    head = _props(schema, "HeadStartBody")
    assert (head["ctx"]["minimum"], head["ctx"]["maximum"]) == (w.MIN_CTX, w.MAX_CTX)
    assert head["devices"]["maxItems"] == w.MAX_DEVICES
    assert head["tensor_split"]["items"]["maximum"] == w.MAX_TENSOR_SHARE
    assert (head["n_gpu_layers"]["maximum"], head["n_gpu_layers"]["default"]) == (
        w.MAX_GPU_LAYERS,
        w.DEFAULT_GPU_LAYERS,
    )
    assert _props(schema, "RpcDevice")["host"]["pattern"] == f"^{w.IPV4.pattern}$"

    status = _props(schema, "SessionStatusBody")
    assert tuple(status["state"]["enum"]) == w.STATES
    end = _props(schema, "RelayEndBody")
    assert tuple(end["outcome"]["enum"]) == w.RELAY_OUTCOMES
    request = _props(schema, "RelayRequestBody")
    assert [request["endpoint"]["const"]] == list(w.RELAY_PATHS)
    response = _props(schema, "RelayResponseBody")
    assert response["content_type"]["pattern"] == f"^{w.CONTENT_TYPE.pattern}$"
    assert response["content_type"]["maxLength"] == w.MAX_CONTENT_TYPE
    data = _props(schema, "RelayDataBody")
    assert data["data_b64"]["maxLength"] == w.RELAY_MAX_CHUNK_B64
    assert data["seq"]["maximum"] == w.RELAY_MAX_SEQ
    rtt = _props(schema, "RttSample")
    assert rtt["rtt_us"]["maximum"] == w.MAX_RTT_US
    assert _props(schema, "PeerRttBody")["samples"]["maxItems"] == w.MAX_RTT_SAMPLES


def _agent_frames() -> list[str]:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    key = "A" * 42 + "Q="
    lan = w.Endpoint(host="192.0.2.10", port=51820, kind="lan")
    models = tuple(
        p.ModelInfo(
            name=f"m{i}.gguf",
            size_bytes=p.MAX_MODEL_BYTES,
            digest="sha256:" + "0" * 64,
            arch="qwen2",
            n_layers=p.MAX_LAYERS,
            n_ctx_train=p.MAX_COUNT,
            n_embd=1,
            n_head=None,
            n_head_kv=8,
            kv_bytes_per_token=p.MAX_KV_BYTES_PER_TOKEN,
        )
        for i in range(p.MAX_MODELS)
    )
    offer = p.Offer(
        roles=("head", "worker"),
        runtime="engine:b1@sha256:" + "a" * 64,
        endpoints=tuple(("192.0.2.10", 51820, "lan") for _ in range(p.MAX_ENDPOINTS)),
        models=models,
        sessions=tuple(f"s{i}" for i in range(p.MAX_SESSIONS_REPORTED)),
    )
    hello = p.hello(
        "h1",
        machine_id="mch-example",
        agent_version="1.0",
        ram_total_mb=1,
        ram_free_mb=1,
        cards=(),
        offer=offer,
    )
    bare = p.hello(
        "h2",
        machine_id="m",
        agent_version="1",
        ram_total_mb=1,
        ram_free_mb=None,
        cards=(),
        offer=p.Offer(roles=(), runtime=None, endpoints=(), models=(), sessions=()),
    )
    return [
        hello,
        bare,
        w.session_prepared(
            "c1", session_id="s1", public_key=key, listen_port=1, endpoints=[lan] * 8
        ),
        w.session_prepared(
            "c1", session_id="s" * 64, public_key=key, listen_port=65535, endpoints=[]
        ),
        *[w.session_status(None, session_id="s1", state=state) for state in w.STATES],
        w.session_status(
            "q1",
            session_id="s1",
            state="failed",
            role="head",
            error_code="start_failed",
            progress_pct=100,
            log_excerpt="x\x00y‮" + "z" * 10_000,
        ),
        w.relay_response("q1", status=200, content_type="text/event-stream"),
        w.relay_response(
            "q1", status=599, content_type="application/json; charset=utf-8"
        ),
        w.relay_data("q1", seq=0, data=b"\x00" * w.RELAY_MAX_CHUNK_BYTES),
        w.relay_data("q1", seq=w.RELAY_MAX_SEQ, data=b"x"),
        *[
            w.relay_end("q1", outcome=outcome, error_code=None)
            for outcome in w.RELAY_OUTCOMES
        ],
        w.relay_end("q1", outcome="error", error_code="upstream_failed"),
        w.peer_rtt([("rig-a", 0)]),
        w.peer_rtt([(f"r{i}", w.MAX_RTT_US) for i in range(w.MAX_RTT_SAMPLES)]),
        w.ack("c1"),
        w.refusal("c1", "busy", "this rig is in another session"),
    ]


def test_every_session_frame_the_agent_writes_is_valid_against_the_schema(
    schema: dict[str, Any],
) -> None:
    from mcgyvr.rig import protocol as p

    for frame in _agent_frames():
        assert len(frame.encode()) <= p.MAX_MESSAGE_BYTES
        message = json.loads(frame)
        rig_schema.validate(message, schema, "#/$defs/AgentMessage")


def test_the_agent_refuses_to_write_a_session_frame_the_schema_refuses() -> None:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    key = "A" * 42 + "Q="
    bad: list[Callable[[], object]] = [
        lambda: w.session_prepared(
            "c", session_id="s", public_key="nokey", listen_port=1, endpoints=[]
        ),
        lambda: w.session_prepared(
            "c", session_id="s", public_key=key, listen_port=0, endpoints=[]
        ),
        lambda: w.session_status(None, session_id="s", state="dancing"),
        lambda: w.session_status(None, session_id="s", state="ready", role="boss"),
        lambda: w.relay_response("q", status=99, content_type="text/plain"),
        lambda: w.relay_response("q", status=200, content_type="text/plain; a=b; c=d"),
        lambda: w.relay_data("q", seq=0, data=b""),
        lambda: w.relay_data("q", seq=0, data=b"x" * (w.RELAY_MAX_CHUNK_BYTES + 1)),
        lambda: w.relay_end("q", outcome="maybe"),
        lambda: w.peer_rtt([]),
        lambda: w.peer_rtt([("r", w.MAX_RTT_US + 1)]),
        lambda: p.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=(),
            offer=p.Offer(
                roles=(),
                runtime=None,
                endpoints=(),
                models=(p.ModelInfo(name="../x.gguf", size_bytes=1),),
                sessions=(),
            ),
        ),
        lambda: p.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=(),
            offer=p.Offer(
                roles=("boss",), runtime=None, endpoints=(), models=(), sessions=()
            ),
        ),
    ]
    for write in bad:
        with pytest.raises(ValueError):
            write()


def _commands() -> list[dict[str, Any]]:
    key = "B" * 42 + "g="
    return [
        {"type": "session_prepare", "body": {"session_id": "s1", "role": "worker"}},
        {
            "type": "tunnel_up",
            "body": {
                "session_id": "s1",
                "address": "198.51.100.2/24",
                "listen_port": 51820,
                "peers": [
                    {
                        "rig_id": "r1",
                        "public_key": key,
                        "allowed_ips": ["198.51.100.1/32"],
                        "endpoints": [{"host": "192.0.2.1", "port": 1, "kind": "lan"}],
                        "keepalive_s": 0,
                        "later": "ignored",
                    }
                ],
            },
        },
        {
            "type": "worker_start",
            "body": {"session_id": "s1", "cards": [{"card_index": 63, "port": 65535}]},
        },
        {
            "type": "head_start",
            "body": {
                "session_id": "s1",
                "model": {"name": "m.gguf", "digest": "sha256:" + "f" * 64},
                "ctx": 256,
                "devices": [
                    {"kind": "local", "card_index": 0},
                    {"kind": "rpc", "host": "198.51.100.1", "port": 50052},
                ],
                "tensor_split": [0, 1],
                "n_gpu_layers": 0,
                "split_mode": "layer",
            },
        },
        {"type": "session_query", "body": {"session_id": "s1"}},
        {"type": "session_stop", "body": {"session_id": "s1", "reason": "done"}},
        {
            "type": "relay_request",
            "body": {
                "session_id": "s1",
                "request_id": "q1",
                "endpoint": "chat_completions",
                "body_bytes": 0,
                "stream": True,
                "timeout_s": 3600,
                "max_response_bytes": 1,
                "window": 64,
            },
        },
        {
            "type": "relay_data",
            "body": {
                "request_id": "q1",
                "seq": 0,
                "data_b64": base64.b64encode(b"x" * 32768).decode(),
            },
        },
        {"type": "relay_credit", "body": {"request_id": "q1", "chunks": 64}},
        {"type": "relay_cancel", "body": {"request_id": "q1"}},
    ]


def _read(frame: dict[str, Any]) -> Any:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    envelope = p.decode(json.dumps({"v": 1, "id": "c1", **frame}))
    reader = getattr(w, f"read_{frame['type']}")
    return reader(envelope)


def test_every_session_command_the_schema_allows_is_read(
    schema: dict[str, Any],
) -> None:
    for frame in _commands():
        rig_schema.validate({"v": 1, "id": "c1", **frame}, schema, "#/$defs/HubMessage")
        assert _read(frame) is not None


def _refused_commands() -> list[dict[str, Any]]:
    good = {c["type"]: c["body"] for c in _commands()}

    def with_(kind: str, **changes: Any) -> dict[str, Any]:
        return {"type": kind, "body": {**good[kind], **changes}}

    peer = good["tunnel_up"]["peers"][0]
    return [
        with_("session_prepare", role="boss"),
        with_("session_prepare", session_id="a b"),
        with_("tunnel_up", address="198.51.100.2"),
        with_("tunnel_up", peers=[]),
        with_("tunnel_up", peers=[{**peer, "public_key": "short="}]),
        with_("tunnel_up", peers=[{**peer, "allowed_ips": []}]),
        with_("tunnel_up", peers=[{**peer, "allowed_ips": ["1.2.3"]}]),
        with_("tunnel_up", peers=[{**peer, "keepalive_s": 601}]),
        with_("tunnel_up", peers=[peer] * 16),
        with_("worker_start", cards=[]),
        with_("worker_start", cards=[{"card_index": 64, "port": 1}]),
        with_("worker_start", cards=[{"card_index": 0, "port": 0}]),
        with_("head_start", model={"name": "../m.gguf"}),
        with_("head_start", model={"name": "m", "digest": "md5:x"}),
        with_("head_start", ctx=255),
        with_(
            "head_start", devices=[{"kind": "disk", "card_index": 0}], tensor_split=[1]
        ),
        with_(
            "head_start",
            devices=[{"kind": "rpc", "host": "x.invalid", "port": 1}],
            tensor_split=[1],
        ),
        with_("head_start", split_mode="row"),
        with_("relay_request", endpoint="completions"),
        with_("relay_request", body_bytes=(1 << 20) + 1),
        with_("relay_request", window=0),
        with_("relay_request", stream="yes"),
        with_("relay_data", data_b64="!!!!"),
        with_("relay_credit", chunks=65),
    ]


def test_a_session_command_the_schema_refuses_is_refused(
    schema: dict[str, Any],
) -> None:
    from mcgyvr.rig import protocol as p

    for frame in _refused_commands():
        with pytest.raises(rig_schema.SchemaError):
            rig_schema.validate(
                {"v": 1, "id": "c1", **frame}, schema, "#/$defs/HubMessage"
            )
        with pytest.raises(p.ProtocolError) as refused:
            _read(frame)
        assert refused.value.code == "bad_message"


@pytest.mark.parametrize(
    "change",
    [
        {"tensor_split": [1]},  # one share per device
        {"tensor_split": [0, 0]},  # assigns nothing
        {
            "devices": [
                {"kind": "local", "card_index": 0},
                {"kind": "local", "card_index": 0},
            ]
        },
    ],
)
def test_a_head_start_the_hub_itself_refuses_is_refused_too(
    change: dict[str, Any],
) -> None:
    from mcgyvr.rig import protocol as p

    body = {**_commands()[3]["body"], **change}
    with pytest.raises(p.ProtocolError):
        _read({"type": "head_start", "body": body})


def test_a_relay_chunk_over_the_limit_that_the_schemas_length_lets_by_is_refused() -> (
    None
):
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    over = base64.b64encode(b"x" * (w.RELAY_MAX_CHUNK_BYTES + 1)).decode()
    assert len(over) <= w.RELAY_MAX_CHUNK_B64  # the hub checks the decoded size
    with pytest.raises(p.ProtocolError):
        _read(
            {
                "type": "relay_data",
                "body": {"request_id": "q", "seq": 0, "data_b64": over},
            }
        )
