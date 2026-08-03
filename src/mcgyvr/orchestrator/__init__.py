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

from mcgyvr.orchestrator.cache import (
    CachedBuild,
    CacheStats,
    build_index_cached,
    cache_path,
)
from mcgyvr.orchestrator.cache import clear as clear_cache
from mcgyvr.orchestrator.cache import prune as prune_cache
from mcgyvr.orchestrator.context import (
    Acceleration,
    ContextFinding,
    Discrepancy,
    SuppliedContext,
    VerifiedContext,
    accelerate,
    verify,
)
from mcgyvr.orchestrator.decompose import (
    Decomposition,
    DepRef,
    Evidence,
    Proposal,
    Proposer,
    RecordedProposer,
    Refusal,
    decompose,
)
from mcgyvr.orchestrator.index import (
    BuildStats,
    Index,
    IndexBuildError,
    IndexedFile,
    Match,
    SymbolTable,
    build_index,
)
from mcgyvr.orchestrator.read import (
    Deferral,
    Exploration,
    ExplorationError,
    TargetedRead,
    explore,
)
from mcgyvr.orchestrator.repo import AttachedRepo, AttachError, attach
from mcgyvr.orchestrator.resolve import Candidate, Resolution, Verdict, resolve
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

__all__ = [
    "Acceleration",
    "AttachError",
    "AttachedRepo",
    "BuildStats",
    "CacheStats",
    "CachedBuild",
    "Candidate",
    "ContextFinding",
    "Decomposition",
    "Deferral",
    "DepRef",
    "Discrepancy",
    "Evidence",
    "Exploration",
    "ExplorationError",
    "Index",
    "IndexBuildError",
    "IndexedFile",
    "Match",
    "Proposal",
    "Proposer",
    "RecordedProposer",
    "Refusal",
    "Resolution",
    "SuppliedContext",
    "Symbol",
    "SymbolKind",
    "SymbolTable",
    "TargetedRead",
    "Verdict",
    "VerifiedContext",
    "accelerate",
    "attach",
    "build_index",
    "build_index_cached",
    "cache_path",
    "clear_cache",
    "decompose",
    "explore",
    "prune_cache",
    "resolve",
    "verify",
]
