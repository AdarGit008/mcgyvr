"""A hostile session command is refused by name, and starts nothing.

What the hub sends is untrusted, so each command is read against the schema
and then against this rig: a model named with a path, or not on this rig; a
tunnel network that is the LAN's own, or a peer allowed every address, or
reached only at a loopback or named host, a public address called a LAN
one, or a kind of endpoint the agent does not walk; an RPC device outside the
session's tunnel; a card the owner does not lend; a port no unprivileged
server binds; a frame over the protocol's size; a command for a session this
rig is not in, or for a second session while every lent card is held; any
session at all while lending is off. Each is answered with the hub's code and a message
naming the field — never echoing the value — and nothing more is started.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared

#: A public address, written as a number so that no real machine is named.
PUBLIC = str(ipaddress.IPv4Address(2**31 + 5))


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _refused(answer: dict[str, Any] | None, code: str, *hidden: str) -> None:
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == code, answer
    for value in hidden:
        assert value not in answer["body"]["message"]


def _head(pool: Pool) -> None:
    prepared(pool, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)


def _head_start(pool: Pool, **changes: Any) -> dict[str, Any] | None:
    body: dict[str, Any] = {
        "session_id": "s1",
        "model": {"name": fakes.MODEL},
        "ctx": 4096,
        "devices": [{"kind": "local", "card_index": 0}],
        "tensor_split": [1],
    }
    body.update(changes)
    return pool.ask("head_start", "h1", **body)


@pytest.mark.parametrize(
    "name", ["../../etc/passwd", "/etc/passwd", ".hidden.gguf", "dense/model.gguf", ""]
)
def test_a_model_named_with_a_path_is_refused_before_anything_is_looked_up(
    pool: Pool, name: str
) -> None:
    _head(pool)
    _refused(_head_start(pool, model={"name": name}), "bad_message")
    pool.settle()
    assert len(pool.docker.runs()) == 1


def test_a_model_this_rig_does_not_hold_is_missing(pool: Pool) -> None:
    _head(pool)
    _refused(_head_start(pool, model={"name": "other-model.gguf"}), "model_missing")
    pool.settle()
    assert len(pool.docker.runs()) == 1


def test_an_rpc_device_outside_the_sessions_tunnel_is_refused(pool: Pool) -> None:
    _head(pool)
    for host in ("192.0.2.99", "127.0.0.1", fakes.PEER):
        answer = _head_start(
            pool,
            devices=[{"kind": "rpc", "host": host, "port": 50052}],
            tensor_split=[1],
        )
        _refused(answer, "bad_message", host)
    pool.settle()
    assert len(pool.docker.runs()) == 1


def test_a_card_the_owner_does_not_lend_is_not_capable(tmp_path: Path) -> None:
    made = make_pool(tmp_path, cards=(1,))
    try:
        prepared(made)
        made.up("t1", **fakes.tunnel_up_body())
        for card in (0, 2, 9):  # not lent; another vendor's; not there
            answer = made.ask(
                "worker_start",
                f"w{card}",
                session_id="s1",
                cards=[{"card_index": card, "port": 50052}],
            )
            _refused(answer, "not_capable")
        made.settle()
        assert len(made.docker.runs()) == 1
    finally:
        made.sessions.close()


def test_a_port_no_unprivileged_server_binds_is_refused(pool: Pool) -> None:
    prepared(pool)
    pool.up("t1", **fakes.tunnel_up_body())
    answer = pool.ask(
        "worker_start", "w1", session_id="s1", cards=[{"card_index": 0, "port": 22}]
    )
    _refused(answer, "bad_message")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"address": f"{fakes.LAN_ADDRESS.rsplit('.', 1)[0]}.77/24"}, "tunnel_failed"),
        ({"address": f"{PUBLIC}/24"}, "tunnel_failed"),
        ({"address": f"{fakes.SELF}/8"}, "tunnel_failed"),
        ({"listen_port": 51821}, "bad_message"),
    ],
)
def test_a_tunnel_on_addresses_it_must_not_use_is_refused(
    pool: Pool, change: dict[str, Any], code: str
) -> None:
    from mcgyvr.rig import pooled

    prepared(pool)
    _refused(pool.ask("tunnel_up", "t1", **fakes.tunnel_up_body(**change)), code)
    pool.settle()
    assert not [s for s in pool.docker.scripts if s[1] == pooled.TUNNEL_SCRIPT]


@pytest.mark.parametrize(
    "peer_change",
    [
        {"allowed_ips": ["0.0.0.0/0"]},
        {"allowed_ips": [f"{fakes.SELF}/32"]},
        {"allowed_ips": ["192.0.2.0/24"]},
        {"endpoints": [{"host": PUBLIC, "port": 51820, "kind": "lan"}]},
        {"endpoints": [{"host": PUBLIC, "port": 51820, "kind": "unheard_of"}]},
        {"endpoints": [{"host": "127.0.0.1", "port": 51820, "kind": "lan"}]},
        {"endpoints": [{"host": "peer.invalid", "port": 51820, "kind": "lan"}]},
        {"endpoints": [{"host": fakes.LAN_ADDRESS, "port": 51820, "kind": "lan"}]},
        {"endpoints": []},
    ],
)
def test_a_peer_allowed_too_much_or_reached_at_a_foreign_address_is_refused(
    pool: Pool, peer_change: dict[str, Any]
) -> None:
    from mcgyvr.rig import pooled

    prepared(pool)
    body = fakes.tunnel_up_body()
    body["peers"][0].update(peer_change)
    _refused(pool.ask("tunnel_up", "t1", **body), "tunnel_failed", PUBLIC)
    pool.settle()
    assert not [s for s in pool.docker.scripts if s[1] == pooled.TUNNEL_SCRIPT]


def test_a_frame_over_the_protocols_size_is_refused_unread(pool: Pool) -> None:
    from mcgyvr.rig import protocol

    big = json.dumps(
        {
            "v": 1,
            "type": "tunnel_up",
            "id": "t1",
            "body": {"session_id": "s1", "pad": "x" * protocol.MAX_MESSAGE_BYTES},
        }
    )
    reply = pool.dispatcher.dispatch(big, fakes.Stub())
    assert reply is not None
    answer = json.loads(reply)
    assert answer["body"]["code"] == "bad_message" and "re" not in answer
    assert pool.docker.calls == []


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("tunnel_up", fakes.tunnel_up_body(session_id="other")),
        (
            "worker_start",
            {"session_id": "other", "cards": [{"card_index": 0, "port": 50052}]},
        ),
        (
            "head_start",
            {
                "session_id": "other",
                "model": {"name": fakes.MODEL},
                "ctx": 4096,
                "devices": [{"kind": "local", "card_index": 0}],
                "tensor_split": [1],
            },
        ),
    ],
)
def test_a_command_for_a_session_this_rig_is_not_in_is_unknown(
    pool: Pool, kind: str, body: dict[str, Any]
) -> None:
    prepared(pool)
    _refused(pool.ask(kind, "c9", **body), "unknown_session")
    pool.settle()
    assert len(pool.docker.runs()) == 1


def test_a_second_session_while_every_lent_card_is_held_is_busy(pool: Pool) -> None:
    prepared(pool)
    pool.up("t1", **fakes.tunnel_up_body())
    cards = [{"card_index": 0, "port": 50052}, {"card_index": 1, "port": 50053}]
    ack = pool.ask("worker_start", "w1", session_id="s1", cards=cards)
    assert ack is not None and ack["type"] == "ack", ack
    pool.wait_for("session_status", "ready")
    runs = len(pool.docker.runs())
    _refused(pool.ask("session_prepare", "p2", session_id="s2", role="worker"), "busy")
    pool.settle()
    assert len(pool.docker.runs()) == runs


def test_nothing_is_lent_while_lending_is_off(tmp_path: Path) -> None:
    made = make_pool(tmp_path, enabled=False)
    try:
        _refused(
            made.ask("session_prepare", "p1", session_id="s1", role="worker"),
            "not_capable",
        )
        assert made.docker.calls == []
    finally:
        made.sessions.close()


def test_the_head_is_not_offered_without_a_models_folder(tmp_path: Path) -> None:
    made = make_pool(tmp_path, roles=("worker",))
    try:
        _refused(
            made.ask("session_prepare", "p1", session_id="s1", role="head"),
            "not_capable",
        )
        assert made.docker.calls == []
    finally:
        made.sessions.close()


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": "s1", "role": "boss"},
        {"session_id": "../s1", "role": "worker"},
        {"session_id": "s1"},
        {"session_id": 1, "role": "worker"},
    ],
)
def test_a_prepare_not_of_the_schemas_shape_is_a_bad_message(
    pool: Pool, body: dict[str, Any]
) -> None:
    _refused(pool.ask("session_prepare", "p1", **body), "bad_message", "boss", "../s1")
    assert pool.docker.calls == []
