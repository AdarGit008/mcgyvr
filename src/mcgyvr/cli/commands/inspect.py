""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.availability import PROBE_TIMEOUT_S
from mcgyvr.capability import (
    ESTIMATES_NOTICE,
    CapabilityTableError,
    load,
)
from mcgyvr.config import (
    ConfigError,
)
from mcgyvr.config import load as load_config

if TYPE_CHECKING:  #
    pass

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _named_path, _OneSetup, add_config


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
    #
    #
    #`.
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

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    print(f"{config.path}: {len(pool)} usable rung(s), in ladder order:\n")
    ladder_budget = 0
    for rung in pool.rungs:
        budget = int((config.get("attempts") or {}).get(rung.name, 1))
        ladder_budget += budget
        tries = "1 attempt" if budget == 1 else f"{budget} attempts"
        #
        #
        draws = draws_for(config, rung.name)
        if draws > 1:
            tries += f", {draws} draws"
        family = family_of(config, rung.name)
        print(f"  {rung.name:<20} {family.name:<14} {tries:<11} {rung.model}")
    if not pool.rungs:
        print("  (none — every rung's source is unusable)")
    else:
        #
        #
        #
        #
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

    #
    #
    #
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
        #
        #
        #be
        #
        print(f"\nProbed {len(availability.verdicts)} source(s):")
        for name, verdict in sorted(availability.verdicts.items()):
            state = "live" if verdict.live else "down"
            print(f"  {name:<20} {state:<5} {verdict.elapsed_s:.2f}s  {verdict.how}")

    #��
    #
    return 0


def _catalog(args: argparse.Namespace) -> int:
    from mcgyvr.catalog import CatalogError, catalog
    from mcgyvr.escalate import how_judged

    try:
        book = catalog()
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    #
    #
    #
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
            #
            #
            print(f"{len(unservable)} type(s) this ladder cannot start:")
            for name in sorted(unservable):
                print(f"  {name}")
        else:
            print(f"Every type is servable by the ladder in {config.path}.")
    return 0


def _contract(args: argparse.Namespace) -> int:

    from mcgyvr.contract import ContractError, load
    from mcgyvr.escalate import how_judged

    try:
        contract = load(Path(args.path))
    except ContractError as exc:
        #
        #
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
        #
        #
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
    #
    #
    #
    reply = not contract.is_deterministic and not contract.kind.judges_a_change
    if reply:
        print(f"  risk:    {contract.risk}")
        print(f"  judged:  {how_judged(contract.kind)}")
    else:
        print(
            f"  risk:    {contract.risk} — verified by "
            f"{contract.verification.policy.replace('_', ' ')}"
        )
    #
    #
    #
    #
    if contract.is_session:
        print(
            f"  limits:  raw connection: no output cap, no prompt checks, "
            f"{contract.limits.attempts} attempt(s)"
        )
    elif not contract.is_deterministic:
        if contract.limits.max_output_tokens is not None:
            output_budget = f"<={contract.limits.max_output_tokens} output tokens"
        elif contract.needs_output_cap:
            #
            #
            #
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


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ""

    caps = sub.add_parser(
        "capabilities",
        #
        #
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
