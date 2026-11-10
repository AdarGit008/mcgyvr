"""The deterministic context layer, re-exported as one flat namespace.

Each submodule owns one step and stays importable directly; this module gathers
their public names so a caller can ``from mcgyvr.repo import resolve``
without knowing which step a name lives on.

``symbols`` extracts ``Symbol``/``SymbolKind`` from source (Python with ``ast``;
JS/TS, Go, Rust and Java with tree-sitter, one module each under ``languages``), and
``index`` builds an ``Index`` over a repository from it (``build_index``, with
``IndexBuildError`` for a build that cannot start and ``IndexedFile``,
``SymbolTable``, ``Match`` and ``BuildStats`` describing the result). ``resolve``
ranks the files a request most likely means (``Resolution``/``Candidate``, and a
``Verdict`` of resolved, ambiguous or empty), ``read`` turns that ranking into
excerpts that fit a token budget (``explore`` returning an ``Exploration`` of
``TargetedRead``s, a ``Deferral`` for each region the budget ran out on, and the
tokens saved by regions the caller already supplied), and ``context`` checks the
paths and contents a caller supplied against the index (``verify`` ->
``VerifiedContext``/``ContextFinding``/``Discrepancy``) and re-ranks with their
help (``accelerate`` -> ``Acceleration``). ``mcgyvr.decompose`` runs those steps
for a prompt, hands the evidence to a caller-supplied ``Proposer``, and turns its
``Proposal``s into a ``Decomposition`` of contracts and ``Refusal``s; it is the
only part that takes a proposer, so it is its own package above this one.

``repo`` attaches the repository a run works on (``attach`` yielding an
``AttachedRepo``, or raising ``AttachError``) and explains what a sandbox built
from the repository's commit would leave out (``head_only_note``). ``cache``
memoises index builds on disk (``build_index_cached``, ``cache_path``,
``CachedBuild``, ``CacheStats``); its ``clear`` and ``prune`` functions are
re-exported here as ``clear_cache`` and ``prune_cache`` to say which cache they
clear.

Names not listed in ``__all__`` -- ``references`` -- remain reachable only
through their own modules.
"""

from __future__ import annotations

from mcgyvr.repo.cache import (
    CachedBuild,
    CacheStats,
    build_index_cached,
    cache_path,
)
from mcgyvr.repo.cache import clear as clear_cache
from mcgyvr.repo.cache import prune as prune_cache
from mcgyvr.repo.context import (
    Acceleration,
    ContextFinding,
    Discrepancy,
    SuppliedContext,
    VerifiedContext,
    accelerate,
    verify,
)
from mcgyvr.repo.index import (
    BuildStats,
    Index,
    IndexBuildError,
    IndexedFile,
    Match,
    SymbolTable,
    build_index,
)
from mcgyvr.repo.read import (
    Deferral,
    Exploration,
    ExplorationError,
    TargetedRead,
    explore,
)
from mcgyvr.repo.repo import AttachedRepo, AttachError, attach, head_only_note
from mcgyvr.repo.resolve import Candidate, Resolution, Verdict, resolve
from mcgyvr.repo.symbols import Symbol, SymbolKind

__all__ = [
    "Acceleration",
    "AttachError",
    "AttachedRepo",
    "BuildStats",
    "CacheStats",
    "CachedBuild",
    "Candidate",
    "ContextFinding",
    "Deferral",
    "Discrepancy",
    "Exploration",
    "ExplorationError",
    "Index",
    "IndexBuildError",
    "IndexedFile",
    "Match",
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
    "explore",
    "head_only_note",
    "prune_cache",
    "resolve",
    "verify",
]
