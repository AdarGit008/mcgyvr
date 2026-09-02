"""A shim: ``tests.sweeprows`` is ``tools.runs.rows``, re-exported under its old name.

The parser moved beside the door. As ``tests/sweeprows.py`` it ran only in CI,
post-hoc, over one hard-coded directory; ``tools/runs/run.sh`` now reads every
artifact a step wrote back through ``rows.read()`` before it exits 0 (gate 8),
so the module the door trusts is the module the tests trust. The twelve
behaviour tests still import it by this name, and this file keeps that import
working without becoming a second parser: every public name here IS the object
in ``tools/runs/rows.py`` — nothing is redefined — and
``tests/test_a_shim_is_not_a_second_parser.py`` holds it to that.
"""

from __future__ import annotations

from tools.runs.rows import *  # noqa: F403
