"""Command-line entrypoint.

Only what is built is exposed.
"""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import signal
import sys
import textwrap
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

import yaml

from mcgyvr import __version__
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import PROBE_TIMEOUT_S
from mcgyvr.capability import (
    ESTIMATES_NOTICE,
    GB_PER_GIB,
    CapabilityTableError,
    Model,
    load,
    table_path,
)
from mcgyvr.config import (
    API_OUTPUT_TOKENS,
    CONFIG_PATH_ENV,
    FLEET_FILENAME,
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)
from mcgyvr.config import config_path as resolve_config_path
from mcgyvr.config import load as load_config
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for
from mcgyvr.emit import (
    Drift,
    EmitError,
    LockedLaunchError,
    check_all,
    check_locked,
    emit_all,
    emit_locked,
    is_locked,
    planned_locked_paths,
    planned_paths,
    resolved_launch,
    unplanned,
    unplanned_locked,
)
from mcgyvr.emit import sleep_mode as emit_sleep_mode
from mcgyvr.exits import Exit
from mcgyvr.fleet.files import FleetFileError, load_fleet
from mcgyvr.fleet.roots import (
    FLEETS_SHOWN,
    HOME_DIR,
    HOME_ENV,
    LIVE_FILE_SHOWN,
    RIGS_SHOWN,
    FolderError,
)
from mcgyvr.initialize import (
    PRIORITIES,
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
    render_fleet,
)
from mcgyvr.scan import Mismatch, ModelOnDisk, Scan
from mcgyvr.serving import (
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    host_of,
    units_for,
)

#: The three places a config is looked for, in order, as every `--config`
#: help line states them: one sentence, so no command names a fourth.
CONFIG_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, then the working directory when it holds fleet.yaml, "
    f"then the live fleet folder under {FLEETS_SHOWN} that {LIVE_FILE_SHOWN} "
    f"names — a directory holding fleet.yaml and policy.yaml"
)
#: Where `mcgyvr setup` writes when no path is given. Never a live fleet folder:
#: those are written only by `mcgyvr fleet promote`, and never in place.
INIT_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, else the working directory — never a live fleet "
    f"folder, which only `mcgyvr fleet promote` writes"
)

#: Where a machine's owner reads how to stand the ladder up; `run` prints it
#: when a model contract finds no config. Relative to the repository, as the
#: skill directory is: the reader is the person who has the checkout this ran
#: from, and an absolute path resolved here would be this machine's, not theirs.
SETUP_DOC = "skills/mcgyvr/SETUP.md"

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.detect import Detection
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.drive import Recording
    from mcgyvr.escalate import Delivered, Halted, Judgement
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.knowledge.record import ModelRecord
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted, Try
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.session import Session


def _capabilities(args: argparse.Namespace) -> int:
    try:
        table = load()
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    models = table.fitting(args.vram) if args.vram else table.models
    labels = ", ".join(c.label for c in table.card_classes) or "none declared"
    classes = f"Card classes in the table: {labels}."
    if args.vram:
        print(
            f"Models that fit {args.vram:g} GB with working headroom. "
            f"{ESTIMATES_NOTICE} {classes}\n"
        )
    else:
        print(f"Shipped models. {ESTIMATES_NOTICE} {classes}\n")

    for model in models:
        backend = f" [{model.requires_backend} only]" if model.requires_backend else ""
        kept_out = "  not in a fit listing" if model.not_for_fit is not None else ""
        print(f"  {model.id:<28} {model.vram_gb_working:>5.1f} GB{backend}{kept_out}")

    if table.caveats:
        print("\nHarness caveats (ways a naive reading or benchmark run goes wrong):")
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
    print("Units:")
    for unit in config.units.values():
        credential = (
            f"key from ${unit.api_key_env}" if unit.api_key_env else "no credential"
        )
        engine = unit.engine or "llama.cpp"
        print(
            f"  {unit.name:<16} {engine:<9} {unit.address:<32} "
            f"x{unit.width or 1}  ({credential})"
        )

    print("\nLadder, in ladder order:")
    for name in config.ladder.names:
        print(f"  {name:<16} {config.units[name].model:<32}")

    if config.is_local_only:
        print(
            "\nNo rung needs a credential: this install needs no API key, and the "
            "deterministic gate is its acceptance bar."
        )
    return 0


def _local_pool(args: argparse.Namespace) -> int:
    from mcgyvr.decision import JEV_ROLE
    from mcgyvr.escalate import Ceiling
    from mcgyvr.local_pool import SourceUnavailableError, source_map
    from mcgyvr.route import draws_for, family_of

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
    # The family, the attempt budget and the breadth are shown because they
    # are the routing decision (#24), and a decision nobody can read is one
    # nobody can check.
    # A family is a cost class rather than a location, so printing it says how
    # dear a rung is to ask without saying which machine answers.
    #
    # The rungs are listed in the order the ladder names them, which is the
    # order work climbs them. That is cheapest first only when the ladder was
    # written so, and the header says the order the list is in, not the one a
    # ladder usually has.
    print(f"{config.path}: {len(pool)} usable rung(s), in ladder order:\n")
    ladder_budget = 0
    for rung in pool.rungs:
        budget = int((config.get("attempts") or {}).get(rung.name, 1))
        ladder_budget += budget
        tries = "1 attempt" if budget == 1 else f"{budget} attempts"
        # The breadth is a routing decision too, shown only where it is not
        # the default, so an unconfigured install's line is unchanged.
        draws = draws_for(config, rung.name)
        if draws > 1:
            tries += f", {draws} draws"
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
            "max_attempts"
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

    # Relief rungs (relief.yaml) are other people's units: printed apart from
    # the ladder because they are never a step of it. `position` is where the
    # hub judged the host's model against yours, and it places nothing.
    if pool.relief or pool.relief_skipped:
        print(
            f"\nRelief rungs (hitchhike), {len(pool.relief)} usable: taken under "
            f"`fanout: idle` only when your own rung is full, never climbed to. "
            f"Each host can read the prompts sent to it."
        )
        for rung in pool.relief:
            lent = config.relief[rung.name]
            host = f", hosted by {lent.hosted_by}" if lent.hosted_by else ""
            print(
                f"  {rung.name:<20} {lent.position or '':<14} "
                f"x{lent.width or 1}  {lent.served_model or rung.model}{host}"
            )
        for skip in pool.relief_skipped:
            print(f"  {skip.name:<20} skipped\n      ↳ {skip.reason}")

    for role in ("orchestrator", "verifier", JEV_ROLE):
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
    from mcgyvr.escalate import how_judged

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
        kind = book.get(args.name) or book.operation(args.name)
        if kind is None:
            try:
                book.require(args.name)
            except CatalogError as exc:
                operations = ", ".join(op.name for op in book.operations)
                print(
                    f"error: {exc} Deterministic operations (`task_type: code` "
                    f"with `operation:`): {operations}",
                    file=sys.stderr,
                )
            return 1
        if kind.task_type:
            print(
                f"{kind.name}  [operation of `{kind.task_type}`, starts on "
                f"{kind.starts_on.name}]\n"
            )
            print(
                f"  Ask for it with `task_type: {kind.task_type}` and "
                f"`operation: {kind.name}`.\n"
            )
        else:
            print(f"{kind.name}  [starts on {kind.starts_on.name}]\n")
        print(f"  {kind.doc}\n")
        print(f"  guarantee:  {kind.guarantee}\n")
        print(f"  warrant:    {kind.warrant}\n")
        print(f"  judged:     {how_judged(kind)}\n")
        if kind.session:
            print(
                "  session:    no target and no scope; the reply is returned in "
                "the result file's `answer` and kept in the session log "
                "(`mcgyvr sessions`), never written to the tree.\n"
            )
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

    print(
        "Deterministic operations (not task types: a tool does the work, never a "
        "model; ask for one with `task_type: code` and `operation: <name>`):\n"
    )
    for op in book.operations:
        print(f"  {op.name:<24} {op.starts_on.name:<14}")
        print(f"      {op.guarantee}")
        print(f"      evidence: {', '.join(op.evidence_names)}\n")

    if config is not None:
        if unservable:
            # Naming them is the point: a count would tell a caller there is a
            # problem without telling them which task to stop asking for.
            print(f"{len(unservable)} type(s) this ladder cannot start:")
            for name in sorted(unservable):
                print(f"  {name}")
        else:
            print(f"Every type is servable by the ladder in {config.path}.")
    return 0


def _contract(args: argparse.Namespace) -> int:
    import json

    from mcgyvr.contract import ContractError, load
    from mcgyvr.escalate import how_judged

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
    operation = f", operation {contract.operation}" if contract.operation else ""
    print(f"  {contract.id}  [{contract.task_type}{operation}] — {tier}")
    if contract.is_session:
        # A session writes nothing, so there is no file to name: a target or
        # scope line here would say the opposite of what the run does.
        print(
            "  session: the reply is returned in the result file's `answer` and "
            "kept in the session log (<journal.dir>/sessions/); nothing is "
            "written to the repository"
        )
        if contract.target or contract.scope.allow:
            given = contract.target or ", ".join(contract.scope.allow)
            print(f"  note:    {given} is not written: target and scope are not used")
    else:
        print(f"  target:  {contract.target}")
        print(f"  allow:   {', '.join(contract.scope.allow)}")
        if contract.scope.forbid:
            print(f"  forbid:  {', '.join(contract.scope.forbid)}")
    if contract.deps:
        print(f"  deps:    {', '.join(d.path for d in contract.deps)}")
    if contract.stop_conditions:
        print(f"  stops:   {len(contract.stop_conditions)} condition(s)")
    # A reply (chat, agent, media) is never gated as a change or reviewed:
    # it is judged by its output checks or by nothing, in the words its result
    # will use (`how_judged`), and its acceptance commands never judge it.
    reply = not contract.is_deterministic and not contract.kind.judges_a_change
    if reply:
        print(f"  risk:    {contract.risk}")
        print(f"  judged:  {how_judged(contract.kind)}")
    else:
        print(
            f"  risk:    {contract.risk} — verified by "
            f"{contract.verification.policy.replace('_', ' ')}"
        )
    # The cap model is decided by task type (owner, 2026-10-14), and this line
    # says which rule the contract is under. A deterministic operation calls
    # no model, so it has no reply to cap and no model attempts to count, and
    # prints no line at all.
    if contract.is_session:
        print(
            f"  limits:  raw connection: no output cap, no prompt checks, "
            f"{contract.limits.attempts} attempt(s)"
        )
    elif not contract.is_deterministic:
        if contract.limits.max_output_tokens is not None:
            output_budget = f"<={contract.limits.max_output_tokens} output tokens"
        elif contract.needs_output_cap:
            # Valid, and never sent as it stands: the run refuses a
            # model-written contract with no cap before any model is called,
            # so say so here, where refusing costs nothing.
            output_budget = (
                "no output cap stated — `mcgyvr run` refuses it until "
                "`limits.max_output_tokens` is stated"
            )
        else:
            output_budget = "uncapped (raw text)"
        print(
            f"  limits:  {output_budget}, "
            f"<={contract.max_input_tokens} prompt tokens, "
            f"{contract.limits.attempts} attempt(s)"
        )
    if reply:
        if contract.acceptance:
            print(
                "  acceptance: not run on the reply — a reply is judged by its "
                "output checks alone"
            )
    elif contract.acceptance:
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
            print(f"  {gpu.name} — {gpu.size}  ({gpu.how})")
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
                protocol = f"api={backend.api}"
                print(f"{indent}{backend.name:<20} {backend.base_url:<30} {protocol}")
                if backend.models:
                    for model in backend.models:
                        print(f"{indent}    listed: {model}")
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
    from mcgyvr.sandbox.base import SandboxError, choose_mode
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
    _say_what_the_sandbox_leaves_out(repo)

    # Show what a run here would resolve to: the setup's `sandbox.mode` and
    # `sandbox.allow_fallback`, read as a run reads them. No setup at all is
    # the schema's defaults (`docker`, no fallback); a setup that cannot be
    # read has no resolved mode to show.
    chosen = Path(args.config) if getattr(args, "config", None) else None
    try:
        config: Config | None = load_config(chosen)
    except ConfigMissingError as exc:
        if chosen is not None:
            # Named with --config and not there: an error, as on `run`, not
            # the defaults a bare install reads.
            print(f"error: {exc}", file=sys.stderr)
            return 1
        config = None
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    configured = (
        config.get("sandbox.mode") if config is not None else None
    ) or "docker"
    try:
        choice = choose_mode(
            configured,
            docker_ok,
            allow_fallback=_sandbox_policy(config)["allow_fallback"],
        )
    except SandboxError as refused:
        print(f"Sandbox mode: refused  ({docker_how})")
        print(f"  - {refused}")
    else:
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


def _reads_the_tree(contract: Contract) -> bool:
    """Whether a run of ``contract`` reads anything off the repository's HEAD.

    The note :func:`_say_what_the_sandbox_leaves_out` prints is about what a
    sandbox of HEAD holds, so it is worth reading only to a run that looks in
    it. Every run that writes a change does. A session (``chat``, ``agent``)
    writes nothing and has no target: it reads the tree only through the
    ``sources`` it names and the commands it declares. One with neither — a
    plain ``chat`` — reads nothing there, and telling it to commit files it
    never opens is noise (e2e run 3, T4). An ``agent``'s sources are read off
    HEAD, so it is told. Read off the contract and the catalog's ``session``
    flag, never a task type's name, which no consumer of the vocabulary
    spells.
    """
    if not contract.is_session:
        return True
    return bool(contract.sources or contract.acceptance or contract.demonstration)


def _say_what_the_sandbox_leaves_out(repo: Path) -> list[str]:
    """Say on stderr what a sandbox of ``repo``'s HEAD will not hold.

    Returns the note as a one-item list, or an empty one when there is
    nothing to say, for a run to carry into its result file as well.
    """
    from mcgyvr.orchestrator import head_only_note

    note = head_only_note(repo)
    if note is None:
        return []
    print(f"note: {note}", file=sys.stderr)
    return [note]


def _mib(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f} MiB"


#: Said by every deprecated ``--profile`` warning: the word also names the
#: config's ``profile: live|dev``, which is a different setting and stays.
_NOT_THE_CONFIG_PROFILE = (
    "(this is not the config's `profile: live|dev`, a different setting that stays)"
)


def _setup_priority(args: argparse.Namespace) -> str | None:
    """The priority ``setup`` composes for, reading the old ``--profile``.

    ``--profile`` is deprecated: a word naming a priority maps onto it, any
    other text is ignored, and ``--priority`` wins when both are given. Each
    case says so on stderr, and that the config's ``profile`` is another thing.
    """
    priority: str | None = args.priority
    if args.profile is None:
        return priority
    head = (
        "warning: `mcgyvr setup --profile` is deprecated and will be removed "
        "in the release after next"
    )
    word = str(args.profile).strip().lower()
    names = "|".join(PRIORITIES)
    if priority is not None:
        print(
            f"{head}; --profile {args.profile!r} is ignored because "
            f"`--priority {priority}` was given {_NOT_THE_CONFIG_PROFILE}",
            file=sys.stderr,
        )
        return priority
    if word in PRIORITIES:
        print(
            f"{head}; use `--priority {word}` {_NOT_THE_CONFIG_PROFILE}",
            file=sys.stderr,
        )
        return word
    print(
        f"{head}; --profile {args.profile!r} names no priority ({names}), so it "
        f"is ignored and the default ladder is written {_NOT_THE_CONFIG_PROFILE}",
        file=sys.stderr,
    )
    return None


class _SetupInteractiveError(Exception):
    """The interactive wizard stopped; the message says why."""


def _stdin_isatty() -> bool:
    """Whether setup's stdin is a terminal, as a seam a test can state."""
    return sys.stdin.isatty()


def _setup_is_interactive(args: argparse.Namespace) -> bool:
    """Whether ``mcgyvr setup`` should prompt rather than write from flags.

    Interactive only with a person at the keyboard and no flag already given:
    any flag names a decision already made, and a pipe is an agent driving the
    command.
    """
    if not _stdin_isatty():
        return False
    return not (
        bool(args.host)
        or bool(args.api)
        or args.force
        or args.priority is not None
        or args.profile is not None
        or args.use_case is not None
        or args.deployment is not None
        or args.jev is not None
        or args.mcorch is not None
        or args.window is not None
        or args.session_sandbox is not None
    )


def _parse_setup_rigs(answer: str) -> tuple[str, ...]:
    """Rigs from one prompt answer: comma/space list, with ``--host`` stripped."""
    rigs: list[str] = []
    for token in answer.replace(",", " ").split():
        if token == "--host":
            continue
        if token.startswith("--host="):
            token = token.split("=", 1)[1]
        elif token.startswith("--"):
            continue
        if token:
            rigs.append(token)
    return tuple(dict.fromkeys(rigs))


def _ask_setup_rigs(prompt: Callable[[str], str] = input) -> tuple[str, ...]:
    """Step 1: which rigs serve this setup, defaulting to this machine."""
    answer = prompt("Which rig(s) should serve this setup? [this machine only] ")
    return _parse_setup_rigs(answer) or ("localhost",)


def _confirm(question: str, prompt: Callable[[str], str] = input) -> bool:
    """An explicit yes to one irreversible step; anything else is no."""
    return str(prompt(question)).strip().lower() in {"y", "yes"}


def _setup_scan_rigs(rigs: Sequence[str]) -> dict[str, Scan]:
    """Step 2: measure each rig and record it, so ``emit`` can size from it."""
    from mcgyvr.detect import is_local_host

    scans: dict[str, Scan] = {}
    for rig in dict.fromkeys(rigs):
        if is_local_host(rig):
            measured = scan_module.scan()
        else:
            try:
                measured = scan_module.scan_over(scan_module.Reach.ssh(rig))
            except (
                scan_module.Unreachable,
                scan_module.ScannerMissing,
                scan_module.ScanFailed,
            ) as exc:
                raise _SetupInteractiveError(f"{rig}: {exc}") from exc
        scan_module.write_scan(measured, scan_module.default_root())
        scans[rig] = measured
    return scans


def _setup_placements(
    rigs: Sequence[str], scans: Mapping[str, Scan]
) -> dict[str, Mapping[str, Any]]:
    """Step 3: one coding/single placement per rig, printed as JSON."""
    plans: dict[str, Mapping[str, Any]] = {}
    for rig in dict.fromkeys(rigs):
        try:
            plan = recommend_module.plan(
                profile="coding",
                users=1,
                hosts=(rig,),
                premeasured={rig: scans[rig]},
            )
        except (recommend_module.RecommendError, recommend_module.CatalogError) as exc:
            raise _SetupInteractiveError(f"{rig}: {exc}") from exc
        sys.stdout.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        if not isinstance(plan.get("placement"), Mapping):
            raise _SetupInteractiveError(
                f"{rig}: recommend produced no placement to serve"
            )
        plans[rig] = plan
    return plans


def _setup_on_disk_match(
    scan: Scan | None, model_id: str, quant: str, size_bytes: int
) -> ModelOnDisk | None:
    """The first model already on the rig's disk matching id + quant + size.

    The scan collected the rig's own inventory, so this holds for a remote rig
    (its weights live on the rig, not on the machine running ``setup``). The id
    is matched by its last segment, its canonical local name, or the id itself
    — a GGUF's name carries no org — and the size only when it is known (a size
    of 0 is not known). The quant is enforced only when the file tags one: the
    canonical local name omits the quant, so an untagged GGUF (quant ``None``)
    is reused on the strength of its name and size rather than refused for a
    quant the file name does not state.
    """
    if scan is None:
        return None
    basename = model_id.lower().rsplit("/", 1)[-1]
    canonical = model_id.replace("/", "_").lower()
    wanted_quant = (quant or "").lower()
    for model in scan.models_on_disk:
        if model.name.lower() not in (basename, model_id.lower(), canonical):
            continue
        if model.quant is not None and model.quant.lower() != wanted_quant:
            continue
        if size_bytes and model.size_bytes != size_bytes:
            continue
        return model
    return None


def _setup_downloads(
    plans: Mapping[str, Mapping[str, Any]],
    scans: Mapping[str, Scan],
    prompt: Callable[[str], str] = input,
) -> tuple[tuple[str, ModelRecord], ...]:
    """Step 4: ask reuse or download for every placement, gated on the answer."""
    from mcgyvr.knowledge import store as knowledge_store

    known = {record.key: record for record in knowledge_store.offline().records}
    downloads: list[tuple[str, ModelRecord]] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        model_id = str(placement.get("model_id") or "")
        if not model_id:
            # A local-store pick is already on disk; nothing is downloaded.
            continue
        quant = str(placement.get("quant") or "")
        size_bytes = int(placement.get("size_bytes") or 0)
        scan = scans.get(rig)
        hit = _setup_on_disk_match(scan, model_id, quant, size_bytes)
        if hit is not None:
            answer = prompt(
                f"{rig}: {model_id} {quant} ({hit.size_bytes} bytes) is already "
                f"on disk. Reuse it instead of downloading? [Y/n] "
            )
            if str(answer).strip().lower() not in {"n", "no"}:
                print(f"{rig}: reusing {model_id} {quant} already on disk")
                continue
            chosen = True
        else:
            answer = prompt(
                f"Download {model_id}{' ' + quant if quant else ''} for {rig}? [y/N] "
            )
            chosen = str(answer).strip().lower() in {"y", "yes"}
        if not chosen:
            continue
        record = known.get((model_id, quant))
        if record is None or record.weights is None:
            raise _SetupInteractiveError(
                f"{model_id} {quant}: no download record is known for this model"
            )
        downloads.append((rig, record))
    return tuple(downloads)


def _setup_suffix() -> str:
    """A RUN_ID suffix unique to this setup step (gate 5 claims the id)."""
    import os
    import time

    return f"setup-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


def _setup_fetch(rig: str, record: ModelRecord, path: Path) -> None:
    """Step 5: download one chosen model through the door's ``serve fetch``."""
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import fetchlist, safe_host
    from mcgyvr.serving.gatelib import DOOR_MODULE

    wants = fetchlist.from_records([record])
    path.mkdir(parents=True, exist_ok=True)
    fetch_file = path / f"fetch-{safe_host(rig)}.json"
    fetch_file.write_text(fetchlist.dump(wants), encoding="utf-8")
    code = wakelib.spawn_door(
        [
            sys.executable,
            "-m",
            DOOR_MODULE,
            "serve",
            "fetch",
            "--host",
            rig,
            "--weights",
            str(fetch_file),
            "--suffix",
            _setup_suffix(),
        ]
    )
    if code != 0:
        raise _SetupInteractiveError(f"{rig}: serve fetch exited {code}")
    print(f"{rig}: fetched {record.model_id} {record.quant}")


def _setup_synthetic_detection(
    plans: Mapping[str, Mapping[str, Any]],
) -> Detection:
    """The recommended servers as if they were already answering.

    ``initialize`` binds only models a running server lists, so the wizard
    writes a bootstrap config from this synthetic detection, emits the launch
    specs for it, starts the containers, and then re-runs ``initialize`` over
    the real servers.
    """
    from mcgyvr.detect import Backend, Detection
    from mcgyvr.serving import DEFAULT_PORT

    backends: list[Backend] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        model_id = str(placement.get("model_id") or "")
        if not model_id:
            raise _SetupInteractiveError(
                f"{rig}: its placement is a local checkpoint, and the wizard "
                "does not bootstrap from a local store yet"
            )
        engine = str(placement.get("engine") or "llama.cpp")
        kind = "vllm" if engine == "vllm" else "llama-server"
        port = 8000 if engine == "vllm" else DEFAULT_PORT
        name = f"{rig}_{kind}" if len(plans) > 1 else kind
        backends.append(
            Backend(
                name=name,
                base_url=f"http://{rig}:{port}/v1",
                api="openai",
                models=(model_id,),
                how="interactive setup",
                host=rig,
                kind=kind,
            )
        )
    return Detection(
        backends=tuple(backends), provenance={"backends": "interactive setup"}
    )


def _setup_context_window(plans: Mapping[str, Mapping[str, Any]]) -> int:
    """The window ``emit`` sizes the bootstrap config at, across the rigs.

    Each placement was priced at its own ``context_length``; the window handed
    to ``emit`` is the smallest of them, the one every placed model fits at.
    A placement without a readable window is refused, never guessed.
    """
    windows: list[int] = []
    for rig, plan in plans.items():
        placement = plan["placement"]
        ctx = placement.get("context_length")
        if not isinstance(ctx, int) or isinstance(ctx, bool) or ctx <= 0:
            raise _SetupInteractiveError(
                f"{rig}: its placement declares no context window to size at"
            )
        windows.append(ctx)
    return min(windows)


def _setup_emit(path: Path, ctx_per_slot: int) -> None:
    """Step 6a: ``mcgyvr emit`` the launch specs for the bootstrap config."""
    code = main(
        [
            "emit",
            "--config",
            str(path),
            "--out",
            str(path),
            "--ctx-per-slot",
            str(ctx_per_slot),
        ]
    )
    if code != 0:
        raise _SetupInteractiveError(f"mcgyvr emit exited {code}")


def _setup_start(rigs: Sequence[str], scans: Mapping[str, Scan], path: Path) -> None:
    """Step 6b: start each emitted launch spec through the door's ``serve up``."""
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import spec_files, spec_name

    for rig in dict.fromkeys(rigs):
        scan = scans[rig]
        host = scan.machine.host
        try:
            whole = path / spec_name(host)
        except UnitError as exc:
            raise _SetupInteractiveError(f"{rig}: {exc}") from exc
        if whole.is_file():
            compose = whole
        else:
            files = spec_files(path, host)
            if not files:
                # The product holds one unit per model: two rigs asked to
                # serve the same model collapse to one backend, and the rig
                # left out gets no launch spec. That is expected, not an
                # emit failure, so skip it rather than abort the whole
                # ``serve up``.
                print(
                    f"{rig}: no launch spec was emitted for {host} — its model "
                    "is served from another rig (one unit per model); leaving "
                    "it idle"
                )
                continue
            if len(files) > 1:
                raise _SetupInteractiveError(
                    f"{rig}: mcgyvr emit wrote alternatives for {host}; "
                    "start one by hand"
                )
            compose = files[0]
        code = wakelib.spawn_door(
            wakelib.door_argv(
                direction="up", host=rig, compose=compose, suffix=_setup_suffix()
            ),
            env={
                **os.environ,
                # The config directory, not its fleet.yaml: the loader reads
                # both fleet.yaml and policy.yaml (the ladder) from it.
                CONFIG_PATH_ENV: str(path),
            },
        )
        if code != 0:
            raise _SetupInteractiveError(f"{rig}: serve up exited {code}")


def _setup_interactive(path: Path) -> int:
    """The guided ``mcgyvr setup``: prompt, then perform each step."""
    try:
        rigs = _ask_setup_rigs()
        print(f"Serving on: {', '.join(rigs)}")
        scans = _setup_scan_rigs(rigs)
        plans = _setup_placements(rigs, scans)
        ctx_per_slot = _setup_context_window(plans)
        downloads = _setup_downloads(plans, scans)
        for rig, record in downloads:
            _setup_fetch(rig, record, path)

        synthetic = _setup_synthetic_detection(plans)
        bootstrap = initialize(
            path, force=True, detection=synthetic, use_case="coding", profile="dev"
        )
        if not bootstrap.written:
            raise _SetupInteractiveError("the bootstrap setup was not written")
        print(f"Wrote bootstrap setup at {bootstrap.path}\n")

        _setup_emit(path, ctx_per_slot)
        if _confirm(f"Start the serving containers on {', '.join(rigs)}? [y/N] "):
            _setup_start(rigs, scans, path)
        else:
            print(
                "Containers were not started. The bootstrap setup and launch "
                "specs are written; start the containers, then re-run "
                "`mcgyvr setup --force` to bind and lock them."
            )
            return 0

        final = initialize(
            path, force=True, hosts=tuple(rigs), use_case="coding", profile="dev"
        )
        if not final.written:
            raise _SetupInteractiveError("the running setup was not written")
        print(f"Wrote {final.path} bound to the running servers\n")

        # The final init rewrote fleet.yaml from the running servers and so
        # dropped the launch the bootstrap emit stamped. Re-emit here so the
        # fleet that is about to be locked carries the resolved launch; the
        # compose rewrite is idempotent and the stamp is what matters.
        _setup_emit(path, ctx_per_slot)

        if _confirm("Lock the fleet and name it live? [y/N] "):
            approved, unapproved = _own_fleet_live(path)
        else:
            approved, unapproved = (), ("The fleet was not locked or made live.",)
        decisions = final.decisions + approved
        if decisions:
            print("What was decided, and why:")
            for decision in decisions:
                print(f"  - {decision}")
            print()
        limits = final.limits + unapproved
        if limits:
            print("What is NOT configured, and what that costs:")
            for limit in limits:
                print(f"  - {limit}")
        return 0
    except _SetupInteractiveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except InitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, CapabilityTableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _setup(args: argparse.Namespace) -> int:
    # Not the config resolution order: with a fleet named live, that ends in a
    # promoted folder, and a promoted folder is never written in place.
    path = Path(args.path) if args.path else (named_config_path() or Path.cwd())
    if _setup_is_interactive(args):
        return _setup_interactive(path)
    # Parsed before anything is detected: a mistyped `--api` is the operator's
    # to fix, and making them wait out a network sweep to hear about it is
    # spending their time to tell them something already known.
    try:
        api_units = tuple(parse_api_unit(spec) for spec in (args.api or ()))
    except ApiSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    priority = _setup_priority(args)
    try:
        result = initialize(
            path,
            force=args.force,
            hosts=tuple(args.host or ()),
            api_units=api_units,
            priority=priority,
            use_case=args.use_case or "coding",
            deployment=args.deployment,
            jev=args.jev,
            mcorch=args.mcorch,
            window=args.window,
            session_sandbox=args.session_sandbox,
        )
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

    # What setup wrote is the user's own fleet; approving it is what lets a
    # fresh `profile: live` setup run. A setup run that did not write is not one
    # it bound, so it approves nothing.
    approved, unapproved = _own_fleet_live(result.path) if result.written else ((), ())
    decisions = result.decisions + approved
    if decisions:
        print("What was decided, and why:")
        for decision in decisions:
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

    limits = result.limits + unapproved
    if limits:
        print("What is NOT configured, and what that costs:")
        for limit in limits:
            print(f"  - {limit}")
    return 0


def _own_fleet_live(setup: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Approve the setup ``setup`` wrote at ``setup`` as the user's own fleet and
    name it live; ``(decisions, limits)`` saying what was done, or why not.

    Through the path every live fleet takes: a folder under the config folder
    (:func:`mcgyvr.fleet.promote.approve_own`), named by ``live.json``
    (:func:`mcgyvr.fleet.promote.use`), and admitted as any live fleet is. With
    init's own fleet already live, a new folder is approved and named in its
    place, and the old one is kept. Any other live fleet is never replaced
    (``mcgyvr fleet use`` switches), and a machine of the user's is not
    approved: it is approved only by a read of it. Every rig the setup lays a
    unit on is read first — the local machine without ssh, a remote one over
    ssh — and only then is the fleet approved with each of them laid out.
    """
    from mcgyvr.fleet.promote import (
        PromoteRefusedError,
        approve_own,
        approve_own_rigs,
        is_own,
        use,
    )
    from mcgyvr.fleet.roots import LiveFleetError, live_fleet

    refused = (
        "A live run is refused until a fleet is live (`mcgyvr fleet use`); "
        "`profile: dev` runs without live admission."
    )
    try:
        current = live_fleet()
    except LiveFleetError as exc:
        return (), (f"No fleet was made live: {exc}. {refused}",)
    if current is not None and not is_own(current):
        return (
            f"{current} is live, and stays so: your own fleet was not approved "
            "over it (`mcgyvr fleet use` switches).",
        ), ()
    rigs = _rigs(setup)
    try:
        if not rigs:
            folder = approve_own(setup)
        else:
            rig_ids = {
                rig: _read_local_rig(rig)
                if rig == "localhost"
                else _read_remote_rig(rig)
                for rig in rigs
            }
            folder = approve_own_rigs(setup, rigs=rig_ids)
        switch = use(folder.name)
    except PromoteRefusedError as exc:
        if current is None:
            return (), (f"No fleet was made live: {exc}. {refused}",)
        return (), (
            f"Your own fleet was not approved again: {exc}. {current}, approved "
            "before, stays live, and a run that dispatches to an unapproved "
            "machine is refused.",
        )
    if rigs:
        where = (
            ". Its rig units sit on "
            + ", ".join(rigs)
            + ", laid out and approved by a read of each."
        )
    else:
        where = (
            ". Every unit in it is hosted, so it lays out no rig and live "
            "admission reads none."
        )
    return (
        f"Approved your own fleet for live runs: {folder}, named in "
        f"{switch.pointer}"
        + (f" in place of {current}" if current is not None else "")
        + where,
    ), ()


def _rigs(setup: Path) -> tuple[str, ...]:
    """The rigs the setup init wrote lays units on, in sorted order.

    A machine of the user's is approved only by a read of it: the local machine
    is read without ssh (:func:`_read_local_rig`), a remote one over ssh
    (:func:`_read_remote_rig`). A hosted unit lays out no rig, so it names none.
    """
    from mcgyvr.config import FLEET_FILENAME
    from mcgyvr.fleet.files import FleetFileError, load_fleet

    try:
        fleet = load_fleet((setup / FLEET_FILENAME).read_text(encoding="utf-8"))
    except (OSError, FleetFileError):
        return ()
    rigs = {
        str(body.get("rig"))
        for body in (fleet.get("units") or {}).values()
        if "rig" in body
    }
    return tuple(sorted(rigs))


def _read_local_rig(rig: str) -> str:
    """Read the local machine with the door's own readers, no ssh, and write its
    rig file; return the rig id the lock pins.

    The machine mcgyvr runs on is reached directly: the door's scanner
    (:mod:`mcgyvr.serving.rigscan`) for the rig file, and the door's snapshot
    reader (``rig-snapshot.sh``) for the rig id (:func:`mcgyvr.fleet.ids.rig_id`).
    Nothing here ssh's; a remote machine is read over ssh by
    :func:`_read_remote_rig`.
    """
    import json
    import subprocess

    from mcgyvr import scan as scan_module
    from mcgyvr.fleet import ids
    from mcgyvr.fleet.promote import PromoteRefusedError
    from mcgyvr.fleet.read import ReadError
    from mcgyvr.fleet.read import parse as parse_reading
    from mcgyvr.serving import rigfile, rigscan
    from mcgyvr.serving.run import GATE_SCRIPTS

    # The door's own scanner, run locally: the same copy the door ships to a
    # remote rig, so the rig file this writes reads the same when the door
    # re-reads it.
    measured = scan_module.Scan.from_json(json.dumps(rigscan.scan()))
    try:
        done = subprocess.run(
            ["bash", str(GATE_SCRIPTS / "rig-snapshot.sh")],
            capture_output=True,
            text=True,
            check=False,
            timeout=60.0,
        )
    except subprocess.TimeoutExpired as exc:
        raise PromoteRefusedError(f"{rig}: the local snapshot timed out") from exc
    except OSError as exc:
        raise PromoteRefusedError(
            f"{rig}: the local snapshot could not start: {exc}"
        ) from exc
    if done.returncode != 0:
        raise PromoteRefusedError(
            f"{rig}: the local snapshot could not run: "
            f"{done.stderr.strip()[:300] or '(no stderr)'}"
        )
    try:
        snapshot = parse_reading(done.stdout).snapshot
    except ReadError as exc:
        raise PromoteRefusedError(f"{rig}: {exc}") from exc
    try:
        rig_id = ids.rig_id(snapshot)
    except ValueError as exc:
        raise PromoteRefusedError(f"{rig}: {exc}") from exc
    # Both readers succeeded before anything is written: a refusal leaves the
    # rig-folder untouched. A rig file that will not write is a refusal, not a
    # traceback: the fleet is not approved for lack of a read's record.
    try:
        rigfile.write(rigfile.from_scan(rig, measured))
    except (OSError, rigfile.RigFileError) as exc:
        raise PromoteRefusedError(
            f"{rig}: its rig file could not be written: {exc}"
        ) from exc
    return rig_id


def _read_remote_rig(rig: str) -> str:
    """Read ``rig``'s snapshot over the sanctioned read-only ssh line and
    return the rig id the lock pins.

    The wizard runs outside the door, so the door-gated ssh
    (:func:`mcgyvr.serving.gatelib.ssh`) is not usable here; the one sanctioned
    read of a remote rig from outside is
    :func:`mcgyvr.serving.gatelib.ssh_read_only`, which ships the door's own
    ``rig-snapshot.sh`` as one read-only line
    (``echo <base64> | base64 -d | bash -s``) and prints the reader's
    ``key=value`` snapshot. A rig that cannot be read is a refusal, not a
    traceback, and nothing here writes a rig file: the door's ``serve up``
    gate 2 already filed the rig file during the wizard.
    """
    import subprocess

    from mcgyvr.fleet import ids
    from mcgyvr.fleet.promote import PromoteRefusedError
    from mcgyvr.fleet.read import ReadError
    from mcgyvr.fleet.read import parse as parse_reading
    from mcgyvr.serving import gatelib

    command = gatelib.rig_snapshot_read_command()
    try:
        done = gatelib.ssh_read_only(rig, command)
    except subprocess.TimeoutExpired as exc:
        raise PromoteRefusedError(f"{rig}: the remote snapshot timed out") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise PromoteRefusedError(
            f"{rig}: the remote snapshot could not start: {exc}"
        ) from exc
    if done.returncode != 0:
        raise PromoteRefusedError(
            f"{rig}: the remote snapshot could not run: "
            f"{done.stderr.strip()[:300] or '(no stderr)'}"
        )
    try:
        snapshot = parse_reading(done.stdout).snapshot
    except ReadError as exc:
        raise PromoteRefusedError(f"{rig}: {exc}") from exc
    try:
        rig_id = ids.rig_id(snapshot)
    except ValueError as exc:
        raise PromoteRefusedError(f"{rig}: {exc}") from exc
    return rig_id


def _attach(args: argparse.Namespace) -> int:
    from mcgyvr.orchestrator import AttachError, attach

    into = Path(args.into) if args.into else None
    try:
        with attach(args.repo, into=into) as repo:
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
            # The signature is what a contract would carry as a dep, so
            # showing it here is how a reviewer checks the text against the
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


def _read_document(
    query: str, root: Path, index: Any, resolution: Any, plan: Any
) -> dict[str, Any]:
    """The `read --json` document: shortlist, reads, and every such file's text.

    The texts come from the index the command built, not from a second read
    of the disk, so the document is the index: a server that assembles one
    from it (:mod:`mcgyvr.mcorch.evidence`) holds what this command held.
    ``located`` is the adapters' checker lookup, made here because only here
    is the repository on disk.
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
        # The checker each language adapter locates here, where the repository
        # is: the one lookup a server reading this document cannot make itself.
        "located": locate_checkers(root),
    }


def _delegate(args: argparse.Namespace) -> int:
    """Turn a prompt plus a repository into validated contracts.

    The delegated-mode half of the product, and the first real caller of
    :func:`~mcgyvr.orchestrator.decompose.decompose`'s ``propose`` seam. This
    command attaches and indexes the repository, and ``decompose`` runs the
    rest of the deterministic pass (resolve → read) internally; this command
    also adds the one ingredient ``decompose`` does not bind itself: the
    orchestrator role, resolved through :func:`~mcgyvr.delegate.proposer_for`
    and dispatched below the pool seam by :func:`~mcgyvr.runner.dispatch_role`.

    A keyless install has no orchestrator role, and that is an ordinary,
    documented answer (:data:`~mcgyvr.delegate.NO_ORCHESTRATOR_ROLE`, exit
    ``REFUSED``) rather than a traceback. With a role bound, the emitted
    contracts are printed or written to ``--output``, and ``--run`` drives
    each of them through the existing ``run`` machinery.
    """

    from mcgyvr.config import ConfigError, ConfigMissingError, named_config_path
    from mcgyvr.delegate import NO_ORCHESTRATOR_ROLE, DelegationError
    from mcgyvr.exits import Exit
    from mcgyvr.local_pool import SourceUnavailableError, source_map
    from mcgyvr.orchestrator import (
        AttachError,
        IndexBuildError,
        attach,
        build_index,
        decompose,
    )
    from mcgyvr.runner import RunnerError

    chosen = Path(args.config) if args.config else None
    named = chosen if chosen is not None else named_config_path()
    config: Config | None = None
    config_error: ConfigError | None = None
    try:
        config = load_config(chosen)
    except ConfigMissingError as exc:
        config_error = exc
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # A default location with nothing in it is the supported bare install; a
    # path somebody typed is not (the same distinction ``_run`` draws). Both
    # leave ``config`` unset, and the bare one is answered as "no orchestrator
    # role" because there is nowhere to bind one.
    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config is None and not bare_install:
        print(f"error: {config_error}", file=sys.stderr)
        return 1
    if config is None:
        print(NO_ORCHESTRATOR_ROLE, file=sys.stderr)
        return Exit.REFUSED

    pool = source_map(config)
    try:
        propose = _proposer_for_delegate(config, pool)
    except SourceUnavailableError as exc:
        print(
            f"error: the orchestrator role is declared but cannot run: {exc}. "
            f"Bind `orchestrator.unit` to a usable unit, or author contracts "
            f"yourself and run them with `mcgyvr run`.",
            file=sys.stderr,
        )
        return 1
    if propose is None:
        print(NO_ORCHESTRATOR_ROLE, file=sys.stderr)
        return Exit.REFUSED

    into = Path(args.into) if args.into else None
    try:
        with attach(args.repo, into=into) as repo:
            # Before the read: the baseline below is observed in the working
            # tree, and each drafted contract runs in a sandbox of HEAD, so on
            # a dirty tree the two can disagree.
            _say_what_the_sandbox_leaves_out(repo.root)
            index = build_index(repo.root)
            decomposition = decompose(
                index,
                args.prompt,
                propose=propose,
                config=config,
                budget=args.budget,
            )
            _report_decomposition(decomposition)
            written = _write_delegated(
                decomposition, Path(args.output) if args.output else None
            )
            if args.run:
                return _run_delegated(args, repo.root, decomposition, written)
            return 0
    except AttachError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (DelegationError, RunnerError, SourceUnavailableError) as exc:
        # The role was bound and could not be asked, or answered unreadably —
        # a reviewer-side fault, reported, never a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _proposer_for_delegate(config: Config, pool: SourceMap) -> Proposer | None:
    """The proposer ``mcgyvr delegate`` drafts with, by ``orchestrator.authoring``.

    ``classifier`` puts the typed proposer (the jev unit, or the orchestrator
    role when none is bound) first and the prose proposer behind it; anything
    else is the prose proposer alone, as before the field existed.
    """
    from mcgyvr.delegate import (
        classifier_proposer_for,
        proposer_by_authoring,
        proposer_for,
    )

    strategy = config.get("orchestrator.authoring")
    typed = classifier_proposer_for(pool) if strategy == "classifier" else None
    return proposer_by_authoring(
        None if not isinstance(strategy, str) else strategy,
        typed=typed,
        prose=proposer_for(pool),
    )


def _report_decomposition(dec: Decomposition) -> None:
    """One line per outcome, to stderr so stdout stays machine-readable."""
    if dec.contracts:
        print(f"{len(dec.contracts)} contract(s) proposed:", file=sys.stderr)
        for contract in dec.contracts:
            print(
                f"  {contract.id}  [{contract.task_type}] {contract.target}",
                file=sys.stderr,
            )
    else:
        print("No contracts were emitted.", file=sys.stderr)
    for refusal in dec.refusals:
        print(f"  refused: {refusal}", file=sys.stderr)


def _write_delegated(dec: Decomposition, output: Path | None) -> list[Path]:
    """Write each emitted contract to ``output``, or print them to stdout.

    Returns the files written, so ``--run`` can drive the same documents it
    showed the caller.
    """
    if output is None:
        for document in dec.documents:
            print(document)
        return []
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for contract, document in zip(dec.contracts, dec.documents, strict=True):
        path = output / f"{contract.id}.json"
        path.write_text(document + "\n", encoding="utf-8")
        written.append(path)
        print(f"wrote {path}", file=sys.stderr)
    return written


def _run_delegated(
    args: argparse.Namespace,
    repo: Path,
    dec: Decomposition,
    written: Sequence[Path],
) -> int:
    """Execute each emitted contract through the existing ``run`` machinery.

    Contracts that were only printed to stdout are staged into a temporary
    directory first; ``_run`` reads a contract from a path, and the same
    document must reach both the caller and the runner.
    """
    if not dec.contracts:
        return 0

    import shutil
    import tempfile

    from mcgyvr.session import SessionError, resolve

    paths = list(written)
    staging: Path | None = None
    if not paths:
        staging = Path(tempfile.mkdtemp(prefix="mcgyvr-delegate-"))
        for contract, document in zip(dec.contracts, dec.documents, strict=True):
            path = staging / f"{contract.id}.json"
            path.write_text(document + "\n", encoding="utf-8")
            paths.append(path)

    try:
        session = resolve(args.orchestrator)
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        return 1

    code = 0
    try:
        for path in paths:
            run = argparse.Namespace(
                contract=str(path),
                config=args.config,
                repo=str(repo),
                sandbox=args.sandbox,
                commit=args.commit,
                branch=args.branch,
                record=args.record,
                result=None,
                orchestrator=args.orchestrator,
                session=session,
            )
            result = _run(run)
            if result != 0:
                code = result
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    return code


def _run(args: argparse.Namespace) -> int:
    """Drive one contract to a gated verdict, and optionally to a commit.

    Committing is opt-in. A gate verdict costs the user a sandbox that is torn
    down either way, and a commit is a write to a repository they did not hand
    over for one — so ``--commit`` is what makes the difference, and its absence
    leaves the accepted change in the working tree and nothing else in the
    repository: no commit, no branch, no receipt.

    Two paths, chosen by the contract rather than by a flag. A deterministic
    contract names a program and is run here; anything else climbs a ladder and
    is :func:`_climb`'s. The split is the contract's catalog entry (its
    ``operation``'s, or its ``task_type``'s) because that is where the catalog
    already records which family work of this kind may
    *begin* on, and a flag that let a caller override it would be a second,
    quieter answer to the question ``starts_on`` exists to settle.

    **A tool step has three outcomes here, not two**
    (:class:`~mcgyvr.drive.ToolOutcome`): the program **could not run**
    (126/127, an environment issue — the work is still doable on a dearer
    family); the program **ran and did the
    job its type describes** (:attr:`~mcgyvr.drive.ToolOutcome.performed`, which
    is where any residue it reported goes on to the gate, because the gate is
    the thing that judges a result and stopping here means the result is never
    judged); and the program **ran and failed** (fatal — a fixer that could not
    load its config applied the guarantee to nothing, and the gate reading that
    same config is broken in the same way).

    The test is the exit code, against the set of codes that invocation reports
    under — the rule :func:`mcgyvr.gate.adapter.trusted_stdout` applies to the
    gate's own invocations. What the program said it will not fix is printed
    here.

    **Every run is journaled, in one place, and nothing a caller passes moves
    it.** The journal is mcgyvr's own record — ``<journal.dir>/<orchestrator>.jsonl``
    with the prompts and replies content-addressed under ``blobs/``, each
    run's result under ``results/`` and each ``chat`` or ``agent`` session
    under ``sessions/``. It exists to be *compounded*: how often the
    floor finishes a task type on its own, what a rung costs per accepted
    change, whether escalating paid are all questions about every run there has
    been, and they can only be asked where every run is. ``--record DIR`` is a
    complete second copy for the caller's own reading, and a copy that cannot
    be written is a line on stderr rather than the end of a run mcgyvr has
    already recorded. ``--result PATH`` is the same bargain for the result file: it
    says where the *caller* reads it, and ours keeps its own.

    **Both paths, not only the dispatching one.** A deterministic contract
    sends nothing to a model and is journaled all the same: how often the floor
    finishes a task type on its own cannot be computed from a table missing the
    floor's runs. The floor writes one row naming the program that did the
    work, with ``tier: deterministic`` beside it and no prompt, reply or token
    counts, because it made no dispatch and must not look as though it did.

    The orchestrator is the session that typed the command
    (:mod:`mcgyvr.session`), resolved in :func:`main` before anything here runs,
    so a row can be followed back to the conversation. The only thing printed
    about the result is its path: the caller reads a file, not the scrollback.
    """
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.contract import ContractError
    from mcgyvr.contract import load as load_task_contract
    from mcgyvr.drive import Recording, gate_adapters
    from mcgyvr.result import (
        RunResult,
        result_path,
        run_stamp,
        session_path,
        session_record,
        write,
        write_session,
    )
    from mcgyvr.session import with_mcorch_transcript
    from mcgyvr.telemetry import run_tags

    session: Session = args.session

    try:
        contract = load_task_contract(Path(args.contract))
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1
    # Warned, never refused: the sandbox is HEAD by design, and a dirty tree
    # only blocks delivery where the target itself is dirty. Said only where
    # the run reads the tree at all (e2e run 3, T4).
    notes = _say_what_the_sandbox_leaves_out(repo) if _reads_the_tree(contract) else []

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
        # `config_error` says `mcgyvr setup` and where the file would go, which
        # is the whole remedy for an operator who already knows what a config
        # is for. It is not the whole remedy for the reader this line actually
        # has: an agent following the skill, which names no setup verb and no
        # lever, onto a machine nobody has set up. So the message keeps the
        # loader's own remedy and adds where the rest of it is written down.
        print(f"error: {config_error} {SETUP_DOC} says how.", file=sys.stderr)
        return 1

    # Ours, and nothing a caller passes moves it. The journal is a corpus to be
    # compounded — how often the floor finishes a task type on its own, what a
    # rung costs per accepted change, whether escalating paid — and every one of
    # those questions is about *all* the runs there have been.
    configured = config.get("journal.dir") if config is not None else None
    journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()
    # An mcorch writer's transcript is under this directory and nowhere the
    # parser could have looked: attached now that the directory is known.
    session = with_mcorch_transcript(session, journal_dir)
    # Theirs, for their own reading. A complete copy — every line, every blob,
    # the result file — so a reader of the journal reads it exactly as it reads
    # ours, and a failure to write one is a note rather than the end of a
    # run we have already recorded correctly (`Recording.copy_failed`).
    #
    # A copy of the corpus *into* the corpus is dropped rather than made, and
    # this is not a nicety: the copy is written to `<dir>/<orchestrator>.jsonl`
    # by the same name ours is, so naming our own directory would append every
    # line to the same file twice. `fold` keeps both rows — a repeat attempt id
    # is a collision, not a supersede — so a reader that builds one table row
    # per folded attempt would count one dispatch as two.
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
        # It names the result file because that is the path the caller reads;
        # the floor's row and mcgyvr's own copy of the result go under the
        # default journal dir. Only the floor reaches this line — a climb
        # without a ladder was refused above.
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
        # A session writes nothing, so it has no target, whatever it gave.
        target="" if contract.is_session else contract.target,
        orchestrator=session.orchestrator,
        run=stamp,
        session_file=str(session.session_file) if session.session_file else None,
        journal=str(journal_dir),
        notes=notes,
    )

    # Every run, both paths: the floor dispatches nothing and is journaled too.
    try:
        recording = Recording(
            path=journal_dir / f"{session.orchestrator}.jsonl",
            orchestrator=session.orchestrator,
            run=stamp,
            session_file=session.session_file,
            mirrors=mirrors,
        )
        # Every row carries the caller's tags, so tags that cannot be read
        # are refused here, once, rather than as a failed row per attempt.
        run_tags()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # Asked before the run rather than discovered during it. Our sink raises on
    # an unwritable path (`telemetry.observe`), and a raise from inside a
    # dispatch reaches the caller as a traceback with no `result:` line; a
    # directory that is a file or a path with no permission is an
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
    print(f"journal: {recording.path}", file=sys.stderr)

    # Settled once, here, so both paths below open the same sandbox
    # (`_sandbox_mode` says who answers).
    args.sandbox = _sandbox_mode(args.sandbox, contract, config)
    # Settled once too, for delivery (`_commit`): it judges the bytes again,
    # and a gate that read a different setup from the sandbox's would refuse
    # where the change lands what the setup asked it to accept where it was
    # written (`gate.param_mutation`).
    args.gate_adapters = gate_adapters(config)
    # And whether, and onto which branch, an accepted change is committed: the
    # same precedence (`_settle_delivery`).
    _settle_delivery(args, config)

    if contract.is_deterministic:
        code = _floor(args, contract, repo, report, config, recording=recording)
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

    # A chat or agent run is a session, and its answer is kept (owner, e2e run
    # 1 F7: "answers are not throwaway nowhere"): a record of its own under
    # the journal, written before the result file so the result never names a
    # record that is not there. Not fatal when it cannot be written: the answer
    # is in the result file all the same, and the line says where it is not.
    if contract.is_session:
        logged = session_path(journal_dir, contract.id, stamp)
        try:
            write_session(
                logged,
                session_record(
                    report,
                    contract_path=Path(args.contract).absolute(),
                    question=contract.task,
                    result=keep,
                    journal=recording.path,
                ),
            )
        except OSError as exc:
            print(
                f"error: this session could not be logged at {logged}: {exc}. "
                f"Its answer is in the result file.",
                file=sys.stderr,
            )
        else:
            report.session_record = str(logged)
            print(f"session: {logged}", file=sys.stderr)
            for mirror in mirrors:
                try:
                    _copy(logged, session_path(mirror, contract.id, stamp))
                except OSError as exc:
                    print(
                        f"error: this session could not be copied into {mirror}: "
                        f"{exc}. It is at {logged}.",
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
        # what the file would have said that matters — where the change went
        # included, which is `delivery`'s to say beside the judgement.
        went = report.delivery if report.delivery != report.detail else ""
        print(
            f"error: the result could not be written to {failed}: {exc}. "
            f"The run came to {report.outcome}"
            + (f": {report.detail}" if report.detail else "")
            + (f"; {went}" if went else "")
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


def _sessions(args: argparse.Namespace) -> int:
    """List the session log, newest first, or show one session whole.

    The log is the journal's ``sessions/``: ``--journal DIR`` (a ``--record``
    copy, say), else the config's ``journal.dir``, else the schema default — a
    bare install has a journal too. One line per session in the listing, and
    the question and the answer in full when one is named.
    """
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.result import SESSIONS_DIR, sessions

    if args.journal is not None:
        journal_dir = Path(args.journal).expanduser()
    else:
        chosen = Path(args.config) if args.config else None
        try:
            configured = load_config(chosen).get("journal.dir")
        except ConfigError as exc:
            # No config where nobody named one is the bare install, whose
            # journal is the default; a config someone named is theirs to fix.
            bare = isinstance(exc, ConfigMissingError) and (
                chosen is None and named_config_path() is None
            )
            if not bare:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            configured = None
        journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()

    found = sessions(journal_dir)
    if args.id is None:
        if not found:
            print(f"no sessions in {journal_dir / SESSIONS_DIR}")
            return 0
        for path in found[: args.limit]:
            record = json.loads(path.read_text(encoding="utf-8"))
            asked = " ".join(str(record.get("question", "")).split())
            print(
                f"{path.stem}  [{record.get('task_type')}] "
                f"{record.get('outcome')}  {_clip(asked, 60)}"
            )
        return 0

    path = journal_dir / SESSIONS_DIR / f"{args.id}.json"
    # An id is a file name in the log, never a path out of it.
    if Path(args.id).name != args.id or not path.is_file():
        print(
            f"error: no session {args.id!r} in {journal_dir / SESSIONS_DIR}; "
            f"`mcgyvr sessions` lists them.",
            file=sys.stderr,
        )
        return 1
    record = json.loads(path.read_text(encoding="utf-8"))
    contract = record.get("contract") or {}
    print(f"{record.get('session')}  [{record.get('task_type')}]")
    print(f"  outcome:   {record.get('outcome')} ({record.get('assurance')})")
    print(f"  unit:      {record.get('unit')}")
    print(f"  started:   {record.get('started')}")
    print(f"  finished:  {record.get('finished')}")
    print(f"  contract:  {contract.get('path')} (sha256 {contract.get('sha256')})")
    print(f"  result:    {record.get('result')}")
    print(f"  record:    {path}")
    print(f"\nasked:\n{record.get('question')}")
    answer = record.get("answer") or f"(none: {record.get('detail')})"
    print(f"\nanswer:\n{answer}")
    return 0


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


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
    config: Config | None,
    *,
    recording: Recording,
) -> int:
    """Run a deterministic contract's program, gate what it did, and record it.

    **The floor journals, on the same terms as a dispatch.** It writes no
    prompt and no reply because it sent none, but it is a run, and a corpus
    that held only the runs the floor did *not* handle could not answer the one
    question the deterministic tier exists to raise: how much work finishes
    here, for free and in one attempt, rather than on a model.

    The row is written once the program and the gate have both run inside
    :func:`~mcgyvr.telemetry.observe`, and is corrected afterwards with how the
    result was judged and where it went. ``rung`` is the program that did it —
    ``ruff``, not a model — and ``tier`` is ``deterministic`` beside it, so one
    query can count a floor run against a ladder attempt without the two
    vocabularies colliding in one column.

    What is deliberately outside the row: opening the sandbox. It is the
    floor's ``pool.bind`` — the step before the work that decides whether there
    is any — and the ladder does not journal a dispatch it could not make
    either. What is counted is what ran.
    """
    from mcgyvr.deterministic import tool_steps
    from mcgyvr.drive import (
        DriveError,
        acceptance_for,
        gate_workspace,
        run_tool_step,
        task_ceiling,
    )
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.telemetry import correct, observe

    if args.record is not None:
        # The floor dispatches nothing and journals all the same: the
        # `--record` directory gets this run's row, its verdict and a copy of
        # its result, and so does mcgyvr's own `journal.dir`.
        print(
            f"note: {contract.id} is a {contract.kind.name!r} contract and runs "
            f"on the deterministic floor; it dispatches nothing, so the copy in "
            f"{args.record} is a row naming the program that did the work and a "
            f"copy of this run's result, with no prompt or reply beside them"
        )
    steps = tool_steps(contract)
    if not steps:
        return _error(
            report,
            f"no program is bound to {contract.kind.name!r} for "
            f"{contract.target}. The work is still doable on a dearer "
            f"family, which this command does not climb to.",
        )

    try:
        sandbox = open_sandbox(repo, mode=args.sandbox, **_sandbox_policy(config))
    except SandboxError as exc:
        return _error(report, str(exc))

    # One row per run, not per step: `tool_steps` returns one step or none —
    # "a tool fails identically on retry" — and a key per step would invent a
    # breadth the floor does not have.
    rung = steps[0].tool.program or contract.kind.name
    attempt_id = recording.attempt_id(contract.id, rung, 1)

    # What an in-process step said it did, for the journal's verdict row.
    performed: list[str] = []

    def work() -> GateResult:
        for note in sandbox.notes:
            print(f"note: {note}")
        # The run's own ceiling, as its acceptance commands get
        # (`acceptance_for`): left to `run_tool_step`, a step is timed by the
        # config at the default location rather than the one `--config` named.
        ceiling = task_ceiling(config)
        for step in steps:
            outcome = run_tool_step(step, sandbox, timeout=ceiling)
            print(f"  {_ran(step)}")
            if not outcome.ran:
                raise FloorStoppedError(str(outcome.environment_issue))
            assert outcome.result is not None  # `ran` is `result is not None`
            if not outcome.performed:
                raise FloorStoppedError(
                    (outcome.result.stderr or outcome.result.stdout).strip()
                )
            if not step.argv and outcome.result.stdout.strip():
                # An in-process step's own account of what it touched — for
                # `rename_symbol`, every file and line it renamed in and every
                # same-named occurrence it judged to be another symbol. A
                # program's stdout is its own business; this one is the only
                # record of which files the change spans, so it is printed,
                # kept in the result's notes and handed to the journal.
                said = outcome.result.stdout.strip()
                print(textwrap.indent(said, "    "))
                performed.append(f"{_ran(step)}\n{said}")
                report.notes.append(f"{_ran(step)}: {said}")
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
        return gate_workspace(contract, sandbox, config=config)

    try:
        with sandbox:
            # The baseline `_climb` checks before a rung is charged, checked
            # here before the tool runs: a suite already red on the unchanged
            # tree is the contract's or the tree's problem, and judging it
            # after the tool would file it as the tool's change, `rejected`.
            # No row yet — the run has not started its work.
            acceptance = acceptance_for(contract, sandbox, config=config)
            if acceptance is not None:
                baseline = acceptance.baseline()
                for note in baseline.notes:
                    print(f"note: {note}")
                report.notes.extend(baseline.notes)
                if baseline.issue is not None:
                    return _error(report, str(baseline.issue))
            result = observe(
                work,
                path=recording.path,
                attempt_id=attempt_id,
                orchestrator=recording.orchestrator,
                rung=rung,
                task_type=contract.task_type,
                operation=contract.operation,
                session_file=recording.session_file,
                tier=DETERMINISTIC,
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
                performed="\n".join(performed),
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


def _runs_no_command(contract: Contract) -> bool:
    """Whether ``contract`` is a session that declares no command to run.

    Such a run only stages its reply for the output checks, so its sandbox is
    ``sandbox.sessions``'s to choose and not ``sandbox.mode``'s (owner, e2e
    run 2 R10: docker for chat and agent is opt-in at setup).
    """
    return contract.is_session and not (
        contract.acceptance_commands or contract.demonstration_commands
    )


def _sandbox_mode(typed: str | None, contract: Contract, config: Config | None) -> str:
    """The sandbox mode a run of ``contract`` opens.

    A flag typed at the terminal is a person overriding their own file and
    wins. With none, a session that runs no command reads `sandbox.sessions`
    (`tempdir` unset), and every other run reads `sandbox.mode` (`docker`
    unset): a session that declares a command runs it as any task does.
    """
    if typed:
        return typed
    key, unset = (
        ("sandbox.sessions", "tempdir")
        if _runs_no_command(contract)
        else ("sandbox.mode", "docker")
    )
    return str((config.get(key) if config is not None else None) or unset)


#: Said once when a session that runs no command is staged on this host.
SESSION_SANDBOX_NOTE = (
    "This session runs no command, so its reply is staged in a throwaway "
    "checkout on this host and no container is built or started "
    "(`sandbox.sessions: tempdir`; `docker` gives sessions a container)."
)


def _ran(step: ToolStep) -> str:
    """The line that says what a floor step ran, as a person would retype it.

    A program is its command line. An in-process step has no command line —
    :attr:`~mcgyvr.deterministic.ToolStep.argv` is empty on purpose — and
    joining nothing printed a bare ``$``, which says a command ran and names
    none. It is said instead as what it is: mcgyvr's own operation, with the
    pair it was given.
    """
    if step.argv:
        return f"$ {' '.join(step.argv)}"
    said = f"(in-process) {step.tool.operation}"
    if step.rename.stated:
        said += f" {step.rename.old} -> {step.rename.new}"
    return said


def _sandbox_policy(config: Config | None) -> dict[str, Any]:
    """What the `sandbox` block says about a sandbox beyond its mode.

    Read in one place for both paths that open one, so the floor and the climb
    cannot come to disagree about whether a missing daemon falls back or what
    network a container gets. No config is the schema's defaults: refuse
    rather than fall back, and Docker's default network.
    """
    if config is None:
        return {"allow_fallback": False, "network": "bridge"}
    return {
        "allow_fallback": bool(config.get("sandbox.allow_fallback", False)),
        "network": config.get("sandbox.network", "bridge"),
    }


def _error(report: RunResult, detail: str, *, outcome: str = "error") -> int:
    """Print an error the way every branch here does, and keep it for the result.

    The outcome is set here, not left to whatever the caller had written
    before things went wrong. A caller reporting under a more specific word
    passes it.
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
    each family's rungs in the order the operator wrote them into the ladder
    and gives each the attempts the policy's ``attempts`` map declares for it,
    capped by the contract's ``limits.attempts``; and ``max_escalations`` with
    ``max_attempts`` bound how far the walk gets. A ``--rung`` flag would be a
    fourth party to a decision three files already settle, and the first time it
    disagreed with the ladder the operator would have two orderings and no way
    to tell which one ran.

    Hence ``--config`` and no rung flag. It resolves the same way every other
    command's does — ``$MCGYVR_CONFIG``, then the working directory, then
    the live fleet folder the config folder's ``live.json`` names — because a
    second resolution order for the same file is a
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
    from mcgyvr.capacity import Capacity, CapacityError
    from mcgyvr.cooldown import Cooldown
    from mcgyvr.drive import DriveError, acceptance_for, worker_attempt
    from mcgyvr.escalate import Outcome, ascent, escalate
    from mcgyvr.fleet_manager import hook_for as fleet_hook_for
    from mcgyvr.local_pool import SourceUnavailableError, source_map
    from mcgyvr.route import RouteError
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from mcgyvr.verify import reviewers_for

    # Live is admitted before anything here is built, opened or dispatched
    # (the lab's fleet-identity plan, §6): each rig of the live
    # fleet is read through the door and held to its lock
    # (`mcgyvr.fleet.admission`). At the
    # top, the conservative place: a refused run costs no pool, no capacity slot
    # and no sandbox. A dev run reads no rig.
    if config.get("profile") == "live":
        refused = _admitted_live(config)
        if refused is not None:
            report.outcome = "error"
            report.detail = refused
            return Exit.REFUSED

    # What the ladder manager (`mcgyvr manage`) has chosen for this ladder, if
    # it runs one: the config a task climbs with, and the hooks that let the
    # manager read the queue. An unmanaged ladder is handed back unchanged.
    from mcgyvr import ladder_manager
    from mcgyvr.pressure import Board

    managed = ladder_manager.for_task(config, read_board=Board().read)
    config = managed.config
    if managed.note is not None:
        print(f"note: {managed.note}")

    # Structural resolution, no probe: a live-reachability sweep costs one
    # timeout per source and answers a question the dispatch below is about to
    # ask for real. `mcgyvr local_pool --probe` is where an operator asks it in
    # advance, and paying for it here would charge every run for a diagnosis.
    #
    # `Availability.not_serving` — whether the model a rung declares is the one
    # its port holds — is not asked here either: `source_map(config)` takes no
    # probe, so this function resolves its ladder without a network. A wrong
    # model is caught at dispatch instead: llama-server answers a request
    # naming another model from the weights it holds, and the runner refuses a
    # reply whose `model` names other weights (`runner.WrongWeightsError`).
    pool = source_map(config)

    # The width `mcgyvr config` prints, actually applied. Built here, once, and
    # handed to both `ascent` and `escalate`: the reservations one makes are
    # the loads the other reads, so two capacities would be two tallies of one
    # rig. Its slot files are a host-wide rendezvous, which is what makes this
    # bound hold across concurrent `mcgyvr run` processes and not merely
    # within one — the case it exists for, since a single contract dispatches
    # one request at a time and never contends with itself. Its server reader
    # is what lets `fanout: idle` count a client that is not mcgyvr: a rung is
    # full by either count (Capacity.judge), and it is read only where that
    # question is asked.
    from mcgyvr.pressure import server_counts

    try:
        capacity = Capacity.of(config, gauge=managed.gauge, busy=server_counts(pool))
    except CapacityError as exc:
        return _error(report, str(exc))

    # The cooldown learns from dispatch failures, not from a probe, so its
    # liveness half is a stub that always reports live. Probing here would
    # charge every run for a diagnosis the dispatch below is about to make for
    # real, and `mcgyvr local_pool --probe` is where an operator asks it in advance.
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

    cooldown = Cooldown(probe=_always_live, shared=managed.held)
    try:
        route = ascent(config, pool, contract, capacity=capacity)
    except RouteError as exc:
        return _error(report, str(exc))
    if not route:
        return _error(
            report,
            f"{contract.id} is a {contract.task_type!r} contract and "
            f"starts on the {route.floor.name!r} family; nothing in {config.path} "
            f"can run it. {route.reason}",
            outcome=Outcome.NOTHING_TO_RUN.value,
        )

    # Before the sandbox, for the reason the paragraph above gives: an install
    # whose named verifier cannot serve is refused while refusing is still
    # free. `verifier.enabled` is acted on here — on unless the config says
    # `false` — and `reviewers_for` reads the rest once: the named
    # `verifier.unit` (or, for work its own model wrote, the fallback
    # `verify.stand_in_rung` picks), or, with none named, the next dearer
    # local rung with another model for each builder (never a hosted one). A
    # builder with no independent reviewer is not refused; its acceptance is
    # labelled unverified and says so. A reply (`chat`, `agent`, `media`) is never
    # reviewed, so none is resolved for it and a verifier the install cannot
    # serve does not refuse it (owner, e2e run 2 R11: "agent and chat have no
    # gates").
    try:
        reviewers = (
            reviewers_for(config, pool, capacity=capacity)
            if contract.kind.judges_a_change
            else None
        )
    except SourceUnavailableError as exc:
        return _error(
            report,
            f"verification is enabled and the verifier role cannot run: "
            f"{exc}. Bind `verifier.unit` to a usable unit, or set "
            f"`verifier.enabled: false` to accept on the deterministic gate.",
        )

    try:
        # A session that runs no command and was not given a container is
        # staged on this host without `open_sandbox`: no daemon is probed, so
        # Docker need not be installed, and neither the weaker-mode note nor
        # `sandbox.network: none`'s refusal applies — both are about commands,
        # and none runs. Its workspace is a checkout of HEAD as in any mode.
        sandbox = (
            TempDirSandbox(repo, notes=(SESSION_SANDBOX_NOTE,))
            if _runs_no_command(contract) and args.sandbox == "tempdir"
            else open_sandbox(
                repo,
                mode=args.sandbox,
                image=config.get("sandbox.image"),
                setup=config.get("sandbox.setup") or (),
                # The worker runs outside the sandbox and the sandbox has to be
                # able to reach it: a container with no route to the source is
                # a task that gates fine and never gets an answer to gate.
                endpoints=tuple(unit.address for unit in config.units.values()),
                **_sandbox_policy(config),
            )
        )
    except SandboxError as exc:
        return _error(report, str(exc))

    try:
        with sandbox:
            for note in sandbox.notes:
                print(f"note: {note}")
            # The baseline, before the first rung: `Acceptance.baseline`
            # runs both lists against the unchanged tree, so a demonstration
            # that already passes or a suite that is already red is refused
            # here rather than charged to a model. The issue's own wording
            # tells the two apart, because the operator's next move differs:
            # one says fix the contract, the other says fix the tree. What the
            # commands left behind was cleaned up, and the notes say what.
            acceptance = acceptance_for(contract, sandbox, config=config)
            if acceptance is not None:
                baseline = acceptance.baseline()
                for note in baseline.notes:
                    print(f"note: {note}")
                report.notes.extend(baseline.notes)
                issue = baseline.issue
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
                recording=recording,
                cooldown=cooldown,
                reviewers=reviewers,
            )
            if config.get("profile") == "live":
                driver = _warning_pulled_steps(driver)

            outcome = escalate(
                config,
                pool,
                contract,
                driver,
                capacity=capacity,
                # The fleet-manager seam: a Jev difficulty judgment that may
                # route a hard task to an asleep smarter rung before the api.
                # ``None`` for an install with no asleep smarter rung, or one
                # that has not enabled sleep-wake — which is every install
                # that did not ask for the feature.
                wake_hook=fleet_hook_for(config, pool, cooldown=cooldown),
                presence=managed.presence,
            )
            return _report_climb(
                args, contract, sandbox, repo, outcome, recording, report
            )
    except (DriveError, SandboxError, CapacityError) as exc:
        return _error(report, str(exc))


def _admitted_live(config: Config) -> str | None:
    """``None`` when live admission admits this command, else why not, printed.

    Each rig of the live fleet is read through the door and held to the lock
    (:func:`mcgyvr.fleet.admission.admit`), and a unit on a rig in ``config``,
    the config the command loaded, must be one the live fleet lays out there. A
    plan to clean or restore refuses, and the door commands that would carry it
    out are printed and not run: that a live command carries its plan out is not
    decided.
    """
    from mcgyvr.fleet.admission import admit
    from mcgyvr.fleet.admit import LiveRefusedError

    try:
        admission = admit(units=config.get("units") or {})
    except LiveRefusedError as exc:
        detail = f"live admission: {exc}"
        print(f"refused: {detail}", file=sys.stderr)
        return detail
    if admission.admitted:
        return None
    detail = (
        f"live admission: the rigs of {admission.fleet} do not read as locked; "
        "nothing was cleaned or restored, and these door commands would do it"
    )
    print(f"refused: {detail}:", file=sys.stderr)
    for line in admission.commands:
        print(f"  {line}", file=sys.stderr)
    return detail


def _warning_pulled_steps(
    attempt: Callable[[Try], Judgement],
) -> Callable[[Try], Judgement]:
    """``attempt``, warning once on stderr before each pulled step is dispatched.

    Warned, not enforced. A step whose unit's combination is pulled
    (:func:`mcgyvr.fleet.alerts.live_pulled_units`) is named, with each pulled
    field and its count, and then dispatched exactly as it would have been:
    this wraps the attempt and never answers for it, so the rungs, the attempts
    and the outcome are the climb's own. Pulls that cannot be read are one
    warning, and the run goes on; nothing here fails a run.
    """
    from mcgyvr.fleet.alerts import live_pulled_units

    try:
        units = live_pulled_units()
    except Exception as exc:
        print(
            f"warning: pulls could not be read ({exc}); every step is dispatched "
            f"without them — see `mcgyvr fleet alerts`",
            file=sys.stderr,
        )
        units = {}
    warned: set[str] = set()

    def warning(this: Try) -> Judgement:
        name = this.rung.name
        entries = units.get(name)
        if entries and name not in warned:
            warned.add(name)
            fields = ", ".join(
                (
                    f"{entry['field']} x{entry['count']}"
                    if entry["unit"] == name
                    else f"{entry['unit']} {entry['field']} x{entry['count']}"
                )
                for entry in entries
            )
            print(
                f"warning: step {name} is pulled: {fields}; dispatched anyway — "
                f"see `mcgyvr fleet alerts`",
                file=sys.stderr,
            )
        return attempt(this)

    return warning


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
    from mcgyvr.escalate import Assurance, Delivered
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

    spent = (
        f"on {outcome.rung} ({outcome.assurance.value}) "
        f"after {outcome.attempts_spent} attempt(s) and "
        f"{outcome.escalations} escalation(s)"
    )
    # The headline waits for delivery when there is one: "accepted" is said
    # only of a change that was written (e2e run 2, R2).
    verdict = _Headline(
        headline=f"{contract.id}: accepted {spent}",
        passed=f"{contract.id}: checks passed {spent}",
    )
    report.outcome = "accepted"
    report.rung = outcome.rung
    report.assurance = outcome.assurance.value
    # How the work was judged, in the judgement's own words — verified by whom,
    # unverified and why, or a reply's checks — into the result file, which is
    # what a caller is told to read.
    report.detail = outcome.judgement.detail
    if outcome.assurance is Assurance.UNVERIFIED:
        # Said where it cannot be missed, because nothing else about the run
        # looks different: the change is accepted on the gate alone.
        print(
            f"UNVERIFIED: {contract.id} is accepted with no independent review "
            f"approving it — {outcome.judgement.detail}",
            file=sys.stderr,
        )
    elif outcome.assurance in (Assurance.CHECKED, Assurance.UNCHECKED):
        print(f"note: {outcome.judgement.detail}", file=sys.stderr)
    bound = outcome.judgement.accepted
    if bound is None:
        # `judge` only reaches PASSED through a gate that accepted, and
        # `worker_attempt` binds on exactly that branch. Refusing rather than
        # asserting because the alternative to a bound value is not a fallback:
        # there is nothing to deliver, and a commit assembled from anything else
        # would be bytes no gate read.
        verdict.say()
        return _error(
            report,
            f"{contract.id} was accepted on {outcome.rung} without bound "
            f"content, so there is nothing a delivery could re-judge.",
        )
    if contract.output_schema in ("prose", "media_artifact"):
        # A raw-text reply is the answer, not a file that gets committed: the
        # harness reads it off the result file rather than off a delivery. No
        # `_commit` is attempted and the accepted exit is returned.
        report.answer = bound.content
        verdict.say()
        print(f"\n{contract.id}: answer —\n{bound.content}")
        return 0
    landed = outcome.history[-1]
    return _commit(
        args,
        contract,
        repo,
        sandbox.source_base_commit(),
        bound,
        report,
        verdict=verdict,
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

    A raise with ``draw: null`` has three causes: a gate that died on an early
    draw, a draw whose ``pool.bind`` raised before it reached a row, and a raise
    after the last draw. This line is only ever written about a row that
    exists, so ``rows - 1`` is the last draw that answered, and naming that draw
    is true of all three.
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
    performed: str = "",
) -> int:
    """Print the gate verdict, correct the row it is about, and commit when asked.

    ``recording`` and ``attempt_id`` arrive from :func:`_floor`, its only
    caller, which writes one row per run and needs it corrected the way
    :func:`_report_climb` corrects a climb's: the row says the program ran, and
    the correction says how the gate judged it. They are optional because the
    correcting is the only part of this a caller can decline, not because there
    is a second caller that declines it — a climb never comes through here, it
    reports itself and reaches :func:`_commit` directly.

    ``performed`` is what an in-process step said it did — a rename's files and
    lines — and goes into the verdict's correction beside the findings, so the
    journal keeps the one account of which files the change spans.

    **What is delivered is what the program changed.** The binding is minted
    over the sandbox's whole change set, the files the gate just judged, not
    over ``target`` alone: a ``rename_symbol`` that renamed a definition and its
    importers is one change in several files, and delivering only the target
    left the user's tree importing a name that no longer exists. Delivery then
    holds every file to the contract's scope and lands them in one commit, or
    none.
    """
    from mcgyvr.deliver import Accepted, DeliveryError
    from mcgyvr.escalate import Assurance
    from mcgyvr.gate.changeset import ChangeSet
    from mcgyvr.route import Verdict
    from mcgyvr.telemetry import correct

    verdict = _Headline(
        headline=f"{contract.id}: gate {'accepted' if result.accepted else 'rejected'}",
        passed=f"{contract.id}: checks passed",
        below=(
            *(f"  ✗ {finding}" for finding in result.findings),
            *(f"  ? {issue}" for issue in result.environment_issues),
        ),
    )
    report.findings = [str(finding) for finding in result.findings]
    if recording is not None and attempt_id is not None:
        # The gate's word for it, in the gate's vocabulary — the same two words
        # a climb's attempts are corrected with, so one query counts them
        # together. `_commit` appends a second correction on top saying where
        # the work went, and the folded row is that later one.
        said = [str(finding) for finding in result.findings]
        if performed:
            said.append(performed)
        correct(
            path=recording.path,
            attempt_id=attempt_id,
            outcome=(Verdict.PASSED if result.accepted else Verdict.FAILED).value,
            detail="\n".join(said),
            orchestrator=recording.orchestrator,
            mirrors=recording.mirrors,
            on_copy_error=recording.copy_failed,
        )
    if not result.accepted:
        verdict.say()
        report.outcome = "rejected"
        return 1

    changed = ChangeSet.detect(sandbox.workspace)
    try:
        bound = Accepted.read(
            repo=sandbox.workspace,
            contract=contract,
            result=result,
            paths=[change.path for change in changed] or None,
        )
    except DeliveryError as exc:
        verdict.say()
        return _error(report, str(exc))
    if not changed:
        # The program ran, the gate had nothing to object to, and the tree is
        # exactly as it was: the target already is what the task type asks for.
        # Delivery would refuse it as a change identical to its base — which is
        # right for a model that answered with its target unchanged, and wrong
        # for a program that did its job and found nothing to do. The floor's
        # no-op ends on its own word, exit 0, with or without --commit, and
        # nothing is written or committed. Checked after binding: a target
        # that cannot be read is an error whatever changed.
        detail = (
            f"{contract.target} already is what {contract.kind.name!r} asks for; "
            f"nothing was written"
        )
        verdict.say()
        print(f"\n{contract.id}: {NOTHING_TO_CHANGE} — {detail}")
        report.outcome = NOTHING_TO_CHANGE
        report.detail = detail
        if recording is not None and attempt_id is not None:
            correct(
                path=recording.path,
                attempt_id=attempt_id,
                outcome=NOTHING_TO_CHANGE,
                detail=detail,
                orchestrator=recording.orchestrator,
                mirrors=recording.mirrors,
                on_copy_error=recording.copy_failed,
            )
        return 0
    # Only now: `accepted` tells the caller the change is in the target, and
    # until the bytes are bound there is nothing to put there. A tool's change
    # on the gate is what `deterministic` labels.
    report.outcome = "accepted"
    report.assurance = Assurance.DETERMINISTIC.value
    return _commit(
        args,
        contract,
        repo,
        sandbox.source_base_commit(),
        bound,
        report,
        verdict=verdict,
        recording=recording,
        attempt_id=attempt_id,
    )


def _settle_delivery(args: argparse.Namespace, config: Config | None) -> None:
    """Settle ``args.commit`` to a bool and ``args.branch`` to a name or ``""``.

    The precedence ``--sandbox`` has: a flag typed at the terminal is a person
    overriding their own file for one run and wins; with no flag the policy
    answers (``delivery.commit``, ``delivery.branch``); with neither, nothing is
    committed. ``--branch NAME`` implies ``--commit`` — naming where to commit
    is asking for a commit — while ``delivery.branch`` does not: it is where
    commits go once something turns them on. ``--branch`` with ``--no-commit``
    is refused at parse time (:func:`_one_delivery_answer`) and never reaches
    here. A run with no usable config commits only when a flag says so.
    """
    typed = (getattr(args, "branch", None) or "").strip()
    policy_commit = bool(config.get("delivery.commit")) if config is not None else False
    policy_branch = (
        config.get("delivery.branch") if config is not None else None
    ) or ""
    commit = getattr(args, "commit", None)
    args.commit = True if typed else (policy_commit if commit is None else commit)
    args.branch = typed or policy_branch


def _one_delivery_answer(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Refuse ``--branch`` that is blank, or typed beside ``--no-commit``.

    At parse time, through the parser's own ``error``, so it exits 2 like every
    other usage error and before a config is read or a sandbox opened. The two
    flags ask for opposite things; picking one would be guessing which the
    person meant.
    """
    branch = getattr(args, "branch", None)
    if branch is None:
        return
    if not branch.strip():
        parser.error(
            "--branch was given an empty name. Name the branch to commit onto, "
            "or leave the flag off to commit onto the one you have checked out."
        )
    if getattr(args, "commit", None) is False:
        parser.error(
            f"--branch {branch} asks for a commit onto {branch}, and --no-commit "
            f"asks for none. Pass one of them."
        )


#: The words :func:`_commit` appends to the accepted attempt's row. The
#: vocabulary is this caller's, as ``telemetry.correct`` says it must be.
COMMITTED = "committed"
NOT_COMMITTED = "not_committed"
DELIVERY_REFUSED = "delivery_refused"
#: The floor's word for a program that found nothing to change, written by
#: :func:`_report_run` in place of a delivery. Not a refusal: the run exits 0.
NOTHING_TO_CHANGE = "nothing_to_change"
#: The word for an attempt that raised instead of judging: the row says
#: ``ok: false`` already, and the correction says the climb counted it.
RAISED = "error"

#: The ``tier`` a floor row carries. The catalog's own name for the family that
#: runs programs rather than models (``catalog().families`` — ``deterministic``,
#: ``local``, ``api``), so a floor row and a ladder row, whose tier is
#: ``family_of(...).name``, are comparable in one column rather than in two
#: vocabularies that happen to look alike. It is a literal and not a lookup
#: because the floor has no rung to ask the catalog about;
#: ``tests/test_a_floor_run_is_in_the_corpus_too.py`` pins the row's ``tier``
#: to the same literal.
DETERMINISTIC = "deterministic"


@dataclass(frozen=True)
class _Headline:
    """The stdout lines that say how a run's change was judged and where it went.

    Built by the two reporters (:func:`_report_run`, :func:`_report_climb`)
    and said once, by whichever path ends the run: :func:`_commit` after
    delivery has answered, or the reporter itself on a path that delivers
    nothing. ``headline`` is the line of a change that landed (or of a run
    that never reached delivery); ``passed`` opens the line of one delivery
    refused, which goes on to say ``but not written`` and why (e2e run 2, R2).
    ``below`` is what is printed under either — the gate's findings and
    environment issues.
    """

    headline: str
    passed: str
    below: tuple[str, ...] = ()

    def say(self, *, refused: str | None = None) -> None:
        line = (
            self.headline
            if refused is None
            else (f"{self.passed}, but not written: {refused}")
        )
        print(f"\n{line}")
        for each in self.below:
            print(each)


def _commit(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    base: str,
    bound: Accepted,
    report: RunResult,
    *,
    verdict: _Headline,
    recording: Recording | None = None,
    attempt_id: str | None = None,
) -> int:
    """Deliver an accepted change into the user's repository, when asked to.

    Shared by both halves of ``run`` so that "what ``--commit`` does" has one
    answer. ``bound`` is an :class:`~mcgyvr.deliver.Accepted` in both cases and
    never a string: the deterministic path mints it off the workspace the gate
    read, the ladder path carries the one its attempt minted there, and delivery
    re-judges either in the repository the commit lands in.

    Whether to commit and onto which branch are ``args.commit`` and
    ``args.branch`` as :func:`_settle_delivery` left them — the flags typed,
    else ``delivery.commit`` and ``delivery.branch``, else no commit — the same
    on both paths, whether or not the contract climbed a ladder. An empty
    branch is the one checked out.

    What *is* handed over is the gate's adapters as the run's setup built them
    (``args.gate_adapters``, settled in :func:`_run`), so delivery judges by the
    same ``gate`` settings the sandbox did. A caller that settled none is
    refused by name rather than delivered under the strict default it did not
    choose.

    **The default is the working tree, and that is not a lack.** Not committing
    — the shipped policy — leaves the accepted change in the target and the
    repository otherwise untouched: no commit, no branch, no receipt. The journal row
    of the accepted attempt is told so (``not_committed``), and told
    ``committed <sha> on <branch>`` or ``delivery_refused`` otherwise, so the
    folded outcome is how the work finally landed.

    **The verdict's headline is printed here, once delivery has answered.**
    A change delivery refused was not written, and a stdout that said
    ``gate accepted`` above a refusal on stderr read as an acceptance (e2e
    run 2, R2). So ``verdict`` is said as it was when the change landed, and
    as ``<id>: checks passed, but not written: <reason>`` for every reason
    delivery refuses; the exit code, the result file and the ``error:`` line
    on stderr are unchanged.
    """
    from mcgyvr.deliver import DeliveryError, DeliveryRefusedError, deliver, place
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

    def refused(reason: str) -> None:
        # The refusal is the run's outcome, so `detail` carries it too (set by
        # the caller with the outcome); `delivery` says it where every other
        # delivery says where the change went.
        verdict.say(refused=reason)
        _say_reported(bound)
        landed(DELIVERY_REFUSED, reason)
        report.delivery = reason

    adapters = getattr(args, "gate_adapters", None)
    if adapters is None:
        verdict.say()
        return _error(
            report,
            "delivery was reached with no `gate_adapters` settled for this run, "
            "so it cannot judge the change by the setup's `gate` settings; "
            "nothing was written",
        )

    if not args.commit:
        try:
            place(
                repo=repo,
                contract=contract,
                content=bound,
                base=base,
                adapters=adapters,
            )
        except DeliveryError as exc:
            refused(str(exc))
            if isinstance(exc, DeliveryRefusedError):
                # The checks behind the refusal, not only its sentence — the
                # same lines a gate rejection leaves in `findings`.
                report.findings = [str(finding) for finding in exc.findings]
            return _error(report, str(exc), outcome=DELIVERY_REFUSED)
        verdict.say()
        _say_reported(bound)
        left = ", ".join(path for path, _ in bound.files(contract))
        print(f"\nLeft in {left}, not committed (pass --commit to commit).")
        for path, _ in bound.files(contract):
            _say_not_rerun(adapters, path)
        # Beside the judgement, never over it: `detail` stays how the work
        # was judged, and where it went is `delivery`'s (#183).
        report.delivery = f"not committed; change left in {left}"
        landed(NOT_COMMITTED, report.delivery)
        return 0

    try:
        delivery = deliver(
            repo=repo,
            contract=contract,
            content=bound,
            base=base,
            branch=getattr(args, "branch", None) or "",
            adapters=adapters,
        )
    except DeliveryError as exc:
        refused(str(exc))
        return _error(report, str(exc), outcome=DELIVERY_REFUSED)

    if not delivery.committed:
        refused(delivery.reason)
        report.outcome = DELIVERY_REFUSED
        report.detail = delivery.reason
        report.findings = [str(finding) for finding in delivery.findings]
        return 1
    verdict.say()
    _say_reported(bound)
    print(f"\n{delivery}")
    for path in delivery.paths:
        _say_not_rerun(adapters, path)
    report.committed = delivery.committed
    report.commit = delivery.commit
    report.branch = delivery.branch
    report.handoff = delivery.handoff
    report.delivery = str(delivery)
    landed(COMMITTED, f"{delivery.commit[:12]} on {delivery.branch or 'HEAD'}")
    return 0


def _say_not_rerun(adapters: Sequence[LanguageAdapter], path: str) -> None:
    """Print which checker delivery left out because it loads ``path`` as code."""
    from mcgyvr.deliver import not_rerun_here

    note = not_rerun_here(adapters, path)
    if note:
        print(f"  {note}")


def _say_reported(bound: Accepted) -> None:
    """Print once each finding the gate reported only because the setup said so.

    Under ``gate.param_mutation: report`` a function that changes its argument
    is accepted, and the finding travels as one of the gate's observations,
    which nothing else here prints. It is the one observation a user turned
    from a refusal into a report, so it is the only one printed; the others
    (style, repair notes) are not. Unset or ``refuse``, an accepted change
    carries no such finding and nothing is printed. The behaviour lives in this
    function and its one call in :func:`_commit`.
    """
    from mcgyvr.gate.typecheck import PARAM_MUTATION, ParamMutation

    for finding in bound.observations:
        if finding.code != PARAM_MUTATION:
            continue
        where = (
            finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        )
        print(
            f"  reported: {where} [{finding.code}] {finding.message} "
            f"(not refused: gate.param_mutation is {ParamMutation.REPORT.value})"
        )


def _scan(args: argparse.Namespace) -> int:
    """Measure this machine, record it, and say what stopped matching.

    ``--json`` exits :attr:`Exit.OK` even when the scan disagrees with the
    record, and that asymmetry is the point rather than an oversight.
    ``--json`` is not a quieter mode of this command for a person; it prints
    the wire format that :func:`mcgyvr.scan.Scan.from_json` reads — the same
    shape the shipped self-contained scanner prints on a rig. The exit-code
    channel belongs to the human-facing command, which keeps exit 4: a rig
    that lost a DIMM or a card still delivers its measurement down the wire
    and the mismatch goes to stderr, where the operator reads it.
    """
    if args.rig is not None:
        return _scan_rig(args.rig, as_json=args.json)
    measured = scan_module.scan(
        model_stores=tuple(Path(store) for store in (args.model_store or ()))
    )
    root = scan_module.default_root()
    prior = scan_module.load_prior(scan_module.os_machine_id(measured), root)
    drift = scan_module.compare(measured, prior)
    # Recorded before anything is reported, and recorded even when it
    # disagrees with the last scan. A mismatch is a successful measurement of a
    # machine that changed, not a failed one; withholding it would leave the
    # stale record in place for the next run to disagree with all over again.
    path = scan_module.write_scan(measured, root)

    if args.json:
        # stdout is the wire format `Scan.from_json` reads — the same shape the
        # shipped self-contained scanner prints on the rig. One banner line
        # here and the scan stops parsing, so everything a person would read
        # goes to stderr.
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
        device = f" on {measured.disk.device}" if measured.disk.device else ""
        total = (
            f" of {measured.disk.total_gb:.1f} GB"
            if measured.disk.total_gb is not None
            else ""
        )
        print(
            f"  Disk     {measured.disk.free_gb:.1f} GB free{total} "
            f"at {measured.disk.path}{device}"
        )
    for model in measured.models_on_disk:
        quant = f" {model.quant}" if model.quant else ""
        print(
            f"  Model    {model.name}{quant} "
            f"({model.size_bytes / 1024 / 1024 / 1024:.1f} GiB)"
        )
    for note in measured.notes:
        print(f"  - {note}")
    print(f"\nRecorded at {path}")

    if drift:
        _report_mismatches(drift, sys.stdout)
        return Exit.MISMATCH
    return Exit.OK


def _scan_rig(rig: str, *, as_json: bool) -> int:
    """Scan ``rig`` over ssh and save it as the door's rig file; say what moved.

    The scan is the read-only one ``mcgyvr recommend`` takes (the shipped
    scanner, over the user's own ssh config and keys with ``BatchMode``), and
    the file is what a user-mode door run holds the rig to
    (:mod:`mcgyvr.serving.rigfile`). A rig that does not answer writes
    nothing.
    """
    from mcgyvr.serving import rigfile

    try:
        target = rigfile.path(rig)
        try:
            before = rigfile.read(rig)
        except rigfile.RigFileError as exc:
            print(f"note: the rig file there is replaced: {exc}", file=sys.stderr)
            before = None
    except rigfile.RigFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.USAGE
    try:
        measured = scan_module.scan_over(scan_module.Reach.ssh(rig))
    except scan_module.Unreachable:
        print(
            f"error: {rig} did not answer ssh (BatchMode: your own ssh config and "
            "keys, no password prompt); no rig file is written",
            file=sys.stderr,
        )
        return Exit.ERROR
    except (scan_module.ScannerMissing, scan_module.ScanFailed):
        print(
            f"error: {rig} answered ssh but the scan did not run there (it needs "
            "python3); no rig file is written",
            file=sys.stderr,
        )
        return Exit.ERROR
    now = rigfile.from_scan(rig, measured)
    rigfile.write(now)
    out = sys.stderr if as_json else sys.stdout
    if as_json:
        sys.stdout.write(now.to_json())
    print(f"{rig}: {now.hostname}, docker {now.docker or 'not read'}", file=out)
    for card in now.cards:
        print(f"  card {card.index}  {card.said()}", file=out)
    if now.ram_total_gb is not None:
        print(f"  RAM     {now.ram_total_gb:.1f} GB", file=out)
    if now.cpu_cores is not None or now.cpu_threads is not None:
        print(
            f"  CPU     {now.cpu_cores or '?'} cores, {now.cpu_threads or '?'} threads",
            file=out,
        )
    if now.bandwidth_gbps is not None:
        print(
            f"  Memory  {now.bandwidth_gbps:.1f} GB/s ({now.bandwidth_how})",
            file=out,
        )
    if now.disk_path is not None:
        device = f" on {now.disk_device}" if now.disk_device else ""
        print(
            f"  Disk    {now.disk_free_gb} GB free"
            f"{f' of {now.disk_total_gb} GB' if now.disk_total_gb is not None else ''}"
            f" at {now.disk_path}{device}",
            file=out,
        )
    for model in now.models_on_disk:
        quant = f" {model.quant}" if model.quant else ""
        print(
            f"  Model   {model.name}{quant} "
            f"({model.size_bytes / 1024 / 1024 / 1024:.1f} GiB)",
            file=out,
        )
    if now.private_ipv4 is not None:
        print(f"  Address {now.private_ipv4} ({now.private_ipv4_how})", file=out)
    else:
        print(f"  Address no private IPv4 recorded: {now.private_ipv4_how}", file=out)
    for note in now.notes:
        print(f"  - {note}", file=out)
    if before is not None:
        for change in rigfile.moved(before, now):
            print(f"moved since {before.read_at}: {change.said()}", file=out)
    print(f"\nSaved as {target}", file=out)
    return Exit.OK


def _users_count(value: str) -> int:
    """``single`` or a positive count — the two spellings ``recommend`` takes."""
    if value == "single":
        return 1
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"users must be `single` or a number, not {value!r}"
        ) from None
    if count < 1:
        raise argparse.ArgumentTypeError(f"users must be at least 1, not {count}")
    return count


def _recommend(args: argparse.Namespace) -> int:
    """Print one JSON plan: which checkpoint and engine serve ``args.profile``.

    Read-only: the rigs are re-read over the sanctioned detection ssh path and
    nothing is written, woken or slept. The plan is the only thing on stdout.
    """
    try:
        made = recommend_module.plan(
            profile=args.profile,
            users=args.users,
            hosts=args.host,
            model_stores=args.model_store,
        )
    except (recommend_module.RecommendError, recommend_module.CatalogError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    sys.stdout.write(json.dumps(made, indent=2, sort_keys=True) + "\n")
    return Exit.OK


def _serve(args: argparse.Namespace) -> int:
    """Hand a card back, or take it back, by name.

    A thin front over the door's two steps for the operator who wants to say it
    by hand, and it is deliberately **not** gated by
    ``serving.enable_sleep_wake``: that switch exists so that mcgyvr does not
    decide to take a card down without being asked, and a person typing this has
    asked (the lab's sleep-wake plan, §15).

    ``sleep`` drains before it evicts. Every slot of every bound the card serves
    is taken first, so a dispatch that had already been admitted finishes rather
    than having its container killed under it — the one thing whole-card
    eviction is not allowed to do (D8 of the same plan). The census that
    decides *whether* to sleep is a reading and this is a hold, and between the
    two a dispatch can start, which is why both exist. Then the card goes down
    the way the ladder manager puts one down (:func:`mcgyvr.wake.put_down`): at
    vLLM's level 2 where every unit can, stopped otherwise.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    from mcgyvr import wake as wakelib
    from mcgyvr.capacity import Capacity, SlotUnavailableError

    # A live wake starts units, so it is admitted as a live run is, and refused
    # while the rigs do not read as locked: nothing is restored for it, because
    # carrying a plan out is not decided. A sleep is always admitted: stopping
    # starts nothing unapproved, and it is the way out.
    if (
        args.direction == "wake"
        and config.get("profile") == "live"
        and _admitted_live(config) is not None
    ):
        return Exit.REFUSED

    try:
        if args.direction == "wake":
            made = wakelib.wake(config, args.host)
        else:
            card = wakelib.card_named(config, args.host)
            capacity = Capacity.of(config)
            with capacity.drain(
                card.sources, timeout=wakelib.drain_timeout(config, card)
            ):
                made = wakelib.sleep(config, args.host)
    except wakelib.WakeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except SlotUnavailableError as busy:
        print(f"error: {busy}", file=sys.stderr)
        return Exit.REFUSED

    if not made.ok:
        print(
            f"error: the door exited {made.code} on `serve {made.direction}` for "
            f"{made.host} — read its envelope in the door's log under "
            f"~/.local/state/mcgyvr/door/",
            file=sys.stderr,
        )
        return Exit.ERROR
    how = {
        "sleep": "resting at level 2, its processes kept",
        "down": "stopped",
        "wake": "woken in its processes",
        "up": "started",
    }.get(made.direction, made.direction)
    print(
        f"{made.host} {args.direction}: {how}, {made.seconds:.1f}s "
        f"({made.compose_file})"
    )
    return Exit.OK


def _manage(args: argparse.Namespace) -> int:
    """Run the ladder manager: Jev sleeps and wakes the ladder's units by its queue.

    Optional per fleet: a ladder with no unit that can sleep and wake, or one
    whose ``serving.enable_sleep_wake`` is off, is told so and nothing is built
    — no pool, no capacity, no file under the rendezvous directory, no network.
    Otherwise the manager reads the queue on each local rung every
    ``manager.interval_s``, asks Jev only where more than one answer is legal,
    and throws the same two switches ``mcgyvr serve`` does
    (:class:`mcgyvr.wake.CardSwitches`). See :mod:`mcgyvr.ladder_manager`.

    It may wake a card, so it is admitted as a live wake is: refused while the
    live fleet's rigs do not read as locked. It runs until interrupted;
    ``--once`` is one tick, for a person who wants to see what it would read.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    from mcgyvr import ladder_manager
    from mcgyvr.pressure import exclusive

    why = ladder_manager.applicable(config)
    if why is not None:
        print(f"nothing to manage: {why}")
        return Exit.OK

    if config.get("profile") == "live" and _admitted_live(config) is not None:
        return Exit.REFUSED

    # One manager per host: a second would throw switches on the same cards
    # from streaks and a dwell of its own, sleeping what the first just woke.
    with exclusive(ladder_manager.MANAGER_LOCK) as held:
        if held is not True:
            print(
                "error: another `mcgyvr manage` is running on this host"
                if held is False
                else "error: no lock could be taken under the rendezvous "
                "directory, so mcgyvr cannot tell whether another `mcgyvr "
                "manage` is running on this host",
                file=sys.stderr,
            )
            return Exit.REFUSED
        return _manage_held(args, config)


def _card_mib(config: Config) -> dict[str, dict[int, int]]:
    """Each card's memory in MiB from the recorded scans, by host and card index.

    The scans ``emit`` sizes against, resolved to the hosts this ladder names
    (:func:`_resolve_hosts`); a host with no scan is not in the answer, and the
    ladder manager then makes no room on it and says so at start.
    """
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import cards

    hosts = {card.host for card in cards(config).values()}
    try:
        scans = _resolve_hosts(_scans(scan_module.default_root()), hosts)
    except OSError:
        return {}
    return wakelib.card_rooms({host: scans[host] for host in hosts if host in scans})


def _manage_held(args: argparse.Namespace, config: Config) -> int:
    """:func:`_manage` once this process is the host's only ladder manager."""
    from mcgyvr import fleet_manager, ladder_manager
    from mcgyvr import wake as wakelib
    from mcgyvr.capacity import Capacity, CapacityError
    from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
    from mcgyvr.local_pool import source_map
    from mcgyvr.pressure import Board, Gauge, HostCooling, Pressure, RungCooling

    pool = source_map(config)
    fast = fleet_manager.fast_rung(config, pool)
    if fast is None:
        print("error: no local rung for Jev to run on", file=sys.stderr)
        return Exit.ERROR
    gauge = Gauge()
    try:
        capacity = Capacity.of(config, gauge=gauge)
    except CapacityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    stated = config.units[fast.name].request_timeout_s
    bounds = ladder_manager.Bounds.of(config)
    board = Board()
    # The card the decisions run on is never slept: the `jev.unit` when one
    # is bound (every decision asks it), the fast rung when not.
    jev = config.get("jev.unit") or fast.name
    view = ladder_manager.View.of(config, jev=jev)
    switches = wakelib.CardSwitches(config, capacity, card_mib=_card_mib(config))
    manager = ladder_manager.Manager(
        view,
        bounds,
        pressure=Pressure(pool, capacity, gauge),
        switches=switches,
        decide=ladder_manager.decide_on(
            pool,
            fast.name,
            timeout_s=DEFAULT_REQUEST_TIMEOUT_S if stated is None else stated,
        ),
        cooling=RungCooling(pool, hold_s=bounds.dwell_s, shared=HostCooling()),
        say=print,
        publish=board.publish,
    )
    print(
        f"managing {', '.join(view.resident)}; can sleep and wake: "
        f"{', '.join(ladder_manager.sleepable_rungs(config))}; Jev runs on "
        f"{jev}; every {bounds.interval_s:g}s"
    )
    for rung, alone in wakelib.left_alone(config).items():
        print(f"note: {rung} is left alone: {alone}")
    for rung in ladder_manager.sleepable_rungs(config):
        why = switches.why_no_room(rung)
        if why is not None:
            print(f"note: no room is made for {rung}: {why}")
    try:
        ladder_manager.run(
            manager, interval_s=bounds.interval_s, ticks=1 if args.once else None
        )
    except KeyboardInterrupt:
        print("stopped")
    return Exit.OK


def _merge_resolved(
    block: Mapping[str, Any], resolved: Mapping[str, Any]
) -> dict[str, Any]:
    """``block`` with ``resolved``'s fields filled where the block states none.

    What an operator wrote wins: a key the block already states is left alone,
    and only what is missing is stamped. The same rule holds inside
    ``launch``, which is free-form and may already carry sizing keys
    (``vram_gb``, ``shards``, ...) beside the argv/env/volumes the emit layer
    resolves.
    """
    merged = dict(block)
    for key in ("engine", "image", "container", "hf_cache"):
        if key in resolved and not merged.get(key):
            merged[key] = resolved[key]
    stated = merged.get("launch")
    launch = dict(stated) if isinstance(stated, Mapping) else {}
    for key, value in (resolved.get("launch") or {}).items():
        if key not in launch or launch[key] is None:
            launch[key] = value
    if launch:
        merged["launch"] = launch
    return merged


def _block_declares(block: Mapping[str, Any]) -> bool:
    """Whether ``block`` already declares a model spec rather than the table's.

    Mirrors :func:`mcgyvr.serving.declared_models`' own skip condition: a block
    that states anything under ``launch`` (or ``hf_cache``, ``room_mib``,
    ``kv_cache_memory_bytes``) is sized from what it declares, so a stamp must
    not paper over those keys with the shipped table's numbers.
    """
    return bool(
        block.get("launch")
        or block.get("hf_cache") is not None
        or block.get("room_mib") is not None
        or block.get("kv_cache_memory_bytes") is not None
    )


def _sizing_keys(spec: ModelSpec) -> dict[str, Any]:
    """The scalar sizing keys a shipped dense row declares, for re-sizing.

    A dev unit sized from the shipped table declares nothing in ``fleet.yaml``,
    so once ``launch`` carries the resolved argv/env/volumes,
    :func:`mcgyvr.serving.declared_models` reads it as a declared spec of all
    zeros and refuses the next emit. Copying the table's scalar facts keeps the
    two emits the same bytes. MoE rows and geometries are never copied: those
    reach emit only through an operator's own declaration, which the stamp
    already preserves.
    """
    keys: dict[str, Any] = {}
    for key in ("vram_gb", "disk_gb", "ram_gb", "kv_cache_dtype_k", "kv_cache_dtype_v"):
        value = getattr(spec, key, None)
        if value:
            keys[key] = value
    return keys


def _render_launch_block(launch: Mapping[str, Any]) -> str:
    """The ``launch:`` block of one unit, indented to sit at four spaces."""
    dumped = yaml.safe_dump(dict(launch), sort_keys=True, width=200)
    lines = ["    launch:"]
    lines.extend(
        f"      {line}" if line else "" for line in dumped.rstrip("\n").splitlines()
    )
    return "\n".join(lines)


def _render_stamped_fleet(fleet: Mapping[str, Any]) -> str:
    """Render a stamped ``fleet.yaml`` with the schema renderer, plus ``launch``.

    :func:`mcgyvr.initialize.render_fleet` renders every unit field but does not
    know how to spell a free-form ``launch`` mapping, so the launch blocks are
    rendered here and spliced into its output at the field's own place — the
    schema comments and the operator's ordering survive.
    """
    launches: dict[str, Mapping[str, Any]] = {}
    render_units: dict[str, Any] = {}
    for name, block in (fleet.get("units") or {}).items():
        block = dict(block)
        launch = block.pop("launch", None)
        if isinstance(launch, Mapping) and launch:
            launches[name] = launch
        render_units[name] = block
    text = render_fleet({**fleet, "units": render_units})

    current: str | None = None
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            name = line[2:-1].strip()
            current = name if name in launches else None
        elif current is not None and line.startswith("    # launch:  # "):
            out.append(_render_launch_block(launches[current]))
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` beside ``path`` and move it over atomically."""
    staged = path.with_name(f".{path.name}.tmp")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)


def _stamp_launch(
    config: Config,
    units: Iterable[Unit],
    *,
    sleep_mode: bool,
    specs: Iterable[ModelSpec],
) -> Path | None:
    """Stamp ``resolved_launch`` into each serving unit of ``config``'s fleet.yaml.

    Returns the file written, or ``None`` when there is no fleet.yaml beside the
    config (a single merged document has none) or nothing changed. The write is
    atomic and idempotent: a unit that already states a field keeps it.

    A unit that was sized from the shipped table declares no model spec in
    ``fleet.yaml``; once its ``launch`` carries the resolved argv, the loader
    would read it as a declared spec of zeros. The table's scalar facts are
    stamped beside the launch for exactly those units so a re-emit re-sizes to
    the same argv.
    """
    if config.path is None:
        raise EmitError("the config has no path, so fleet.yaml cannot be stamped")
    fleet_path = config.path / FLEET_FILENAME
    if not fleet_path.is_file():
        return None
    try:
        fleet = load_fleet(fleet_path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise EmitError(f"{fleet_path}: cannot be read to stamp — {exc}") from exc

    catalogue = {spec.name: spec for spec in specs} | declared_models(config)
    blocks = dict(fleet.get("units") or {})
    changed = False
    for unit in units:
        resolved = resolved_launch(unit, sleep_mode=sleep_mode)
        spec = catalogue.get(unit.model)
        for name in unit.rungs:
            block = blocks.get(name)
            if not isinstance(block, Mapping):
                continue
            declared = _block_declares(block)
            merged = _merge_resolved(block, resolved)
            if (
                not declared
                and spec is not None
                and spec.geometry is None
                and not spec.moe
            ):
                launch = dict(merged.get("launch") or {})
                for key, value in _sizing_keys(spec).items():
                    launch.setdefault(key, value)
                merged["launch"] = launch
            if merged != block:
                blocks[name] = merged
                changed = True
    if not changed:
        return None
    fleet["units"] = blocks
    try:
        _atomic_write(fleet_path, _render_stamped_fleet(fleet))
    except OSError as exc:
        raise EmitError(f"{fleet_path}: cannot be written — {exc}") from exc
    return fleet_path


def _emit(args: argparse.Namespace) -> int:
    """Write one compose file per launch spec for the ladder's serving units.

    A launch spec is what comes up together, which is a host wherever a host's
    units are co-residents and is one model wherever they take turns on a port.
    Nothing is started. See :mod:`mcgyvr.emit` — this hands the operator a
    launch spec and stops.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # A locked setup is rendered from what it states and never sized, so it is
    # decided before a scan is read: a locked unit needs none.
    try:
        fleet = _locked_fleet(config)
    except (FleetFileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    if fleet is not None:
        return _emit_locked(fleet, args, config.path)

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
    specs = _model_specs()
    try:
        units = units_for(config, scans, specs=specs, ctx_per_slot=args.ctx_per_slot)
        # What each unit's sizing says beside its answer (`Fit.notes`), such as
        # a host memory figure it has not read; a fitting unit's `why` reaches
        # no one else. Before `hold_together`, which may refuse the set.
        for unit in sorted(units, key=lambda u: u.key.slug):
            for note in unit.fit.notes:
                print(f"note: {unit.key.slug}: {note}", file=sys.stderr)
        # `hold_together` returns a sentence for each host it cut into
        # alternatives; they are printed as warnings below so the cut is not
        # only a second `wrote ...` line.
        cut = hold_together(units, scans)
    except UnitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    out = Path(args.out) if args.out else Path.cwd()
    # vLLM's sleep mode and its unauthenticated routes, only where the config
    # asked mcgyvr to sleep and wake cards (`emit.sleep_mode`).
    asleep = emit_sleep_mode(config)

    # Before the files and before the check, because it is the fact both of
    # them are about: a host that was cut into alternatives has N files where it
    # had one, only one of which is ever up.
    for said in cut:
        print(f"warning: {said}", file=sys.stderr)

    # `--check` is the whole answer to "the config moved and the rig did not".
    # It is here rather than in the door because this is the function that
    # knows what a config implies, and the comparison must be against the
    # bytes this same call would write — `check_all` shares the plan with
    # `emit_all` so the two cannot drift apart the way the thing they are
    # detecting did.
    if args.check:
        try:
            drifted = check_all(units, root=out, sleep_mode=asleep)
        except UnitError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return Exit.REFUSED
        except (EmitError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return Exit.ERROR
        return _report_drift(
            drifted,
            unplanned(units, out, sleep_mode=asleep),
            planned_paths(units, out, sleep_mode=asleep),
        )

    try:
        written = emit_all(units, root=out, sleep_mode=asleep)
    except UnitError as exc:
        # A ladder describing a shape mcgyvr will not stand behind, not a
        # failure to render one: same exit code as `hold_together`'s refusal,
        # which is the other thing that reads a unit set and declines it.
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except (EmitError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # The same launch that was just written to compose is stamped back into
    # the config's fleet.yaml, so a later lock of this setup is emittable and
    # admissible. A stamp failure is an error: a compose file and a fleet.yaml
    # that disagree are the exact drift this command exists to prevent.
    try:
        stamped = _stamp_launch(config, units, sleep_mode=asleep, specs=specs)
    except EmitError as exc:
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
    if stamped is not None:
        print(f"stamped {stamped}")
    print("\nNothing was started. `docker compose -f <file> up -d` is yours to run.")
    return Exit.OK


def _locked_fleet(config: Config) -> dict[str, Any] | None:
    """The config's ``fleet.yaml`` when it is a locked setup, else ``None``.

    Read with :mod:`mcgyvr.fleet.files`, because the run config drops
    ``fleets`` and ``unit_id`` as the lock's, and those are what a locked emit
    is cut by.
    """
    if config.path is None:
        return None
    where = config.path / FLEET_FILENAME
    if not where.is_file():
        return None
    fleet = load_fleet(where.read_text(encoding="utf-8"))
    return fleet if is_locked(fleet) else None


def _emit_locked(
    fleet: dict[str, Any], args: argparse.Namespace, setup: Path | None = None
) -> int:
    """Emit a locked setup: each unit's stated launch, one file per fleet per rig.

    ``setup`` is the directory the setup was loaded from: a unit's
    ``launch.seccomp`` names a profile relative to it, and that profile is
    written beside the compose file that names it.
    """
    if args.ctx_per_slot is not None:
        print(
            "refused: a locked unit serves the window its launch.argv states, "
            "so --ctx-per-slot has nothing to set",
            file=sys.stderr,
        )
        return Exit.REFUSED
    out = Path(args.out) if args.out else Path.cwd()
    try:
        if args.check:
            return _report_drift(
                check_locked(fleet, out, setup),
                unplanned_locked(fleet, out, setup),
                planned_locked_paths(fleet, out, setup),
            )
        written = emit_locked(fleet, out, setup)
    except LockedLaunchError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except (EmitError, UnitError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    for compose in written:
        print(f"wrote {compose}")
    print("\nNothing was started. `docker compose -f <file> up -d` is yours to run.")
    return Exit.OK


def _report_drift(
    drifted: Sequence[Drift], leftover: Sequence[Path], planned: Sequence[Path]
) -> Exit:
    """Say which compose files stopped matching the config, and stop.

    Nothing here writes: an operator re-emits and then restarts the container,
    and doing the first half for them would leave a rig serving argv that no
    file on disk has ever named. The exit code is
    :attr:`~mcgyvr.exits.Exit.MISMATCH`, which is what ``scan`` already returns
    for a record and a machine that stopped agreeing — this is that fact about
    a different pair.

    A missing file and a stale one are printed differently on purpose. The
    first is one command away from correct; the second is two, and the second
    of those is on the rig.

    **A third kind, and it is not a drift of any planned file.** `unplanned`
    names a launch spec on disk, for a rig this ladder still binds, that this
    config would not write — the `compose.<host>.yml` an earlier emit left
    behind when the host stopped fitting together, holding every unit on one
    card. It is reported at the same severity because while it is there
    :func:`mcgyvr.wake.compose_for` finds more than one launch spec for the card
    and declines to wake it. The repair is the other one, and the sentence says
    so — a drifted file is re-emitted, this one is deleted.
    """
    if not drifted and not leftover:
        # The files this config would write, asked of the function that writes
        # them.
        for path in planned:
            print(f"{path.name} is what this config emits")
        return Exit.OK

    for path in leftover:
        print(
            f"mismatch: {path} is a launch spec this config does not write. "
            f"`mcgyvr emit` leaves the files it no longer plans where they are, "
            f"so this is an older cut of the same rig — and while it is there a "
            f"wake finds more than one launch spec for that card and will not "
            f"pick one. Bring up what you mean and delete it; nothing here "
            f"deletes a file that may be what is running.",
            file=sys.stderr,
        )

    for item in sorted(drifted, key=lambda d: d.path.name):
        if item.missing:
            print(
                f"mismatch: no compose file at {item.path} — this config "
                f"names the rig and nothing has been emitted for it. Run "
                f"`mcgyvr emit` to write it.",
                file=sys.stderr,
            )
            continue
        print(
            f"mismatch: {item.path} is not what this config emits. The file "
            f"was written from an older config, so the rig is serving argv "
            f"nobody is reading any more. Run `mcgyvr emit` and then restart "
            f"the unit — the file alone changes nothing that is already up.",
            file=sys.stderr,
        )
        for line in item.diff():
            print(f"  {line}", file=sys.stderr)
    return Exit.MISMATCH


def _report_mismatches(found: Sequence[Mismatch], stream: TextIO) -> None:
    if not found:
        return
    print("mismatch: this machine no longer matches its last scan:", file=stream)
    for item in found:
        print(f"  {item.field}: was {item.prior}, now {item.measured}", file=stream)


def _scans(root: Path) -> dict[str, Scan]:
    """Every machine recorded under ``root``, keyed by the name it calls itself.

    That is ``platform.node()``, which is not the name a unit's ``address``
    carries; :func:`_resolve_hosts` is what bridges the two. Keying by the
    recorded name and widening afterwards keeps this function a faithful
    reading of the directory — one key per machine, no invented names — so the
    reconciliation is somewhere a reader can find it and argue with it.

    A record that cannot be read is skipped rather than fatal, on the same rule
    the rest of the scan layer runs on: the answer to an unreadable scan is to
    take another one, and that is what ``_emit``'s never-scanned refusal asks
    for anyway.
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
    for name in config.ladder.names:
        unit = config.units.get(name)
        if unit is None:
            raise UnitError(f"{name}: no unit named {name!r}")
        wanted[name] = host_of(unit.address)
    return wanted


#: Names that cannot mean any machine but the one this process is running on.
#: Everything numeric is left to :mod:`ipaddress` below, which knows the whole
#: of ``127.0.0.0/8`` and ``::1`` without this file listing them.
_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _names_this_machine(name: str) -> bool:
    """Whether ``name`` can only ever mean the machine this process runs on.

    ``0.0.0.0`` counts. It is not a loopback address, but nothing else can be
    reached at it either: written in a unit's ``address`` it means "the server I am
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

    Without this, ``emit`` refuses the machine it is running on. A config
    written by ``mcgyvr setup`` says ``address: http://localhost:8080``,
    ``mcgyvr scan`` files the record under ``platform.node()``, and the two
    never agree — so the most ordinary setup there is, one rig serving itself,
    reports "localhost has never been scanned" the instant after it was
    scanned.

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


def _local_scan(scans: dict[str, Scan], os_machine_id: str) -> Scan | None:
    """The recorded scan of this very machine, or None if it has never run one."""
    for recorded in scans.values():
        if recorded.machine.id == os_machine_id:
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


def _model_spec(model: Model, moe: bool, name: str | None = None) -> ModelSpec:
    """One serving spec from one capability row; the table's decimal GB to GiB.

    ``name`` is the key the catalogue files the spec under, which is normally
    the row's ``id``; a row that also carries a catalog ``model_id`` is filed
    under that id too (the same measured numbers, so a unit named by its
    catalog pick resolves to this benchmarked row).
    """
    return ModelSpec(
        name=name or model.id,
        vram_gb=model.vram_gb_working / GB_PER_GIB,
        ram_gb=0.0,
        disk_gb=model.weights_gb / GB_PER_GIB,
        vae_decode_gb=(model.vae_decode_gb or 0.0) / GB_PER_GIB,
        cpu_only=model.cpu_only,
        moe=moe,
        geometry=None,
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def _model_specs() -> tuple[ModelSpec, ...]:
    """Serving specs for the rows of the shipped capability estimates.

    The shipped model catalog's own facts are folded in first, keyed by each
    entry's ``model_id``: a catalog pick the capability table does not name is
    still servable, sized from the file's bytes and its own context and KV
    figures (:func:`_catalog_specs`). Then the capability table's measured
    rows are added, keyed by BOTH their ``id`` and (when one is mapped) their
    ``model_id``, so the measured ``vram_gb_working`` wins over the computed
    catalog figure wherever the two name one model.

    ``vram_gb`` and ``disk_gb`` come off the typed reader. Whether a model has
    experts — and so a knob for *where* its weights sit — is in the table file
    but not in :class:`mcgyvr.capability.Model`, so it is read
    from the same file rather than guessed from a name. Getting it wrong is not
    cosmetic: a dense model that does not fit is a refusal, while an MoE that
    does not fit is a model that fits differently (:mod:`mcgyvr.serving`).

    ``geometry`` is ``None`` for every row because neither the table nor the
    catalog carries GGUF geometry. A dense row is therefore sized on its
    scalar figures, one slot wide; an MoE row is refused rather than sized
    (:func:`mcgyvr.serving.fit`), because ``--n-cpu-moe`` moves whole blocks
    and what each block's experts weigh is in the tensor table and nowhere
    else. An operator who has scanned the file points
    ``units.<name>.launch.geometry_json`` at the scan, and that lifts the
    refusal for the model they scanned — on the scan's numbers, not the
    table's.

    The table is in decimal GB and sizing is in GiB; the conversion happens
    here, once (:data:`mcgyvr.capability.GB_PER_GIB`).

    ``ram_gb`` is ``0.0`` for every row, dense and MoE alike. It is a floor an
    operator may raise, not a declaration this function can make: what an MoE
    actually spills depends on the card and is derived per machine by
    :func:`mcgyvr.serving._placement`.
    """
    specs: list[ModelSpec] = list(_catalog_specs())
    architectures = _architectures()
    for model in load().models:
        moe = architectures.get(model.id) == "moe"
        specs.append(_model_spec(model, moe))
        if model.model_id is not None and model.model_id != model.id:
            specs.append(_model_spec(model, moe, name=model.model_id))
    return tuple(specs)


def _catalog_specs() -> tuple[ModelSpec, ...]:
    """Serving specs derived from the shipped model catalog's own facts.

    A catalog pick the capability table does not name is still servable: the
    file's bytes and the KV cache its own ``context_length`` and
    ``kv_bytes_per_token`` price give a dense scalar spec, one slot wide, with
    no GGUF geometry. ``disk_gb`` is the file's bytes in GiB; ``vram_gb`` is
    the weights plus the full-context KV cache, also in GiB, so the fit check
    no longer relies on a measured scalar that may not exist. ``moe`` and
    ``cpu_only`` are false because these rows are dense GGUF checkpoints, and
    ``geometry`` is ``None``: the catalog carries no tensor table.
    """
    from mcgyvr.knowledge import store as knowledge_store
    from mcgyvr.knowledge.record import KnowledgeError

    try:
        records = knowledge_store.shipped()
    except KnowledgeError as exc:
        raise CapabilityTableError(str(exc)) from exc
    specs: list[ModelSpec] = []
    for one in records:
        size_gib = one.size_bytes.value / (1024**3)
        kv_gib = one.context_length.value * one.kv_bytes_per_token.value / (1024**3)
        specs.append(
            ModelSpec(
                name=one.model_id,
                vram_gb=size_gib + kv_gib,
                ram_gb=0.0,
                disk_gb=size_gib,
                moe=False,
                cpu_only=False,
                geometry=None,
                kv_cache_dtype_k="f16",
                kv_cache_dtype_v="f16",
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

    **A blank is not "the caller named none".** Every path here is optional and
    resolves a default when absent; an empty string is falsy and equals
    ``Path('.')``, so unrefused it would take that default — for ``--record``,
    the current directory.

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
            "behind. Pass a path, or leave the argument off to take the default "
            "on purpose."
        )
    return value


class _RepoByPosition(argparse.Action):
    """The old spelling, a repository typed by position, refused by name.

    Hidden from the usage: it is not an argument, only the catch for one that
    is no longer taken. Without it the old form meets argparse's bare
    "unrecognized arguments", which says nothing about ``--repo``. Absent, it
    is never called (its default is ``SUPPRESS``) and leaves nothing behind.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise argparse.ArgumentError(
            None,
            f"the repository is named with --repo, not by position: --repo {values}",
        )


def _add_repo(parser: argparse.ArgumentParser, what: str) -> None:
    """``--repo PATH``, the one way every verb is told its repository.

    ``run`` named it with this flag and five other verbs by position, so the
    flag a user learned on ``run`` was refused everywhere else. Every verb now
    takes the flag, defaulting to the current directory and refusing a blank
    the way ``run`` always has (:func:`_named_path`); a repository typed by
    position is refused by :class:`_RepoByPosition`.
    """
    parser.add_argument(
        "--repo",
        default=".",
        type=_named_path,
        metavar="PATH",
        help=f"{what} (default: .)",
    )
    parser.add_argument(
        "_repo_by_position",
        nargs="?",
        default=argparse.SUPPRESS,
        action=_RepoByPosition,
        help=argparse.SUPPRESS,
    )


def add_config(
    parser: argparse.ArgumentParser,
    *,
    dest: str = "config",
    what: str = "config to read",
) -> None:
    """``--config PATH``, the one way every verb is told which setup to read.

    ``run`` took the setup as ``--config`` while ``config`` and ``local_pool``
    took it by position, ``catalog`` as ``--against``, and ``sandbox``,
    ``fleet alerts`` and the ``rig`` agent had no way to name it, so the flag a
    user learned on ``run`` was refused elsewhere (e2e run 2, R9). Every verb
    that reads the setup now takes it, with ``run``'s meaning and precedence:
    the directory (or one merged file) it names wins over ``$MCGYVR_CONFIG``,
    the working directory and the live fleet, and leaving it off takes that
    chain. ``tests/test_every_command_that_reads_a_config_takes_dash_dash_config.py``
    walks the parser so a new verb cannot miss it.

    ``dest`` is for a verb whose older spelling is kept beside the flag (a
    positional, ``--against``): both store into it through
    :class:`_OneSetup`, so the handler reads one value and two different
    setups on one line are refused.
    """
    parser.add_argument(
        "--config",
        dest=dest,
        default=argparse.SUPPRESS,
        type=_named_path,
        metavar="PATH",
        action=_OneSetup,
        help=f"{what} (default: {CONFIG_DEFAULT_HELP})",
    )


class _OneSetup(argparse.Action):
    """Store a setup path, refusing a second, different one on the same line.

    The action of ``--config`` and of the older spelling a verb keeps beside it
    (``mcgyvr config PATH``, ``catalog --against PATH``). A value that names no
    path — an absent positional, a bare ``--against`` — never replaces one
    that does, so the order they are typed in does not matter. Two paths that
    differ are a usage error through the subparser's own ``error`` (exit 2):
    picking one would be guessing which setup the person meant.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        earlier = getattr(namespace, self.dest, None)
        if not isinstance(values, str):
            if not isinstance(earlier, str):
                setattr(namespace, self.dest, values)
            return
        if (
            isinstance(earlier, str)
            and Path(earlier).expanduser() != Path(values).expanduser()
        ):
            parser.error(
                f"the command line names two setups, {earlier} and {values}; "
                "name one, with --config"
            )
        setattr(namespace, self.dest, values)


def _name_the_writer(run: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Resolve who is writing the journal, or refuse at parse time.

    Before a config is read, a sandbox opened or a directory created, through
    the subparser's own ``error`` so the refusal reads like every other usage
    error and exits 2. The writer is the session that typed the command
    (:mod:`mcgyvr.session`): ``--orchestrator ID`` if given, else the Claude
    Code or Pi session in the environment, else a refusal whose message names
    all three. A default derived from the process is a single-orchestrator
    assumption (the lab's port-from-local-ai note, §9), so there
    is no default, only a flag and two variables to ask for.

    An id containing ``/`` is refused here too, because the id *is* the file
    name — ``DIR/<ID>.jsonl`` — and ``agent/a`` would write ``DIR/agent/a.jsonl``
    with its blobs under ``DIR/agent/blobs``, where an index over ``DIR`` finds
    neither.

    A blank id is refused here as well, at parse time and exit 2. The
    environment's session does not stand in for it: a
    caller who typed the flag was naming the writer, and an empty value is that
    caller getting the name wrong rather than declining to give one.
    """
    from mcgyvr.session import SessionError, resolve

    if args.orchestrator is not None and not args.orchestrator.strip():
        run.error(
            "--orchestrator was given an empty id: a row that cannot say which "
            "orchestrator produced it is the hole the field exists to close. "
            "Pass an ID, or leave the flag off to be named by the session "
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


def _mcorch_serve(args: argparse.Namespace) -> int:
    """Serve the orchestrator rung as the agent, at an Anthropic Messages address.

    Refuses a config whose orchestrator is not ``type: mcorch`` — the command
    has nothing to serve then — and, under a live profile, a fleet live
    admission does not admit (:func:`_admitted_live`), as ``run`` is. Binds the
    loopback and the facade's own port unless told otherwise; prints where it
    listens and the writer id it journals under, so a reader can find the
    transcript; runs until interrupted.
    """
    from mcgyvr.config import MCORCH
    from mcgyvr.decision import UnboundRoleError
    from mcgyvr.local_pool import SourceUnavailableError
    from mcgyvr.mcorch import bind, serve
    from mcgyvr.mcorch.authoring import AuthoringUnavailableError

    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    if config.get("orchestrator.type") != MCORCH:
        print(
            f"refused: orchestrator.type is {config.get('orchestrator.type')!r}, "
            f"and `mcgyvr mcorch serve` serves only `orchestrator.type: {MCORCH}`. "
            "Set it, with `orchestrator.unit`, `orchestrator.authoring` and "
            "`jev.unit`, or use the orchestrator the config has.",
            file=sys.stderr,
        )
        return Exit.REFUSED
    if config.get("profile") == "live" and _admitted_live(config) is not None:
        return Exit.REFUSED
    try:
        bound = bind.bind(config, journal_dir=bind.journal_dir(config))
    except (UnboundRoleError, SourceUnavailableError, AuthoringUnavailableError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED

    address = args.bind if args.bind else serve.DEFAULT_BIND
    port = args.port if args.port is not None else serve.FACADE_PORT
    server = serve.make_server(bind.facade(bound), bind=address, port=port)
    host, bound_port = str(server.server_address[0]), int(server.server_address[1])
    print(f"mcorch serving http://{host}:{bound_port} as writer {bound.writer}")
    print(f"transcript: {bound.transcript.path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return Exit.OK


def _fleet_lock(args: argparse.Namespace) -> int:
    """Write the fleet lock from the fleet, evidence and policy files named."""
    import json

    from mcgyvr.derived import DerivedNumbersError, class_tolerances
    from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
    from mcgyvr.fleet.lock import LockRefusedError, write
    from mcgyvr.fleet.roots import HOME_DIR, is_live, lock_root

    dev_root = lock_root("dev")
    assert dev_root is not None, "the dev lock root is the run root, a path"
    root = Path(args.root) if args.root else dev_root
    if is_live(root):
        print(
            f"error: {root} is or lies under a folder live fleets are read from (the "
            f"config folder, or {HOME_DIR}). A lock is written from dev runs "
            "into the dev root and reaches live only through `mcgyvr fleet "
            "promote`",
            file=sys.stderr,
        )
        return 1
    # One authoritative parser: ``fleet.yaml`` and ``policy.yaml`` are the
    # operator-authored files ``mcgyvr.fleet.files`` defines, so the lock reads
    # them through it rather than guessing JSON. Evidence stays JSON: a dev run
    # writes it.
    try:
        fleet = load_fleet(Path(args.fleet).read_text(encoding="utf-8"))
        policy = (
            load_policy(Path(args.policy).read_text(encoding="utf-8"))
            if args.policy
            else None
        )
    except FleetFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # Evidence stays JSON: a dev run writes it, so a bad file is named here
    # rather than left as a traceback.
    try:
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # The class tolerances, looked up in `mcgyvr.derived`: the rule is pinned in
    # `mcgyvr.fleet.lock`, the values are estimates the user can set. The lock
    # weighs only warm decode against NVMe, so it reads decode's classes.
    try:
        tolerances = {"warm_decode_class_pct": class_tolerances()["warm_decode_tok_s"]}
    except DerivedNumbersError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        write(root, fleet, evidence, policy=policy, tolerances=tolerances)
    except LockRefusedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"locked: {root / 'records' / 'fleet'}")
    return 0


def _fleet_alerts(args: argparse.Namespace) -> int:
    """List the combinations the journal holds pulled, unit and field each.

    The journal is ``--journal``, else ``<journal.dir>/fleet`` of the live fleet
    — where ``mcgyvr fleet probe`` files (:func:`mcgyvr.fleet.probe.journal_dir`).
    The lock is read from the root the config's profile names
    (:func:`mcgyvr.fleet.roots.lock_root`) unless ``--root`` names one.
    """
    from mcgyvr.config import ConfigMissingError, field_at
    from mcgyvr.fleet.alerts import pulled
    from mcgyvr.fleet.probe import ProbeError, journal_dir
    from mcgyvr.fleet.roots import LiveFleetError, live_fleet_dir, lock_root

    if args.journal:
        journal = Path(args.journal)
    else:
        try:
            journal = journal_dir(live_fleet_dir())
        except (LiveFleetError, ProbeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    root: Path | None
    if args.root:
        root = Path(args.root)
    else:
        chosen = Path(args.config) if getattr(args, "config", None) else None
        try:
            profile = str(load_config(chosen).get("profile"))
        except ConfigMissingError as exc:
            if chosen is not None:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            spec = field_at("profile")
            profile = str(spec.default) if spec is not None else "live"
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            where = lock_root(profile)
        except LiveFleetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        # With no fleet named live there is no lock to clear a pull, so every
        # pull the journal holds is listed.
        root = where
    for combination, entries in pulled(journal, root).items():
        for entry in entries:
            print(f"{combination} {entry['unit_id']} {entry['field']}")
    return 0


def _fleet_promote(args: argparse.Namespace) -> int:
    """Write a new live fleet folder from one fleet's dev lock, or refuse it."""
    from mcgyvr.fleet.promote import PromoteRefusedError, promote
    from mcgyvr.fleet.roots import lock_root

    dev = lock_root("dev")
    assert dev is not None, "the dev lock root is the run root, always a path"
    try:
        folder = promote(dev, Path(args.setup), args.name)
    except PromoteRefusedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"promoted: {args.name} -> {folder}")
    return 0


def _fleet_use(args: argparse.Namespace) -> int:
    """Name a promoted fleet live, and say what the lock knows of the move.

    Any promoted folder whose layout matches its lock may be
    named; the move from the fleet that was live is reported as locked — in
    that fleet's ``next``, with the downtime and wake its lock measured — or
    as unmeasured. Nothing is started either way.
    """
    from mcgyvr.fleet.promote import PromoteRefusedError, use
    from mcgyvr.fleet.roots import layout_of

    try:
        switch = use(args.name)
    except (PromoteRefusedError, OSError) as exc:
        # OSError: a config folder that cannot be searched or written.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"live: {switch.name} ({switch.pointer})")
    if switch.previous is None:
        print("move: none, no fleet was live")
    elif switch.previous == switch.name:
        print(f"move: none, {switch.name} was already live")
    elif switch.locked:
        print(
            f"move: {switch.previous} -> {switch.name} is locked: "
            f"{layout_of(switch.previous)}'s lock lists {switch.layout} in next"
        )
        # The lock's own figures, as it recorded them.
        for move in switch.moves:
            wakes = ", ".join(
                f"{unit} {seconds} s"
                for unit, seconds in sorted((move.get("wake_s") or {}).items())
            )
            print(
                f"  {move.get('rig')}: downtime {move.get('downtime_s')} s"
                + (f", wake {wakes}" if wakes else "")
            )
    else:
        print(
            f"move: {switch.previous} -> {switch.name} is unmeasured: "
            f"{switch.unmeasured}. use starts nothing; a live serve up is "
            f"admitted from {switch.name}'s own lock"
        )
    if switch.untagged_date is not None:
        print(
            f"untagged: {switch.name} carries no lock date in its name; its lock "
            f"is dated {switch.untagged_date}. `mcgyvr fleet tag {switch.name}` "
            f"renames the folder to {switch.layout}@{switch.untagged_date}"
        )
    return 0


def _fleet_tag(args: argparse.Namespace) -> int:
    """Rename a folder promoted before the ruling to <fleet>@<its lock date>."""
    from mcgyvr.fleet.promote import PromoteRefusedError, tag

    try:
        folder = tag(args.name)
    except (PromoteRefusedError, OSError) as exc:
        # OSError: a config folder that cannot be searched or written.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"tagged: {args.name} -> {folder}")
    return 0


def _fleet_probe(args: argparse.Namespace) -> int:
    """Probe the live fleet's idle units by their lock's own method, and judge them.

    Exit 1 when the probe cannot run at all or a unit's probe could not run;
    an alert is printed and filed, and is not a failed probe
    (:mod:`mcgyvr.fleet.probe`).
    """
    from mcgyvr.fleet import linkread, read
    from mcgyvr.fleet.probe import ProbeError, run

    try:
        report = run(
            units=args.units or None,
            reader=read.spawn_read,
            link_reader=linkread.door_timer(),
        )
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for unit, figures in report.probed.items():
        shown = ", ".join(f"{name} {value:.2f}" for name, value in figures.items())
        print(f"probed {unit}: {shown}")
    for unit, count in report.busy.items():
        print(f"busy {unit}: {count} in flight, not probed")
    for unit in report.contended:
        print(f"contended {unit}: took work during the probe; filed, not judged")
    for unit, (fields, reason) in report.not_read.items():
        print(f"not read {unit}: {', '.join(fields)} ({reason})")
    for unit, (fields, reason) in report.off_the_rig.items():
        print(f"not judged {unit}: {', '.join(fields)} recorded ({reason})")
    for alert in report.alerts:
        print(f"alert {alert['unit_id']} {alert['field']}")
    for key, says in report.links.items():
        print(f"link {key}: {says}")
    for unit, why in report.failed.items():
        print(f"error: {unit}: {why}", file=sys.stderr)
    for key, why in report.links_failed.items():
        print(f"error: link {key}: {why}", file=sys.stderr)
    return report.exit_code


def _build() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """The whole command line, plus the ``run`` subparser on its own.

    Two returns because :func:`_name_the_writer` refuses a blank
    ``--orchestrator`` through the subparser that owns the flag, so its usage
    line is the one the caller was typing against
    (tests/test_a_blank_orchestrator_is_refused_not_filed.py).
    """
    from mcgyvr.catalog import catalog

    use_case_names = tuple(u.name for u in catalog().use_cases)
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
    )
    parser.add_argument(
        "--version",
        action=_Version,
        nargs=0,
        help="the product version, and the path of the config a run here would use",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    caps = sub.add_parser(
        "capabilities",
        # argparse does not abbreviate subcommands the way it abbreviates
        # flags, so the short name is spelled out as an alias.
        aliases=["caps"],
        help="show the shipped estimates by card class",
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
        action=_OneSetup,
        help="the same as --config, by position",
    )
    add_config(conf, dest="path")
    conf.set_defaults(func=_config)

    local_pool = sub.add_parser(
        "local_pool",
        help="show the ladder as it resolves against the declared sources",
    )
    local_pool.add_argument(
        "path",
        nargs="?",
        default=None,
        type=_named_path,
        action=_OneSetup,
        help="the same as --config, by position",
    )
    add_config(local_pool, dest="path")
    local_pool.add_argument(
        "--probe",
        action="store_true",
        help=(
            "also ask each source whether it is answering, and drop the rungs "
            "of any that is not (off by default: resolving a ladder should not "
            "require a network)"
        ),
    )
    local_pool.add_argument(
        "--probe-timeout",
        type=float,
        default=PROBE_TIMEOUT_S,
        metavar="SECONDS",
        help=f"how long a source has to answer a probe (default: {PROBE_TIMEOUT_S:g})",
    )
    local_pool.set_defaults(func=_local_pool)

    cat = sub.add_parser(
        "catalog",
        help="show the task types mcgyvr can be asked for, and what each guarantees",
    )
    cat.add_argument(
        "name",
        nargs="?",
        default=None,
        help=(
            "show one task type or deterministic operation in full "
            "(default: list them all)"
        ),
    )
    cat.add_argument(
        "--against",
        nargs="?",
        default=False,
        const=None,
        type=_named_path,
        metavar="CONFIG",
        action=_OneSetup,
        help=(
            "resolve against a configured ladder and name the types it cannot "
            f"start (default config: {CONFIG_DEFAULT_HELP})"
        ),
    )
    add_config(
        cat,
        dest="against",
        what="resolve against this setup's ladder, as --against PATH does",
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
    sca.add_argument(
        "--rig",
        metavar="RIG",
        default=None,
        help=(
            "scan RIG instead, over your own ssh (read-only), and save it as the "
            f"serving door's rig file RIG.json in {RIGS_SHOWN}, which a door run "
            "from an install holds the rig to; says what moved since the last"
        ),
    )
    sca.add_argument(
        "--model-store",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "a directory holding *.gguf and *.safetensors checkpoints to "
            "inventory as models-on-disk, in addition to the weights dir "
            "(repeatable)"
        ),
    )
    sca.set_defaults(func=_scan)

    rec = sub.add_parser(
        "recommend",
        help="print one JSON plan: which checkpoint and engine serve a profile",
    )
    rec.add_argument(
        "--profile",
        required=True,
        choices=recommend_module.PROFILES,
        help="the usage profile to place for",
    )
    rec.add_argument(
        "--users",
        required=True,
        type=_users_count,
        metavar="N|single",
        help="how many users the placement serves: `single` or a positive number",
    )
    rec.add_argument(
        "--host",
        action="append",
        required=True,
        metavar="RIG",
        help="a rig to re-read over ssh and place on (repeatable)",
    )
    rec.add_argument(
        "--model-store",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "a directory on the rig holding *.gguf checkpoints (repeatable); "
            "when any fits, recommend only from it"
        ),
    )
    rec.set_defaults(func=_recommend)

    srv = sub.add_parser(
        "serve",
        help="put a card to sleep, or wake it, through the serving door",
    )
    srv.add_argument(
        "direction",
        choices=("sleep", "wake"),
        help=(
            "sleep drains every slot the card serves, then rests it at vLLM "
            "level 2 where every unit is vLLM and has the sleep route, and "
            "stops it otherwise; wake brings it back the way it went"
        ),
    )
    srv.add_argument(
        "--host",
        required=True,
        metavar="HOST",
        help="the rig, as the host in a unit's `address` names it",
    )
    srv.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    srv.set_defaults(func=_serve)

    man = sub.add_parser(
        "manage",
        help=(
            "let Jev sleep and wake the ladder's units by the queue on it "
            "(runs until interrupted)"
        ),
    )
    man.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    man.add_argument(
        "--once",
        action="store_true",
        help="read the queue and decide once, then stop",
    )
    man.set_defaults(func=_manage)

    emi = sub.add_parser(
        "emit",
        help="write a compose file per launch spec for the ladder's serving units",
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
    # Not defaulted and not required: a unit that declares `window` is emitted
    # at it, and this flag speaks for the units that declare none. A unit with
    # no window from either is refused (`serving._window_for`), because the
    # cache, the `-c` on the argv and the `--n-cpu-moe` floor are all priced
    # against it.
    emi.add_argument(
        "--ctx-per-slot",
        type=int,
        metavar="N",
        help=(
            "the window this run serves per slot, for units that declare no "
            "`window` of their own; `-c` is this times the slot count, "
            "and the cache law is fed the same product. A unit that declares "
            "its window is emitted at that window, and a flag that contradicts "
            "a declaration is refused rather than preferred"
        ),
    )
    emi.add_argument(
        "--check",
        action="store_true",
        help=(
            "compare the files already under --out with what this config "
            "emits and write nothing: exit 4 when they disagree, naming each "
            "file and the lines that moved. A config edited without "
            "re-emitting is two configurations, and the rig goes on serving "
            "the older one"
        ),
    )
    emi.set_defaults(func=_emit)

    sbx = sub.add_parser(
        "sandbox",
        help="show the sandbox mode and the stack detected for a repository",
    )
    _add_repo(sbx, "the repository to inspect")
    sbx.add_argument(
        "--cache",
        action="store_true",
        help="list cached task images with their sizes instead of inspecting a repo",
    )
    sbx.add_argument(
        "--clear-cache",
        action="store_true",
        help="remove every task image mcgyvr has cached",
    )
    add_config(sbx, what="setup whose `sandbox` block a run here would read")
    sbx.set_defaults(func=_sandbox)

    setup = sub.add_parser(
        "setup",
        help=(
            "scan, plan, download, emit and write a config bound to what is reachable"
        ),
    )
    setup.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="HOST",
        help=(
            "bind backends on this machine too, by name or address "
            "(repeatable; default: localhost only)"
        ),
    )
    setup.add_argument(
        "--api",
        action="append",
        default=[],
        metavar="SPEC",
        help=(
            "bind a hosted API unit, which needs no GPU and no local backend, "
            "as `model=<id>,address=<url>,api_key_env=<VAR>` (repeatable), "
            "optionally `,output_tokens=<N>` for the room its replies are "
            f"given (default {API_OUTPUT_TOKENS}: a reasoning model spends it "
            "thinking before it writes). api_key_env is the NAME of the environment "
            "variable holding your key, never the key itself"
        ),
    )
    setup.add_argument(
        "path",
        nargs="?",
        default=None,
        action=_OneSetup,
        help=f"where to write (default: {INIT_DEFAULT_HELP})",
    )
    # The setup it writes, and the one it reads first to keep hand edits. Its
    # default chain is its own (INIT_DEFAULT_HELP): never the live fleet.
    setup.add_argument(
        "--config",
        dest="path",
        default=argparse.SUPPRESS,
        type=_named_path,
        metavar="PATH",
        action=_OneSetup,
        help="the same as PATH: the setup to write",
    )
    setup.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing config, discarding hand edits",
    )
    setup.add_argument(
        "--priority",
        default=None,
        choices=PRIORITIES,
        metavar="PRIORITY",
        help=(
            "compose the ladder for this priority (throughput, quality or "
            "cost) instead of writing the default ladder. The decision runs on "
            "the first detected backend; every number in the file stays "
            "measured or the schema's, never the model's"
        ),
    )
    setup.add_argument(
        "--profile",
        default=None,
        metavar="TEXT",
        help=(
            "deprecated, removed in the release after next: use --priority. "
            "A word naming a priority maps onto it; other text is ignored. Not "
            "the config's `profile: live|dev`"
        ),
    )
    setup.add_argument(
        "--use-case",
        default=None,
        choices=use_case_names,
        metavar="USE_CASE",
        help=(
            "which use case this install serves: coding (the deterministic "
            "gate), chat (raw endpoint), agent (un-gated, from its sources) or "
            "media-gen (media_valid + safety + ASR-WER); default: coding"
        ),
    )
    setup.add_argument(
        "--deployment",
        default=None,
        choices=("hybrid", "local-only"),
        metavar="MODEL",
        help=(
            "how mcgyvr is run: hybrid (an API-tier orchestrator drives it) or "
            "local-only (mcgyvr is the backend and provisions a local "
            "orchestrator for a non-chat use case); default: hybrid"
        ),
    )
    setup.add_argument(
        "--jev",
        default=None,
        metavar="UNIT",
        help=(
            "dedicate VRAM to a Jev unit: the written unit every typed decision "
            "asks, never slept or woken (an opt-in; no model is picked for you)"
        ),
    )
    setup.add_argument(
        "--mcorch",
        default=None,
        metavar="UNIT",
        help=(
            "enable mcorch on a written unit: the conversational agent a harness "
            "points at (`mcgyvr mcorch serve`); needs --jev and --window, and "
            "writes orchestrator.type mcorch, authoring direct, deployment "
            "local-only"
        ),
    )
    setup.add_argument(
        "--window",
        default=None,
        type=int,
        metavar="TOKENS",
        help=(
            "with --mcorch: the tokens the agent's unit serves in one request, "
            "read back off the running process"
        ),
    )
    setup.add_argument(
        "--session-sandbox",
        default=None,
        choices=("tempdir", "docker"),
        metavar="MODE",
        help=(
            "the sandbox a chat or agent run gets when it runs no command, "
            "written as `sandbox.sessions`: tempdir (the default: no container "
            "is built or started, and Docker is not needed) or docker (opt in "
            "to a task container, as code and media get)"
        ),
    )
    setup.set_defaults(func=_setup)

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

    fleet = sub.add_parser(
        "fleet",
        help="lock a fleet, and read what the lock approves",
    )
    fleet_sub = fleet.add_subparsers(dest="fleet_command", required=True)
    flock = fleet_sub.add_parser(
        "lock",
        help=(
            "write the fleet lock from passing dev runs (into the dev root's lock tree)"
        ),
    )
    flock.add_argument(
        "--fleet",
        required=True,
        metavar="PATH",
        help="fleet.yaml to lock (units, rigs, fleets)",
    )
    flock.add_argument(
        "--evidence",
        required=True,
        metavar="PATH",
        help="dev-run evidence (rig cards, combination validations, moves) as JSON",
    )
    flock.add_argument(
        "--policy",
        default=None,
        metavar="PATH",
        help="policy.yaml whose ladder must name only fleet units (default: none)",
    )
    flock.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help=(
            "where the lock tree is written (default: the dev root — "
            "$MCGYVR_RUN_ROOT, else the checkout). Anything in or under the config "
            f"folder (${HOME_ENV}, else {HOME_DIR}) or in or under {HOME_DIR} is "
            "refused: a live fleet comes only from `mcgyvr fleet promote`"
        ),
    )
    flock.set_defaults(func=_fleet_lock)
    fpromote = fleet_sub.add_parser(
        "promote",
        help=(
            f"write a new live fleet folder FLEET@DATE/ under {FLEETS_SHOWN} "
            "from its dev lock, DATE being the lock's own validated_at day (one "
            "way; never over an existing folder)"
        ),
    )
    fpromote.add_argument(
        "name", metavar="FLEET", help="the fleet to promote, by its plain name"
    )
    fpromote.add_argument(
        "--setup",
        required=True,
        metavar="DIR",
        help=(
            "the dev setup directory (fleet.yaml and policy.yaml) the dev "
            "lock was written from"
        ),
    )
    fpromote.set_defaults(func=_fleet_promote)
    fuse = fleet_sub.add_parser(
        "use",
        help=(
            f"name a promoted fleet live, in {LIVE_FILE_SHOWN}, and say whether "
            "the move from the fleet that was live is one its lock measured"
        ),
    )
    fuse.add_argument(
        "name",
        metavar="FLEET@DATE",
        help="the promoted folder to run live (a pre-ruling folder by its plain name)",
    )
    fuse.set_defaults(func=_fleet_use)
    ftag = fleet_sub.add_parser(
        "tag",
        help=(
            "rename a fleet folder promoted before 2026-09-16 to FLEET@DATE/ "
            f"under {FLEETS_SHOWN}, DATE being its lock's validated_at day"
        ),
    )
    ftag.add_argument("name", metavar="FLEET", help="the untagged folder to rename")
    ftag.set_defaults(func=_fleet_tag)
    fprobe = fleet_sub.add_parser(
        "probe",
        help=(
            "judge the live fleet's idle units by their lock's own measurement, "
            "filed under <journal.dir>/fleet"
        ),
    )
    fprobe.add_argument(
        "units",
        nargs="*",
        metavar="UNIT",
        help="the awake units to probe (default: every awake unit of the live fleet)",
    )
    fprobe.set_defaults(func=_fleet_probe)
    falerts = fleet_sub.add_parser(
        "alerts",
        help="list the combinations the journal holds pulled",
    )
    falerts.add_argument(
        "--journal",
        default=None,
        metavar="DIR",
        help=(
            "where the fleet journal was filed (default: <journal.dir>/fleet of "
            "the live fleet, where `mcgyvr fleet probe` files)"
        ),
    )
    falerts.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help=(
            "where the lock tree is read (default: the lock root the config's "
            f"profile names — for live the fleet {LIVE_FILE_SHOWN} names, "
            "for dev the dev root)"
        ),
    )
    add_config(falerts, what="setup whose `profile` picks the lock root")
    falerts.set_defaults(func=_fleet_alerts)

    from mcgyvr.rig import verbs as rig_verbs

    rig_verbs.add_parser(sub, add_config=add_config)

    mcorch = sub.add_parser(
        "mcorch",
        help="serve the orchestrator rung as the agent a harness talks to",
    )
    mcorch_sub = mcorch.add_subparsers(dest="mcorch_command", required=True)
    mserve = mcorch_sub.add_parser(
        "serve",
        help=(
            "serve an Anthropic Messages API address for a harness to point at "
            "(ANTHROPIC_BASE_URL); needs `orchestrator.type: mcorch`"
        ),
    )
    mserve.add_argument(
        "--config",
        default=None,
        type=_named_path,
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    mserve.add_argument(
        "--bind",
        default=None,
        help=(
            "the address to listen on (default: the loopback; a LAN or tailnet "
            "address lets another machine's harness reach it)"
        ),
    )
    mserve.add_argument(
        "--port",
        default=None,
        type=int,
        help="the port to listen on (default: the facade's own)",
    )
    mserve.set_defaults(func=_mcorch_serve)

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
            "runs is this file's — the ladder order, each unit's `attempts` and "
            "the `max_escalations` and `max_attempts` ceilings — never a flag "
            f"(default: {CONFIG_DEFAULT_HELP})"
        ),
    )
    _add_repo(run, "the git repository the work is done against")
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
            "`docker`, which is refused when no daemon answers unless "
            "`sandbox.allow_fallback` is on"
        ),
    )
    run.add_argument(
        "--commit",
        # No default, as for `--sandbox`: `delivery.commit` answers when no flag
        # is typed (`_settle_delivery`).
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "commit the change when the gate accepts it, or not (--no-commit), "
            "whatever `delivery.commit` says. Not committed — the default — the "
            "accepted change is left in the working tree and the repository is "
            "otherwise untouched: no commit, no branch. Committed, it goes onto "
            "the branch you have checked out, or onto `delivery.branch`"
        ),
    )
    run.add_argument(
        "--branch",
        default=None,
        metavar="NAME",
        help=(
            "commit onto branch NAME instead of the one you have checked out, "
            "which is left exactly as it was; implies --commit and overrides "
            "`delivery.branch`. Created from HEAD when absent"
        ),
    )
    run.add_argument(
        "--record",
        default=None,
        type=_named_path,
        metavar="DIR",
        help=(
            "also journal this run under DIR, as a complete second copy for "
            "your own reading: DIR/<ID>.jsonl, DIR/blobs/, DIR/results/ and "
            "DIR/sessions/, read "
            "back from DIR directly. This does not move mcgyvr's "
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
            "stay distinguishable. Default: the session that typed this "
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

    ses = sub.add_parser(
        "sessions",
        help="list the chat and agent sessions the journal keeps, or show one",
    )
    ses.add_argument(
        "id",
        nargs="?",
        default=None,
        help="show this session whole: question, answer, unit, outcome "
        "(default: list them, newest first)",
    )
    ses.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"whose `journal.dir` to read (default: {CONFIG_DEFAULT_HELP})",
    )
    ses.add_argument(
        "--journal",
        default=None,
        type=_named_path,
        metavar="DIR",
        help="read the sessions of this journal instead, e.g. a --record copy",
    )
    ses.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="list at most N sessions (default: 20)",
    )
    ses.set_defaults(func=_sessions)

    delegate = sub.add_parser(
        "delegate",
        help="turn a prompt plus a repository into validated contracts",
    )
    delegate.add_argument(
        "prompt",
        help="the natural-language request to decompose into contracts",
    )
    _add_repo(
        delegate,
        "the repository to work against: a local git checkout, or a URL to "
        "clone (https/git/file)",
    )
    delegate.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=(
            "config that binds the orchestrator role, which delegates the "
            f"prompt to (default: {CONFIG_DEFAULT_HELP})"
        ),
    )
    delegate.add_argument(
        "--into",
        default=None,
        metavar="DIR",
        help="clone a URL repo into DIR and keep it, instead of a temp dir",
    )
    delegate.add_argument(
        "--budget",
        type=int,
        default=None,
        metavar="TOKENS",
        help=(
            "cap the deterministic read at TOKENS estimated tokens before the "
            "orchestrator is asked (default: the decompose default)"
        ),
    )
    delegate.add_argument(
        "--output",
        default=None,
        metavar="DIR",
        help=(
            "write each emitted contract to DIR/<id>.json instead of printing "
            "them to stdout"
        ),
    )
    delegate.add_argument(
        "--run",
        action="store_true",
        help="execute each emitted contract through the existing run machinery",
    )
    delegate.add_argument(
        "--sandbox",
        default=None,
        choices=("docker", "tempdir"),
        help="sandbox mode for --run; default is `sandbox.mode`, then `docker`",
    )
    delegate.add_argument(
        "--commit",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "commit each accepted change, or not (--no-commit), whatever "
            "`delivery.commit` says (with --run)"
        ),
    )
    delegate.add_argument(
        "--branch",
        default=None,
        metavar="NAME",
        help="commit each accepted change onto branch NAME; implies --commit",
    )
    delegate.add_argument(
        "--record",
        default=None,
        type=_named_path,
        metavar="DIR",
        help="also journal each --run under DIR, as a complete second copy",
    )
    delegate.add_argument(
        "--orchestrator",
        default=None,
        metavar="ID",
        help="who writes the journal for --run (default: the session)",
    )
    delegate.set_defaults(func=_delegate)

    return parser, run


def build_parser() -> argparse.ArgumentParser:
    """The command line as a person types it.

    Public so what a run reads and what a person typed can be checked against
    each other.
    """
    return _build()[0]


class _Version(argparse.Action):
    """``--version``: the product, then the config a run here would be made under.

    Two lines and not one, because they are two identities: the wheel is the
    code, and the config is the setup. The config is the one `load()` locates —
    `$MCGYVR_CONFIG`, then a working directory holding `fleet.yaml`, then the
    fleet the config folder's `live.json` names — so the path printed is the
    config a run typed at this prompt would load. No config prints
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
            print(f"config: {config.path}")
        parser.exit(0)


@contextlib.contextmanager
def hanging_up_on_interrupt() -> Iterator[None]:
    """Ctrl-C hangs up on every dispatch of the process before it stops the
    command. A dispatch runs on a thread of a batch and ``KeyboardInterrupt``
    is the main thread's alone, which then waits for those threads to finish
    what they were asked, each unit decoding for nobody meanwhile. So, while
    a command runs, the interrupt first hangs up on them all
    (:func:`mcgyvr.runner.hang_up_all`: each unit's next write fails, each
    dispatch ends, none is made after), then is the ``KeyboardInterrupt`` it
    always was, from the same place. Only Python's own handler is replaced,
    and only on the main thread, where a signal is heard."""
    from mcgyvr import runner

    if (
        threading.current_thread() is not threading.main_thread()
        or signal.getsignal(signal.SIGINT) is not signal.default_int_handler
    ):
        yield
        return

    def interrupted(signum: int, frame: object) -> None:
        runner.hang_up_all()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupted)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, signal.default_int_handler)


def main(argv: Sequence[str] | None = None) -> int:
    parser, run = _build()
    args = parser.parse_args(argv)
    if args.func is _run:
        _name_the_writer(run, args)
        _one_delivery_answer(run, args)
    elif args.func is _delegate:
        _one_delivery_answer(parser, args)
    try:
        with hanging_up_on_interrupt():
            result: int = args.func(args)
    except FolderError as exc:
        # A folder variable that names no usable folder, or a guarded folder
        # that cannot be resolved: one line naming it, whichever command met
        # it first.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
