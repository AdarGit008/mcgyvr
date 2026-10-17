""

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

#
#
DEFAULT_BIND = "127.0.0.1"

#
FACADE_PORT = 8787

#
#
MAX_BODY_BYTES = 32 * 1024 * 1024

#
#
PING_INTERVAL_S = 5.0

#
#
#
MODEL_ID = "mcorch"

#
type Responder = Callable[[MessagesRequest], Turn]

#
#
type Observer = Callable[[MessagesRequest, Turn, str, float], None]

_MESSAGES = "/v1/messages"
_COUNT = "/v1/messages/count_tokens"
_MODELS = "/v1/models"


@dataclass(frozen=True)
class Facade:
    ""

    respond: Responder
    model: str = MODEL_ID
    max_body_bytes: int = MAX_BODY_BYTES
    ping_interval_s: float = PING_INTERVAL_S
    on_turn: Observer | None = None


def make_server(facade: Facade, *, bind: str, port: int) -> ThreadingHTTPServer:
    ""

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
        #
        #
        return

    #

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

    #

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

    #

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

    #

    def _watched(
        self, request: MessagesRequest, still_there: Callable[[], bool]
    ) -> dict[str, Any] | None:
        ""
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
        ""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return False
            return bool(self.connection.recv(1, socket.MSG_PEEK) == b"")
        except (OSError, ValueError):
            return True

    def _ping(self) -> bool:
        ""
        try:
            self.wfile.write(anthropic.PING)
            self.wfile.flush()
        except OSError:
            return False
        return True

    #

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
