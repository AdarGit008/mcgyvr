"""What the agent does with each message the hub sends: one handler per type.

Every frame from the hub goes through :meth:`Dispatcher.dispatch`. The frame
is read as an envelope first (:func:`mcgyvr.rig.protocol.decode`), then handed
to the one handler registered under its type, with the agent's session; what
the handler returns is the answer the agent sends, or nothing.

Today the dispatcher knows ``ack`` and ``error``: it reads their bodies and
hands them to the session (:class:`Session`). A type it does not know is
answered with ``unsupported_type``, re the frame, and the channel stays open,
as the protocol asks of a receiver. A frame that is not well formed, or a
known type whose body is not, is answered with the protocol's code and
reaches no handler.

This is the seam the hub's commands are added at: starting a worker or a
head, stopping one, relaying a request. Each is a handler registered under its
type (:meth:`Dispatcher.register`) that reads its own body, does its work
through the product's serving door, and answers with ``ack`` or ``error`` re
the command. A handler that raises is answered with ``failed`` and the agent
goes on; the exception's text is not sent, since it may hold what the hub has
no business reading.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from mcgyvr.rig import protocol


class Session(Protocol):
    """What the dispatcher tells the agent's session."""

    def on_ack(self, ack: protocol.Ack) -> None:
        """The hub acknowledged a message the agent sent."""

    def on_error(self, error: protocol.Error) -> None:
        """The hub refused a message, or is about to close the channel."""


#: A handler: the frame and the session in, the answer to send (or ``None``).
Handler = Callable[[protocol.Envelope, Session], str | None]

#: The code a handler's failure is answered with.
FAILED = "failed"


def _ack(envelope: protocol.Envelope, session: Session) -> None:
    session.on_ack(protocol.read_ack(envelope))


def _error(envelope: protocol.Envelope, session: Session) -> None:
    session.on_error(protocol.read_error(envelope))


class Dispatcher:
    """The handlers by type: ``ack`` and ``error``, and whatever is registered."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {"ack": _ack, "error": _error}

    def known(self) -> tuple[str, ...]:
        """The types a handler is registered under, in registration order."""
        return tuple(self._handlers)

    def register(self, kind: str, handler: Handler) -> None:
        """Handle ``kind`` with ``handler``; a type is registered once."""
        if not protocol.TAG.fullmatch(kind):
            raise ValueError(f"{kind!r} is not a message type")
        if kind in self._handlers:
            raise ValueError(f"{kind!r} has a handler already")
        self._handlers[kind] = handler

    def dispatch(self, raw: str | bytes, session: Session) -> str | None:
        """Handle one hub frame; the answer to send, if any."""
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
        except Exception as failure:  # the agent outlives a handler
            return _refusal(
                FAILED,
                f"the agent failed handling {envelope.type} "
                f"({failure.__class__.__name__})",
                envelope.id,
            )


def _refusal(code: str, message: str, re: str | None) -> str:
    return protocol.error(protocol.new_id(), code=code, message=message, re=re)
