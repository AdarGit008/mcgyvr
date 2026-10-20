"""The worker-facing side of a run: what is sent to it, and what comes back.

Three concerns, each in its own module:

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
tree.
"""
