""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from mcgyvr.rig import protocol


class Session(Protocol):
    ""

    def on_ack(self, ack: protocol.Ack) -> None:
        ""

    def on_error(self, error: protocol.Error) -> None:
        ""


#
Handler = Callable[[protocol.Envelope, Session], str | None]

#
FAILED = "failed"


def _ack(envelope: protocol.Envelope, session: Session) -> None:
    session.on_ack(protocol.read_ack(envelope))


def _error(envelope: protocol.Envelope, session: Session) -> None:
    session.on_error(protocol.read_error(envelope))


class Dispatcher:
    ""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {"ack": _ack, "error": _error}

    def known(self) -> tuple[str, ...]:
        ""
        return tuple(self._handlers)

    def register(self, kind: str, handler: Handler) -> None:
        ""
        if not protocol.TAG.fullmatch(kind):
            raise ValueError(f"{kind!r} is not a message type")
        if kind in self._handlers:
            raise ValueError(f"{kind!r} has a handler already")
        self._handlers[kind] = handler

    def dispatch(self, raw: str | bytes, session: Session) -> str | None:
        ""
        try:
            envelope = protocol.decode(raw)
        except protocol.ProtocolError as refused:
            return _refusal(refused.code, refused.message, refused.re)
        handler = self._handlers.get(envelope.type)
        if handler is None:
            return _refusal(
                protocol.ErrorCode.UNSUPPORTED_TYPE,
                f"this agent does not handle {envelope.type}",
                envelope.id,
            )
        try:
            return handler(envelope, session)
        except protocol.ProtocolError as refused:
            return _refusal(refused.code, refused.message, refused.re or envelope.id)
        except Exception as failure:  #
            return _refusal(
                FAILED,
                f"the agent failed handling {envelope.type} "
                f"({failure.__class__.__name__})",
                envelope.id,
            )


def _refusal(code: str, message: str, re: str | None) -> str:
    return protocol.error(protocol.new_id(), code=code, message=message, re=re)
