"""What a worker is sent, and what may be read back from it.

Two halves of one protocol, kept together because they only make sense
together: :mod:`~mcgyvr.worker.prompt` tells the worker to reply with one
fenced block, and :mod:`~mcgyvr.worker.reply` is what refuses a reply that is
not one. Splitting them across modules that do not import each other is how the
instruction and the parser drift apart.

:mod:`~mcgyvr.worker.bundle` is the measured system prompt (CLM-0004) and the
enforcement of the size the measurement justifies.

Nothing here dispatches. Choosing a rung and escalating are #24's, bounding
concurrency is #23's, and a :class:`~mcgyvr.runner.Request` still carries plain
text — this package only decides what that text is and what may be believed
about the answer.
"""

from __future__ import annotations

from mcgyvr.worker.bundle import (
    MAX_BUNDLE_BYTES,
    Bundle,
    BundleError,
    BundleMissingError,
    BundleStanding,
    BundleTooLargeError,
    bundle_for,
    load_bundle,
)
from mcgyvr.worker.prompt import WorkerPrompt, build_prompt, render_user_message
from mcgyvr.worker.reply import (
    WHOLE_FILE,
    ParsedFile,
    ReplyError,
    parse_pinned,
    parse_reply,
)

__all__ = [
    "MAX_BUNDLE_BYTES",
    "WHOLE_FILE",
    "Bundle",
    "BundleError",
    "BundleMissingError",
    "BundleStanding",
    "BundleTooLargeError",
    "ParsedFile",
    "ReplyError",
    "WorkerPrompt",
    "build_prompt",
    "bundle_for",
    "load_bundle",
    "parse_pinned",
    "parse_reply",
    "render_user_message",
]
