"""The gate as the driver asks it of a sandbox.

``gate_workspace`` is the one function an attempt and the delivery path both
gate a change through: it refuses a workspace that holds a nested git entry,
and otherwise runs the gate over the tree the model left — the contract's scope
and the secret scan first, then the structured-data check, the language
adapters, the output-evidence rungs, the type check, the semantic rung and the
contract's acceptance commands, each skipped once an earlier one has recorded a
finding, with the contract's prose passed to the rungs that read it.
``gate_prose_workspace`` is the narrow form a prose or media reply gets, where
only the output rungs apply.

The rest of the module is what the attempt loop composes around those two: a
reply written into a fresh sandbox (``gate_in_sandbox``), a format-only
rejection tidied and gated again (``_cleaned``), a rejected tree repaired by
the deterministic tools and gated again (``_repair_and_regate``), the
reviewer's JEV check asked of the winning draw alone (``_typed_checks``), and
the reviewer's calls sent through the waker so a card that was slept is woken
for them (``_through``). ``task_ceiling``, ``acceptance_for``,
``output_checks_for`` and ``gate_adapters`` are the seams that turn a contract
and a config into the inputs those rungs take.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import mcgyvr.drive as _drive
from mcgyvr.deliver import Accepted
from mcgyvr.gate import Finding, Gate, GateResult
from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.adapter import SandboxRunner
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.jev import JevCheck
from mcgyvr.gate.output import ASR_WER, MEDIA_VALID, SAFETY_PASS, OutputChecks
from mcgyvr.gate.semantic import SemanticCheck
from mcgyvr.gate.typecheck import ParamMutation, TypeCheck
from mcgyvr.sandbox.base import nested_git
from mcgyvr.scope import inside
from mcgyvr.verify import Reviewer, independent

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Sequence
    from typing import Any

    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.decision import Decision
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.wake import Waker


def _jev_for(builder: str, reviewing: Reviewer | None) -> JevCheck | None:
    """The reviewer's JEV check, or ``None`` when it is not the one to ask.

    The check is asked only of a reviewer that was settled and whose model
    identity differs from the builder's: a model is not shown its own build to
    judge. ``None`` here means the typed rung does not run at all, which is why
    the caller carries the value as ``JevCheck | None`` rather than as an empty
    check that would answer nothing.
    """
    if reviewing is None or not independent(builder, reviewing.model):
        return None
    return reviewing.jev


def _through(
    waker: Waker | None, reviewer: Reviewer, *, jev_resident: bool = False
) -> Reviewer:
    """A reviewer whose calls are sent through the waker for its own unit.

    A reviewer with no unit — one reached by a command rather than by a rung the
    waker holds a card for — comes back as it is, and so does every reviewer
    when no waker was handed in. Otherwise ``ask`` and ``decide`` are wrapped in
    :meth:`~mcgyvr.wake.Waker.dispatching`, so a card that was put to sleep is
    woken before the call is sent, and a refusal is retried once the wake has
    run. ``jev_resident`` says the JEV unit is bound and so never slept: its
    ``decide`` is left unwrapped, since a wake around a resident unit would spend
    a round trip on a call that cannot be refused.
    """
    if waker is None or reviewer.unit is None:
        return reviewer
    unit = reviewer.unit
    ask, decide, jev = reviewer.ask, reviewer.decide, reviewer.jev

    def woken_ask(prompt: str) -> str:
        return waker.dispatching(unit, lambda: ask(prompt))

    def woken(seam: Callable[[Any], Decision]) -> Callable[[Any], Decision]:
        if jev_resident:
            return seam
        return lambda state: waker.dispatching(unit, lambda: seam(state))

    return replace(
        reviewer,
        ask=woken_ask,
        decide=woken(decide) if decide is not None else None,
        jev=replace(jev, decide=woken(jev.decide)) if jev is not None else None,
    )


def _typed_checks(
    contract: Contract,
    sandbox: Sandbox,
    gate: GateResult,
    bound: Accepted,
    jev: JevCheck | None,
) -> tuple[GateResult, Accepted]:
    """Ask the reviewer's JEV check of the winning draw, once it was accepted.

    The check reads the workspace's change, so the winner is written back into a
    reset sandbox first: whichever tree the sandbox was left holding, the text
    the check reads is ``bound.content`` and nothing else. The report's findings,
    observations and environment issues are folded into the gate result and the
    report is carried on ``jev``; the content is then read back out of the
    workspace, so what the caller delivers is the tree the check saw.

    Nothing is asked when there is no check, or when the gate refused: a
    rejected change has no accepted draw for a typed verdict to be about. A
    ``JevCheck`` is non-blocking by default, so what it says arrives as
    observations and this cannot turn an acceptance into a rejection.
    """
    if jev is None or not gate.accepted:
        return gate, bound
    sandbox.reset()
    target = inside(sandbox.workspace, contract.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bound.content.encode("utf-8", "surrogateescape"))
    report = jev.run(ChangeSet.detect(sandbox.workspace), contract.prose)
    asked = replace(
        gate,
        findings=(*gate.findings, *report.findings),
        observations=(*gate.observations, *report.observations),
        environment_issues=(*gate.environment_issues, *report.environment_issues),
        jev=report,
    )
    return asked, Accepted.read(repo=sandbox.workspace, contract=contract, result=asked)


def _cleaned(
    contract: Contract,
    sandbox: Sandbox,
    result: GateResult,
    bound: Accepted,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> tuple[GateResult, Accepted]:
    """Tidy a format-only rejection with the deterministic cleaner, and regate.

    ``tidy`` rewrites the bound text only where the verdict is one the
    formatter itself raised, so a rejection on anything else comes back with
    ``regate`` false and the result and the bound value are returned untouched.
    A tidied text is gated again in the sandbox, and the verdict and the content
    come from that second run rather than from the first.
    """
    cleanup = _drive.tidy(
        content=bound.content,
        result=result,
        target=contract.target,
        repo=sandbox.workspace,
    )
    if not cleanup.regate:
        return result, bound
    regated = gate_in_sandbox(
        contract, sandbox, cleanup.content, adapters=adapters, config=config
    )
    return regated, Accepted.read(
        repo=sandbox.workspace, contract=contract, result=regated
    )


def _repair_and_regate(
    contract: Contract,
    sandbox: Sandbox,
    rejected: GateResult,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> GateResult:
    """Repair a rejected workspace with the deterministic tools, and regate it.

    ``repair`` runs the tools over the tree the model left; where it rewrote a
    file, the repaired tree is gated again and the verdict returned is the
    regate's, not the one that was rejected. Each rewritten path also arrives as
    a style observation saying that the tools changed the file before the
    verdict, so a reader knows the delivered tree is the repaired one rather
    than the reply.

    A repair that changed nothing leaves the rejection standing as it was, with
    whatever environment issues the repair reported appended to it.
    """
    from mcgyvr.gate.findings import Finding
    from mcgyvr.gate.typecheck import STYLE
    from mcgyvr.repair import repair

    outcome = repair(sandbox=sandbox, contract=contract)
    if not outcome.changed:
        if outcome.environment_issues:
            return replace(
                rejected,
                environment_issues=(
                    *rejected.environment_issues,
                    *outcome.environment_issues,
                ),
            )
        return rejected
    regated = _drive.gate_workspace(contract, sandbox, adapters=adapters, config=config)
    noted = tuple(
        Finding(
            check=STYLE,
            path=path,
            message="repair: the deterministic tools rewrote this file before "
            "the verdict; what is delivered is the repaired tree, not the reply",
        )
        for path in outcome.repaired
    )
    return replace(
        regated,
        observations=(*regated.observations, *noted),
        environment_issues=(*regated.environment_issues, *outcome.environment_issues),
    )


def gate_in_sandbox(
    contract: Contract,
    sandbox: Sandbox,
    content: str,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> GateResult:
    """Gate ``content`` as the contract's target, in a reset sandbox.

    The text is written to the target's path inside the workspace — confined to
    the workspace, parents created, and encoded with ``surrogateescape`` so a
    byte that is not valid UTF-8 survives the round trip — and the whole gate is
    then run over that tree. The gate is reached through the package's name, so
    a caller that substitutes ``mcgyvr.drive.gate_workspace`` is answered by its
    own version: this is the seam a test judges a change it already holds
    through, with no model in the way.
    """
    sandbox.reset()
    target = inside(sandbox.workspace, contract.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8", "surrogateescape"))
    return _drive.gate_workspace(contract, sandbox, adapters=adapters, config=config)


def task_ceiling(config: Config | None = None) -> float | None:
    """The task ceiling in seconds, or ``None`` when nothing declares one.

    The value is the config's ``task_timeout_s``. With no config handed in, one
    is loaded here, and a missing config file answers ``None`` rather than
    raising: a caller asking how long a command may run is not the thing that
    failed.
    """
    if config is None:
        from mcgyvr.config import ConfigMissingError, load

        try:
            config = load()
        except ConfigMissingError:
            return None
    declared = config.get("task_timeout_s")
    return float(declared) if declared is not None else None


def acceptance_for(
    contract: Contract, sandbox: Sandbox, *, config: Config | None = None
) -> Acceptance | None:
    """The contract's acceptance rung, or ``None`` when it names no commands.

    Acceptance commands and demonstration commands both count: a contract that
    declares either has something to run, and either way the commands run in the
    sandbox, held to the task ceiling. ``None`` means the rung is not wired at
    all, so the gate never runs one.
    """
    if not (contract.acceptance_commands or contract.demonstration_commands):
        return None
    return Acceptance(
        sandbox,
        contract.acceptance_commands,
        timeout=_drive.task_ceiling(config),
        demonstrations=contract.demonstration_commands,
    )


def output_checks_for(contract: Contract, workspace: Path) -> OutputChecks | None:
    """The output-evidence rungs a contract declares, or ``None`` for none.

    Only ``media_valid``, ``safety_pass`` and ``asr_wer`` are rungs the output
    check implements, and they run in that order whatever order the contract's
    evidence names them in; the declared names are read as a set, so a name
    declared twice is still one rung. ``None`` when the contract declares none
    of them — a coding contract produces no output for these to read.
    """
    declared = set(contract.evidence_names)
    checks = tuple(
        name for name in (MEDIA_VALID, SAFETY_PASS, ASR_WER) if name in declared
    )
    if not checks:
        return None
    return OutputChecks(
        checks=checks,
        workspace=workspace,
        target=contract.target,
        media_kind=contract.media_kind,
        transcript=contract.transcript,
        wer_threshold=contract.wer_threshold,
    )


def gate_prose_workspace(contract: Contract, sandbox: Sandbox) -> GateResult:
    """Gate a prose or media reply: the output rungs, and nothing else.

    A prose or media reply changes no source, so the one rung it faces is the
    output-evidence rung. A contract that declares no output evidence is
    answered with an empty result, and an empty result is an acceptance: a
    ``GateResult`` is accepted when it holds no findings and no inconclusive
    rung. That is how a chat or agent reply runs no check at all.
    """
    rung = output_checks_for(contract, sandbox.workspace)
    if rung is None:
        return GateResult()
    report = rung.run()
    return GateResult(
        findings=report.findings,
        environment_issues=report.environment_issues,
        inconclusive=report.inconclusive,
    )


def gate_workspace(
    contract: Contract,
    sandbox: Sandbox,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> GateResult:
    """Run the whole gate over a sandbox's workspace, and return its verdict.

    A workspace holding a nested git entry is refused before any change is read:
    host git would run that repository's config over the tree, so the change is
    not accepted and the entry that caused it is named. Otherwise the gate is
    handed the workspace's detected change, the contract's scope, its acceptance
    and demonstration commands, a type check, the semantic rung, the output rungs
    its evidence declares, and the contract's prose for the rungs that read it.
    The adapters are the caller's when given and ``gate_adapters(config)``'
    otherwise.
    """
    nested = nested_git(sandbox.workspace)
    if nested is not None:
        # A git entry below the workspace is a repository of its own, and host
        # git would run its config over this tree, so nothing is read here.
        return GateResult(
            findings=(
                Finding(
                    check="workspace",
                    path=nested,
                    names_a_file=False,
                    code="nested-git",
                    message=(
                        f"the workspace holds the git entry {nested}; host git "
                        f"would run that repository's config, so the tree is "
                        f"not read and the change is not accepted"
                    ),
                ),
            )
        )
    acceptance = acceptance_for(contract, sandbox, config=config)
    # The acceptance rung runs the contract's own commands inside this sandbox,
    # so a command reads the change and not the host, and it is held to the
    # task ceiling rather than to a model's timeout.
    runner = SandboxRunner(sandbox)
    owners = adapters if adapters is not None else gate_adapters(config)
    return Gate(tuple(adapter.running_in(runner) for adapter in owners)).run(
        ChangeSet.detect(sandbox.workspace),
        contract.scope,
        acceptance=acceptance,
        # The JEV rung is left out on purpose: it is a model, and the attempt
        # loop asks it of the winning draw only, after a verdict has picked one
        # (see ``_typed_checks``). Each rung passed here is skipped once a
        # finding is recorded, in this order: output evidence, the type check,
        # the semantic rung, and the acceptance commands last.
        typecheck=TypeCheck(repo=sandbox.workspace, runner=runner),
        semantic=SemanticCheck(sandbox=sandbox),
        output=output_checks_for(contract, sandbox.workspace),
        contract_text=contract.prose,
    )


def gate_adapters(config: Config | None) -> tuple[LanguageAdapter, ...]:
    """The language adapters the gate runs, with the setup's mutation mode.

    The Python adapter's reading of a function that changes a parameter it was
    handed comes from ``gate.param_mutation`` and defaults to
    ``ParamMutation.REFUSE``, the mode that refuses such a change; ``SKIP`` does
    not look for it and ``REPORT`` reports it as style. The JavaScript adapter
    takes no setting, and a caller with no config gets the defaults.
    """
    mode = (
        config.get("gate.param_mutation", ParamMutation.REFUSE)
        if config is not None
        else ParamMutation.REFUSE
    )
    return (PythonAdapter(param_mutation=mode), JavaScriptAdapter())
