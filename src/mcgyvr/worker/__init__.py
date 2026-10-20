"""The worker-facing side of a run: what is sent to it, and what comes back.

Three concerns, each in its own module and re-exported here so callers reach them
through one name:

- `bundle` — the standing prompt bundle for a use case (or, for coding, for the
  language that owns the target), loaded from the packaged prompt files with its
  sweep standing intact, and refused when it is over the measured byte ceiling.
- `prompt` — `build_prompt` turns a contract into the system and user text for
  one dispatch (target content, interface, dependency signatures, numbered
  sources, stop conditions, the reply shape, and any retry notes), together with
  the token count and the preflight fit issue, if the prompt does not fit.
- `reply` — `parse_reply` (and `parse_pinned`) turn a finished reply's text into
  the bytes meant for a file under a named output schema, or refuse with a
  `ReplyError` code instead of writing a plausible file.

This package only builds the request and judges the answer; it does not run
backends, write files, or keep state. `sources` lives alongside for reading the
tree, but is not part of the surface exported here.
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
    PROSE,
    WHOLE_FILE,
    ParsedFile,
    ReplyError,
    parse_pinned,
    parse_reply,
)

__all__ = [
    "MAX_BUNDLE_BYTES",
    "PROSE",
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
