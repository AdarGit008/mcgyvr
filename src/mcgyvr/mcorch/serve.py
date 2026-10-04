"""The Anthropic Messages API facade: the address a harness points at.

``ANTHROPIC_BASE_URL=http://127.0.0.1:PORT claude``, or pi's
``anthropic-messages`` provider with the same base URL, sends the harness's
conversation here as ``POST /v1/messages``. The facade reads the request
(:func:`mcgyvr.mcorch.anthropic.parse_request`), hands it to the loop
(:func:`mcgyvr.mcorch.loop.respond`), and writes the reply back in the API's
own shapes — a ``message`` object, or the SSE event sequence with ``ping``
keep-alives while the loop works (the harness streams; a stream that is silent
for a minute is a stream the harness gives up on). The two side doors the API
documents and a harness may knock on are answered too: ``GET /v1/models``
lists the one model this server is, and ``POST /v1/messages/count_tokens``
answers with the product's own token estimate — Claude Code's documentation
does not state whether it calls either, so both are served rather than
guessed at. Every other path is ``not_found_error``.

Security baseline: binds ``127.0.0.1`` unless ``--bind`` says otherwise (the
rigs are on a tailnet), reads at most :data:`MAX_BODY_BYTES` of a body, and
never checks or logs the credential header a harness sends — there is no
secret here to check it against, and a request from the loopback is the
user's own. The stdlib server is enough: one harness, a handful of requests
a minute, no dependency added.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from mcgyvr.mcorch import anthropic
from mcgyvr.mcorch.anthropic import ApiError, MessagesRequest
from mcgyvr.mcorch.loop import Turn
from mcgyvr.orchestrator.read import estimate_tokens

#: The address a server binds when nobody says otherwise: the loopback. A LAN
#: address is `--bind`'s to give.
DEFAULT_BIND = "127.0.0.1"

#: The port a server listens on when `--port` names none.
FACADE_PORT = 8787

#: The most a request body may hold, in bytes: the Messages API's own request
#: limit, so a harness built against the API never meets a smaller one here.
MAX_BODY_BYTES = 32 * 1024 * 1024

#: How often, in seconds, a streaming reply sends `ping` while the loop works.
PING_INTERVAL_S = 5.0

#: The one model this server is, as `GET /v1/models` lists it. The `model` a
#: harness names in a request is echoed back in the reply, whatever it is: the
#: harness picked a name it knows, and the reply is for the harness.
MODEL_ID = "mcorch"

#: The loop as the facade sees it: one request in, one turn out.
type Responder = Callable[[MessagesRequest], Turn]

#: An observer of finished turns: the request, the turn, its stop reason and
#: the seconds it took. The transcript is one.
type Observer = Callable[[MessagesRequest, Turn, str, float], None]

_MESSAGES = "/v1/messages"
_COUNT = "/v1/messages/count_tokens"
_MODELS = "/v1/models"


@dataclass(frozen=True)
class Facade:
    """What a server serves: the loop, and the bounds it serves it under."""

    respond: Responder
    model: str = MODEL_ID
    max_body_bytes: int = MAX_BODY_BYTES
    ping_interval_s: float = PING_INTERVAL_S
    on_turn: Observer | None = None


def make_server(facade: Facade, *, bind: str, port: int) -> ThreadingHTTPServer:
    """A bound, not yet serving, HTTP server; the caller runs ``serve_forever``."""

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
        # Quiet by design: the transcript is the record, and the access log of
        # a loopback server tells an operator nothing it does not already know.
        return

    # --- routing ---------------------------------------------------------------

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

    # --- bodies ----------------------------------------------------------------

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

    # --- the turn --------------------------------------------------------------

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
        try:
            _, message, _ = self._turn(request)
        except Exception as exc:
            self._error(
                ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "api_error", str(exc))
            )
            return
        self._json(HTTPStatus.OK, message)

    def _stream(self, request: MessagesRequest) -> None:
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                _, outcome["message"], _ = self._turn(request)
            except Exception as exc:
                outcome["error"] = exc

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        while worker.is_alive():
            worker.join(timeout=self.facade.ping_interval_s)
            if worker.is_alive():
                self.wfile.write(anthropic.PING)
                self.wfile.flush()
        failure = outcome.get("error")
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

    # --- writing ---------------------------------------------------------------

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
