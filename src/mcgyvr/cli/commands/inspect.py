"""The read-only `mcgyvr` commands: capabilities, config, local_pool, catalog, contract.

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


from mcgyvr import __version__, atomic


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
    LIVE_FILE_SHOWN,
    RIGS_SHOWN,
    STAGING_SHOWN,
    FolderError,
)


from mcgyvr.initialize import (
    PRIORITIES,
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
    render_fleet,
    unit_names,
)


from mcgyvr.scan import ModelOnDisk, Scan


from mcgyvr.serving import (
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    host_of,
    units_for,
)


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

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _OneSetup, _named_path, add_config


def _capabilities(args: argparse.Namespace) -> int:
    try:
        table = load()
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    models = table.fitting(args.vram) if args.vram else table.models
    if args.vram:
        print(
            f"Models that fit {args.vram:g} GB with working headroom. "
            f"{ESTIMATES_NOTICE}\n"
        )
    else:
        print(f"Shipped models. {ESTIMATES_NOTICE}\n")

    for model in models:
        backend = f" [{model.requires_backend} only]" if model.requires_backend else ""
        kept_out = "  not in a fit listing" if model.not_for_fit is not None else ""
        print(f"  {model.id:<28} {model.vram_gb_working:>5.1f} GB{backend}{kept_out}")
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


def add_parser(sub: argparse.ArgumentParser) -> None:
    """Register `capabilities`, `config`, `local_pool`, `catalog`, `contract`."""

    caps = sub.add_parser(
        "capabilities",
        # argparse does not abbreviate subcommands the way it abbreviates
        # flags, so the short name is spelled out as an alias.
        aliases=["caps"],
        help="show the shipped model estimates",
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

