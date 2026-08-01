"""The orchestrator: a prompt plus a repository become contracts.

This is the largest single piece of v1 and the one in sharpest tension with
the north star — it spends expensive tokens to plan work whose whole purpose
is to save them. The resolution is deterministic-first (ADR-0001, epic #45): a
zero-token index shortlists before any model reads a file, and the model reads
only what the index names.

Only what is built is exported here; the scope of what is coming is the issue
tree under #45.
"""

from __future__ import annotations

from mcgyvr.orchestrator.repo import AttachedRepo, AttachError, attach

__all__ = ["AttachError", "AttachedRepo", "attach"]
