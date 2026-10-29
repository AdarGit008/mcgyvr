"""The helper's replies are read strictly or not at all; no request strays.

The agent believes a reply of the ``mcgyvr-wg`` helper only when it is exactly
the answer to the request it sent: the same id, ``ok`` true with exactly the
verb's result fields, each of its type and in its range, or ``ok`` false with
one of the grammar's error codes and a short printable reason. Anything else
— a key too many or too few, a boolean for a number, NaN, a line that is not
one object or is too long — raises, so the session fails rather than acting
on it. The banner must name the pinned helper, tag and proto. And every value
the agent sends is checked first, so a peer's key, a host or an argument can
never start a second request.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.rig import pooled, wghelper, wgpin

KEY = "D" * 42 + "Q="


def line(body: dict[str, Any]) -> bytes:
    return (json.dumps(body) + "\n").encode()


def test_a_reply_with_exactly_its_fields_is_read() -> None:
    found = wghelper.read_reply(
        line({"id": 3, "ok": True, "public_key": KEY}), 3, "prepare"
    )
    assert found == {"public_key": KEY}


@pytest.mark.parametrize(
    ("body", "verb"),
    [
        ({"id": 4, "ok": True, "public_key": KEY}, "prepare"),  # another request
        ({"id": 3, "ok": True}, "prepare"),  # a field too few
        ({"id": 3, "ok": True, "public_key": KEY, "private_key": KEY}, "prepare"),
        ({"id": 3, "ok": True, "public_key": "A" * 44}, "prepare"),  # not a key
        ({"id": 3, "ok": True, "port": True}, "forward"),  # a boolean for a number
        ({"id": 3, "ok": True, "port": 70000}, "forward"),
        ({"id": 3, "ok": True, "pid": 0}, "spawn"),
        ({"id": 3, "ok": "yes", "public_key": KEY}, "prepare"),
        ({"id": 3, "ok": True, "state": "zombie", "exit": None}, "state"),
        ({"id": 3, "ok": True, "rtt_ms": -1, "full": True, "size": 1172}, "ping"),
        ({"id": 3, "ok": True, "rtt_ms": 0.5, "full": 1, "size": 1172}, "ping"),
        (
            {
                "id": 3,
                "ok": True,
                "now": 5,
                "peers": [{"key": KEY, "handshake": 1, "endpoint": "300.1.1.1:5"}],
            },
            "peers",
        ),
        ({"id": 3, "ok": False, "error": "no_such_code", "why": "x"}, "lease"),
        ({"id": 3, "ok": False, "error": "internal", "why": "a\nb"}, "lease"),
        ({"id": 3, "ok": False, "error": "internal", "why": "x" * 301}, "lease"),
        ({"id": 3, "ok": False, "error": "internal"}, "lease"),
    ],
)
def test_a_reply_that_is_not_exactly_the_answer_is_not_believed(
    body: dict[str, Any], verb: str
) -> None:
    with pytest.raises(wghelper.HelperError) as raised:
        wghelper.read_reply(line(body), 3, verb)
    assert raised.value.code == "protocol"
    assert isinstance(raised.value, pooled.PoolError)


@pytest.mark.parametrize(
    "raw",
    [
        b"not json\n",
        b'{"id": 3, "ok": true, "rtt_ms": NaN, "full": true, "size": 1172}\n',
        b"[3]\n",
        b'{"id": 3, "ok": true}',  # no line end: cut short
        b'{"id": 3, "ok": true, "x": "' + b"a" * wghelper.LINE_MAX + b'"}\n',
    ],
)
def test_a_line_that_is_not_one_json_object_is_not_believed(raw: bytes) -> None:
    with pytest.raises(wghelper.HelperError) as raised:
        wghelper.read_reply(raw, 3, "ping")
    assert raised.value.code == "protocol"


def test_a_refusal_raises_with_the_helpers_own_code() -> None:
    body = {"id": 3, "ok": False, "error": "bind_failed", "why": "port 51820 is held"}
    with pytest.raises(wghelper.HelperError) as raised:
        wghelper.read_reply(line(body), 3, "prepare")
    assert raised.value.code == "bind_failed"
    assert "port 51820 is held" in str(raised.value)


def test_the_banner_must_name_the_pinned_helper_tag_and_proto() -> None:
    good = {
        "id": 0,
        "ok": True,
        "helper": wgpin.PROGRAM,
        "version": wgpin.TAG,
        "proto": wgpin.PROTO,
    }
    assert wghelper.read_banner(line(good)) == wgpin.TAG
    for change in (
        {"helper": "wireproxy"},
        {"version": "v0.0.9"},
        {"proto": wgpin.PROTO + 1},
        {"id": 1},
        {"extra": True},
    ):
        with pytest.raises(wghelper.HelperError):
            wghelper.read_banner(line({**good, **change}))


@pytest.mark.parametrize(
    "send",
    [
        lambda h: h.prepare(51820, ["192.0.2.1\n{}"], 60),
        lambda h: h.prepare(80, ["192.0.2.1"], 60),
        lambda h: h.forward("head", "198.51.100.1", 22),
        lambda h: h.forward("worker-0", "198.51.100.1", 50052),
        lambda h: h.forward("head", "example.invalid", 50052),
        lambda h: h.up(
            "198.51.100.2/24",
            1200,
            [
                wghelper.UpPeer(
                    KEY + "\n", "192.0.2.20", 51820, 25, ("198.51.100.1/32",)
                )
            ],
        ),
        lambda h: h.up("198.51.100.2", 1200, []),
        lambda h: h.spawn(
            "head", Path("llama-server"), [], {}, Path("/tmp"), Path("/tmp/x.log")
        ),
        lambda h: h.spawn(
            "head",
            Path("/bin/llama-server"),
            ["a\x00b"],
            {},
            Path("/tmp"),
            Path("/tmp/x.log"),
        ),
        lambda h: h.spawn(
            "head",
            Path("/bin/llama-server"),
            [],
            {"A=B": "c"},
            Path("/tmp"),
            Path("/tmp/x.log"),
        ),
        lambda h: h.stun("not-a-token", [("203.0.113.9", 3478)], 3, 500),
    ],
)
def test_a_value_outside_the_grammar_is_never_sent(send: Any, tmp_path: Path) -> None:
    helper = wghelper.Helper(["/nonexistent"], log=tmp_path / "helper.log")
    with pytest.raises(wghelper.HelperError) as raised:
        send(helper)
    assert raised.value.code == "bad_request"


def test_a_helper_that_cannot_start_is_gone_not_a_crash(tmp_path: Path) -> None:
    helper = wghelper.Helper([str(tmp_path / "missing")], log=tmp_path / "h.log")
    with pytest.raises(wghelper.HelperError) as raised:
        helper.start()
    assert raised.value.code == "gone"
    with pytest.raises(wghelper.HelperError):
        helper.lease()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"id": 3, "ok": false, "error": [1], "why": "x"}\n',
        b"[" * 60000 + b"\n",
        b'{"id": 3, "ok": true, "port": 50052, "port": 1}\n',
        b'{"id": 3, "ok": true, "rtt_ms": 1' + b"0" * 400 + b', "full": true, '
        b'"size": 1172}\n',
    ],
)
def test_whatever_a_hostile_reply_provokes_is_not_believed(raw: bytes) -> None:
    verb = "ping" if b"rtt_ms" in raw else "forward"
    with pytest.raises(wghelper.HelperError) as raised:
        wghelper.read_reply(raw, 3, verb)
    assert raised.value.code == "protocol"


@pytest.mark.parametrize(
    "endpoint", ["1.2.3.4:²", "1.2.3.4:0443", "1.2.3.4:٤٤٣", "1.2.3.4:70000"]
)
def test_an_endpoint_port_is_ascii_digits_with_no_leading_zero(endpoint: str) -> None:
    body = {
        "id": 3,
        "ok": True,
        "now": 5,
        "peers": [{"key": KEY, "handshake": 1, "endpoint": endpoint}],
    }
    with pytest.raises(wghelper.HelperError):
        wghelper.read_reply(line(body), 3, "peers")


def test_a_forward_below_the_unprivileged_ports_is_not_believed() -> None:
    with pytest.raises(wghelper.HelperError):
        wghelper.read_reply(line({"id": 3, "ok": True, "port": 80}), 3, "forward")


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "127.0.0.1", "224.0.0.1", "255.255.255.255"]
)
def test_a_session_socket_binds_none_of_the_hosts_no_peer_reaches(
    host: str, tmp_path: Path
) -> None:
    helper = wghelper.Helper(["/nonexistent"], log=tmp_path / "helper.log")
    with pytest.raises(wghelper.HelperError) as raised:
        helper.prepare(51820, [host], 60)
    assert raised.value.code == "bad_request"
