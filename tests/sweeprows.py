"""A shim: ``tests.sweeprows`` is ``tools.runs.rows``, re-exported.

The door (``python -m mcgyvr.serving.run``) reads every artifact a step wrote
back through ``rows.read()`` before it exits 0 (gate 8, ``08-parse.py``), so the
module the door trusts is the module the tests trust. Tests import it by this
name, and this file keeps that import working without becoming a second parser:
every public name here IS the object in ``tools/runs/rows.py`` — nothing is
redefined — and ``tests/test_a_shim_is_not_a_second_parser.py`` holds it to
that.
"""

from __future__ import annotations

from tools.runs.rows import *  # noqa: F403
