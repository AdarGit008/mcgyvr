"""The `mcgyvr repo` commands: attach, index, resolve, and read.

`attach` shows what a repository turned out to be — root, starting revision, how
it was obtained, whether it is dirty. `index` builds the deterministic index and
reports what it cost, optionally running a text search or a symbol lookup over
it. `resolve` turns a natural-language query into a ranked shortlist of paths.
`read` goes one step further and prints the regions that shortlist justifies,
within a token budget. The heavy lifting lives in `mcgyvr.orchestrator`; each
command here is argument plumbing, a human-readable report, and an exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

from mcgyvr.cli.common import _add_repo, _mib


def _attach(args: argparse.Namespace) -> int:
    from mcgyvr.orchestrator import AttachError, attach

    into = Path(args.into) if args.into else None
    try:
        with attach(args.repo, into=into) as repo:
            # Inside the context `repo` is an AttachedRepo describing what was
            # obtained: origin, root, checked-out revision, and uncommitted paths.
            print(f"Repository attached ({repo.origin}):")
            print(f"  root:     {repo.root}")
            print(
                f"  revision: {repo.revision}"
                + (" (empty tree — no commit yet)" if repo.is_unborn else "")
            )
            print(f"  source:   {repo.source}")
            if repo.ephemeral:
                print("  lifetime: ephemeral (removed when this command exits)")
            if repo.is_dirty:
                print(
                    f"\nWorking tree is dirty — {len(repo.dirty)} uncommitted path(s):"
                )
                for path in repo.dirty:
                    print(f"  {path}")
                print(
                    "\nA change measured against a dirty tree also carries these "
                    "edits; commit or stash them before dispatching work."
                )
            else:
                print("  worktree: clean")
    except AttachError as exc:
        # AttachError covers every way the source was unusable: a path that is
        # not a git checkout, a refused ssh remote, a clone that failed.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _index(args: argparse.Namespace) -> int:
    from mcgyvr.orchestrator import (
        IndexBuildError,
        build_index,
        build_index_cached,
        clear_cache,
    )

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    if args.clear_cache:
        removed = clear_cache(root)
        print(f"Cleared {len(removed)} cached index(es) for {root}")
        return 0

    cache = None
    try:
        if args.no_cache:
            index = build_index(root)
        else:
            built = build_index_cached(root, refresh=args.refresh_cache)
            index, cache = built.index, built.cache
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stats = index.stats
    print(f"Indexed {root}")
    print(
        f"  {stats.files_indexed} files, {stats.symbol_count} symbols, "
        f"{_mib(stats.bytes_indexed)} in {stats.elapsed_seconds:.3f}s"
    )
    if stats.languages:
        langs = ", ".join(f"{name} x{n}" for name, n in sorted(stats.languages.items()))
        print(f"  languages: {langs}")
    if stats.files_skipped_large or stats.files_skipped_binary:
        print(
            f"  skipped: {stats.files_skipped_large} large, "
            f"{stats.files_skipped_binary} binary"
        )
    if stats.degraded_extensions:
        print("  text-only (no grammar): " + ", ".join(stats.degraded_extensions))
    if cache is not None:
        print(
            f"  cache: {cache.reused} reused, {cache.restamped} unchanged, "
            f"{cache.rebuilt} rebuilt, {cache.dropped} dropped"
            + (f" — {cache.note}" if cache.note else "")
        )

    if args.search:
        hits = index.search(args.search, limit=args.limit)
        print(f'\nText search "{args.search}" — {len(hits)} hit(s):')
        for match in hits:
            print(f"  {match.path}:{match.line}: {match.text.strip()}")

    if args.symbol:
        defs = index.symbols.definitions(args.symbol)
        refs = index.symbols.references(args.symbol)
        print(
            f'\nSymbol "{args.symbol}" — '
            f"{len(defs)} definition(s), {len(refs)} reference(s):"
        )
        for symbol in defs:
            detail = f" [{symbol.detail}]" if symbol.detail else ""
            print(f"  def  {symbol.path}:{symbol.line}{detail}")
            # A definition's signature may span several lines; each one is
            # printed on its own indented line so the first line stays aligned
            # under the `def` entry it belongs to.
            for line in symbol.signature.splitlines():
                print(f"         {line}")
        for symbol in refs:
            print(f"  ref  {symbol.path}:{symbol.line}")
    return 0


def _resolve(args: argparse.Namespace) -> int:
    from mcgyvr.orchestrator import IndexBuildError, Verdict, build_index, resolve

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1
    try:
        index = build_index(root)
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result = resolve(index, args.query, limit=args.limit)
    count = len(result.candidates)
    print(f'"{args.query}" — {result.verdict.value}, {count} candidate(s):')
    if result.verdict is Verdict.EMPTY:
        print("  (no candidate matched — try a symbol name or a filename)")
    for rank, candidate in enumerate(result.candidates, start=1):
        print(f"  {rank}. {candidate.path}  ({candidate.score:g})")
        for reason in candidate.evidence:
            print(f"       · {reason}")
    # An ambiguous or empty verdict is still an answer, so it still exits 0;
    # only a bad repository path or an index failure is an error.
    return 0


def _read(args: argparse.Namespace) -> int:
    from mcgyvr.orchestrator import (
        ExplorationError,
        IndexBuildError,
        SuppliedContext,
        accelerate,
        build_index,
        explore,
        resolve,
        verify,
    )

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1
    try:
        index = build_index(root)
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    resolution = resolve(index, args.query, limit=args.limit)

    # The caller's --holds paths are read here, from the working tree, so verify()
    # can compare the text the caller holds against the lines the index parsed.
    contents: dict[str, str] = {}
    for held in args.holds:
        try:
            contents[held] = (root / held).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read --holds {held}: {exc}", file=sys.stderr)
            return 1
    supplied = SuppliedContext(paths=tuple(args.hint), contents=contents)
    verified = verify(index, supplied)
    accelerated = accelerate(resolution, verified)
    resolution = accelerated.resolution

    try:
        plan = explore(
            index,
            resolution,
            budget=args.budget,
            context=args.context,
            supplied=verified,
        )
    except ExplorationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_read_document(args.query, root, index, resolution, plan)))
        return 0

    state = "exhausted" if plan.exhausted else "complete"
    saved = f", {plan.saved} saved" if plan.saved else ""
    print(
        f'"{args.query}" — read {len(plan.reads)} region(s), '
        f"{plan.spent}/{plan.budget} est. tokens{saved} ({state}):"
    )
    for read in plan.reads:
        held_marker = " (supplied)" if read.supplied else ""
        print(
            f"  #{read.candidate_rank} {read.path}:{read.start}-{read.end}"
            f"  [{read.reason}]  ~{read.estimated_tokens}t{held_marker}"
        )
    # Findings come from checking the supplied paths against the index and from
    # re-ranking: a dropped hint, stale held text, or a hint the deterministic
    # pass never shortlisted. They are reported, not fatal.
    for finding in accelerated.findings:
        print(f"  ! {finding.path}: {finding.detail}")
    if plan.deferred:
        cost = sum(item.estimated_tokens for item in plan.deferred)
        print(f"\n  deferred {len(plan.deferred)} region(s) (~{cost}t over budget):")
        for item in plan.deferred:
            print(f"    #{item.candidate_rank} {item.path}:{item.start}-{item.end}")
    # Regions left deferred mean the budget ran out, which is a reportable
    # outcome rather than an error, so the command still exits 0.
    return 0


def _read_document(
    query: str, root: Path, index: Any, resolution: Any, plan: Any
) -> dict[str, Any]:
    """The single JSON document `repo read --json` prints.

    It carries the query and root, the resolution with each candidate's score and
    evidence, every read region with its text, the full text of each shortlisted
    and read path as the index holds it, and the type-check command each language
    adapter locates here — enough for a consumer with no path to this repository
    to work from the evidence alone.
    """
    from mcgyvr.orchestrator.decompose import locate_checkers

    wanted = [candidate.path for candidate in resolution.candidates]
    wanted += [read.path for read in plan.reads if read.path not in wanted]
    by_path = {file.path: file for file in index.files}
    return {
        "prompt": query,
        "root": str(root),
        "resolution": {
            "verdict": resolution.verdict.value,
            "candidates": [
                {"path": c.path, "score": c.score, "evidence": list(c.evidence)}
                for c in resolution.candidates
            ],
        },
        "reads": [
            {
                "path": read.path,
                "start": read.start,
                "end": read.end,
                "reason": read.reason,
                "text": read.text,
            }
            for read in plan.reads
        ],
        "files": [
            {"path": path, "text": "\n".join(by_path[path].lines)}
            for path in wanted
            if path in by_path
        ],
        # Type-check commands keyed by adapter name, so the document also says
        # how this repository's types can be checked without rediscovering it.
        "located": locate_checkers(root),
    }


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the attach, index, resolve, and read subcommands and their flags."""

    att = sub.add_parser(
        "attach",
        help="attach a repository (local path or clone URL) and show its state",
    )
    _add_repo(
        att,
        "the repository to attach: a local git checkout, or a URL to clone "
        "(https/ssh/git/file)",
    )
    att.add_argument(
        "--into",
        default=None,
        metavar="DIR",
        help="clone a URL into DIR and keep it, instead of an ephemeral temp dir",
    )
    att.set_defaults(func=_attach)

    idx = sub.add_parser(
        "index",
        help="build the deterministic index of a repository and show what it cost",
    )
    _add_repo(idx, "the repository to index")
    idx.add_argument(
        "--search",
        default=None,
        metavar="TERM",
        help="also run a text search for TERM and show the hits",
    )
    idx.add_argument(
        "--symbol",
        default=None,
        metavar="NAME",
        help="also show where NAME is defined and referenced",
    )
    idx.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="cap the number of text-search hits shown (default: 20)",
    )
    idx.add_argument(
        "--no-cache",
        action="store_true",
        help="build from source without reading or writing the index cache",
    )
    idx.add_argument(
        "--refresh-cache",
        action="store_true",
        help="ignore the cached index, rebuild from source, and store the result",
    )
    idx.add_argument(
        "--clear-cache",
        action="store_true",
        help="remove this repository's cached index and exit",
    )
    idx.set_defaults(func=_index)

    res = sub.add_parser(
        "resolve",
        help="resolve a natural-language target to a ranked shortlist of paths",
    )
    res.add_argument(
        "query",
        help='what to find, in words — e.g. "the fetch helper" or a symbol name',
    )
    _add_repo(res, "the repository to resolve against")
    res.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="cap the shortlist to N candidates (default: 10)",
    )
    res.set_defaults(func=_resolve)

    rd = sub.add_parser(
        "read",
        help="resolve a target, then read the regions it justifies within a budget",
    )
    rd.add_argument(
        "query",
        help='what to find, in words — e.g. "the fetch helper" or a symbol name',
    )
    _add_repo(rd, "the repository to read from")
    rd.add_argument(
        "--budget",
        type=int,
        default=2000,
        metavar="TOKENS",
        help="cap exploration at TOKENS estimated tokens (default: 2000)",
    )
    rd.add_argument(
        "--context",
        type=int,
        default=25,
        metavar="LINES",
        help="lines per read window around each anchor (default: 25)",
    )
    rd.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="cap the resolver shortlist to N candidates first (default: 10)",
    )
    rd.add_argument(
        "--hint",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "a path you believe is relevant; re-ranks the shortlist but can never "
            "add to it or overturn a resolved leader (repeatable)"
        ),
    )
    rd.add_argument(
        "--holds",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "a path whose current content you already hold; verified against the "
            "index, and if it matches its regions cost the budget nothing "
            "(repeatable)"
        ),
    )
    rd.add_argument(
        "--json",
        action="store_true",
        help=(
            "print one JSON document instead of the report: the request, the "
            "shortlist, the regions read, and the whole text of every shortlisted "
            "and read file — what a server with no path to this repository needs "
            "to index it (mcorch gathers evidence this way, through the harness)"
        ),
    )
    rd.set_defaults(func=_read)
