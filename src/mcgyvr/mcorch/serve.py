"""The facade: the orchestrator rung served over HTTP as the Anthropic Messages API.

A harness is pointed at this address with ``ANTHROPIC_BASE_URL``, and asks for
messages the way it asks any API for them. Each message request is parsed into
a :class:`~mcgyvr.mcorch.anthropic.MessagesRequest`, run as one turn of the loop
by the :class:`Facade`'s responder, and written back in the API's own shapes:
one ``message`` object, or the server-sent event sequence, with ``ping``
keep-alives while the turn is still running. The two side doors the API
documents are here as well, ``GET /v1/models`` and ``POST
/v1/messages/count_tokens``; every other path is a ``not_found_error``. A body
larger than the cap is refused unread, and a client that hangs up mid-turn
hangs up on the rung, so the unit stops instead of decoding for nobody.
"""

from __future__ import annotations

import json
import select
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from mcgyvr import runner
from mcgyvr.mcorch import anthropic
from mcgyvr.mcorch.anthropic import ApiError, MessagesRequest
from mcgyvr.mcorch.loop import Turn
from mcgyvr.orchestrator.read import estimate_tokens

# The address the facade listens on unless told otherwise: the loopback,
# so no other machine reaches the rung behind it by accident.
DEFAULT_BIND = "127.0.0.1"

# The port `mcgyvr mcorch serve` listens on when it is not told one.
FACADE_PORT = 8787

# The most of a request body that will be read: a harness sends whole
# transcripts, and a body over this is refused rather than read.
MAX_BODY_BYTES = 32 * 1024 * 1024

# How often a turn in flight is looked in on, and so how often a streamed
# answer gets its ping; each look waits at most this long.
PING_INTERVAL_S = 5.0

# The one model id this server answers as: it is the id in the model
# documents, the loop behind it never reads the model asked for, and a
# GET for any other id is a not_found_error.
MODEL_ID = "mcorch"

# One turn of the loop as the facade calls it: a parsed request in, a Turn out.
type Responder = Callable[[MessagesRequest], Turn]

# Told about each finished turn — its request, the turn, the stop reason,
# and the seconds it took — once the message has been built.
type Observer = Callable[[MessagesRequest, Turn, str, float], None]

_MESSAGES = "/v1/messages"
_COUNT = "/v1/messages/count_tokens"
_MODELS = "/v1/models"


@dataclass(frozen=True)
class Facade:
    """What the server is given: the responder that runs one turn, the model
    id it answers as, the largest body it will read, how often it looks at a
    client mid-turn, and an optional observer of finished turns."""

    respond: Responder
    model: str = MODEL_ID
    max_body_bytes: int = MAX_BODY_BYTES
    ping_interval_s: float = PING_INTERVAL_S
    on_turn: Observer | None = None


def make_server(facade: Facade, *, bind: str, port: int) -> ThreadingHTTPServer:
    """A threading HTTP server on ``bind:port`` that answers through ``facade``.

    The handler is subclassed here so this facade, and not another
    server's, is the one its requests reach.
    """

    class Handler(_Handler):
        pass

    Handler.facade = facade
    return ThreadingHTTPServer((bind, port), Handler)


def _created_at() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class _Handler(BaseHTTPRequestHandler):
    facade: Facade
    protocol_version = "HTTP/1.1"
    server_version = "mcorch"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        # Silent on purpose: the base class writes a line to stderr for every
        # request, and a harness drives this server request after request.
        return

    # Dispatch: the base class calls one of these by HTTP method, per request.

    def do_GET(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        if path == _MODELS:
            self._json(HTTPStatus.OK, self._listing())
            return
        if path.startswith(f"{_MODELS}/"):
            wanted = path.removeprefix(f"{_MODELS}/")
            if wanted == self.facade.model:
                self._json(HTTPStatus.OK, self._model())
                return
            self._error(
                ApiError(HTTPStatus.NOT_FOUND, "not_found_error", f"model: {wanted}")
            )
            return
        self._error(ApiError(HTTPStatus.NOT_FOUND, "not_found_error", f"{path}"))

    def do_POST(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        if path not in (_MESSAGES, _COUNT):
            self._error(ApiError(HTTPStatus.NOT_FOUND, "not_found_error", f"{path}"))
            return
        body = self._body()
        if body is None:
            return
        if path == _COUNT:
            self._count(body)
            return
        request = anthropic.parse_request(body)
        if isinstance(request, ApiError):
            self._error(request)
            return
        if request.stream:
            self._stream(request)
        else:
            self._message(request)

    # Reading the body, and counting one without running a turn.

    def _body(self) -> bytes | None:
        length = self.headers.get("Content-Length")
        try:
            size = int(length) if length is not None else 0
        except ValueError:
            self._error(anthropic.invalid("Content-Length: not a number"))
            return None
        if size > self.facade.max_body_bytes:
            self._error(
                ApiError(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "request_too_large",
                    f"the body is {size} bytes; this server reads at most "
                    f"{self.facade.max_body_bytes}",
                )
            )
            return None
        return self.rfile.read(size)

    def _count(self, body: bytes) -> None:
        try:
            raw = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            self._error(anthropic.invalid(f"the body is not JSON: {exc}"))
            return
        if not isinstance(raw, dict) or not isinstance(raw.get("messages"), list):
            self._error(anthropic.invalid("messages: a list is required"))
            return
        counted = estimate_tokens(
            json.dumps(raw.get("messages"))
            + json.dumps(raw.get("system", ""))
            + json.dumps(raw.get("tools", []))
        )
        self._json(HTTPStatus.OK, {"input_tokens": counted})

    # Answering a turn that has run: a message object, or the event stream.

    def _turn(self, request: MessagesRequest) -> tuple[Turn, dict[str, Any], float]:
        started = time.monotonic()
        turn = self.facade.respond(request)
        elapsed = time.monotonic() - started
        message = anthropic.message_from(
            turn.reply,
            model=request.model,
            message_id=anthropic.new_id("msg"),
            input_tokens=estimate_tokens(
                json.dumps(list(request.messages)) + request.system
            ),
        )
        if self.facade.on_turn is not None:
            self.facade.on_turn(request, turn, str(message["stop_reason"]), elapsed)
        return turn, message, elapsed

    def _message(self, request: MessagesRequest) -> None:
        outcome = self._watched(request, lambda: True)
        if outcome is None:
            return
        failure = outcome.get("error")
        try:
            if failure is not None:
                self._error(
                    ApiError(
                        HTTPStatus.INTERNAL_SERVER_ERROR, "api_error", str(failure)
                    )
                )
                return
            self._json(HTTPStatus.OK, outcome["message"])
        except OSError:
            self.close_connection = True

    def _stream(self, request: MessagesRequest) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        try:
            self.end_headers()
        except OSError:
            self.close_connection = True
            return
        outcome = self._watched(request, self._ping)
        if outcome is None:
            return
        failure = outcome.get("error")
        try:
            if failure is not None:
                self.wfile.write(
                    anthropic.sse(
                        "error",
                        {
                            "type": "error",
                            "error": {"type": "api_error", "message": str(failure)},
                        },
                    )
                )
                self.wfile.flush()
                return
            for name, data in anthropic.events_for(outcome["message"]):
                self.wfile.write(anthropic.sse(name, data))
            self.wfile.flush()
        except OSError:
            self.close_connection = True

    # Watching a turn while it runs: it is hung up on when its client leaves.

    def _watched(
        self, request: MessagesRequest, still_there: Callable[[], bool]
    ) -> dict[str, Any] | None:
        """Run the turn on a worker thread under a hang-up, and keep watch.

        Returns the worker's outcome — ``{"message": ...}``, or ``{"error":
        ...}`` if the responder raised — or ``None`` if the client went first,
        in which case the rung has been hung up on and the connection is
        marked to close. ``still_there`` is called once per ping interval and
        is how the streaming path sends its pings; a ``False`` from it counts
        as the client having gone.
        """
        hangup = runner.Hangup()
        outcome: dict[str, Any] = {}

        def work() -> None:
            with hangup:
                try:
                    _, outcome["message"], _ = self._turn(request)
                except Exception as exc:
                    outcome["error"] = exc

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        while True:
            worker.join(timeout=self.facade.ping_interval_s)
            if not worker.is_alive():
                return outcome
            if self._client_gone() or not still_there():
                hangup.hang_up()
                worker.join()
                self.close_connection = True
                return None

    def _client_gone(self) -> bool:
        """Whether the client has closed its end of the connection.

        A connection that is readable now and reads empty has hung up. The
        read peeks, so bytes a pipelining client has already sent stay in
        the buffer and it counts as still there. A socket that cannot be
        asked counts as gone.
        """
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return False
            return bool(self.connection.recv(1, socket.MSG_PEEK) == b"")
        except (OSError, ValueError):
            return True

    def _ping(self) -> bool:
        """Write one ping event to the stream and say whether it went: a write
        that fails is the client gone, which ends the wait."""
        try:
            self.wfile.write(anthropic.PING)
            self.wfile.flush()
        except OSError:
            return False
        return True

    # Writing: the model documents a listing is made of, and both bodies.

    def _listing(self) -> dict[str, Any]:
        model = self._model()
        return {
            "data": [model],
            "has_more": False,
            "first_id": model["id"],
            "last_id": model["id"],
        }

    def _model(self) -> dict[str, Any]:
        return {
            "type": "model",
            "id": self.facade.model,
            "display_name": self.facade.model,
            "created_at": _created_at(),
        }

    def _json(self, status: HTTPStatus, document: dict[str, Any]) -> None:
        body = json.dumps(document).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, error: ApiError) -> None:
        body = error.body()
        self.send_response(error.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
