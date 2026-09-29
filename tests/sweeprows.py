"""A shim: ``tests.sweeprows`` is ``tools.runs.rows``, re-exported.

The door (``python -m mcgyvr.serving.run``) reads every artifact a step wrote
back through ``rows.read()`` before it exits 0 (gate 8, ``08-parse.py``), so the
module the door trusts is the module the tests trust. The door tests copy this
file into the throw-away checkouts they run the door from (``tests/onedoor.py``),
and it keeps the name importable without becoming a second parser: every public
name here IS the object in ``tools/runs/rows.py`` — nothing is redefined.
"""

from __future__ import annotations

from tools.runs.rows import *  # noqa: F403
