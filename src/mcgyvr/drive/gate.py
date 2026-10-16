"""The gate half of the drive seam: judging, ceiling, and the verifier."""

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
    """The gate's typed-question rung, asked of ``builder``'s reviewer, or ``None``.

    ``None`` where there is no reviewer, where it has no typed seam, and where
    it is not independent of the builder: the rung's questions are asked of
    the reviewer, and a model judging its own added lines is the self-review
    :func:`~mcgyvr.verify.verify` refuses before a verdict — so it is refused
    before the gate's questions too, before anything is spent.
    """
    if reviewing is None or not independent(builder, reviewing.model):
        return None
    return reviewing.jev


def _through(
    waker: Waker | None, reviewer: Reviewer, *, jev_resident: bool = False
) -> Reviewer:
    """``reviewer`` with every seam sent through ``waker``, as a builder's is.

    The same :meth:`~mcgyvr.wake.Waker.dispatching` the builder's dispatch
    goes through, keyed by the unit the reviewer runs on: a refused port wakes
    that card once and the ask is sent again. ``waker`` is ``None`` for a
    config that did not enable sleep and wake, and then nothing changes.

    ``jev_resident`` says a ``jev.unit`` answers the typed seams (``decide`` and
    the Jev rung): that unit is resident and never woken (owner ruling), so
    those seams go around the waker and only the prose ``ask`` still goes
    through it. A typed decision never wakes anything first.
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
    """Ask the reviewer's typed checks of the accepted change, once.

    The gate's Jev rung, run here rather than inside every draw's gate: each
    question is a request to the reviewer, and a draw the gate rejected, or
    one that lost to another draw, is not worth one. Nothing is asked of a
    change the gate did not accept.

    The winning bytes are written back into the workspace — ``best_of`` has
    restored it after every draw — so the rung reads the added lines from the
    tree, as it does inside the gate, and the binding is minted again from that
    tree with the answers in it, the verdict and its bytes moving together as
    :func:`_cleaned` moves them.
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
    """Tidy the winning draw, and re-judge it when the tidy-up changed it.

    The verdict and the binding move together or not at all, which is the whole
    reason this is one function rather than two lines at the call site. A
    :class:`~mcgyvr.cleanup.Cleanup` reports :attr:`~mcgyvr.cleanup.Cleanup.regate`
    when the bytes it hands back were rewritten, and its own
    :attr:`~mcgyvr.cleanup.Cleanup.accepted` is the verdict about the bytes that
    went *in* — deliberately, because behind a format rejection the gate stopped
    before its typecheck, semantic and acceptance rungs and this module has no
    idea what they would have said. Carrying that verdict forward beside the new
    file would be a verdict about bytes that are not the file's.

    So the answer to ``regate`` is a gate run, not a re-read. ``gate_in_sandbox``
    writes the cleaned bytes into the workspace and judges what is now there,
    and the binding is minted from that same tree — so the pair that leaves here
    is a verdict and the file it was computed over, as the pair that arrived was.

    ``tidy`` is handed :attr:`~mcgyvr.deliver.Accepted.content` rather than a
    string carried from the reply, and ``repo`` is the sandbox workspace rather
    than the user's checkout: the tree whose formatter configuration decides what
    clean means has to be the tree the gate checked, or the cleanup tidies a file
    into a shape the gate then complains about.

    One pass, not a loop. ``ruff format`` is a fixed point, so a second cleanup
    over the first one's output would rewrite nothing; a loop would be a retry
    budget nobody declared, inside an attempt that already has one.
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
    """Repair and re-gate, on the same rung and with no model retry.

    The gate judges and never writes; :func:`mcgyvr.repair.repair` writes and
    never judges — the declared imports, the linter's own autofixes and the
    formatter, over the contract's scope and nothing else. A rejected draw is
    repaired in place and judged again before the ladder spends anything,
    under ``cleanup.enabled``, which is on unless an install says otherwise.

    The tree is what is delivered. ``best_of`` mints the winner's binding off
    this sandbox one line after this returns, so an accepted verdict here is
    a verdict about the repaired bytes and the file that leaves is the file
    that was judged; the reply the model sent is in the journal. When the
    tools changed nothing the first verdict stands unrepeated — a second
    gate over identical bytes is a subprocess for an answer already in hand.
    A repair that ran is said out loud as an observation, so a reader of the
    row knows the delivered file is not the reply verbatim; what the repair
    could not run rides along as an environment issue.
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
    """Write ``content`` as the contract's target in ``sandbox`` and gate it.

    Shared by both tiers, which is the point: a change is judged by the same
    rungs whether a program produced it or a model did, and a floor with its own
    weaker gate would make "the deterministic tier is cheap" mean "the
    deterministic tier is unchecked".

    The write is through ``surrogateescape``: a reply is text that came off a
    socket and may carry bytes no codec round-trips, and a writer that raised
    on them would fail the attempt for the one reason the worker cannot do
    anything about.

    The acceptance commands are the contract's own, split by
    :attr:`~mcgyvr.contract.Contract.acceptance_commands`, and they run inside
    this sandbox — never on the host. That is the whole reason the gate takes an
    :class:`~mcgyvr.gate.acceptance.Acceptance` bound to a sandbox rather than a
    list of commands.
    """
    sandbox.reset()
    target = inside(sandbox.workspace, contract.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8", "surrogateescape"))
    return _drive.gate_workspace(contract, sandbox, adapters=adapters, config=config)


def task_ceiling(config: Config | None = None) -> float | None:
    """The policy's ``task_timeout_s``, or ``None`` where no config settles it.

    A contract's acceptance command runs any program it names, and this is the ceiling
    one that hangs is held to.

    ``config`` is the run's own — the one ``--config`` named — and when a caller
    holds one it is the only answer: a run judged under another setup's ceiling
    is judged under a budget nobody gave it. A caller holding none gets the
    config at the default location.

    A *missing* default config is not an error here: refusing a gate because
    there is no config would make the ceiling a requirement rather than a
    bound, and a bare install is supported. No config means no declared
    ceiling, which is what `None` says. A config that is *there* and does not
    load is the other situation and raises (owner ruling): it is a ceiling the
    operator wrote, and reading it as "no ceiling" hands a contract's arbitrary
    shell no wall clock at all — silently, on the one surface a user is asked
    to edit.
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
    """The contract's acceptance rung, bound to ``sandbox`` and to the ceiling.

    ``None`` when the contract declares neither list — there is nothing to run
    and nothing to time. Built here rather than inside `Gate` because only this
    layer holds the open sandbox, and read by both the preflight in
    `cli._climb` and by :func:`gate_workspace`, so the commands a run is judged
    on are the commands its baseline was taken with.
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
    """The gate's output-checks rung, or ``None`` when the contract declares none.

    Only the three structural evidence kinds the gate makes itself are mapped
    here; the command-producing kinds have their own rungs. Built beside
    :func:`acceptance_for` rather than inside ``Gate`` because the declared
    evidence and the workspace are what this layer holds.
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
    """Judge a raw-text reply by the contract's output checks and nothing else.

    A raw-text reply is the answer itself, not a file to be tidied, repaired or
    verifier-reviewed. The only bar it must clear is the structural output
    evidence the contract declares — a media artifact's ``media_valid`` — and a
    ``chat`` or ``agent`` session, which declares none, is accepted with no gate
    at all (owner, e2e run 2 R11: "agent and chat have no gates").
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
    """Judge whatever is in ``sandbox`` right now against ``contract``.

    The half of :func:`gate_in_sandbox` that does not write, because the two
    tiers arrive at a change differently and are judged identically. A model
    hands back content and something has to put it on disk; a program on the
    deterministic floor has already written the tree itself, and a gate that
    insisted on being handed content would have to read the file back out and
    write it again — two more chances for the bytes to stop being the bytes.

    "Against ``contract``" includes the contract's own words
    (``contract_text``). Two rungs can only be as right as what the contract
    asked for — the acceptance commands, and ``param-mutation``, which rejects
    a function for mutating its caller's object and has to stand down where the
    contract *ordered* that.

    With no ``adapters`` handed in, the gate's are the ones ``config`` asks for
    (:func:`gate_adapters`), built here rather than handed down by the driver:
    the adapters :func:`worker_attempt` holds also decide what a worker is sent.
    """
    nested = nested_git(sandbox.workspace)
    if nested is not None:
        # Before any host git reads the tree (owner ruling): a nested
        # repository's config is run by the child git host git starts in it.
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
    # The checkers that load code from the workspace's own configuration — the
    # type checker's plugins, eslint's and prettier's config modules — run
    # where the task's commands do, never on the host beside it.
    runner = SandboxRunner(sandbox)
    owners = adapters if adapters is not None else gate_adapters(config)
    return Gate(tuple(adapter.running_in(runner) for adapter in owners)).run(
        ChangeSet.detect(sandbox.workspace),
        contract.scope,
        acceptance=acceptance,
        # The other two rungs `Gate.run` accepts. They are built here and not
        # inside `Gate` because both need what only this layer holds: the open
        # sandbox, and the workspace the declaration lives in. A repository
        # that declares no checker still gets `None` from
        # `TypeCheck.declared_command`, so the absence is not a rejection.
        typecheck=TypeCheck(repo=sandbox.workspace, runner=runner),
        semantic=SemanticCheck(sandbox=sandbox),
        output=output_checks_for(contract, sandbox.workspace),
        contract_text=contract.prose,
    )


def gate_adapters(config: Config | None) -> tuple[LanguageAdapter, ...]:
    """The gate's language adapters as ``config`` asks for them.

    The only setting they read is ``gate.param_mutation``; a caller holding no
    config gets the strict reading, the same pair ``Gate()`` builds on its own.
    That pair is spelled in four other places (``gate/runner.py``,
    ``deliver.py``, ``orchestrator/decompose.py``, ``worker/bundle.py``); the
    last two only ask which files an adapter owns, which no setting changes.
    """
    mode = (
        config.get("gate.param_mutation", ParamMutation.REFUSE)
        if config is not None
        else ParamMutation.REFUSE
    )
    return (PythonAdapter(param_mutation=mode), JavaScriptAdapter())
