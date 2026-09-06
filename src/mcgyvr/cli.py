"""Command-line entrypoint.

Only what is built is exposed. Subcommands appear here as they land; the
scope of record for what is coming is the issue tree.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import textwrap
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from mcgyvr import __version__
from mcgyvr import scan as scan_module
from mcgyvr.availability import PROBE_TIMEOUT_S
from mcgyvr.capability import GB_PER_GIB, CapabilityTableError, load, table_path
from mcgyvr.config import (
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    CONFIGS_DIR,
    USER_CONFIG_DIR,
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)
from mcgyvr.config import config_path as resolve_config_path
from mcgyvr.config import keep as keep_config
from mcgyvr.config import load as load_config
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for
from mcgyvr.emit import EmitError, emit_all
from mcgyvr.exits import Exit
from mcgyvr.initialize import InitError, initialize
from mcgyvr.scan import Mismatch, Scan
from mcgyvr.serving import ModelSpec, UnitError, hold_together, host_of, units_for

#: The three places a config is looked for, in order, as every `--config`
#: help line states them: one sentence, so no command names a fourth.
CONFIG_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, ./{CONFIG_FILENAME} or {USER_CONFIG_DIR}/{CONFIG_FILENAME}"
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.drive import Recording
    from mcgyvr.escalate import Delivered, Halted
    from mcgyvr.gate import GateResult
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.session import Session


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
    # `None` rather than a resolved path when no argument was given: a config
    # that is not there has a different remedy depending on who named it, and
    # resolving here throws that away — see `config.load`.
    try:
        config = load_config(Path(args.path) if args.path else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{config.path}: valid")
    # The identity every row and result made under this file will carry, and
    # the name of its copy under the journal's configs/ (R2).
    print(f"digest: {config.digest()}\n")
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

    try:
        config = load_config(Path(args.path) if args.path else None)
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
        try:
            config = load_config(Path(args.against) if args.against else None)
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


def _cap_undeclared(contract: Contract) -> str | None:
    """Why a model contract with no declared reply cap is refused, or None.

    The loader derives ``limits.max_output_tokens`` from the task type's own
    evidence, silently, because the bench and the corpus need a number. A
    person's run does not get that silence (owner, 2026-09-05: "fail loud
    when no budget is declared"): the first live ladder cut the top rung's
    reply at a derived 1024 after a 41-second climb, and nobody had chosen
    the number. The derived figure is printed as the value to start from. A
    deterministic contract has no reply to cap and is not asked.
    """
    if contract.is_deterministic or contract.max_output_tokens_declared:
        return None
    return (
        f"limits.max_output_tokens is not declared, and {contract.task_type} is "
        f"executed by a model: a reply cut at a cap nobody chose is spent "
        f"silently. State the cap in the contract — the type's own evidence "
        f"would size it at {contract.limits.max_output_tokens} tokens, which is "
        f"a starting value, not a measurement."
    )


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
    undeclared = _cap_undeclared(contract)
    if undeclared is not None:
        print(f"error: {undeclared}", file=sys.stderr)
        return Exit.USAGE

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
    leaves the accepted change in the working tree and nothing else in the
    repository: no commit, no branch, no receipt (owner's ruling, 2026-09-03).

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

    **Every run is journaled, in one place, and nothing a caller passes moves
    it.** The journal is mcgyvr's own record — ``<journal.dir>/<orchestrator>.jsonl``
    with the prompts and replies content-addressed under ``blobs/`` and each
    run's result under ``results/``. It exists to be *compounded*: how often the
    floor finishes a task type on its own, what a rung costs per accepted
    change, whether escalating paid are all questions about every run there has
    been, and they can only be asked where every run is. ``--record DIR`` used
    to answer them by making them unanswerable — it replaced this directory
    rather than adding to it, so a run made with it was recorded there and
    nowhere else, in a directory that is usually inside a repository, and
    repositories are cloned, go stale and are thrown away. It is now a complete
    second copy for the caller's own reading, and a copy that cannot be written
    is a line on stderr rather than the end of a run mcgyvr has already
    recorded. ``--result PATH`` is the same bargain for the result file: it
    says where the *caller* reads it, and ours keeps its own.

    **Both paths, not only the dispatching one.** A deterministic contract
    sends nothing to a model and used to journal nothing with it, which left
    the corpus holding only the runs the floor did not handle — and the ratio
    that justifies having a deterministic tier at all cannot be computed from a
    table missing its denominator. The floor writes one row naming the program
    that did the work, with ``tier: deterministic`` beside it and no prompt,
    reply or token counts, because it made no dispatch and must not look as
    though it did.

    The orchestrator is the session that typed the command
    (:mod:`mcgyvr.session`), resolved in :func:`main` before anything here runs,
    so a row can be followed back to the conversation. The only thing printed
    about the result is its path: the caller reads a file, not the scrollback.
    """
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.contract import ContractError
    from mcgyvr.contract import load as load_task_contract
    from mcgyvr.drive import Recording
    from mcgyvr.result import RunResult, result_path, run_stamp, write

    session: Session = args.session

    try:
        contract = load_task_contract(Path(args.contract))
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    undeclared = _cap_undeclared(contract)
    if undeclared is not None:
        # Before the repo, the config, the session and the journal: nothing is
        # filed for a run that was refused for what its contract left out.
        print(f"error: {undeclared}", file=sys.stderr)
        return Exit.USAGE

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1

    # The ladder path needs the config; the deterministic floor does not and
    # must keep running without one. Both need the journal dir, which is the
    # config's when there is one and the schema default when the floor runs
    # bare — a default the reference states, not one invented here.
    config: Config | None = None
    config_error: ConfigError | None = None
    # `--config` or nothing, handed on as it came: the loader locates the file
    # when nobody named one, because the remedy for a config that is not there
    # turns on who chose the path and a caller that resolves it first has
    # already lost that. What stays here is the question the loader cannot
    # answer — whether anybody named a path at all — because that decides
    # whether this run says anything: a default location with nothing in it is
    # the supported bare install, and a path someone typed is not.
    chosen = Path(args.config) if args.config else None
    named = chosen if chosen is not None else named_config_path()
    path = named if named is not None else resolve_config_path()
    try:
        config = load_config(chosen)
    except ConfigError as exc:
        config_error = exc
    if config is None and not contract.is_deterministic:
        print(f"error: {config_error}", file=sys.stderr)
        return 1

    # Ours, and nothing a caller passes moves it. The journal is a corpus to be
    # compounded — how often the floor finishes a task type on its own, what a
    # rung costs per accepted change, whether escalating paid — and every one of
    # those questions is about *all* the runs there have been. `--record DIR`
    # used to replace this directory rather than add to it, so a run made with
    # it was recorded there and nowhere else, and the corpus was whatever was
    # left over with no way to know which runs were missing. The directory a
    # caller passes is usually inside the repository they are working in, and
    # repositories are cloned, go stale and are thrown away: a record kept only
    # there has a half-life.
    configured = config.get("journal.dir") if config is not None else None
    journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()
    # Theirs, for their own reading. A complete copy — every line, every blob,
    # the result file — so `tools/live/review.py DIR` reads it exactly as it
    # reads ours, and a failure to write one is a note rather than the end of a
    # run we have already recorded correctly (`Recording.copy_failed`).
    #
    # A copy of the corpus *into* the corpus is dropped rather than made, and
    # this is not a nicety: the copy is written to `<dir>/<orchestrator>.jsonl`
    # by the same name ours is, so naming our own directory appended every line
    # to the same file twice. `fold` survives that — a re-logged attempt id
    # supersedes — but `tools/live/index.py` appends a table row per attempt
    # record and would have counted one dispatch as two, which is exactly the
    # kind of quiet double-count a corpus is kept in order not to have.
    # Resolved before comparing, because `--record .` and an absolute
    # `journal.dir` are the same directory spelled two ways.
    asked = Path(args.record).expanduser() if args.record is not None else None
    mirrors = (
        (asked,)
        if asked is not None and asked.resolve() != journal_dir.resolve()
        else ()
    )

    # One stamp names the run: the result file carries it and every journal
    # row keys on it, so a re-run of the same contract is a second run and
    # not a second copy of the first (`Recording.run`). The destination is
    # settled here rather than at the end because the note below states it,
    # and a note may not state something the run has not decided.
    stamp = run_stamp()
    # Ours is written whatever else is; `--result` says where the *caller*
    # reads it, and that is the path the `result:` line names. The two are the
    # same file when the flag is off, and `write` is called once for it.
    keep = result_path(journal_dir, contract.id, stamp)
    where = Path(args.result) if args.result else keep

    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config_error is not None and not bare_install:
        # Said, not swallowed. The floor runs without a config on purpose, so
        # this is not an error — but a config that is *there* and cannot be
        # used is not the same thing as none, and silence made the two
        # identical: whatever `journal.dir` that file names is not the
        # directory this run is about to write under, and the operator's only
        # clue was a result file somewhere they had configured away from. So
        # the note names the file, what is wrong with it, and where the answer
        # went instead.
        #
        # It names the result file and not the journal dir because the journal
        # dir is not where this run lands. Only the floor ever reaches this
        # line — a climb without a ladder was refused above — the floor
        # dispatches nothing, and nothing is journaled; and `--result` moves
        # the one file that is written out of that directory entirely. A note
        # exists to add a true fact.
        #
        # The reason is flattened first: a YAML parse error is several lines,
        # and the tail of a multi-line message printed under a `note:` prefix
        # is not part of the note as far as anything reading this output is
        # concerned.
        #
        # "sends its result to", not "its result lands at": this line is
        # printed before the run, so the destination is all it has. Where the
        # result *arrives* is not settled until `write` below returns, and
        # `--result` at an unwritable path leaves the note having reported a
        # file that was never created. Moving the note after the write would
        # trade a false tense for a warning that arrives after the whole run,
        # and after the failures that end it early — so the note keeps its
        # place and states the fact it actually has.
        reason = " ".join(str(config_error).split())
        print(
            f"note: {path} is not usable ({reason}); this run goes on without "
            f"a config and sends its result to {where}"
        )

    report = RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        orchestrator=session.orchestrator,
        run=stamp,
        session_file=str(session.session_file) if session.session_file else None,
        journal=str(journal_dir),
    )

    # Every run, both paths. A deterministic contract dispatches nothing and
    # used to journal nothing with it, which left the corpus holding only the
    # runs the floor did *not* handle — and "how often does the floor finish
    # this task type on its own" is the ladder's whole economic case and cannot
    # be computed from a table missing its denominator.
    try:
        recording = Recording(
            path=journal_dir / f"{session.orchestrator}.jsonl",
            orchestrator=session.orchestrator,
            run=stamp,
            session_file=session.session_file,
            config_digest=config.digest() if config is not None else None,
            mirrors=mirrors,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report.config_digest = recording.config_digest
    # Asked before the run rather than discovered during it. Our sink raises on
    # an unwritable path, by the rule `telemetry` opens with — but raising from
    # inside a dispatch reached the caller as a traceback with no `result:`
    # line, and a directory that is a file or a path with no permission is an
    # operator error that is free to state now and expensive to read later. A
    # full disk part-way through is still a raise; this is the cheap half.
    try:
        journal_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            f"error: the journal at {journal_dir} cannot be written ({exc}). "
            f"Every run is recorded there, so this one is refused rather than "
            f"run unrecorded. Fix the directory, or set `journal.dir` to one "
            f"that works.",
            file=sys.stderr,
        )
        return 1
    # The config that is about to run, kept by its digest beside the journal
    # (R2): the file every row of this run will name, and the one to hand
    # `MCGYVR_CONFIG` to run under exactly this setup again. A copy that
    # cannot be written is refused the way the journal is, and for the same
    # reason: a run whose setup cannot be traced is a run recorded wrong.
    if config is not None:
        try:
            keep_config(config, journal_dir)
        except OSError as exc:
            print(
                f"error: the config this run is made under cannot be kept at "
                f"{journal_dir / CONFIGS_DIR} ({exc}). Every run names its "
                f"config by digest and that copy is what the digest resolves "
                f"to, so this one is refused rather than run untraceable.",
                file=sys.stderr,
            )
            return 1
        # A copy of the journal is a copy of the whole of it — every line,
        # every blob, the result, and the config those rows name — and a
        # copy that fails is a note, as every other part of a copy is.
        for mirror in mirrors:
            try:
                keep_config(config, mirror)
            except OSError as exc:
                recording.copy_failed(mirror, exc)
    print(f"journal: {recording.path}", file=sys.stderr)

    # Settled once, here, so both paths below open the same sandbox. The
    # precedence is the one `sandbox/base.py` states and nothing implemented:
    # a flag typed at the terminal is a person overriding their own file and
    # wins; with no flag the file answers; with neither, `docker`.
    args.sandbox = (
        args.sandbox
        or (config.get("sandbox.mode") if config is not None else None)
        or "docker"
    )

    if contract.is_deterministic:
        code = _floor(args, contract, repo, report, recording=recording)
    else:
        assert config is not None  # refused above when it could not load
        code = _climb(args, contract, repo, config, recording=recording, report=report)

    report.exit_code = code
    # Said once, at the end, and not per row: a directory that is a file fails
    # identically for every line of the run, and a thousand notes about one
    # mistake is a way of not reporting it. The result file carries it too, so
    # a caller who reads the file rather than the scrollback — which is what the
    # skill tells them to do — learns their copy is short.
    for mirror, why in recording.copy_errors.items():
        report.copy_errors[str(mirror)] = why
        print(
            f"error: the copy of this run's journal asked for in {mirror} could "
            f"not be written ({why}). mcgyvr's own record under {journal_dir} is "
            f"complete and the run was not stopped for it.",
            file=sys.stderr,
        )

    # Serialised once and copied, never written twice. `write` stamps
    # ``finished`` from the clock on each call, so a second call would produce
    # a file that differs from the first in the one field a reader would use to
    # tell two runs apart — and these are one run. The caller's path is the one
    # written, because it is what the `result:` line names and what they would
    # notice missing; ours is a copy of those exact bytes.
    failed = where
    try:
        written = write(where, report)
        if keep != where:
            failed = keep
            _copy(written, keep)
    except OSError as exc:
        # Said, not thrown. By now the run has happened — an accepted change
        # is already in the working tree — and a traceback with no `result:`
        # line reads to the caller as a run that never started. One line that
        # names the path, the reason and what the run came to is the whole of
        # what the file would have said that matters.
        print(
            f"error: the result could not be written to {failed}: {exc}. "
            f"The run came to {report.outcome}"
            + (f": {report.detail}" if report.detail else "")
            + f" (exit {code}).",
            file=sys.stderr,
        )
        return 1

    # Their copy of the result, under their copy of the journal, so a directory
    # `--record` named is a whole journal and not a journal missing its answers.
    # Not fatal, for the reason none of their copies are: ours is written.
    for mirror in mirrors:
        try:
            _copy(written, result_path(mirror, contract.id, stamp))
        except OSError as exc:
            print(
                f"error: this run's result could not be copied into {mirror}: "
                f"{exc}. It is at {written}.",
                file=sys.stderr,
            )
    print(f"result: {written}")
    return code


def _copy(source: Path, target: Path) -> None:
    """The same bytes at a second path, whole or not at all.

    Through a staging name and :func:`os.replace`, as
    :func:`~mcgyvr.result.write` does, so a reader never opens a half-written
    result — and the same tidy-up, so a copy that failed part-way leaves no
    ``.part`` for the next reader to wonder about.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.part")
    try:
        staging.write_bytes(source.read_bytes())
        os.replace(staging, target)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


class FloorStoppedError(Exception):
    """The floor's program did not do the work, and said why.

    A local exception rather than an early ``return``, because the run has to
    reach :func:`~mcgyvr.telemetry.observe`'s ``except`` to leave a row. A
    ``ruff`` that is not installed, and one that exits 2 on a config it cannot
    load, are both things the corpus has to be able to count — "the floor could
    not" is an answer to "how often does the floor finish this on its own", and
    a run that returned quietly was indistinguishable from one that never
    happened.
    """


def _floor(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    report: RunResult,
    *,
    recording: Recording,
) -> int:
    """Run a deterministic contract's program, gate what it did, and record it.

    **The floor journals, on the same terms as a dispatch.** It writes no
    prompt and no reply because it sent none, but it is a run, and a corpus
    that held only the runs the floor did *not* handle could not answer the one
    question the deterministic tier exists to raise: how much work finishes
    here, for free and in one attempt, rather than on a model. That is a ratio,
    and its denominator was the missing half.

    The row is written before the gate and corrected after it, which is the
    dispatch's own shape: :func:`~mcgyvr.telemetry.observe` records that the
    work happened, and the correction records how it was judged and where it
    went. ``rung`` is the program that did it — ``ruff``, not a model — and
    ``tier`` is ``deterministic`` beside it, so one query can count a floor run
    against a ladder attempt without the two vocabularies colliding in one
    column.

    What is deliberately outside the row: opening the sandbox. It is the
    floor's ``pool.bind`` — the step before the work that decides whether there
    is any — and the ladder does not journal a dispatch it could not make
    either. What is counted is what ran.
    """
    from mcgyvr.deterministic import tool_steps
    from mcgyvr.drive import DriveError, gate_workspace, run_tool_step
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.telemetry import correct, observe

    if args.record is not None:
        # It dispatches nothing and journals all the same, which is the whole
        # of what changed here: the directory gets this run's row, its verdict
        # and a copy of its result — a journal `tools/live/review.py` reads —
        # and mcgyvr's own copy under `journal.dir` gets the same, because that
        # is the one that has to hold every run there has ever been.
        # One clause under both flags, which is new: the note used to have to
        # branch on `--result`, because the result file was the only thing the
        # recorded directory ever got and `--result` took it away, leaving the
        # note describing a directory that ended up empty. A copy is now a
        # whole journal — row, verdict, result — so there is one true sentence.
        print(
            f"note: {contract.id} is a {contract.task_type!r} contract and runs "
            f"on the deterministic floor; it dispatches nothing, so the copy in "
            f"{args.record} is a row naming the program that did the work and a "
            f"copy of this run's result, with no prompt or reply beside them"
        )
    steps = tool_steps(contract)
    if not steps:
        return _error(
            report,
            f"no program on this machine executes {contract.task_type!r} "
            f"for {contract.target}. The work is still doable on a dearer "
            f"family, which this command does not climb to.",
        )

    try:
        sandbox = open_sandbox(repo, mode=args.sandbox)
    except SandboxError as exc:
        return _error(report, str(exc))

    # One row per run, not per step: `tool_steps` returns one step or none —
    # "a tool fails identically on retry" — and a key per step would invent a
    # breadth the floor does not have.
    rung = steps[0].tool.program or contract.task_type
    attempt_id = recording.attempt_id(contract.id, rung, 1)

    def work() -> GateResult:
        for note in sandbox.notes:
            print(f"note: {note}")
        for step in steps:
            outcome = run_tool_step(step, sandbox)
            print(f"  $ {' '.join(step.argv)}")
            if not outcome.ran:
                raise FloorStoppedError(str(outcome.environment_issue))
            assert outcome.result is not None  # `ran` is `result is not None`
            if not outcome.performed:
                raise FloorStoppedError(
                    (outcome.result.stderr or outcome.result.stdout).strip()
                )
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
        return gate_workspace(contract, sandbox)

    try:
        with sandbox:
            result = observe(
                work,
                path=recording.path,
                attempt_id=attempt_id,
                orchestrator=recording.orchestrator,
                rung=rung,
                task_type=contract.task_type,
                session_file=recording.session_file,
                tier=DETERMINISTIC,
                config_digest=recording.config_digest,
                mirrors=recording.mirrors,
                on_copy_error=recording.copy_failed,
            )
            return _report_run(
                args,
                contract,
                sandbox,
                repo,
                result,
                report,
                recording=recording,
                attempt_id=attempt_id,
            )
    except (FloorStoppedError, DriveError, SandboxError) as exc:
        # The row exists by now — `observe` writes one on both of its paths,
        # and everything caught here is raised from inside it or from the
        # sandbox closing around it — so the verdict is written the way a
        # climb's raised attempt's is. An uncorrected row reads as a run that
        # died before anything could judge it, and "the floor could not" is an
        # answer the corpus is being kept in order to count: a tier that
        # finishes nothing on this machine is a different fact from a tier
        # nobody asked. `open_sandbox` failing is caught above instead, where
        # there is no row yet and a correction would be an orphan.
        correct(
            path=recording.path,
            attempt_id=attempt_id,
            outcome=RAISED,
            detail=str(exc),
            orchestrator=recording.orchestrator,
            mirrors=recording.mirrors,
            on_copy_error=recording.copy_failed,
        )
        return _error(report, str(exc))


def _error(report: RunResult, detail: str, *, outcome: str = "error") -> int:
    """Print an error the way every branch here does, and keep it for the result.

    The outcome is set here, not left to whatever the caller had written
    before things went wrong: ``_report_run`` used to file ``accepted`` the
    moment the gate accepted, and a refusal one line later — a symlinked
    target, say — went out as ``outcome: accepted, exit_code: 1`` with nothing
    in the tree. A caller reporting under a more specific word passes it.
    """
    print(f"error: {detail}", file=sys.stderr)
    report.outcome = outcome
    report.detail = detail
    return 1


def _climb(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    config: Config,
    *,
    recording: Recording | None = None,
    report: RunResult,
) -> int:
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

    Hence ``--config`` and no rung flag. It resolves the same way every other
    command's does — ``$MCGYVR_CONFIG``, then the working directory, then
    ``~/.mcgyvr/config/`` — because a second resolution order for the same file is a
    second file as far as an operator debugging one is concerned. The config is
    loaded once, in :func:`_run`, because the journal dir is read off it before
    a rung is chosen.

    **An install that cannot run this contract is refused before a sandbox is
    opened.** :attr:`~mcgyvr.escalate.Ascent.reason` already carries the sentence
    each empty family wrote about itself — which rung was skipped, which variable
    is unset — and ``escalate`` would reach the same conclusion on its own. Doing
    it here is what keeps a container from being built for a task that was never
    going to dispatch.
    """
    from mcgyvr.availability import AvailabilityVerdict
    from mcgyvr.cooldown import Cooldown
    from mcgyvr.drive import DriveError, acceptance_for, worker_attempt
    from mcgyvr.escalate import ascent, escalate
    from mcgyvr.pool import SourceUnavailableError, source_map
    from mcgyvr.route import RouteError
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.verify import reviewer_for

    # Structural resolution, no probe: a live-reachability sweep costs one
    # timeout per source and answers a question the dispatch below is about to
    # ask for real. `mcgyvr pool --probe` is where an operator asks it in
    # advance, and paying for it here would charge every run for a diagnosis.
    pool = source_map(config)

    # The cooldown learns from dispatch failures, not from a probe, so its
    # liveness half is a stub that always reports live. Probing here would
    # charge every run for a diagnosis the dispatch below is about to make for
    # real, and `mcgyvr pool --probe` is where an operator asks it in advance.
    # The probe parameter is typed `object` rather than `Endpoint` because the
    # seam guard forbids importing `Endpoint` above the seam, and `object` is
    # accepted contravariantly.
    def _always_live(endpoint: object, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,  # type: ignore[attr-defined]
            live=True,
            reason="",
            how="stub probe, no network",
            elapsed_s=0.0,
        )

    cooldown = Cooldown(probe=_always_live)
    try:
        route = ascent(config, pool, contract)
    except RouteError as exc:
        return _error(report, str(exc))
    if not route:
        return _error(
            report,
            f"{contract.id} is a {contract.task_type!r} contract and "
            f"starts on the {route.floor.name!r} family; nothing in {config.path} "
            f"can run it. {route.reason}",
        )

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
        return _error(
            report,
            f"verification is enabled and the verifier role cannot run: "
            f"{exc}. Bind it to a usable source, or set "
            f"`verifier.enabled: false` to accept on the deterministic gate.",
        )

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
        return _error(report, str(exc))

    try:
        with sandbox:
            for note in sandbox.notes:
                print(f"note: {note}")
            # The baseline, before the first rung. `Acceptance.precondition`
            # runs both lists against the UNCHANGED tree, and until it was
            # called nothing did: `run` reasoned from a baseline nobody took
            # ("they failed at baseline, so one still failing is ..."). Two
            # silent failures followed. A `bug_fix` whose demonstration was
            # already passing was judged by running it after the change,
            # seeing green, and reporting the bug fixed — nothing was
            # demonstrated and the result file could not say so. And a
            # contract whose acceptance suite was already red charged the
            # model for the tree's fault, which is the exact thing a preflight
            # exists to prevent. The issue's own wording tells the two apart,
            # because the operator's next move differs completely: one says
            # fix the contract, the other says fix the tree.
            acceptance = acceptance_for(contract, sandbox)
            if acceptance is not None:
                issue = acceptance.precondition()
                if issue is not None:
                    # Filed under `error`, the word the result file
                    # documents for a run that reached no verdict — a
                    # preflight issue is an orchestration error and not
                    # a rejected change (gate/preflight.py). The detail
                    # names it as one.
                    return _error(report, str(issue))
            driver = worker_attempt(
                config,
                pool,
                contract,
                sandbox,
                reviewer=reviewer,
                recording=recording,
                cooldown=cooldown,
            )

            outcome = escalate(config, pool, contract, driver)
            return _report_climb(
                args, contract, sandbox, repo, outcome, recording, report
            )
    except (DriveError, SandboxError) as exc:
        return _error(report, str(exc))


def _report_climb(
    args: argparse.Namespace,
    contract: Contract,
    sandbox: Sandbox,
    repo: Path,
    outcome: Delivered | Halted,
    recording: Recording | None,
    report: RunResult,
) -> int:
    """Print what the climb spent, correct the journal, and commit when asked.

    Every attempt is printed, including the ones that failed, and under a failed
    one the gate's findings, one ``✗`` line each. A ladder walk that reported
    only its answer would leave an operator unable to tell one rung accepting
    immediately from three rungs spent and the dearest one succeeding, which is
    the difference the whole escalation policy is about; and a failure reported
    without its findings leaves the caller unable to write a better contract,
    which is the only thing a caller can do about it.

    **This is where the journal learns how each attempt landed.** Each row was
    written by :func:`~mcgyvr.telemetry.observe` before the gate ran, so it
    says what was asked and what came back and not whether it was any good.
    The verdict is appended now as a correction — ``passed``/``failed``, with
    the finding lines as the detail of a failure, or ``error`` for an attempt
    that raised — and :func:`_commit` appends a second one on the accepted
    attempt saying where the work went. A rung that declined dispatched
    nothing and has no row to correct. An attempt that drew more than once
    (``breadth.draws``) wrote one row per draw: the verdict lands on the draw
    it is about and every other draw of that attempt is ``failed``. ``best_of``
    does not stop early — it draws all of them, gates each and ranks the lot —
    so the rows beside the verdict's are draws whose work did not land, which
    is what ``failed`` says about them here whatever their own gate thought of
    them on its own.

    **An attempt that raised accounts for every row it wrote, and the result
    names the one it died in.** The entry's ``rows`` is how many rows the
    attempt wrote — what is iterated here — its ``draws`` is the breadth it was
    asked for, and its ``draw`` is the one that raised; all three are stated by
    the driver (:class:`~mcgyvr.escalate.DispatchRaisedError`) because nothing
    else knows: an exception carries no draw, and reading it back off the
    journal is inference that mis-attributes twice over — a raise after the
    draws lands on a dispatch that answered, and a draw whose row was lost
    shifts every draw down one. A raise before the first dispatch wrote no
    rows, so nothing is corrected; a correction appended for a row nobody wrote
    is an orphan :func:`~mcgyvr.telemetry.fold` returns and the live view
    drops.

    **Every one of those rows is ``error``, including the draws that answered
    before the raise.** They are not ``failed``: ``failed`` is a gate's word,
    and while the earlier draws may well have been gated, the *attempt* they
    belong to reached no verdict at all — writing one on them would report a
    judgement that never happened, the same coinage this project refuses for a
    draw that produced nothing. What distinguishes the row that actually raised
    is not a different word but ``attempt_id``: the result names it, and only
    it, and names nothing when the raise was no dispatch's.

    The accepted attempt is the last entry of the history: ``route.climb``
    returns the moment an attempt passes, right after recording it.
    """
    from mcgyvr.escalate import Delivered
    from mcgyvr.result import AttemptResult
    from mcgyvr.route import Verdict
    from mcgyvr.telemetry import correct

    for step in outcome.history:
        word = RAISED if step.raised else step.verdict.value
        print(f"  {step.rung} #{step.attempt}: {word} — {step.detail}")
        for finding in step.findings:
            print(f"    ✗ {finding}")
        attempt_id: str | None = None
        # The draw the entry is about: the one the gate judged, or the one the
        # attempt died in. `None` comes off a raised entry only, and says no
        # dispatch of the attempt is the subject — so there is no row for the
        # result to name, and every row it wrote is corrected all the same.
        subject = step.draw
        if recording is not None and step.verdict is not Verdict.DECLINED:
            if subject is not None:
                attempt_id = recording.attempt_id(
                    contract.id, step.rung, step.attempt, subject
                )
            for each in range(step.rows):
                correct(
                    path=recording.path,
                    attempt_id=recording.attempt_id(
                        contract.id, step.rung, step.attempt, each
                    ),
                    outcome=(
                        word if step.raised or each == subject else Verdict.FAILED.value
                    ),
                    detail=_correction_detail(step, each, subject),
                    orchestrator=recording.orchestrator,
                    mirrors=recording.mirrors,
                    on_copy_error=recording.copy_failed,
                )
        report.attempts.append(
            AttemptResult(
                rung=step.rung,
                attempt=step.attempt,
                verdict=word,
                detail=step.detail,
                findings=list(step.findings),
                attempt_id=attempt_id,
                draw=step.draw,
                draws=step.draws,
                rows=step.rows,
            )
        )

    if not isinstance(outcome, Delivered):
        report.outcome = outcome.outcome.value
        report.detail = outcome.detail
        print(f"\n{contract.id}: {outcome.outcome.value}", file=sys.stderr)
        print(f"error: {outcome.detail}", file=sys.stderr)
        return 1

    print(
        f"\n{contract.id}: accepted on {outcome.rung} ({outcome.assurance.value}) "
        f"after {outcome.attempts_spent} attempt(s) and "
        f"{outcome.escalations} escalation(s)"
    )
    report.outcome = "accepted"
    report.rung = outcome.rung
    report.assurance = outcome.assurance.value
    bound = outcome.judgement.accepted
    if bound is None:
        # `judge` only reaches PASSED through a gate that accepted, and
        # `worker_attempt` binds on exactly that branch. Refusing rather than
        # asserting because the alternative to a bound value is not a fallback:
        # there is nothing to deliver, and a commit assembled from anything else
        # would be bytes no gate read.
        return _error(
            report,
            f"{contract.id} was accepted on {outcome.rung} without bound "
            f"content, so there is nothing a delivery could re-judge.",
        )
    landed = outcome.history[-1]
    return _commit(
        args,
        contract,
        repo,
        sandbox.source_base_commit(),
        bound,
        report,
        recording=recording,
        attempt_id=(
            recording.attempt_id(
                contract.id,
                landed.rung,
                landed.attempt,
                # An accepted attempt was judged, and a judged entry names the
                # draw it was judged on. Only a raised entry leaves this unset,
                # and a raise is never the last entry of a `Delivered`.
                landed.draw or 0,
            )
            if recording is not None
            else None
        ),
    )


def _correction_detail(step: Attempted, each: int, subject: int | None) -> str:
    """What the correction on one draw's row says, in this caller's vocabulary.

    Four sentences, because a row is corrected for four different reasons and a
    reader of the journal has only this line to tell them apart: the draw the
    verdict is about carries the gate's findings; a draw that lost to it says
    which draw won; the draw an attempt raised in carries the raise; and a draw
    of a raised attempt that is not that one says so and says where the raise
    was instead — on another draw, or past the last draw that answered.

    That last sentence is why the raised rows are not simply left alone. An
    attempt accounts for every row it wrote: a suffixed row that keeps ``ok:
    true`` and no outcome is indistinguishable from a run that died before it
    could be corrected, which is precisely the reading breadth's own telemetry
    must not invite.

    It used to read "after its draws", which was true of one raise and false of
    two others wearing the same ``draw: null``: a gate that died on draw 0 of
    three, and a draw whose ``pool.bind`` raised before it reached a row, both
    left draws still to come. ``rows`` is what tells them apart — this line is
    only ever written about a row that exists, so ``rows - 1`` is the last draw
    that answered — and naming that draw is true of all three, the raise after
    the last draw included.
    """
    if step.raised:
        if each == subject:
            return step.detail
        where = (
            f"on draw {subject}"
            if subject is not None
            else f"after draw {step.rows - 1} answered"
        )
        return f"the attempt raised {where}; no verdict was reached for this draw"
    if each == subject:
        return "\n".join(step.findings) or step.detail
    return f"a losing draw; the attempt's verdict is on draw {subject}"


def _report_run(
    args: argparse.Namespace,
    contract: Contract,
    sandbox: Sandbox,
    repo: Path,
    result: GateResult,
    report: RunResult,
    *,
    recording: Recording | None = None,
    attempt_id: str | None = None,
) -> int:
    """Print the gate verdict, correct the row it is about, and commit when asked.

    ``recording`` and ``attempt_id`` arrive from :func:`_floor`, its only
    caller, which writes one row per run and needs it corrected the way
    :func:`_report_climb` corrects a climb's: the row says the program ran, and
    the correction says how the gate judged it. They are optional because the
    correcting is the only part of this a caller can decline, not because there
    is a second caller that declines it — a climb never comes through here, it
    reports itself and reaches :func:`_commit` directly.
    """
    from mcgyvr.deliver import Accepted, DeliveryError
    from mcgyvr.route import Verdict
    from mcgyvr.telemetry import correct

    print(f"\n{contract.id}: gate {'accepted' if result.accepted else 'rejected'}")
    for finding in result.findings:
        print(f"  ✗ {finding}")
    for issue in result.environment_issues:
        print(f"  ? {issue}")
    report.findings = [str(finding) for finding in result.findings]
    if recording is not None and attempt_id is not None:
        # The gate's word for it, in the gate's vocabulary — the same two words
        # a climb's attempts are corrected with, so one query counts them
        # together. `_commit` appends a second correction on top saying where
        # the work went, and the folded row is that later one.
        correct(
            path=recording.path,
            attempt_id=attempt_id,
            outcome=(Verdict.PASSED if result.accepted else Verdict.FAILED).value,
            detail="\n".join(str(finding) for finding in result.findings),
            orchestrator=recording.orchestrator,
            mirrors=recording.mirrors,
            on_copy_error=recording.copy_failed,
        )
    if not result.accepted:
        report.outcome = "rejected"
        return 1

    try:
        bound = Accepted.read(repo=sandbox.workspace, contract=contract, result=result)
    except DeliveryError as exc:
        return _error(report, str(exc))
    # Only now: `accepted` tells the caller the change is in the target, and
    # until the bytes are bound there is nothing to put there.
    report.outcome = "accepted"
    return _commit(
        args,
        contract,
        repo,
        sandbox.source_base_commit(),
        bound,
        report,
        recording=recording,
        attempt_id=attempt_id,
    )


#: The words :func:`_commit` appends to the accepted attempt's row. The
#: vocabulary is this caller's, as ``telemetry.correct`` says it must be.
COMMITTED = "committed"
NOT_COMMITTED = "not_committed"
DELIVERY_REFUSED = "delivery_refused"
#: The word for an attempt that raised instead of judging: the row says
#: ``ok: false`` already, and the correction says the climb counted it.
RAISED = "error"

#: The ``tier`` a floor row carries. The catalog's own name for the family that
#: runs programs rather than models (``catalog().families`` — ``deterministic``,
#: ``local``, ``api``), so a floor row and a ladder row, whose tier is
#: ``family_of(...).name``, are comparable in one column rather than in two
#: vocabularies that happen to look alike. It is a literal and not a lookup
#: because the floor has no rung to ask the catalog about, and
#: ``test_a_floor_run_is_in_the_corpus_too`` holds the two together.
DETERMINISTIC = "deterministic"


def _commit(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    base: str,
    bound: Accepted,
    report: RunResult,
    *,
    recording: Recording | None = None,
    attempt_id: str | None = None,
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

    **The default is the working tree, and that is not a lack.** Without
    ``--commit`` the accepted change is left in the target and the repository
    is otherwise untouched — no commit, no branch, no receipt. The journal row
    of the accepted attempt is told so (``not_committed``), and told
    ``committed <sha> on <branch>`` or ``delivery_refused`` otherwise, so the
    folded outcome is how the work finally landed.
    """
    from mcgyvr.deliver import DeliveryError, deliver, place
    from mcgyvr.telemetry import correct

    def landed(outcome: str, detail: str) -> None:
        if recording is not None and attempt_id is not None:
            correct(
                path=recording.path,
                attempt_id=attempt_id,
                outcome=outcome,
                detail=detail,
                orchestrator=recording.orchestrator,
                mirrors=recording.mirrors,
                on_copy_error=recording.copy_failed,
            )

    if not args.commit:
        try:
            place(repo=repo, contract=contract, content=bound, base=base)
        except DeliveryError as exc:
            landed(DELIVERY_REFUSED, str(exc))
            return _error(report, str(exc), outcome=DELIVERY_REFUSED)
        print(f"\nLeft in {contract.target}, not committed (pass --commit to commit).")
        landed(NOT_COMMITTED, f"no --commit; change left in {contract.target}")
        report.detail = f"change left in {contract.target}"
        return 0

    try:
        delivery = deliver(repo=repo, contract=contract, content=bound, base=base)
    except DeliveryError as exc:
        landed(DELIVERY_REFUSED, str(exc))
        return _error(report, str(exc), outcome=DELIVERY_REFUSED)

    print(f"\n{delivery}")
    report.committed = delivery.committed
    report.commit = delivery.commit
    report.branch = delivery.branch
    report.handoff = delivery.handoff
    if delivery.committed:
        landed(COMMITTED, f"{delivery.commit[:12]} on {delivery.branch or 'HEAD'}")
        return 0
    landed(DELIVERY_REFUSED, delivery.reason)
    report.outcome = DELIVERY_REFUSED
    report.detail = delivery.reason
    return 1


def _scan(args: argparse.Namespace) -> int:
    """Measure this machine, record it, and say what stopped matching.

    ``--json`` exits :attr:`Exit.OK` even when the scan disagrees with the
    record, and that asymmetry is the point rather than an oversight.
    ``--json`` is not a quieter mode of this command for a person; it is the
    far end of an ssh pipe, and the only thing that reads it is
    :func:`mcgyvr.scan.scan_over` → ``_ssh`` → ``_run``, which treats *any*
    non-zero status as "this host did not answer" and raises ``Unreachable``.
    Exiting 4 down that channel would take the one event exit 4 exists to
    surface — a rig that lost a DIMM or a card — and make that rig disappear
    from ``scan_all`` altogether, discarding a perfectly good measurement that
    is already sitting on stdout. So the wire format's job is to deliver the
    measurement: the mismatch goes to stderr, where the operator still reads it
    and the parser never does. The exit-code channel belongs to the
    human-facing command, which keeps exit 4.
    """
    measured = scan_module.scan()
    root = scan_module.default_root()
    prior = scan_module.load_prior(scan_module.machine_id(measured), root)
    drift = scan_module.compare(measured, prior)
    # Recorded before anything is reported, and recorded even when it
    # disagrees with the last scan. A mismatch is a successful measurement of a
    # machine that changed, not a failed one; withholding it would leave the
    # stale record in place for the next run to disagree with all over again.
    path = scan_module.write_scan(measured, root)

    if args.json:
        # stdout is the wire format: `mcgyvr scan --json` is what the far end
        # of an ssh pipe runs and `Scan.from_json` is what reads it back
        # (mcgyvr.scan.scan_over). One banner line here and the remote scan
        # stops parsing, so everything a person would read goes to stderr.
        sys.stdout.write(measured.to_json())
        _report_mismatches(drift, sys.stderr)
        return Exit.OK

    machine = measured.machine
    print(f"{machine.host} ({machine.id}), kernel {machine.kernel}")
    if measured.gpus:
        for gpu in measured.gpus:
            print(
                f"  GPU {gpu.index}    {gpu.name} — "
                f"{gpu.vram.free_mib} MiB free of {gpu.vram.total_mib} MiB"
            )
    else:
        print("  GPU      none found")
    if measured.memory is not None:
        print(
            f"  RAM      {measured.memory.available_gb:.1f} GB available of "
            f"{measured.memory.total_gb:.1f} GB"
        )
    if measured.cpu is not None:
        print(f"  CPU      {measured.cpu.cores} cores, {measured.cpu.threads} threads")
    if measured.bandwidth is not None:
        print(
            f"  Memory   {measured.bandwidth.measured_gbps:.1f} GB/s "
            f"({measured.bandwidth.how})"
        )
    if measured.disk is not None:
        print(f"  Disk     {measured.disk.free_gb:.1f} GB free at {measured.disk.path}")
    for note in measured.notes:
        print(f"  - {note}")
    print(f"\nRecorded at {path}")

    if drift:
        _report_mismatches(drift, sys.stdout)
        return Exit.MISMATCH
    return Exit.OK


def _emit(args: argparse.Namespace) -> int:
    """Write one compose file per host for the ladder's serving units.

    Nothing is started. See :mod:`mcgyvr.emit` — this hands the operator a
    launch spec and stops.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    scans = _scans(scan_module.default_root())
    try:
        hosts = _hosts_wanted(config)
    except UnitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    # A source's URL names a *route* to a machine; a scan is filed under what
    # the machine calls *itself*. Those are two names for one rig and they
    # rarely match, so the two are reconciled here, once, before either the
    # refusal below or `units_for` looks a host up.
    scans = _resolve_hosts(scans, hosts.values())

    # Refusal is decided before a single model is looked up, because it is the
    # earlier question and the more useful answer: told "no spec for
    # qwen3-coder-30b" about a rig nobody has measured, an operator goes and
    # edits the model name, which was never the problem.
    unscanned = sorted({host for host in hosts.values() if host not in scans})
    if unscanned:
        for host in unscanned:
            print(
                f"refused: {host} has never been scanned. A unit is sized from "
                f"measured free VRAM, RAM and disk, so there is nothing here to "
                f"size it from — run `mcgyvr scan` on {host} first.",
                file=sys.stderr,
            )
        return Exit.REFUSED

    # A model the table does not carry, and a model too large for the machine
    # it was bound to, are both refusals rather than failures: nothing is
    # broken, mcgyvr is declining to write a launch spec it cannot stand
    # behind. A caller branching on the code should read them the same way it
    # reads an unscanned host. A malformed capability table is a real error.
    try:
        units = units_for(config, scans, specs=_model_specs())
        hold_together(units, scans)
    except UnitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # One llama-server or vLLM process serves one model, so two units sharing a
    # source share a port and the second one loses the race to bind it. The
    # emitted file would look right and fail on the rig, which is the failure
    # this whole module exists to avoid. Ollama is exempt: it swaps models
    # behind one endpoint by design.
    endpoints: dict[str, list[str]] = {}
    for unit in units:
        for rung in unit.rungs:
            tier = config.ladder.get(rung)
            if tier is None:
                continue
            source = config.sources[tier.source]
            if source.api == "ollama":
                continue
            endpoints.setdefault(source.base_url, [])
            if unit.key.slug not in endpoints[source.base_url]:
                endpoints[source.base_url].append(unit.key.slug)
    for base_url, slugs in sorted(endpoints.items()):
        if len(slugs) > 1:
            print(
                f"refused: {base_url} is bound to {len(slugs)} models "
                f"({', '.join(sorted(slugs))}), and one server process serves "
                f"one model — they would contend for the same port. Give each "
                f"model its own source on its own port.",
                file=sys.stderr,
            )
            return Exit.REFUSED

    out = Path(args.out) if args.out else Path.cwd()
    try:
        written = emit_all(units, root=out)
    except (EmitError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    for unit in sorted(units, key=lambda u: u.key.slug):
        rungs = ", ".join(unit.rungs) or "no rung"
        print(
            f"{unit.key.slug}  gpu {unit.gpu}, {unit.width.value} slots "
            f"({unit.width.how})  for {rungs}"
        )
    print()
    for compose in written:
        print(f"wrote {compose}")
    print("\nNothing was started. `docker compose -f <file> up -d` is yours to run.")
    return Exit.OK


def _report_mismatches(found: Sequence[Mismatch], stream: TextIO) -> None:
    if not found:
        return
    print("mismatch: this machine no longer matches its last scan:", file=stream)
    for item in found:
        print(f"  {item.field}: was {item.prior}, now {item.measured}", file=stream)


def _scans(root: Path) -> dict[str, Scan]:
    """Every machine recorded under ``root``, keyed by the name it calls itself.

    That is ``platform.node()``, which is not the name a source's ``base_url``
    carries; :func:`_resolve_hosts` is what bridges the two. Keying by the
    recorded name and widening afterwards keeps this function a faithful
    reading of the directory — one key per machine, no invented names — so the
    reconciliation is somewhere a reader can find it and argue with it.

    A record that cannot be read is skipped rather than fatal, on the same rule
    the rest of the scan layer runs on: the answer to an unreadable scan is to
    take another one, and that is what the refusal below asks for anyway.
    """
    found: dict[str, Scan] = {}
    for path in sorted(root.glob("*.json")):
        try:
            recorded = Scan.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if recorded.machine.host:
            found[recorded.machine.host] = recorded
    return found


def _hosts_wanted(config: Config) -> dict[str, str]:
    """Which machine each rung would run on — rung name to host."""
    wanted: dict[str, str] = {}
    for tier in config.ladder.tiers:
        source = config.sources.get(tier.source)
        if source is None:
            raise UnitError(f"{tier.name}: no source named {tier.source!r}")
        wanted[tier.name] = host_of(source.base_url)
    return wanted


#: Names that cannot mean any machine but the one this process is running on.
#: Everything numeric is left to :mod:`ipaddress` below, which knows the whole
#: of ``127.0.0.0/8`` and ``::1`` without this file listing them.
_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _names_this_machine(name: str) -> bool:
    """Whether ``name`` can only ever mean the machine this process runs on.

    ``0.0.0.0`` counts. It is not a loopback address, but nothing else can be
    reached at it either: written in a ``base_url`` it means "the server I am
    about to start here, on every interface", which is a statement about this
    machine.
    """
    lowered = name.strip().lower().rstrip(".")
    if lowered in _LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _same_host(recorded: str, wanted: str) -> bool:
    """Whether two hostnames are one machine written long and short.

    ``desktop-9`` and ``desktop-9.lan`` are the same rig: a config names it the
    way the operator types it, and ``platform.node()`` reports it the way the
    machine was configured. Only a whole leading label counts, so ``rig`` does
    not match ``rigel.lan`` — the failure this must never have is two different
    machines treated as one, because that sizes a unit from the wrong rig's
    free VRAM and the compose file it writes looks entirely reasonable.
    """
    left = recorded.strip().lower().rstrip(".")
    right = wanted.strip().lower().rstrip(".")
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


def _resolve_hosts(scans: dict[str, Scan], wanted: Iterable[str]) -> dict[str, Scan]:
    """``scans`` again, with a key added for each wanted name that resolves to
    a machine already in it.

    Without this, ``emit`` refuses the machine it is running on. The stock
    config says ``base_url: http://localhost:11434``, ``mcgyvr scan`` files the
    record under ``platform.node()``, and the two never agree — so the most
    ordinary setup there is, one rig serving itself, reports "localhost has
    never been scanned" the instant after it was scanned.

    Resolution is by identity rather than by name wherever it can be: a
    loopback source is matched to the local scan through
    :func:`mcgyvr.scan.local_machine_id`, so it stays right on a machine that
    was renamed and cannot be fooled by a second rig that happens to answer to
    the same hostname. Only the long/short form of a real hostname is matched
    by string, and only when exactly one recorded machine answers to it:
    an ambiguous name resolves to nothing and falls through to the refusal,
    because being told to run `mcgyvr scan` costs a minute and being sized
    against another machine's hardware costs a debugging session.
    """
    resolved = dict(scans)
    local: str | None = None
    for name in wanted:
        if name in resolved:
            continue
        if _names_this_machine(name):
            if local is None:
                local = scan_module.local_machine_id()
            match = _local_scan(scans, local)
        else:
            match = _named_scan(scans, name)
        if match is not None:
            resolved[name] = match
    return resolved


def _local_scan(scans: dict[str, Scan], machine_id: str) -> Scan | None:
    """The recorded scan of this very machine, or None if it has never run one."""
    for recorded in scans.values():
        if recorded.machine.id == machine_id:
            return recorded
    return None


def _named_scan(scans: dict[str, Scan], name: str) -> Scan | None:
    """The one recorded machine ``name`` names, or None if it is not exactly one.

    Two records answering to one name is not a tie to be broken. They are two
    machines, and picking either would hand back hardware the operator did not
    ask about.
    """
    matched = [recorded for host, recorded in scans.items() if _same_host(host, name)]
    if len({recorded.machine.id for recorded in matched}) != 1:
        return None
    return matched[0]


def _model_specs() -> tuple[ModelSpec, ...]:
    """Serving specs for the models the capability table measured.

    Three of the four numbers come straight off the typed reader. The fourth —
    whether a model has experts, and so a knob for *where* its weights sit — is
    in the table file but not in :class:`mcgyvr.capability.Model`, so it is read
    from the same file rather than guessed from a name. Getting it wrong is not
    cosmetic: a dense model that does not fit is a refusal, while an MoE that
    does not fit is a model that fits differently (:mod:`mcgyvr.serving`).

    ``geometry`` is ``None`` for every row because the table carries no GGUF
    geometry for any model. A dense row is therefore sized on its scalar
    figures, one slot wide; an MoE row is refused rather than sized
    (:func:`mcgyvr.serving.fit`), because ``--n-cpu-moe`` moves whole blocks
    and what each block's experts weigh is in the tensor table and nowhere
    else. An operator who has scanned the file points ``models.<id>.geometry_json``
    at the scan, and that lifts the refusal for the model they scanned — on
    the scan's numbers, not the table's.

    **The table is in decimal GB and this module is in GiB.** Tied to a real
    file: ``deepseek-coder-v2-16b.gguf`` is 8_905_109_984 bytes and its row
    says ``weights_gb: 8.9``, which is decimal (GiB would be 8.3). Everything
    downstream compares against ``free_mib / 1024``
    (:data:`mcgyvr.detect.MIB_PER_GB`), so the conversion happens here, once,
    at the boundary where the two conventions meet. Skipping it inflated every
    spec by 7.37% — harmlessly for a while, because the MoE arithmetic carried
    two further errors that cancelled it.

    ``ram_gb`` is ``0.0`` for every row, dense and MoE alike. It is a floor an
    operator may raise, not a declaration this function can make: what an MoE
    actually spills depends on the card and is derived per machine by
    :func:`mcgyvr.serving._placement`. Passing the whole model weight here —
    which is what it used to do — made that derivation inert.
    """
    architectures = _architectures()
    specs: list[ModelSpec] = []
    for model in load().models:
        moe = architectures.get(model.id) == "moe"
        specs.append(
            ModelSpec(
                name=model.id,
                vram_gb=model.vram_gb_working / GB_PER_GIB,
                ram_gb=0.0,
                disk_gb=model.weights_gb / GB_PER_GIB,
                moe=moe,
                geometry=None,
            )
        )
    return tuple(specs)


def _architectures() -> dict[str, str]:
    """``model id -> architecture`` from the shipped table, for the one field
    :mod:`mcgyvr.capability` does not carry yet."""
    path = table_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityTableError(f"cannot read {path}: {exc}") from exc
    return {
        str(entry["id"]): str(entry["architecture"])
        for entry in raw.get("models", [])
        if entry.get("architecture")
    }


def _named_path(value: str) -> str:
    """A path argument's value, refused when it names nothing.

    Argparse's own ``type``, so the refusal is the subparser's usage error —
    exit 2, with the argument's name in it — and arrives before a contract, a
    repository or a config file is opened. That is the same seam and the same
    code as the blank ``--orchestrator`` (:func:`_name_the_writer`), because it
    is the same mistake: an argument given a value that names nothing.

    **A blank is not "the caller named none", and reading it that way is silent
    in every case.** Every path here is optional and every one of them resolves
    a default when it is absent, so the empty string — falsy, and equal to
    ``Path('.')`` once it reaches :class:`~pathlib.Path` — slid into the absent
    branch and the run went on under a default nobody chose. ``--record ''``
    was the worst of them, because it is tested with ``is not None``: the
    journal, its blobs and the result file landed in the *current directory*,
    which is the repository the 2026-09-03 ruling exists to keep clean, and the
    ``result:`` line came out relative to a working directory the caller may
    not still be in. ``--config ''`` and ``--result ''`` were quieter and the
    same shape.

    What puts a blank there is not somebody typing two quotes. It is
    ``--record "$JOURNAL_DIR"`` with the variable unset, which is the shape
    every wrapper script has, and a wrapper is exactly the caller who will not
    read the scrollback to notice.

    Whitespace counts as blank, as it does for the orchestrator id. A directory
    named three spaces is legal on this filesystem and is not what anybody
    meant; the value is otherwise handed on untouched, because a path with a
    space at either end is legal too and stripping it would be this function
    choosing a different file than the caller named.
    """
    if not value.strip():
        raise argparse.ArgumentTypeError(
            "a blank value is not a path. It is what an unset variable leaves "
            "behind, and a blank used to read as 'nobody named a path' — so "
            "the command resolved a default the caller never chose, which for a "
            "directory is the current one. Pass a path, or leave the argument "
            "off to take the default on purpose."
        )
    return value


def _name_the_writer(run: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Resolve who is writing the journal, or refuse at parse time.

    Before a config is read, a sandbox opened or a directory created, through
    the subparser's own ``error`` so the refusal reads like every other usage
    error and exits 2. The writer is the session that typed the command
    (:mod:`mcgyvr.session`): ``--orchestrator ID`` if given, else the Claude
    Code or Pi session in the environment, else a refusal whose message names
    all three. A default derived from the process is exactly the
    single-orchestrator assumption §9 names, so there is no default, only a
    flag and two variables to ask for.

    An id containing ``/`` is refused here too, because the id *is* the file
    name — ``DIR/<ID>.jsonl`` — and ``agent/a`` would write ``DIR/agent/a.jsonl``
    with its blobs under ``DIR/agent/blobs``, where an index over ``DIR`` finds
    neither.

    A blank id is refused here as well, and here is the only place that can do
    it once. It used to be left to :class:`~mcgyvr.drive.Recording`, which
    refuses one — but a deterministic contract never constructs a ``Recording``,
    so ``--orchestrator ''`` ran to completion and left a result file naming
    nobody, and on the ladder path the refusal arrived as exit 1 after a config
    and a contract had been read, where the documented answer to a run with no
    session is exit 2. The environment's session does not stand in for it: a
    caller who typed the flag was naming the writer, and an empty value is that
    caller getting the name wrong rather than declining to give one.
    """
    from mcgyvr.session import SessionError, resolve

    if args.orchestrator is not None and not args.orchestrator.strip():
        run.error(
            "--orchestrator was given an empty id: a row that cannot say which "
            "orchestrator produced it is the hole the field exists to close "
            "(§9). Pass an ID, or leave the flag off to be named by the session "
            "that typed this command."
        )
    if args.orchestrator is not None and "/" in args.orchestrator:
        run.error(
            f"--orchestrator {args.orchestrator!r} cannot contain '/': the id "
            f"is the journal's file name, DIR/<ID>.jsonl"
        )
    try:
        args.session = resolve(args.orchestrator)
    except SessionError as exc:
        run.error(str(exc))


def _build() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """The whole command line, plus the ``run`` subparser on its own.

    Two returns because :func:`_name_the_writer` refuses a blank
    ``--orchestrator`` through the subparser that owns the flag, so its usage
    line is the one the caller was typing against
    (tests/test_a_blank_orchestrator_is_refused_not_filed.py).
    """
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
    )
    parser.add_argument(
        "--version",
        action=_Version,
        nargs=0,
        help="the product version, and the digest of the config a run would use",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    caps = sub.add_parser(
        "capabilities",
        # `caps` is what the command is called in the issue tree and in every
        # transcript of someone using it; argparse does not abbreviate
        # subcommands the way it abbreviates flags, so the short name has to be
        # spelled out or it is an exit-2 usage error.
        aliases=["caps"],
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
        type=_named_path,
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
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
        type=_named_path,
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
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
        type=_named_path,
        metavar="CONFIG",
        help=(
            "resolve against a configured ladder and name the types it cannot "
            f"start (default config: {CONFIG_DEFAULT_HELP})"
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

    sca = sub.add_parser(
        "scan",
        help="measure this machine, record it, and report what changed since",
    )
    sca.add_argument(
        "--json",
        action="store_true",
        help=(
            "write the scan to stdout and nothing else — the wire format the "
            "remote transport parses"
        ),
    )
    sca.set_defaults(func=_scan)

    emi = sub.add_parser(
        "emit",
        help="write a compose file per host for the ladder's serving units",
    )
    emi.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    emi.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="where the compose files are written (default: the current directory)",
    )
    emi.set_defaults(func=_emit)

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
        help=f"where to write (default: {CONFIG_DEFAULT_HELP})",
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
        type=_named_path,
        metavar="PATH",
        help=(
            "ladder to climb when the contract is not deterministic. Which rung "
            "runs is this file's — the tier order, each tier's `attempts` and the "
            "`budgets` ceilings — never a flag "
            f"(default: {CONFIG_DEFAULT_HELP})"
        ),
    )
    run.add_argument(
        "--repo",
        default=".",
        type=_named_path,
        metavar="PATH",
        help="the git repository the work is done against (default: .)",
    )
    run.add_argument(
        "--sandbox",
        # No default. `sandbox.mode` in the config is declared as where this
        # comes from, and a flag that is never absent is a flag the config can
        # never lose to. `_run` settles the precedence: typed flag, else the
        # file, else `docker`.
        default=None,
        choices=("docker", "tempdir"),
        help=(
            "sandbox mode; defaults to `sandbox.mode` in the config, then to "
            "`docker`, which falls back to `tempdir` when no daemon answers "
            "and says so"
        ),
    )
    run.add_argument(
        "--commit",
        action="store_true",
        help=(
            "commit the change into the repository when the gate accepts it. "
            "Without this the accepted change is left in the working tree and "
            "the repository is otherwise untouched: no commit, no branch"
        ),
    )
    run.add_argument(
        "--record",
        default=None,
        type=_named_path,
        metavar="DIR",
        help=(
            "also journal this run under DIR, as a complete second copy for "
            "your own reading: DIR/<ID>.jsonl, DIR/blobs/, DIR/results/, read "
            "back with tools/live/review.py DIR. This does not move mcgyvr's "
            "own record, which is always written under the config's "
            "`journal.dir` so that every run there has ever been can be counted "
            "in one place; a copy that cannot be written is reported and does "
            "not stop the run"
        ),
    )
    run.add_argument(
        "--orchestrator",
        default=None,
        metavar="ID",
        help=(
            "who is writing the journal. Names the sink, <ID>.jsonl, and is "
            "carried on every row, so two orchestrators sharing a directory "
            "stay distinguishable (§9). Default: the session that typed this "
            "command — claude-<id> from CLAUDE_CODE_SESSION_ID, pi-<id> from "
            "PI_SESSION_FILE — and a refusal when there is none"
        ),
    )
    run.add_argument(
        "--result",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=(
            "where *you* read this run's result file (default: <journal "
            "dir>/results/<contract>-<utc stamp>.json). The path is printed as "
            "`result: PATH`; the caller reads the file. mcgyvr keeps its own "
            "copy under the journal directory either way"
        ),
    )
    run.set_defaults(func=_run)

    return parser, run


def build_parser() -> argparse.ArgumentParser:
    """The command line as a person types it.

    Public so what a run reads and what a person typed can be checked against
    each other. ``--sandbox`` is the case that made it necessary: it carried an
    argparse default of ``docker``, so the flag was never absent, so
    ``sandbox.mode`` in a config was never reached and an operator who wrote
    ``tempdir`` ran under Docker and was told nothing.
    """
    return _build()[0]


class _Version(argparse.Action):
    """``--version``: the product, then the config a run here would be made under.

    Two lines and not one, because they are two identities (owner's ruling
    R2): the wheel is the code, and the config is the setup, and a result
    names both. The config is the one `load()` locates — `$MCGYVR_CONFIG`,
    then the working directory, then the user dir — so the digest printed is
    the digest a run typed at this prompt would carry. No config prints
    `none`; one that is there and cannot be read prints why, because a
    version line that swallowed that would be the one lie an operator
    checking their setup cannot afford.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        print(f"mcgyvr {__version__}")
        try:
            config = load_config(None)
        except ConfigMissingError:
            print("config: none")
        except ConfigError as exc:
            print(f"config: unreadable ({exc})")
        except (OSError, RuntimeError) as exc:
            # A `~nobody` in the variable, a working directory that is gone:
            # not a config that cannot be read, one that cannot be found.
            print(f"config: cannot be located ({exc!r})")
        else:
            print(f"config: {config.digest()} ({config.path})")
        parser.exit(0)


def main(argv: Sequence[str] | None = None) -> int:
    parser, run = _build()
    args = parser.parse_args(argv)
    if args.func is _run:
        _name_the_writer(run, args)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
