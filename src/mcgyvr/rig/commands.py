"""The one table from a frame's type tag to the handler that answers it.

``Dispatcher`` reads every frame the hub sends and hands it to the handler
registered under its type, alongside the session the frame came over. The two
frames every agent reads, ``ack`` and ``error``, come built in and are read into
``protocol.Ack`` and ``protocol.Error`` before the session sees them; the
commands the agent serves register their own handler under their type tag.

A handler returns the answer to send or None when nothing is due. A frame that
does not read, a type with no handler here, and a handler that raises are all
answered with an ``error`` frame rather than ending the channel.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from mcgyvr.rig import protocol


class Session(Protocol):
    """What the dispatcher needs of the connection a frame arrived over.

    Only these two calls are made on it, so the agent's own session and a test's
    stand-in both serve.
    """

    def on_ack(self, ack: protocol.Ack) -> None:
        """Take an ack the hub sent: the rig id and beat interval it set."""

    def on_error(self, error: protocol.Error) -> None:
        """Take an error the hub sent: its code and the text to show."""


# One command's handler: the frame as it arrived and the session it came over,
# returning the frame to send back or None when no answer is due.
Handler = Callable[[protocol.Envelope, Session], str | None]

# The code a handler's own exception is answered with. It is not one of the
# protocol's codes, so the hub reads the answer as this agent failing at the
# command rather than as a refusal of the frame it sent.
FAILED = "failed"


def _ack(envelope: protocol.Envelope, session: Session) -> None:
    session.on_ack(protocol.read_ack(envelope))


def _error(envelope: protocol.Envelope, session: Session) -> None:
    session.on_error(protocol.read_error(envelope))


class Dispatcher:
    """The handlers this agent answers the hub with, keyed by message type.

    It starts knowing ``ack`` and ``error``; the parts of the agent that serve
    commands register one handler each under the type tag that command arrives
    as.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {"ack": _ack, "error": _error}

    def known(self) -> tuple[str, ...]:
        """The type tags with a handler, in the order they were registered."""
        return tuple(self._handlers)

    def register(self, kind: str, handler: Handler) -> None:
        """Put one handler under a type tag that is allowed and not taken yet.

        A tag the protocol does not spell as a message type, or one that already
        has a handler, is a ``ValueError`` naming it.
        """
        if not protocol.TAG.fullmatch(kind):
            raise ValueError(f"{kind!r} is not a message type")
        if kind in self._handlers:
            raise ValueError(f"{kind!r} has a handler already")
        self._handlers[kind] = handler

    def dispatch(self, raw: str | bytes, session: Session) -> str | None:
        """Read one frame and hand it to the handler its type names.

        What comes back is the frame to send in answer, or None where the
        handler answered nothing. A frame that is not of the protocol is
        answered with its own code and reaches no handler, and so is a type with
        no handler here, which is answered as ``unsupported_type``.
        """
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
        except Exception as failure:  # the handler's own failure, not the frame's
            return _refusal(
                FAILED,
                f"the agent failed handling {envelope.type} "
                f"({failure.__class__.__name__})",
                envelope.id,
            )


def _refusal(code: str, message: str, re: str | None) -> str:
    return protocol.error(protocol.new_id(), code=code, message=message, re=re)
