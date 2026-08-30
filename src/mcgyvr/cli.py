"""Command-line entrypoint.

Only what is built is exposed. Subcommands appear here as they land; the
scope of record for what is coming is the issue tree.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr import __version__
from mcgyvr.availability import PROBE_TIMEOUT_S
from mcgyvr.capability import CapabilityTableError, load
from mcgyvr.config import CONFIG_FILENAME, CONFIG_PATH_ENV, ConfigError
from mcgyvr.config import config_path as resolve_config_path
from mcgyvr.config import load as load_config
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for
from mcgyvr.initialize import InitError, initialize

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.escalate import Delivered, Halted, Judgement
    from mcgyvr.gate import GateResult
    from mcgyvr.route import Try
    from mcgyvr.sandbox.base import Sandbox


def _capabilities(args: argparse.Namespace) -> int:
    try:
        table = load()
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    models = table.fitting(args.vram) if args.vram else table.models
    if args.vram:
        print(f"Measured models that fit {args.vram:g} GB with working headroom:\n")
    else:
        print("Measured models:\n")

    for model in sorted(models, key=lambda m: m.best_quality or 0, reverse=True):
        quality = model.best_quality
        score = f"{quality:.1%}" if quality is not None else "unmeasured"
        backend = f" [{model.requires_backend} only]" if model.requires_backend else ""
        print(
            f"  {model.id:<28} {model.vram_gb_working:>5.1f} GB  {score:>10}{backend}"
        )

    if table.caveats:
        print("\nHarness caveats that invalidate naive re-measurement:")
        for caveat in table.caveats:
            print(f"  {caveat.id} [{caveat.severity}] {caveat.summary}")
    return 0


def _config(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else resolve_config_path()
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{config.path}: valid\n")
    print("Sources:")
    for source in config.sources.values():
        credential = (
            f"key from ${source.api_key_env}" if source.api_key_env else "no credential"
        )
        print(
            f"  {source.name:<16} {source.api:<8} {source.base_url:<32} "
            f"x{source.max_parallel}  ({credential})"
        )

    print("\nLadder, cheapest first:")
    for tier in config.ladder.tiers:
        print(f"  {tier.name:<16} {tier.model:<32} on {tier.source}")

    if config.is_local_only:
        print(
            "\nEvery rung runs locally: this install needs no API key, and the "
            "deterministic gate is its acceptance bar."
        )
    return 0


def _pool(args: argparse.Namespace) -> int:
    from mcgyvr.escalate import Ceiling
    from mcgyvr.pool import SourceUnavailableError, source_map
    from mcgyvr.route import family_of

    path = Path(args.path) if args.path else resolve_config_path()
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    availability = None
    if args.probe:
        from mcgyvr.availability import Availability

        availability = Availability(timeout_s=args.probe_timeout)
    pool = source_map(config, probe=availability)

    # The ladder, not the endpoints: this command answers "what can run", and
    # where each rung runs is the seam's business (#20). A rung that cannot run
    # names its source in the reason, which is when that fact starts to matter.
    #
    # The family and the attempt budget are shown because they are the routing
    # decision (#24), and a decision nobody can read is one nobody can check.
    # A family is a cost class rather than a location, so printing it says how
    # dear a rung is to ask without saying which machine answers.
    print(f"{config.path}: {len(pool)} usable rung(s), cheapest first:\n")
    ladder_budget = 0
    for rung in pool.rungs:
        tier = config.ladder.get(rung.name)
        budget = tier.attempts if tier is not None else 1
        ladder_budget += budget
        tries = "1 attempt" if budget == 1 else f"{budget} attempts"
        family = family_of(config, rung.name)
        print(f"  {rung.name:<20} {family.name:<14} {tries:<11} {rung.model}")
    if not pool.rungs:
        print("  (none — every rung's source is unusable)")
    else:
        # The escalation policy (#43). A ladder printed without its ceilings
        # reads as though every rung will be tried, and the default is that
        # most of them will not: what bounds the climb is as much the routing
        # decision as the rungs are, and it is decided from this file alone.
        ceiling = Ceiling.of(config)
        cap = min(ladder_budget, ceiling.attempts or ladder_budget)
        source = (
            "budgets.max_attempts"
            if ceiling.attempts is not None
            else "the ladder's own budget"
        )
        print(
            f"\n  Ceiling: at most {ceiling.escalations} escalation(s) — "
            f"{min(len(pool.rungs), ceiling.escalations + 1)} of these "
            f"{len(pool.rungs)} rung(s) — and at most {cap} attempt(s) "
            f"per task ({source})."
        )

    if pool.skipped:
        print(f"\nSkipped {len(pool.skipped)} rung(s):")
        for skip in pool.skipped:
            print(f"  {skip.name:<20} {skip.model}\n      ↳ {skip.reason}")

    for role in ("orchestrator", "verifier"):
        try:
            model = pool.role_model(role)
        except SourceUnavailableError as exc:
            print(f"\n{role}: unavailable — {exc}")
            continue
        if model is not None:
            print(f"\n{role}: {model}")

    if availability is not None:
        # Every source that was actually asked, live ones included. A ladder
        # that came back intact is only reassuring if you can see that the
        # question was put — otherwise it is indistinguishable from a probe
        # that quietly did nothing.
        print(f"\nProbed {len(availability.verdicts)} source(s):")
        for name, verdict in sorted(availability.verdicts.items()):
            state = "live" if verdict.live else "down"
            print(f"  {name:<20} {state:<5} {verdict.elapsed_s:.2f}s  {verdict.how}")

    # An empty or shortened ladder is a reported state, not a command failure —
    # for a keyless install it may be exactly what was configured.
    return 0


def _catalog(args: argparse.Namespace) -> int:
    from mcgyvr.catalog import CatalogError, catalog

    try:
        book = catalog()
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Resolving against a ladder is optional: without one there is still a
    # vocabulary to show, and "which of these can *I* run" is a different
    # question from "what does mcgyvr know how to be asked for".
    config = None
    unservable: set[str] = set()
    if args.against is not False:
        path = Path(args.against) if args.against else resolve_config_path()
        try:
            config = load_config(path)
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        unservable = {t.name for t in book.unservable(config)}

    if args.name:
        kind = book.get(args.name)
        if kind is None:
            gone = book.excluded_entry(args.name)
            if gone is not None:
                print(f"{args.name}: not in the vocabulary.\n", file=sys.stderr)
                print(f"  {gone.reason}", file=sys.stderr)
                if gone.superseded_by:
                    print(f"\n  Use `{gone.superseded_by}` instead.", file=sys.stderr)
                return 1
            print(
                f"error: {args.name!r} is not a known task type. "
                f"Valid: {', '.join(book.names)}",
                file=sys.stderr,
            )
            return 1
        print(f"{kind.name}  [starts on {kind.starts_on.name}]\n")
        print(f"  {kind.doc}\n")
        print(f"  guarantee:  {kind.guarantee}\n")
        print(f"  warrant:    {kind.warrant}\n")
        print("  evidence required:")
        for evidence in kind.required_evidence:
            mark = "$" if evidence.needs_commands else "-"
            print(f"    {mark} {evidence.name}: {evidence.doc}")
        if config is not None and kind.name in unservable:
            print(
                f"\n  NOT SERVABLE by {config.path}: no rung at or above "
                f"`{kind.starts_on.name}` is bound."
            )
        return 0

    print("Task types, cheapest family first:\n")
    for kind in book.task_types:
        flag = "  (unservable here)" if kind.name in unservable else ""
        print(f"  {kind.name:<24} {kind.starts_on.name:<14}{flag}")
        print(f"      {kind.guarantee}")
        print(f"      evidence: {', '.join(kind.evidence_names)}\n")

    if config is not None:
        if unservable:
            # Naming them is the point: a count would tell a caller there is a
            # problem without telling them which task to stop asking for.
            print(f"{len(unservable)} type(s) this ladder cannot start:")
            for name in sorted(unservable):
                print(f"  {name}")
        else:
            print(f"Every type is servable by the ladder in {config.path}.")

    if args.excluded:
        print("\nConsidered and removed:\n")
        for gone in book.excluded:
            replacement = f" (use `{gone.superseded_by}`)" if gone.superseded_by else ""
            print(f"  {gone.name}{replacement}")
            print(f"      {gone.reason}\n")
    return 0


def _contract(args: argparse.Namespace) -> int:
    import json

    from mcgyvr.contract import ContractError, load

    try:
        contract = load(Path(args.path))
    except ContractError as exc:
        # The whole point of the loader is that this message is actionable:
        # it names the field and what a valid value looks like.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.worker_view:
        print(json.dumps(contract.worker_view(), indent=2))
        return 0

    tier = "deterministic tier" if contract.is_deterministic else "model tier"
    print(f"{args.path}: valid\n")
    print(f"  {contract.id}  [{contract.task_type}] — {tier}")
    print(f"  target:  {contract.target}")
    print(f"  allow:   {', '.join(contract.scope.allow)}")
    if contract.scope.forbid:
        print(f"  forbid:  {', '.join(contract.scope.forbid)}")
    if contract.deps:
        print(f"  deps:    {', '.join(d.path for d in contract.deps)}")
    if contract.stop_conditions:
        print(f"  stops:   {len(contract.stop_conditions)} condition(s)")
    print(
        f"  risk:    {contract.risk} — verified by "
        f"{contract.verification.policy.replace('_', ' ')}"
    )
    print(
        f"  limits:  <={contract.limits.max_output_tokens} output tokens, "
        f"<={contract.max_input_tokens} prompt tokens, "
        f"{contract.limits.attempts} attempt(s)"
    )
    if contract.acceptance:
        print("  acceptance:")
        for command in contract.acceptance:
            print(f"    $ {command}")
    else:
        print("  acceptance: none declared — the gate's own checks decide")
    return 0


def _detect(args: argparse.Namespace) -> int:
    hosts = tuple(args.host or ())
    found = detect(targets_for(hosts) if hosts else DEFAULT_PROBE_TARGETS)

    if found.gpus:
        print("GPU:")
        for gpu in found.gpus:
            print(f"  {gpu.name} — {gpu.vram_gb:g} GB  ({gpu.how})")
        if found.has_remote_backend:
            print("  (this machine's card — the remote backends below have their own)")
    else:
        print("GPU: none detected")

    context = []
    if found.cpu_count is not None:
        context.append(f"{found.cpu_count} CPUs")
    if found.ram_gb is not None:
        context.append(f"{found.ram_gb:g} GB RAM")
    if context:
        print(f"Host: {', '.join(context)}")

    print(f"Docker: {'yes' if found.docker else 'no'}  ({found.provenance['docker']})")

    if found.backends:
        print("\nBackends reachable:")
        for host in found.hosts_answering:
            if hosts:
                print(f"  {host}:")
            for backend in (b for b in found.backends if b.host == host):
                indent = "    " if hosts else "  "
                protocol = (
                    f"asked={backend.api} bind={backend.binds_as}"
                    if backend.bound_on_another_protocol
                    else f"api={backend.api}"
                )
                print(f"{indent}{backend.name:<20} {backend.base_url:<30} {protocol}")
                if backend.models:
                    for model in backend.models:
                        print(f"{indent}    already pulled: {model}")
                else:
                    print(f"{indent}    (reachable, but reports no models)")
                print(f"{indent}    {backend.how}")
    else:
        print("\nBackends reachable: none")

    if found.notes:
        print("\nWhat could not be determined, and what it costs:")
        for note in found.notes:
            print(f"  - {note}")
    return 0


def _sandbox(args: argparse.Namespace) -> int:
    from mcgyvr.detect import detect_docker
    from mcgyvr.sandbox.base import choose_mode
    from mcgyvr.sandbox.image import ImageError, clear, list_cached
    from mcgyvr.sandbox.stack import detect_stack

    docker_ok, docker_how = detect_docker()

    if args.clear_cache:
        if not docker_ok:
            print(f"No Docker daemon, so nothing is cached ({docker_how}).")
            return 0
        removed = clear()
        print(f"Cleared {len(removed)} cached image(s).")
        for tag in removed:
            print(f"  removed {tag}")
        return 0

    if args.cache:
        if not docker_ok:
            print(f"No Docker daemon, so nothing is cached ({docker_how}).")
            return 0
        try:
            cached = list_cached()
        except ImageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not cached:
            print("Image cache is empty.")
            return 0
        total = sum(c.size_bytes for c in cached)
        print(f"Cached task images ({_mib(total)} total, newest first):\n")
        for image in cached:
            print(f"  {image.tag:<40} {_mib(image.size_bytes):>10}  [{image.repo}]")
        return 0

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 1

    # The default configured mode is `docker`; show what it resolves to here.
    choice = choose_mode("docker", docker_ok)
    print(f"Sandbox mode: {choice.mode}  ({docker_how})")
    for note in choice.notes:
        print(f"  - {note}")

    stack = detect_stack(repo)
    print(f"\nStack for {repo}:")
    if not stack.detected:
        for note in stack.notes:
            print(f"  - {note}")
        return 0

    print(f"  base image: {stack.base_image}")
    for component in stack.components:
        pin = "pinned" if component.pinned else "UNPINNED"
        print(
            f"  {component.language:<8} {component.package_manager:<8} "
            f"({pin}, {component.how})"
        )
        print(f"      install: {' && '.join(component.install)}")
        print(f"      manifests: {', '.join(component.manifests)}")
    for note in stack.notes:
        print(f"  - {note}")
    return 0


def _mib(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f} MiB"


def _init(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else resolve_config_path()
    try:
        result = initialize(path, force=args.force, hosts=tuple(args.host or ()))
    except InitError as exc:
        # Loud on purpose: nothing was written, and the message says why.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, CapabilityTableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.created:
        print(f"Wrote {result.path}\n")
    elif result.written:
        print(f"Overwrote {result.path} (--force)\n")
    else:
        print(f"{result.path} already exists — nothing was changed.\n")

    if result.decisions:
        print("What was decided, and why:")
        for decision in result.decisions:
            print(f"  - {decision}")
        print()

    if not result.written:
        if result.deltas:
            print("Re-running with --force would change:")
            for delta in result.deltas:
                print(f"  - {delta}")
            print(
                "\nYour edits are kept. Pass --force to accept the proposal "
                "above, or leave the file as it is."
            )
        else:
            print("The proposal matches the file on disk exactly.")
        print()

    if result.limits:
        print("What is NOT configured, and what that costs:")
        for limit in result.limits:
            print(f"  - {limit}")
    return 0


def _attach(args: argparse.Namespace) -> int:
    from mcgyvr.orchestrator import AttachError, attach

    into = Path(args.into) if args.into else None
    try:
        with attach(args.source, into=into) as repo:
            # Print inside the context: for an ephemeral clone the working
            # location only exists here, and the point is to show it resolved.
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
        # Loud on purpose: the boundary is "a repository is required", and the
        # message names what to supply.
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
            # The signature is what a contract would carry as a dep (ADR-0007),
            # so showing it here is how a reviewer checks the text against the
            # file without loading the index themselves.
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
    # An ambiguous outcome is a reportable state, not a failure of the command.
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

    # Supplied context enters only here, after the deterministic pass has already
    # produced its shortlist — it can re-rank and pay for reads, never redirect.
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
    # A rejected hint is always surfaced: silence would be the caller trusting a
    # picture the repository does not agree with.
    for finding in accelerated.findings:
        print(f"  ! {finding.path}: {finding.detail}")
    if plan.deferred:
        cost = sum(item.estimated_tokens for item in plan.deferred)
        print(f"\n  deferred {len(plan.deferred)} region(s) (~{cost}t over budget):")
        for item in plan.deferred:
            print(f"    #{item.candidate_rank} {item.path}:{item.start}-{item.end}")
    # Exhaustion is a reported plan, not a command failure — the caller decides.
    return 0


def _run(args: argparse.Namespace) -> int:
    """Drive one contract to a gated verdict, and optionally to a commit.

    The root of the call graph pattern C found missing. Everything below this
    existed and was reachable from a test; nothing reached it from a command,
    which is what "28 of 35 public entry points have no production caller"
    described.

    Committing is opt-in. A gate verdict costs the user a sandbox that is torn
    down either way, and a commit is a write to a repository they did not hand
    over for one — so ``--commit`` is what makes the difference, and its absence
    prints the verdict and the diff instead.

    Two paths, chosen by the contract rather than by a flag. A deterministic
    contract names a program and is run here; anything else climbs a ladder and
    is :func:`_climb`'s. The split is the contract's ``task_type`` because that
    is where the catalog already records which family work of this kind may
    *begin* on, and a flag that let a caller override it would be a second,
    quieter answer to the question ``starts_on`` exists to settle.

    **A tool step has three outcomes here, not two.** It read any non-zero exit
    as fatal, and ``ruff check --fix`` — which is what ``lint_fix`` binds —
    exits **1** whenever a diagnostic remains after fixing. That is the ordinary
    outcome, and it is the outcome ``lint_fix``'s own guarantee describes: "a
    diagnostic the linter will not fix itself is explicitly out of scope for
    this type". So a contract carried out exactly as the catalog promises came
    back as ``error: <the linter's dump>``, was never gated and never committed.

    The three: the program **could not run** (126/127, an environment issue —
    the work is still doable on a dearer family); the program **ran and did the
    job its type describes** (:attr:`~mcgyvr.drive.ToolOutcome.performed`, which
    is where any residue it reported goes on to the gate, because the gate is
    the thing that judges a result and stopping here means the result is never
    judged); and the program **ran and failed** (fatal — a fixer that could not
    load its config applied the guarantee to nothing, and the gate reading that
    same config is broken in the same way).

    The test is the exit code, against the set of codes that invocation reports
    under, which is ADR-0034 clause 2 one layer out from the gate. Ignoring the
    exit code entirely was the cheaper alternative and is the wrong one twice
    over: it would carry an untouched change to a gate that cannot judge it, and
    it would drop the linter's own account of what it will not fix, which is
    printed here instead.
    """
    from mcgyvr.contract import ContractError
    from mcgyvr.contract import load as load_task_contract
    from mcgyvr.deterministic import tool_steps
    from mcgyvr.drive import DriveError, gate_workspace, run_tool_step
    from mcgyvr.sandbox.base import SandboxError, open_sandbox

    try:
        contract = load_task_contract(Path(args.contract))
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1

    if not contract.is_deterministic:
        return _climb(args, contract, repo)

    steps = tool_steps(contract)
    if not steps:
        print(
            f"error: no program on this machine executes {contract.task_type!r} "
            f"for {contract.target}. The work is still doable on a dearer "
            f"family, which this command does not climb to.",
            file=sys.stderr,
        )
        return 1

    try:
        sandbox = open_sandbox(repo, mode=args.sandbox)
    except SandboxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        with sandbox:
            for note in sandbox.notes:
                print(f"note: {note}")
            for step in steps:
                outcome = run_tool_step(step, sandbox)
                print(f"  $ {' '.join(step.argv)}")
                if not outcome.ran:
                    print(f"error: {outcome.environment_issue}", file=sys.stderr)
                    return 1
                assert outcome.result is not None  # `ran` is `result is not None`
                if not outcome.performed:
                    detail = (outcome.result.stderr or outcome.result.stdout).strip()
                    print(f"error: {detail}", file=sys.stderr)
                    return 1
                if not outcome.ok:
                    # Reported, not swallowed. The tool did what its type
                    # guarantees and is telling us what it will not do — for
                    # `lint_fix`, "a diagnostic the linter will not fix itself
                    # is explicitly out of scope for this type". Printing it is
                    # how the operator learns there is work left that no
                    # deterministic rung is going to take, and it goes to stdout
                    # beside the command rather than to stderr, because nothing
                    # here failed.
                    left = (outcome.result.stdout or outcome.result.stderr).strip()
                    print(
                        f"  note: {step.tool.program} applied its fixes and left "
                        f"what it does not fix (exit {outcome.result.exit_code}); "
                        f"the gate judges what remains:"
                    )
                    print(textwrap.indent(left, "    "))
            result = gate_workspace(contract, sandbox)
            return _report_run(args, contract, sandbox, repo, result)
    except DriveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except SandboxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _climb(args: argparse.Namespace, contract: Contract, repo: Path) -> int:
    """Drive a model-executed contract up the ladder a config describes.

    **Which flag selects a rung: none, and that is the answer rather than a
    deferral.** Rung selection is already owned, in one place, by data this
    command does not get to second-guess. The contract's ``task_type`` names the
    family work of its kind may begin on; :func:`~mcgyvr.escalate.ascent` walks
    the catalog's families upward from there; :func:`~mcgyvr.route.plan` takes
    each family's rungs in the order the operator wrote them into ``ladder.tiers``
    and gives each the attempts its tier declares; and ``budgets.max_escalations``
    with ``budgets.max_attempts`` bound how far the walk gets. A ``--rung`` flag
    would be a fourth party to a decision three files already settle, and the
    first time it disagreed with the ladder the operator would have two orderings
    and no way to tell which one ran. What ``run`` was actually missing is
    therefore not a policy knob but the two *inputs* the ladder needs and this
    command had nowhere to take them from: a config, and the source map resolved
    from it.

    Hence ``--config`` and nothing else. It resolves the same way every other
    command's does — ``$MCGYVR_CONFIG``, then the working directory, then the
    user config dir — because a second resolution order for the same file is a
    second file as far as an operator debugging one is concerned.

    **An install that cannot run this contract is refused before a sandbox is
    opened.** :attr:`~mcgyvr.escalate.Ascent.reason` already carries the sentence
    each empty family wrote about itself — which rung was skipped, which variable
    is unset — and ``escalate`` would reach the same conclusion on its own. Doing
    it here is what keeps a container from being built for a task that was never
    going to dispatch.
    """
    from mcgyvr.drive import DriveError, worker_attempt
    from mcgyvr.escalate import ascent, escalate
    from mcgyvr.pool import SourceUnavailableError, source_map
    from mcgyvr.route import RouteError
    from mcgyvr.runner import RunnerError
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.verify import reviewer_for

    path = Path(args.config) if args.config else resolve_config_path()
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Structural resolution, no probe: a live-reachability sweep costs one
    # timeout per source and answers a question the dispatch below is about to
    # ask for real. `mcgyvr pool --probe` is where an operator asks it in
    # advance, and paying for it here would charge every run for a diagnosis.
    pool = source_map(config)
    try:
        route = ascent(config, pool, contract)
    except RouteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not route:
        print(
            f"error: {contract.id} is a {contract.task_type!r} contract and "
            f"starts on the {route.floor.name!r} family; nothing in {config.path} "
            f"can run it. {route.reason}",
            file=sys.stderr,
        )
        return 1

    # Before the sandbox, for the reason the paragraph above gives: an install
    # that was told to verify and cannot is refused while refusing is still
    # free. `verifier.enabled` is read here and nowhere else — `source_map`
    # binds the role whenever a source and a model are declared, so the flag is
    # the operator's switch and this is the caller that acts on it. `None` is
    # not a downgrade there: it is `verifier.enabled: false`, which asks for
    # acceptance on the deterministic gate alone.
    try:
        reviewer = reviewer_for(pool) if config.get("verifier.enabled") else None
    except SourceUnavailableError as exc:
        print(
            f"error: verification is enabled and the verifier role cannot run: "
            f"{exc}. Bind it to a usable source, or set "
            f"`verifier.enabled: false` to accept on the deterministic gate.",
            file=sys.stderr,
        )
        return 1

    try:
        sandbox = open_sandbox(
            repo,
            mode=args.sandbox,
            image=config.get("sandbox.image"),
            setup=config.get("sandbox.setup") or (),
            # The worker runs outside the sandbox and the sandbox has to be able
            # to reach it: a container with no route to the source is a task that
            # gates fine and never gets an answer to gate.
            endpoints=tuple(source.base_url for source in config.sources.values()),
        )
    except SandboxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Which rung is being driven right now, for the one error that cannot say so
    # itself. `runner` reports the URL it could not reach because a transport
    # knows nothing of ladders, and the rung is the word the operator needs to
    # find the tier to fix. `escalate` does not catch a raising attempt, on
    # purpose, so this is the only place the pairing still exists.
    in_flight: list[str] = []

    try:
        with sandbox:
            for note in sandbox.notes:
                print(f"note: {note}")
            driver = worker_attempt(config, pool, contract, sandbox, reviewer=reviewer)

            def attempt(this: Try) -> Judgement:
                in_flight.append(this.rung.name)
                return driver(this)

            outcome = escalate(config, pool, contract, attempt)
            return _report_climb(args, contract, sandbox, repo, outcome)
    except RunnerError as exc:
        rung = in_flight[-1] if in_flight else route.rungs[0]
        print(
            f"error: rung {rung!r} did not answer, so {contract.id} was not "
            f"driven: {exc}",
            file=sys.stderr,
        )
        return 1
    except (DriveError, SandboxError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _report_climb(
    args: argparse.Namespace,
    contract: Contract,
    sandbox: Sandbox,
    repo: Path,
    outcome: Delivered | Halted,
) -> int:
    """Print what the climb spent and where it ended, and commit when asked.

    Every attempt is printed, including the ones that failed. A ladder walk that
    reported only its answer would leave an operator unable to tell one rung
    accepting immediately from three rungs spent and the dearest one succeeding,
    which is the difference the whole escalation policy is about.
    """
    from mcgyvr.escalate import Delivered

    for step in outcome.history:
        print(f"  {step.rung} #{step.attempt}: {step.verdict.value} — {step.detail}")

    if not isinstance(outcome, Delivered):
        print(f"\n{contract.id}: {outcome.outcome.value}", file=sys.stderr)
        print(f"error: {outcome.detail}", file=sys.stderr)
        return 1

    print(
        f"\n{contract.id}: accepted on {outcome.rung} ({outcome.assurance.value}) "
        f"after {outcome.attempts_spent} attempt(s) and "
        f"{outcome.escalations} escalation(s)"
    )
    bound = outcome.judgement.accepted
    if bound is None:
        # `judge` only reaches PASSED through a gate that accepted, and
        # `worker_attempt` binds on exactly that branch. Refusing rather than
        # asserting because the alternative to a bound value is not a fallback:
        # there is nothing to deliver, and a commit assembled from anything else
        # would be bytes no gate read.
        print(
            f"error: {contract.id} was accepted on {outcome.rung} without bound "
            f"content, so there is nothing a delivery could re-judge.",
            file=sys.stderr,
        )
        return 1
    return _commit(args, contract, repo, sandbox.source_base_commit(), bound)


def _report_run(
    args: argparse.Namespace,
    contract: Contract,
    sandbox: Sandbox,
    repo: Path,
    result: GateResult,
) -> int:
    """Print the gate verdict, and commit it when asked."""
    from mcgyvr.deliver import Accepted, DeliveryError

    print(f"\n{contract.id}: gate {'accepted' if result.accepted else 'rejected'}")
    for finding in result.findings:
        print(f"  ✗ {finding}")
    for issue in result.environment_issues:
        print(f"  ? {issue}")
    if not result.accepted:
        return 1

    try:
        bound = Accepted.read(repo=sandbox.workspace, contract=contract, result=result)
    except DeliveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return _commit(args, contract, repo, sandbox.source_base_commit(), bound)


def _commit(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    base: str,
    bound: Accepted,
) -> int:
    """Deliver an accepted change into the user's repository, when asked to.

    Shared by both halves of ``run`` so that "what ``--commit`` does" has one
    answer. ``bound`` is an :class:`~mcgyvr.deliver.Accepted` in both cases and
    never a string: the deterministic path mints it off the workspace the gate
    read, the ladder path carries the one its attempt minted there, and delivery
    re-judges either in the repository the commit lands in.

    No ``config`` is passed to :func:`~mcgyvr.deliver.deliver`, on either path
    and deliberately. ``deliver`` reads a config's ``delivery.mode`` to decide
    whether the commit lands on a branch of its own, and reads *no* config as a
    commit onto the checked-out branch — which is what ``mcgyvr run --commit``
    is: a person at a terminal saying "commit this", in the tree they are looking
    at. Handing over the ladder's config because the ladder path happens to have
    one would make the same flag mean two things depending on the contract.
    """
    from mcgyvr.deliver import DeliveryError, deliver

    if not args.commit:
        print(f"\nNot committed (no --commit). The change is in {contract.target}.")
        return 0

    try:
        delivery = deliver(repo=repo, contract=contract, content=bound, base=base)
    except DeliveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"\n{delivery}")
    return 0 if delivery.committed else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
    )
    parser.add_argument("--version", action="version", version=f"mcgyvr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    caps = sub.add_parser(
        "capabilities",
        help="show the shipped capability table used to propose worker bindings",
    )
    caps.add_argument(
        "--vram",
        type=float,
        default=None,
        metavar="GB",
        help="show only models that fit this much VRAM with working headroom",
    )
    caps.set_defaults(func=_capabilities)

    conf = sub.add_parser(
        "config",
        help="validate the configuration file and show what it resolves to",
    )
    conf.add_argument(
        "path",
        nargs="?",
        default=None,
        help=f"config to read (default: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})",
    )
    conf.set_defaults(func=_config)

    pool = sub.add_parser(
        "pool",
        help="show the ladder as it resolves against the declared sources",
    )
    pool.add_argument(
        "path",
        nargs="?",
        default=None,
        help=f"config to read (default: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})",
    )
    pool.add_argument(
        "--probe",
        action="store_true",
        help=(
            "also ask each source whether it is answering, and drop the rungs "
            "of any that is not (off by default: resolving a ladder should not "
            "require a network)"
        ),
    )
    pool.add_argument(
        "--probe-timeout",
        type=float,
        default=PROBE_TIMEOUT_S,
        metavar="SECONDS",
        help=f"how long a source has to answer a probe (default: {PROBE_TIMEOUT_S:g})",
    )
    pool.set_defaults(func=_pool)

    cat = sub.add_parser(
        "catalog",
        help="show the task types mcgyvr can be asked for, and what each guarantees",
    )
    cat.add_argument(
        "name",
        nargs="?",
        default=None,
        help="show one task type in full (default: list them all)",
    )
    cat.add_argument(
        "--against",
        nargs="?",
        default=False,
        const=None,
        metavar="CONFIG",
        help=(
            "resolve against a configured ladder and name the types it cannot "
            f"start (default config: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})"
        ),
    )
    cat.add_argument(
        "--excluded",
        action="store_true",
        help="also show the types considered and removed, with the reason",
    )
    cat.set_defaults(func=_catalog)

    con = sub.add_parser(
        "contract",
        help="validate a task contract and show what it resolves to",
    )
    con.add_argument("path", help="contract file to validate (YAML or JSON)")
    con.add_argument(
        "--worker-view",
        action="store_true",
        help="print exactly the fields a worker prompt may be built from",
    )
    con.set_defaults(func=_contract)

    det = sub.add_parser(
        "detect",
        help="show what can run the work, and how each fact was detected",
    )
    det.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="HOST",
        help=(
            "also sweep this machine for backends, by name or address "
            "(repeatable; default: localhost only). Hardware detection stays "
            "local — a remote rig is described by what it serves"
        ),
    )
    det.set_defaults(func=_detect)

    sbx = sub.add_parser(
        "sandbox",
        help="show the sandbox mode and the stack detected for a repository",
    )
    sbx.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="repository to inspect (default: current directory)",
    )
    sbx.add_argument(
        "--cache",
        action="store_true",
        help="list cached task images with their sizes instead of inspecting a repo",
    )
    sbx.add_argument(
        "--clear-cache",
        action="store_true",
        help="remove every task image mcgyvr has cached (the documented reset)",
    )
    sbx.set_defaults(func=_sandbox)

    ini = sub.add_parser(
        "init",
        help="detect what is reachable and write a config bound to it",
    )
    ini.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="HOST",
        help=(
            "bind backends on this machine too, by name or address "
            "(repeatable; default: localhost only)"
        ),
    )
    ini.add_argument(
        "path",
        nargs="?",
        default=None,
        help=f"where to write (default: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})",
    )
    ini.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing config, discarding hand edits",
    )
    ini.set_defaults(func=_init)

    att = sub.add_parser(
        "attach",
        help="attach a repository (local path or clone URL) and show its state",
    )
    att.add_argument(
        "source",
        help="a local git checkout, or a URL to clone (https/ssh/git/file)",
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
    idx.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="repository to index (default: current directory)",
    )
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
    res.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="repository to resolve against (default: current directory)",
    )
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
    rd.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="repository to read from (default: current directory)",
    )
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
    rd.set_defaults(func=_read)

    run = sub.add_parser(
        "run",
        help="execute a contract — on the deterministic floor or up the ladder",
    )
    run.add_argument("contract", help="contract file to execute (YAML or JSON)")
    run.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help=(
            "ladder to climb when the contract is not deterministic. Which rung "
            "runs is this file's — the tier order, each tier's `attempts` and the "
            "`budgets` ceilings — never a flag "
            f"(default: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})"
        ),
    )
    run.add_argument(
        "--repo",
        default=".",
        metavar="PATH",
        help="the git repository the work is done against (default: .)",
    )
    run.add_argument(
        "--sandbox",
        default="docker",
        choices=("docker", "tempdir"),
        help=(
            "sandbox mode; `docker` falls back to `tempdir` when no daemon "
            "answers, and says so"
        ),
    )
    run.add_argument(
        "--commit",
        action="store_true",
        help=(
            "commit the change into the repository when the gate accepts it. "
            "Without this the verdict is printed and nothing is written"
        ),
    )
    run.set_defaults(func=_run)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
