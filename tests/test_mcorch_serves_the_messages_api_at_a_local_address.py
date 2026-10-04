"""mcorch serves the Anthropic Messages API at a local address a harness points at.

``ANTHROPIC_BASE_URL=http://127.0.0.1:PORT claude`` (or pi's
``anthropic-messages`` provider) sends ``POST /v1/messages``, streaming; the
facade answers in the API's own shapes: a ``message`` object, or the SSE event
sequence with ``ping`` keep-alives while the loop works. It also answers the
two side doors the API documents and a harness may knock on — ``GET
/v1/models`` and ``POST /v1/messages/count_tokens`` — and refuses everything
else as ``not_found_error``. A body over the cap is ``request_too_large``; a
malformed one is ``invalid_request_error`` naming the field. The server binds
``127.0.0.1`` unless told otherwise, and the body cap holds whatever it binds.
The rung behind the facade is a scripted double: no model is reached.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator

import pytest

from mcgyvr.mcorch import serve
from mcgyvr.mcorch.anthropic import MessagesRequest
from mcgyvr.mcorch.loop import Trace, Turn
from tests.mcorch_fakes import calls, text

TRACE = Trace(
    kind="main",
    intent="work",
    jev=(),
    dropped_tools=(),
    dropped_system_bytes=0,
    dropped_blocks=(),
    rounds=1,
    internal_calls=(),
    next=None,
)


class _Responder:
    """A stand-in for the loop: answers from a script, optionally slowly."""

    def __init__(self, *turns: Turn, delay_s: float = 0.0) -> None:
        self.turns = list(turns)
        self.delay_s = delay_s
        self.seen: list[MessagesRequest] = []

    def __call__(self, request: MessagesRequest) -> Turn:
        self.seen.append(request)
        if self.delay_s:
            time.sleep(self.delay_s)
        return self.turns.pop(0)


@pytest.fixture
def served(request: pytest.FixtureRequest) -> Iterator[tuple[str, int, _Responder]]:
    responder = getattr(request, "param", None) or _Responder(
        Turn(reply=text("hello"), trace=TRACE)
    )
    facade = serve.Facade(respond=responder, ping_interval_s=0.05)
    server = serve.make_server(facade, bind="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield str(host), int(port), responder
    finally:
        server.shutdown()
        server.server_close()


def _post(
    host: str, port: int, path: str, body: bytes, timeout: float = 5.0
) -> http.client.HTTPResponse:
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    connection.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": "not-checked",
        },
    )
    return connection.getresponse()


def _request(**fields: object) -> bytes:
    base: dict[str, object] = {
        "model": "claude-sonnet-x",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "hi"}],
    }
    base.update(fields)
    return json.dumps(base).encode("utf-8")


def test_a_message_is_answered_as_a_message_object(
    served: tuple[str, int, _Responder],
) -> None:
    host, port, responder = served
    response = _post(host, port, "/v1/messages", _request())
    assert response.status == 200
    assert response.getheader("Content-Type", "").startswith("application/json")
    message = json.loads(response.read())
    assert message["type"] == "message"
    assert message["role"] == "assistant"
    assert message["content"] == [{"type": "text", "text": "hello"}]
    assert message["stop_reason"] == "end_turn"
    assert message["model"] == "claude-sonnet-x"  # the model the harness named
    assert message["id"].startswith("msg_")
    assert responder.seen[0].max_tokens == 64


@pytest.mark.parametrize(
    "served",
    [
        _Responder(
            Turn(
                reply=calls(("Bash", '{"command": "ls"}'), text="listing"),
                trace=TRACE,
            ),
            delay_s=0.2,
        )
    ],
    indirect=True,
)
def test_a_streamed_message_is_the_event_sequence_with_pings_while_the_loop_works(
    served: tuple[str, int, _Responder],
) -> None:
    host, port, _ = served
    response = _post(host, port, "/v1/messages?beta=true", _request(stream=True))
    assert response.status == 200
    assert response.getheader("Content-Type", "").startswith("text/event-stream")
    raw = response.read().decode("utf-8")
    events = [
        chunk.split("\n", 1)[0].removeprefix("event: ")
        for chunk in raw.strip().split("\n\n")
    ]
    assert events[0] == "ping"
    without_pings = [name for name in events if name != "ping"]
    assert without_pings == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert '"stop_reason": "tool_use"' in raw
    assert '"name": "Bash"' in raw


def test_a_malformed_body_is_refused_in_the_apis_error_shape(
    served: tuple[str, int, _Responder],
) -> None:
    host, port, responder = served
    response = _post(host, port, "/v1/messages", _request(max_tokens=0))
    assert response.status == 400
    error = json.loads(response.read())
    assert error["type"] == "error"
    assert error["error"]["type"] == "invalid_request_error"
    assert "max_tokens" in error["error"]["message"]
    assert responder.seen == []


def test_an_unknown_path_is_not_found(served: tuple[str, int, _Responder]) -> None:
    host, port, _ = served
    response = _post(host, port, "/v1/complete", _request())
    assert response.status == 404
    assert json.loads(response.read())["error"]["type"] == "not_found_error"


def test_a_body_over_the_cap_is_too_large(served: tuple[str, int, _Responder]) -> None:
    _, _, responder = served
    facade = serve.Facade(respond=responder, max_body_bytes=100, ping_interval_s=0.05)
    server = serve.make_server(facade, bind="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        small_host, small_port = server.server_address[0], server.server_address[1]
        response = _post(
            str(small_host), int(small_port), "/v1/messages", _request(system="x" * 200)
        )
        assert response.status == 413
        assert json.loads(response.read())["error"]["type"] == "request_too_large"
    finally:
        server.shutdown()
        server.server_close()


def test_count_tokens_answers_an_estimate(served: tuple[str, int, _Responder]) -> None:
    host, port, responder = served
    body = json.dumps(
        {
            "model": "claude-sonnet-x",
            "messages": [{"role": "user", "content": "a" * 400}],
        }
    ).encode("utf-8")
    response = _post(host, port, "/v1/messages/count_tokens", body)
    assert response.status == 200
    counted = json.loads(response.read())
    assert isinstance(counted["input_tokens"], int)
    assert counted["input_tokens"] > 0
    assert responder.seen == []  # no turn is run for a count


def test_models_lists_the_one_model_this_server_is(
    served: tuple[str, int, _Responder],
) -> None:
    host, port, _ = served
    connection = http.client.HTTPConnection(host, port, timeout=5.0)
    connection.request("GET", "/v1/models")
    response = connection.getresponse()
    assert response.status == 200
    listing = json.loads(response.read())
    assert [model["id"] for model in listing["data"]] == [serve.MODEL_ID]
    assert listing["has_more"] is False
    connection = http.client.HTTPConnection(host, port, timeout=5.0)
    connection.request("GET", f"/v1/models/{serve.MODEL_ID}")
    assert connection.getresponse().status == 200
    connection = http.client.HTTPConnection(host, port, timeout=5.0)
    connection.request("GET", "/v1/models/other")
    assert connection.getresponse().status == 404


def test_the_server_binds_the_loopback_unless_told_otherwise() -> None:
    assert serve.DEFAULT_BIND == "127.0.0.1"
    server = serve.make_server(
        serve.Facade(respond=_Responder()), bind=serve.DEFAULT_BIND, port=0
    )
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_the_facade_reports_each_turn_to_its_observer(
    served: tuple[str, int, _Responder],
) -> None:
    _, _, responder = served
    seen: list[tuple[str, str]] = []

    def observe(
        request: MessagesRequest, turn: Turn, stop_reason: str, _: float
    ) -> None:
        seen.append((request.model, stop_reason))

    facade = serve.Facade(respond=responder, on_turn=observe)
    server = serve.make_server(facade, bind="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        responder.turns.append(Turn(reply=text("again"), trace=TRACE))
        _post(
            str(server.server_address[0]),
            int(server.server_address[1]),
            "/v1/messages",
            _request(),
        ).read()
    finally:
        server.shutdown()
        server.server_close()
    assert seen == [("claude-sonnet-x", "end_turn")]
