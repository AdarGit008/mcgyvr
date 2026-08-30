"""Command-line entrypoint.

Only what is built is exposed. Subcommands appear here as they land; the
scope of record for what is coming is the issue tree.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

from mcgyvr import __version__
from mcgyvr import scan as scan_module
from mcgyvr.availability import PROBE_TIMEOUT_S
from mcgyvr.capability import CapabilityTableError, load, table_path
from mcgyvr.config import CONFIG_FILENAME, CONFIG_PATH_ENV, Config, ConfigError
from mcgyvr.config import config_path as resolve_config_path
from mcgyvr.config import load as load_config
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for
from mcgyvr.emit import EmitError, emit_all
from mcgyvr.exits import Exit
from mcgyvr.initialize import InitError, initialize
from mcgyvr.scan import Mismatch, Scan
from mcgyvr.serving import ModelSpec, UnitError, host_of, units_for


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
            binding = pool.role(role)
        except SourceUnavailableError as exc:
            print(f"\n{role}: unavailable — {exc}")
            continue
        if binding is not None:
            print(f"\n{role}: {binding.model}")

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
    path = Path(args.config) if args.config else resolve_config_path()
    try:
        config = load_config(path)
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

    ``ram_gb`` is what system memory may be asked to hold, which is only ever
    non-zero for an MoE — a dense model has nowhere to spill to, and claiming
    RAM it would never use would refuse rigs that can serve it. For an MoE it
    is the whole weight, because the table does not state the split: it carries
    a working set and a weight, and ``weights - working`` is zero or negative
    for all three MoE rows it ships, so subtracting one from the other claimed
    that a model spilling five gigabytes of experts needs no memory at all.
    The whole weight is the one figure that cannot under-state the demand, and
    under-stating it is the direction that swaps somebody's host.

    ``blocks`` is ``None`` for every row because the table carries no block
    count for any model. That refuses an MoE rather than guessing one
    (:func:`mcgyvr.serving.fit`): ``--n-cpu-moe`` counts blocks, gpt-oss-20b
    has 24 where the sweep's Qwen3 pair has 48, and pricing one at the other's
    layout writes an offload wrong by a factor of two in gigabytes. A dense
    model has no such knob, so the field says nothing about it either way.
    Adding a block count to the table is what lifts the refusal.
    """
    architectures = _architectures()
    specs: list[ModelSpec] = []
    for model in load().models:
        moe = architectures.get(model.id) == "moe"
        specs.append(
            ModelSpec(
                name=model.id,
                vram_gb=model.vram_gb_working,
                ram_gb=model.weights_gb if moe else 0.0,
                disk_gb=model.weights_gb,
                moe=moe,
                blocks=None,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
    )
    parser.add_argument("--version", action="version", version=f"mcgyvr {__version__}")
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
        metavar="PATH",
        help=f"config to read (default: ${CONFIG_PATH_ENV} or ./{CONFIG_FILENAME})",
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

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
