#!/usr/bin/env python3
"""The mission runner: one admitted commit through the orchestrator, on a local pool.

`#365 <https://github.com/AdarGit008/mcgyvr/issues/365>`_ item 4, riding the
owner's decisions recorded on the issue: admission is code+test commits from
Adar's own repos, a multi-file commit stays one task and ``decompose`` owns the
split, **no API fallback**, and the judge is output beside issue body at the
month's review. This module is the loop those decisions describe, and nothing
in it is new product surface: every step is a call into ``src/mcgyvr`` —
:func:`~mcgyvr.orchestrator.repo.attach`,
:func:`~mcgyvr.orchestrator.index.build_index`,
:func:`~mcgyvr.orchestrator.decompose.decompose`,
:func:`~mcgyvr.escalate.escalate` — strung together off-SURFACE.

**The defect this prevents is a run that answers a different question than the
one asked.** The question is whether the *local* pool reaches a commit's own
tests from its issue body. A ladder with a credentialed rung would let a task
that the local rungs cannot do climb to an API and come back accepted, and the
record would then read as a local result. :func:`require_local_only` refuses
that config **before** anything is dispatched, naming every source that requires
a credential and where it is bound — so the refusal is a fact about the config
file, not about what a task happened to reach. :attr:`Config.is_local_only`
looks at the ladder alone; this looks at every declared source, because the
orchestrator and verifier roles dispatch too.

**The worktree stays the parent; the acceptance travels by content.** Item 1
checks out the parent tree and keeps the child's tests off disk (its leakage
rule), and item 3 writes them into each sandbox *after* the change set is
computed, so the gate never attributes someone else's test file to the worker
(``changeset.py`` reads an untracked file as worker-added). This runner reads
them once off the child commit through item 3's ``acceptance_files_from`` and
hands them to every attempt. Only after the last gate has run are they written
beside the delivered files, for the one whole-tree run of the narrowed command
whose exit status the record carries — and that run, like every per-try
acceptance, goes through E4's :class:`~mcgyvr.sandbox.tempdir.TempDirSandbox`:
a command read off someone else's commit runs on an archived copy with the
credential variables filtered, never in the canonical clone's worktree with the
host environment. The assembled worktree is what the record was built from,
and :func:`main` releases it from the clone once the record is written unless
``--keep-worktree`` asks to inspect it.

**Siblings are loaded at call time, by path.** ``tasks``, ``propose``,
``attempt`` and ``record`` are items 1, 2, 3 and 5 and are built on the same
lane; this module imports cleanly and :func:`require_local_only` is testable
while they are absent. A sibling that is missing is a named refusal
(:class:`SiblingMissing`); a sibling whose factory wants something this runner
does not hold is another (:class:`SiblingMismatch`), naming the parameter —
never a positional guess.

**The bar is declared by the runner, not named by the model.** The catalog's
command-needing evidence is left for a proposer to fill, and in a mission the
command is not the model's to invent: it is the child's tests, narrowed. Item
2's proposals pass through :class:`_DeclaringProposer`, which fills the slot
each type needs with item 3's ``acceptance_for`` — the same computation
``make_attempt`` runs — so the declared command and the one that runs cannot
disagree.

**Each delivery is committed before the next climb.** Item 3 populates every
try's sandbox with ``git archive HEAD`` of the worktree, so a file that only
sits uncommitted beside it is invisible to the next contract's base: on a
multi-contract task the second contract would be attempted against the parent
tree as if the first had never delivered. So after each ``Delivered`` the file
is delivered through :func:`mcgyvr.deliver.deliver` — the one seam in the
project that commits, which re-runs the gate over the bytes on disk inside the
repository lock before staging — and the record lists the sha each contract
moved HEAD to (``output.head``). A delivery it refuses is recorded at stage
``deliver`` rather than counted as one, because a refusal reported as a
completion is B8's defect wearing a different hat. The commits belong to the
mission worktree; once it is released they dangle in the canonical clone until
it prunes, which is the cost of the base being a real tree rather than a copy.

**The record carries no verdict.** Everything pass/fail-shaped lives under
``output.gate``: the whole-tree run's exit status (``gate.whole``) and, per
contract, the climb's verdicts and item 3's trace of every try
(``gate.contracts``). ``output.outcomes`` carries only the rule that ended each
climb (:class:`~mcgyvr.escalate.Outcome`) and its counts; ``verdict`` anywhere
else is the review's word and item 5 refuses it on read. A halted escalation is
recorded the same way — the unrecoverable is recorded, not skipped (ADR-0026
lens 1). So is everything that stopped a contract before or during its climb:
``output.attempt_refusals`` names each one with its stage — a bar the proposer
could not declare (``declare``), an attempt item 3 refused to assemble
(``assemble``), or a dispatch that raised a :class:`~mcgyvr.runner.RunnerError`
mid-climb (``dispatch``, with the rung and the exception's name, because
"srv2 was down" and "the ollama path refused a quality-sensitive request" are
different findings about the pool and neither is a finding about the task).
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import inspect
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from mcgyvr.catalog import catalog
from mcgyvr.config import Config
from mcgyvr.config import load as load_config
from mcgyvr.contract import Contract
from mcgyvr.deliver import DeliveryError, Identity, deliver
from mcgyvr.escalate import Delivered, Halted, Judgement, escalate
from mcgyvr.orchestrator.decompose import (
    Decomposition,
    Evidence,
    Proposal,
    Proposer,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.repo import attach
from mcgyvr.pool import Endpoint, PoolError, SourceMap, source_map
from mcgyvr.route import Try, family_of
from mcgyvr.runner import RunnerError
from mcgyvr.sandbox.base import Sandbox

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

#: Where the admitted tasks live: session-mine's corpus, outside every repo.
DEFAULT_DB = Path.home() / "claude" / "session-mine" / "sessions.sqlite"

#: The header this run's intent is declared under (#322: record, not refuse).
INTENT_RECORD = "run-header/1"
INTENT_QUESTION = (
    "does the local pool reach a commit's own tests from its issue body (#365)"
)

#: What this campaign cannot measure, stated in every record's intent so the
#: month's review does not read the corresponding refusals and failures as a
#: result about the pool (#322: record, not refuse).
INTENT_LIMITS = (
    "targets must pre-exist in the parent tree (decompose refuses a proposal "
    "whose target is not in the index, so a commit that adds a source file "
    "reads as a request refusal)",
    "acceptance runs with the runner's own toolchain on PATH (the mcgyvr venv), "
    "not the target repository's, so an import the venv lacks reads as a "
    "failed test",
    "a multi-file commit whose one test asserts every file's new behaviour "
    "cannot pass on any contract but the last, so earlier contracts halt and "
    "nothing is committed between climbs (delivery is committed per contract "
    "only when that contract's own climb is Delivered)",
    "a parent tree with no tests/ directory and no pytest in pyproject.toml "
    "has no adapter test command, so every proposal on it is a stage='declare' "
    "refusal ('no test command') — a commit that added the repository's first "
    "tests reads this way",
)

#: Item numbers of #365, so a missing sibling is refused by the item it is.
_ITEMS = {"tasks": "1", "propose": "2", "attempt": "3", "record": "5"}

#: How much of the test command's output the record keeps, per stream.
_OUTPUT_TAIL = 8000

#: The catalog's two command-needing evidence names that a commit's own tests
#: can supply: ``tests_pass`` (passes at baseline, so ``acceptance``) and
#: ``failing_test_first`` (fails at baseline, so ``demonstration``). Named
#: rather than derived from ``needs_acceptance_commands`` because that
#: property is true of ``type_annotation`` too, whose command-needing evidence
#: is ``type_check`` — a bar the child's tests are not.
_TESTS_PASS = "tests_pass"
_FAILING_TEST_FIRST = "failing_test_first"

#: The identity a delivery is committed under. Set through the environment so
#: the commit works on any clone, configured or not; deliberately not the host
#: user's, because the commit is scaffolding for the next climb's base and
#: never authorship.
_DELIVERY_IDENTITY = Identity(name="mcgyvr mission", email="mission@mcgyvr.invalid")

#: Where a refusal stopped a contract, for the record (see :class:`AttemptRefusal`).
STAGE_DECLARE = "declare"
STAGE_ASSEMBLE = "assemble"
STAGE_DISPATCH = "dispatch"
STAGE_DELIVER = "deliver"


class MissionError(Exception):
    """Base class for every refusal this runner makes."""


class NoApiFallback(MissionError):  # noqa: N818 — the rule, named as #365 names it
    """A declared source requires a credential; #365 runs on the local pool only."""


class SiblingMissing(MissionError):  # noqa: N818
    """A ``tools/missions/`` module this runner calls is not on disk yet."""


class SiblingMismatch(MissionError):  # noqa: N818
    """A sibling's factory wants a parameter this runner does not hold."""


class DeliveredPathEscapes(MissionError):  # noqa: N818
    """A delivered file's path resolves outside the worktree."""


class RecordAlreadyThere(MissionError):  # noqa: N818
    """``records/missions/<sha>/task.json`` exists; a run is not overwritten."""


@dataclass(frozen=True)
class AttemptRefusal:
    """One contract that never climbed, or stopped mid-climb, and why.

    Recorded rather than skipped (ADR-0026 lens 1). ``subject`` is the
    contract id — or, at :data:`STAGE_DECLARE`, the proposal's target, since
    no contract exists yet. ``rung`` and ``exception`` are set only at
    :data:`STAGE_DISPATCH`, where the finding is about a rung and not the task.
    """

    subject: str
    stage: str
    why: str
    rung: str | None = None
    exception: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": self.subject,
            "stage": self.stage,
            "refusal": self.why,
            "rung": self.rung,
            "exception": self.exception,
        }


class AdmittedTask(Protocol):
    """What this runner reads off item 1's ``Task`` — a structural view, so the
    sibling's dataclass satisfies it without an import between modules."""

    @property
    def sha(self) -> str: ...
    @property
    def repo_root(self) -> Path: ...
    @property
    def parent(self) -> str: ...
    @property
    def spec(self) -> str: ...
    @property
    def test_paths(self) -> tuple[str, ...]: ...
    @property
    def reachable(self) -> bool: ...


# --- the rule ---------------------------------------------------------------


def require_local_only(config: Config) -> None:
    """Refuse a config with any credentialed source, before a single dispatch.

    Every declared source is checked, not only the ladder's: a role bound to an
    API source dispatches too. The message names each offending source, the
    variable it wants, and where the config binds it, so the fix is a config
    edit and not a guess.
    """
    offending: list[str] = []
    for name in sorted(config.sources):
        source = config.sources[name]
        if not source.requires_credential:
            continue
        bound = [
            f"ladder tier {tier.name!r}"
            for tier in config.ladder.tiers
            if tier.source == name
        ]
        bound.extend(
            f"role {role!r}"
            for role in ("orchestrator", "verifier")
            if (config.get(f"{role}.source") == name)
        )
        where = ", ".join(bound) or "declared and unbound"
        offending.append(f"{name} (api_key_env={source.api_key_env}; {where})")
    if offending:
        raise NoApiFallback(
            "#365 runs on the local pool with no API fallback, and this config "
            f"declares {len(offending)} source(s) that require a credential: "
            + "; ".join(offending)
            + (f" — in {config.path}" if config.path is not None else "")
            + ". Remove them from the config for a mission run."
        )


def record_dir(repo_root: Path, sha: str) -> Path:
    """Where one task's record lives: ``records/missions/<sha>`` under the repo."""
    return repo_root / "records" / "missions" / sha


# --- siblings, by path -------------------------------------------------------


def _sibling(name: str) -> types.ModuleType:
    """Load ``tools/missions/<name>.py`` the way the tests do, once per process."""
    module_name = f"missions_{name}"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    path = HERE / f"{name}.py"
    if not path.is_file():
        raise SiblingMissing(
            f"tools/missions/{name}.py does not exist — #365 item "
            f"{_ITEMS.get(name, '?')} has not landed, and run.py needs it here"
        )
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SiblingMissing(f"{path} cannot be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _construct(factory: Callable[..., Any], what: str, **offered: Any) -> Any:
    """Call a sibling's factory with the subset of ``offered`` it names.

    The siblings are written in parallel, so their keyword names are not this
    module's to assume. A required parameter that nothing offered covers is a
    :class:`SiblingMismatch` naming it and what was on the table — the
    alternative, passing positionally, is how a worktree ends up where a config
    was expected.
    """
    signature = inspect.signature(factory)
    kwargs: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name in offered:
            kwargs[parameter.name] = offered[parameter.name]
        elif parameter.default is parameter.empty:
            raise SiblingMismatch(
                f"{what} requires a parameter {parameter.name!r} this runner "
                f"does not hold; offered: {', '.join(sorted(offered))}"
            )
    return factory(**kwargs)


# --- the plan: everything before a worker is asked ----------------------------


@dataclass(frozen=True)
class Plan:
    """The run up to and including decomposition — what ``--dry-run`` prints."""

    task: AdmittedTask
    worktree: Path
    index: Index
    pool: SourceMap
    proposer: Any
    proposer_binding: tuple[str, str, Endpoint]
    """``(what, model, endpoint)`` — the role or rung the proposer dispatched to."""
    decomposition: Decomposition
    declared_refusals: tuple[tuple[str, str], ...] = field(default=())
    """Per proposal whose bar could not be declared: ``(target, why)``."""


def _proposer_binding(pool: SourceMap, rung: str | None) -> tuple[str, str, Endpoint]:
    """Who proposes: the named rung, else the orchestrator role, else the top rung.

    The ladder is written cheapest-first, so its last usable rung is the
    dearest local model — the one to hand judgment to when no role is bound.
    """
    if rung is not None:
        step = pool.get(rung)
        if step is None:
            raise MissionError(
                f"no usable rung named {rung!r}; offered: "
                f"{', '.join(r.name for r in pool.rungs) or 'none'}"
            )
        return (f"rung {rung}", step.model, pool.bind(rung))
    try:
        role = pool.role("orchestrator")
    except PoolError as exc:
        raise MissionError(
            f"the orchestrator role cannot propose: {exc}; pass --proposer-rung "
            "to use a ladder rung"
        ) from exc
    if role is not None:
        return ("role orchestrator", role.model, role.endpoint)
    if not pool.rungs:
        raise MissionError(
            "no usable rung to propose on: "
            + ("; ".join(f"{s.name}: {s.reason}" for s in pool.skipped) or "empty")
        )
    top = pool.rungs[-1]
    return (f"rung {top.name}", top.model, pool.bind(top.name))


def plan_task(
    task: AdmittedTask,
    config: Config,
    *,
    into: Path,
    proposer_rung: str | None = None,
    propose: Proposer | None = None,
) -> Plan:
    """The rule, the checkout, the index, the decomposition — no worker yet.

    ``propose`` overrides the live proposer (a test hands in a recorded one);
    otherwise item 2's :class:`LiveProposer` is built over the product runner,
    bound to :func:`_proposer_binding`'s choice.
    """
    require_local_only(config)
    tasks = _sibling("tasks")
    attempt_module = _sibling("attempt")
    worktree = Path(tasks.checkout(task, into=into))
    with attach(str(worktree)) as repo:
        index = build_index(repo.root)
    pool = source_map(config)
    binding = _proposer_binding(pool, proposer_rung)
    proposer: Any
    if propose is not None:
        proposer = propose
    else:
        live = _sibling("propose")
        _, model, endpoint = binding
        timeout = config.get("budgets.task_timeout_s")
        dispatch = _construct(
            live.runner_dispatch,
            "propose.runner_dispatch",
            endpoint=endpoint,
            model=model,
            timeout_s=None if timeout is None else float(timeout),
        )
        proposer = _construct(
            live.LiveProposer, "propose.LiveProposer", dispatch=dispatch
        )
    declaring = _DeclaringProposer(
        inner=proposer,
        declare=functools.partial(
            _declared, attempt_module, worktree, tuple(task.test_paths)
        ),
    )
    decomposition = decompose(index, task.spec, propose=declaring, config=config)
    return Plan(
        task=task,
        worktree=worktree,
        index=index,
        pool=pool,
        proposer=proposer,
        proposer_binding=binding,
        decomposition=decomposition,
        declared_refusals=tuple(declaring.refusals),
    )


@dataclass(frozen=True)
class _DeclaringProposer:
    """Item 2's proposer with the task's bar declared on every proposal.

    The catalog's command-needing evidence (``tests_pass``,
    ``failing_test_first``) is deliberately not filled by ``decompose`` — only
    a proposer can name a command there. In a mission the command is not the
    model's to name: the bar is the child's own tests, narrowed, and it is
    known before a token is spent. So the proposals come back through here and
    the slot each type requires is filled with item 3's ``acceptance_for`` —
    the same computation ``make_attempt`` runs, so a declared command and the
    one that runs cannot disagree. A proposal that already names one keeps it.

    A bar that cannot be declared — no adapter owns the target, the stack has
    no test runner — is item 3's named refusal, and it is kept in ``refusals``
    as ``(target, why)`` rather than dropped: the proposal goes on unchanged
    for ``decompose`` to refuse for want of a command, and without the reason
    beside it the record would say only that a command was missing, not why
    none could be named.
    """

    inner: Proposer
    declare: Callable[[Proposal], tuple[Proposal, str | None]]
    refusals: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        out: list[Proposal] = []
        for proposal in self.inner(evidence):
            declared, why = self.declare(proposal)
            if why is not None:
                self.refusals.append((proposal.target, why))
            out.append(declared)
        return out


def _declared(
    attempt_module: types.ModuleType,
    worktree: Path,
    test_paths: tuple[str, ...],
    proposal: Proposal,
) -> tuple[Proposal, str | None]:
    """``proposal`` with the narrowed test command in the slot its type needs,
    and the reason none could be named when that is what happened.

    The slot is chosen by the evidence *name*, not by the type's
    command-needing bit: a commit's own test is ``tests_pass`` (passes at
    baseline, so ``acceptance``) or, for ``bug_fix``, ``failing_test_first``
    (fails at baseline, so ``demonstration``). ``type_annotation`` also needs
    a command, but its evidence is ``type_check`` — a type checker's run, not
    a test — and filling its acceptance with the child's tests would declare
    a bar its evidence does not name. It is left for ``decompose`` to refuse
    by name, as is a type the catalog does not know. A target no adapter owns
    comes back unchanged with item 3's reason as the second element.
    """
    kind = catalog().get(proposal.task_type)
    if kind is None:
        return proposal, None
    names = kind.evidence_names
    wants_acceptance = _TESTS_PASS in names and not proposal.acceptance
    wants_demonstration = _FAILING_TEST_FIRST in names and not proposal.demonstration
    if not (wants_acceptance or wants_demonstration):
        return proposal, None
    try:
        command = _construct(
            attempt_module.acceptance_for,
            "attempt.acceptance_for",
            target=proposal.target,
            base=worktree,
            test_paths=test_paths,
        )
    except attempt_module.AttemptError as exc:
        return proposal, str(exc)
    declared = (shlex.join(str(part) for part in command),)
    filled = replace(
        proposal,
        acceptance=declared if wants_acceptance else proposal.acceptance,
        demonstration=declared if wants_demonstration else proposal.demonstration,
    )
    return filled, None


# --- the run: workers, assembly, the whole test, the record ------------------


@dataclass(frozen=True)
class TestRun:
    """The narrowed test command run on the assembled worktree. No verdict."""

    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "accepted": self.returncode == 0,
            "timed_out": self.timed_out,
            "stdout_tail": self.stdout[-_OUTPUT_TAIL:],
            "stderr_tail": self.stderr[-_OUTPUT_TAIL:],
        }


@dataclass(frozen=True)
class MissionResult:
    """What one task's run came to, and where it was written."""

    plan: Plan
    acceptance: Mapping[str, str]
    """The child's test files by path — the bar every attempt ran against."""
    outcomes: tuple[tuple[Contract, Delivered | Halted], ...]
    traces: tuple[tuple[dict[str, Any], ...], ...]
    """Per contract, item 3's trace of every try, as plain data."""
    files: Mapping[str, str]
    test: TestRun | None
    record: Path
    proposer_refusals: tuple[str, ...] = field(default=())
    attempt_refusals: tuple[AttemptRefusal, ...] = field(default=())
    """Every contract (or proposal) that never climbed or stopped mid-climb."""
    commits: tuple[tuple[str, str], ...] = field(default=())
    """Per delivered contract, in order: ``(contract id, sha HEAD moved to)``."""

    @property
    def delivered(self) -> int:
        """How many contracts reached a commit — not how many climbs passed.

        These were the same number while the runner committed whatever a
        ``Delivered`` carried. They stopped being the same when delivery gained
        refusals it can reach on its own: an ignored target, a change that is no
        longer a change, an unbound climb. Counting climb outcomes here would
        print "1 of 1 contract(s) delivered" over a run that committed nothing,
        which is B8's defect — a refusal reported as a completion — in the line
        the operator actually reads.
        """
        return len(self.commits)


def run_task(
    task: AdmittedTask,
    config: Config,
    *,
    db_path: Path,
    into: Path,
    proposer_rung: str | None = None,
    propose: Proposer | None = None,
    attempt_for: Callable[[Contract], Callable[[Try], Judgement]] | None = None,
    records_root: Path = REPO,
) -> MissionResult:
    """One admitted commit, end to end, leaving ``records/missions/<sha>/``.

    ``db_path`` is provenance — the corpus the task was loaded from goes into
    the record's intent, so a reader can find the row. ``attempt_for`` builds
    the per-contract attempt; unset, item 3's ``make_attempt`` is constructed
    by name. ``records_root`` is where the record lands (this repo by default;
    a test points it at a temp dir). A record already there is refused
    **before** the checkout, not after the climb has been spent: item 5 does
    not overwrite, and a refusal after the rig time is a traceback with
    nothing to show for it.
    """
    where = record_dir(records_root, task.sha)
    if (where / "task.json").exists():
        raise RecordAlreadyThere(
            f"{where} already holds a record for {task.sha}; a run is not "
            "overwritten — move it or pick another records_root"
        )
    plan = plan_task(
        task, config, into=into, proposer_rung=proposer_rung, propose=propose
    )
    attempt_module = _sibling("attempt")
    acceptance: dict[str, str] = dict(
        _construct(
            attempt_module.acceptance_files_from,
            "attempt.acceptance_files_from",
            repo_root=task.repo_root,
            sha=task.sha,
            test_paths=task.test_paths,
        )
    )

    outcomes: list[tuple[Contract, Delivered | Halted]] = []
    traces: list[tuple[dict[str, Any], ...]] = []
    files: dict[str, str] = {}
    commits: list[tuple[str, str]] = []
    attempt_refusals: list[AttemptRefusal] = [
        AttemptRefusal(subject=target, stage=STAGE_DECLARE, why=why)
        for target, why in plan.declared_refusals
    ]
    refused_traces: list[tuple[str, tuple[dict[str, Any], ...]]] = []
    for contract in plan.decomposition.contracts:
        if attempt_for is not None:
            attempt = attempt_for(contract)
        else:
            try:
                attempt = _make_attempt(
                    attempt_module, config, plan, contract, acceptance
                )
            except attempt_module.AttemptError as exc:
                # Item 3 refused before a Try (no adapter, a bar that is not
                # the task's): the unrecoverable is recorded, not skipped
                # (ADR-0026 lens 1), and the climb for this contract never runs.
                attempt_refusals.append(
                    AttemptRefusal(
                        subject=contract.id, stage=STAGE_ASSEMBLE, why=str(exc)
                    )
                )
                continue
        watched = _Watched(attempt)
        # Captured before the climb, because that is what it means: the tree
        # every sandbox for this contract was populated from. `deliver` diffs
        # against it, and `MissionSandbox(worktree)` archives `HEAD`, so the two
        # are the same commit by construction. Read here rather than passed as
        # the literal `"HEAD"` — `deliver._resolve` softens that spelling, and
        # B7 was a moving name being read as a fixed one.
        base = _git(plan.worktree, "rev-parse", "HEAD").strip()
        try:
            outcome = escalate(config, plan.pool, contract, attempt=watched)
        except RunnerError as exc:
            # A dispatch that raised is not a judgement about the task (item
            # 3 and route.climb both refuse to fold it into one), so escalate
            # let it through. It is the unrecoverable for this contract —
            # recorded with the rung it happened on and the exception's name,
            # never swallowed — and the run goes on to the next contract.
            attempt_refusals.append(
                AttemptRefusal(
                    subject=contract.id,
                    stage=STAGE_DISPATCH,
                    why=str(exc),
                    rung=watched.rung,
                    exception=type(exc).__name__,
                )
            )
            partial = _trace_of(attempt)
            if partial:
                refused_traces.append((contract.id, partial))
            continue
        outcomes.append((contract, outcome))
        traces.append(_trace_of(attempt))
        if isinstance(outcome, Delivered):
            # One delivery, and it is `mcgyvr.deliver` (pattern B). What stood
            # here wrote `outcome.value` — the caller's copy of the worker's
            # reply — and committed it, so nothing re-established that the bytes
            # reaching this repository were bytes a gate had read. `deliver`
            # re-runs the gate over what is on disk, inside the repository lock,
            # immediately before staging, and it is handed the binding item 3
            # minted in the workspace the verdict was reached in.
            bound = outcome.judgement.accepted
            if bound is None:
                # A `Delivered` with no binding is a caller-supplied
                # `attempt_for` that did not mint one. Recorded rather than
                # written: this seam has no tree to read the accepted bytes back
                # out of, and inventing them from a string is the defect.
                attempt_refusals.append(
                    AttemptRefusal(
                        subject=contract.id,
                        stage=STAGE_DELIVER,
                        why=(
                            "the climb passed but no `Accepted` came with it, so "
                            "there is nothing bound to the verdict to deliver; an "
                            "attempt function must mint one where its gate ran"
                        ),
                        rung=outcome.rung,
                    )
                )
                continue
            try:
                delivery = deliver(
                    repo=plan.worktree,
                    contract=contract,
                    content=bound,
                    base=base,
                    identity=_DELIVERY_IDENTITY,
                )
            except DeliveryError as exc:
                # `deliver` refuses by returning; it *raises* when git itself
                # fails — a signing config, a hook that aborts, a repository
                # that moved under the run. Uncaught, that ends the mission with
                # earlier contracts already committed and no record written,
                # which is the shape B1 came in. It is this contract's
                # unrecoverable and nothing more.
                attempt_refusals.append(
                    AttemptRefusal(
                        subject=contract.id,
                        stage=STAGE_DELIVER,
                        why=str(exc),
                        rung=outcome.rung,
                        exception=type(exc).__name__,
                    )
                )
                continue
            if not delivery.committed:
                # `deliver` refuses rather than raises, and the refusals it can
                # reach here are real answers: the change is no longer a change,
                # the target is ignored, the tree is dirty. Recording one keeps
                # the run going with the reason attached — the alternative,
                # treating a refusal as a delivery, is how B8 reported every
                # failure as a completion.
                attempt_refusals.append(
                    AttemptRefusal(
                        subject=contract.id,
                        stage=STAGE_DELIVER,
                        why=delivery.reason,
                        rung=outcome.rung,
                    )
                )
                continue
            # Read back off the worktree rather than carried from the reply: the
            # tree is what the next contract's sandbox archives and what the
            # whole-tree run reads, so it is also what the record should say was
            # delivered.
            files[delivery.path] = (plan.worktree / delivery.path).read_text(
                encoding="utf-8"
            )
            # Committed, not just written: the next contract's sandbox is
            # ``git archive HEAD`` of this worktree, and an uncommitted file
            # is not in HEAD.
            commits.append((contract.id, delivery.commit))

    test: TestRun | None = None
    if outcomes:
        # Every gate has run; the child's tests may now sit beside the output.
        for path, content in acceptance.items():
            _place(plan.worktree, path, content)
        test = _run_test(
            _whole_command(attempt_module, plan, outcomes[0][0]),
            plan.worktree,
            files,
            acceptance,
            config,
            sandbox_factory=_sandbox_factory(attempt_module),
        )
    refusals = tuple(str(r) for r in getattr(plan.proposer, "refusals", ()))
    written = _write_record(
        plan,
        config,
        db_path,
        acceptance,
        outcomes,
        traces,
        files,
        test,
        refusals,
        tuple(attempt_refusals),
        tuple(refused_traces),
        tuple(commits),
        where,
    )
    return MissionResult(
        plan=plan,
        acceptance=acceptance,
        outcomes=tuple(outcomes),
        traces=tuple(traces),
        files=files,
        test=test,
        record=written,
        proposer_refusals=refusals,
        attempt_refusals=tuple(attempt_refusals),
        commits=tuple(commits),
    )


class _Watched:
    """The attempt :func:`~mcgyvr.escalate.escalate` is handed, remembering the
    rung of the last Try it dispatched.

    A :class:`~mcgyvr.runner.RunnerError` propagates out of ``escalate`` with
    no Try attached, and item 3's trace has no entry for a try whose dispatch
    never returned. This is the one place the rung is known at the moment the
    exception leaves, so the refusal can name it. The wrapped attempt keeps
    its own ``trace``; the caller reads that off the original object.
    """

    def __init__(self, attempt: Callable[[Try], Judgement]) -> None:
        self._attempt = attempt
        self.rung: str | None = None

    def __call__(self, this: Try) -> Judgement:
        self.rung = this.rung.name
        return self._attempt(this)


def _sandbox_factory(attempt_module: types.ModuleType) -> Callable[[Path], Sandbox]:
    """Item 3's sandbox for the whole-tree run — the same one every try used.

    Item 3's ``MissionSandbox`` puts the workspace's sources ahead of the
    host's on ``PYTHONPATH``; the whole-tree run must import the same tree
    the per-try acceptances did, or ``gate.whole`` would be a figure about
    the host's installed package.
    """
    factory = getattr(attempt_module, "MissionSandbox", None)
    if factory is None or not callable(factory):
        raise SiblingMismatch(
            "attempt.MissionSandbox is not there; the whole-tree run would "
            "import the host's sources rather than the worktree's"
        )
    chosen: Callable[[Path], Sandbox] = factory
    return chosen


def _make_attempt(
    attempt_module: types.ModuleType,
    config: Config,
    plan: Plan,
    contract: Contract,
    acceptance: Mapping[str, str],
) -> Callable[[Try], Judgement]:
    """Item 3's attempt for one contract, bound to the pool by name.

    ``dispatch`` is item 3's own ``dispatch_via`` over the pool and
    ``family_of`` is :func:`mcgyvr.route.family_of` over the config — the two
    seams its docstring names for production. The acceptance timeout is left
    to item 3's default: it is a per-try bound, not the task's clock.
    """
    dispatch = _construct(
        attempt_module.dispatch_via, "attempt.dispatch_via", pool=plan.pool
    )
    made = _construct(
        attempt_module.make_attempt,
        "attempt.make_attempt",
        contract=contract,
        base=plan.worktree,
        test_paths=plan.task.test_paths,
        dispatch=dispatch,
        family_of=functools.partial(family_of, config),
        acceptance_files=dict(acceptance),
    )
    if not callable(made):
        raise SiblingMismatch(
            f"attempt.make_attempt returned a {type(made).__name__}, not a callable"
        )
    attempt: Callable[[Try], Judgement] = made
    return attempt


def _trace_of(attempt: object) -> tuple[dict[str, Any], ...]:
    """Item 3's per-try trace as plain data; empty for an attempt without one."""
    out: list[dict[str, Any]] = []
    for entry in getattr(attempt, "trace", ()):
        as_dict = getattr(entry, "as_dict", None)
        if callable(as_dict):
            laid = as_dict()
            if isinstance(laid, Mapping):
                out.append(dict(laid))
    return tuple(out)


def _whole_command(
    attempt_module: types.ModuleType, plan: Plan, first: Contract
) -> tuple[str, ...]:
    """The narrowed command for the whole assembled tree — ``first``'s.

    Every contract of one task narrows to the same test paths on the same
    base; the first *escalated* contract's stack decides the runner, as it
    did per try (a contract item 3 refused never had one).
    """
    command = _construct(
        attempt_module.acceptance_for,
        "attempt.acceptance_for",
        target=first.target,
        base=plan.worktree,
        test_paths=tuple(plan.task.test_paths),
    )
    return tuple(str(part) for part in command)


def _git(worktree: Path, *args: str) -> str:
    """Run git in ``worktree``, returning stdout, raising with git's complaint.

    Read-only here by construction: the one caller asks for ``rev-parse HEAD``.
    Writing is :mod:`mcgyvr.deliver`'s, and ``test_pattern_b_one_owner`` holds
    that — a ``commit`` reached through this helper would be a second delivery
    growing back under a smaller name.
    """
    done = subprocess.run(
        ["git", "-C", str(worktree), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise MissionError(f"git {args[0]} in {worktree} failed: {done.stderr.strip()}")
    return done.stdout


def _place(worktree: Path, rel: str, content: str | bytes) -> None:
    """Write one file under the worktree, refusing a path that leaves it."""
    root = worktree.resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise DeliveredPathEscapes(f"{rel!r} resolves to {target}, outside {root}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")


def _run_test(
    command: Sequence[str],
    worktree: Path,
    files: Mapping[str, str],
    acceptance: Mapping[str, str],
    config: Config,
    *,
    sandbox_factory: Callable[[Path], Sandbox],
) -> TestRun:
    """The narrowed command on the assembled tree, in a sandbox, under the clock.

    The sandbox archives the worktree's ``HEAD`` — the parent plus every
    committed delivery — and the delivered files are written again (the same
    content, so it is idempotent) with the child's tests beside them, the
    way item 3 writes them per try; a caller-supplied attempt whose files
    were never committed is covered by the same write. The command then runs
    on that copy with the credential variables filtered (E4), not in the
    canonical clone's worktree with the host environment. ``sandbox_factory``
    is item 3's, so the whole-tree run imports the workspace's sources the
    way every try did. A timeout is ``returncode=None`` with ``timed_out``
    set: a kill is not a verdict.
    """
    raw = config.get("budgets.task_timeout_s")
    timeout = None if raw is None else float(raw)
    with sandbox_factory(worktree) as sandbox:
        workspace = sandbox.workspace
        for path, content in files.items():
            _place(workspace, path, content)
        for path, content in acceptance.items():
            _place(workspace, path, content)
        result = sandbox.run(list(command), timeout=timeout)
    return TestRun(
        command=tuple(command),
        returncode=None if result.timed_out else result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
    )


def _outcome_dict(contract: Contract, outcome: Delivered | Halted) -> dict[str, Any]:
    """How one contract's climb ended — the rule that ended it, and the counts.

    Nothing verdict-shaped: the per-try verdicts and item 3's traces go under
    ``output.gate`` (:func:`_gate_dict`), the one block the record lets a
    pass/fail live in.
    """
    return {
        "contract": contract.id,
        "target": contract.target,
        "outcome": outcome.outcome.value,
        "rung": outcome.rung if isinstance(outcome, Delivered) else None,
        "entered": [f.name for f in outcome.entered],
        "attempts_spent": outcome.attempts_spent,
        "escalations": outcome.escalations,
        "detail": (
            outcome.judgement.detail
            if isinstance(outcome, Delivered)
            else outcome.detail
        ),
    }


def _gate_dict(
    contract: Contract,
    outcome: Delivered | Halted,
    trace: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """One contract's pass/fail material: the climb's verdicts and every try."""
    return {
        "contract": contract.id,
        "assurance": (
            outcome.assurance.value if isinstance(outcome, Delivered) else None
        ),
        "history": [
            {
                "rung": a.rung,
                "attempt": a.attempt,
                "verdict": a.verdict.value,
                "detail": a.detail,
            }
            for a in outcome.history
        ],
        "trace": list(trace),
    }


def _write_record(
    plan: Plan,
    config: Config,
    db_path: Path,
    acceptance: Mapping[str, str],
    outcomes: Sequence[tuple[Contract, Delivered | Halted]],
    traces: Sequence[tuple[dict[str, Any], ...]],
    files: Mapping[str, str],
    test: TestRun | None,
    refusals: tuple[str, ...],
    attempt_refusals: tuple[AttemptRefusal, ...],
    refused_traces: tuple[tuple[str, tuple[dict[str, Any], ...]], ...],
    commits: tuple[tuple[str, str], ...],
    where: Path,
) -> Path:
    """Lay the run out as item 5's record: output beside spec, verdicts in gate.

    ``refused_traces`` are the tries a contract made before its dispatch
    raised; they carry gate verdicts, so they go under ``output.gate`` like
    every other trace (``gate.refused``), keyed by contract. ``commits`` is
    the sha each delivered contract moved HEAD to, under ``output.head``
    beside the parent it moved from.
    """
    record = _sibling("record")
    task = plan.task
    what, model, endpoint = plan.proposer_binding
    ladder = [
        {"rung": r.name, "model": r.model, "endpoint": plan.pool.bind(r.name).base_url}
        for r in plan.pool.rungs
    ]
    identity = {
        "model": model,
        "endpoint": endpoint.base_url,
        "proposer": what,
        "ladder": ladder,
        "skipped": [{"rung": s.name, "reason": s.reason} for s in plan.pool.skipped],
        "config": None if config.path is None else str(config.path),
    }
    intent = {
        "record": INTENT_RECORD,
        "question": INTENT_QUESTION,
        "issue": "#365",
        "sha": task.sha,
        "parent": task.parent,
        "repo_root": str(task.repo_root),
        "corpus": str(db_path),
        "limits": list(INTENT_LIMITS),
    }
    output = {
        "files": dict(files),
        "contracts": [c.as_dict() for c in plan.decomposition.contracts],
        "refusals": [str(r) for r in plan.decomposition.refusals],
        "proposer_refusals": list(refusals),
        "attempt_refusals": [r.as_dict() for r in attempt_refusals],
        "outcomes": [_outcome_dict(c, o) for c, o in outcomes],
        "head": {
            "parent": task.parent,
            "commits": [
                {"contract": contract_id, "sha": sha} for contract_id, sha in commits
            ],
        },
        "acceptance": {"paths": list(acceptance), "test_paths": list(task.test_paths)},
        "gate": {
            "whole": None if test is None else test.as_dict(),
            "contracts": [
                _gate_dict(c, o, t) for (c, o), t in zip(outcomes, traces, strict=True)
            ],
            "refused": [
                {"contract": contract_id, "trace": list(trace)}
                for contract_id, trace in refused_traces
            ],
        },
    }
    written = record.write(
        where, identity=identity, intent=intent, spec=task.spec, output=output
    )
    return Path(written)


# --- CLI ---------------------------------------------------------------------


def _print_plan(plan: Plan) -> None:
    what, model, endpoint = plan.proposer_binding
    print(f"worktree: {plan.worktree}")
    print(f"proposer: {what} ({model} @ {endpoint.base_url})")
    print(
        f"index: {plan.index.stats.files_indexed} files, "
        f"{plan.index.stats.symbol_count} symbols"
    )
    print(plan.decomposition.explain() or "(nothing emitted, no refusal recorded)")
    for document in plan.decomposition.documents:
        print("---")
        print(document.rstrip())


def _release(
    tasks: types.ModuleType, into: Path, scratch: Path | None, *, keep: bool
) -> None:
    """Give the worktree back to the clone once the run is over.

    ``tasks.checkout`` registers the worktree in the canonical clone with
    ``git worktree add``; left behind, a campaign's worth of them sits in the
    owner's real clones until someone prunes, and a re-run into the same
    ``--into`` is refused for the wrong reason. A run that refused before the
    checkout left nothing to release (``into`` does not exist: checkout
    refuses an existing path, so its presence means checkout made it). A
    release that fails is reported, not raised — the run's own outcome is the
    one to surface. ``scratch`` is the temp dir this runner made for a default
    ``into``, removed with it.
    """
    if keep:
        if into.exists():
            print(f"worktree kept: {into}", file=sys.stderr)
        return
    if into.exists():
        try:
            tasks.release(into)
        except tasks.TaskError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            return
    if scratch is not None:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one admitted commit through the orchestrator on the local pool "
            "and leave a record under records/missions/<sha>/ (#365 item 4)."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--into",
        type=Path,
        default=None,
        help="where the worktree goes (default: a fresh temp dir)",
    )
    parser.add_argument("--proposer-rung", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="stop after decompose and print the contracts",
    )
    parser.add_argument(
        "--keep-worktree",
        action="store_true",
        help=(
            "leave the assembled worktree registered in the clone for inspection "
            "(default: release it once the record is written)"
        ),
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    tasks = _sibling("tasks")
    task = tasks.load(args.db, args.sha)
    into = args.into
    scratch: Path | None = None
    if into is None:
        scratch = Path(tempfile.mkdtemp(prefix=f"mission-{task.sha[:12]}-"))
        into = scratch / "wt"

    try:
        if args.dry_run:
            _print_plan(
                plan_task(task, config, into=into, proposer_rung=args.proposer_rung)
            )
            return 0
        result = run_task(
            task,
            config,
            db_path=args.db,
            into=into,
            proposer_rung=args.proposer_rung,
        )
    except MissionError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    finally:
        _release(tasks, into, scratch, keep=args.keep_worktree)
    _print_plan(result.plan)
    for refusal in result.attempt_refusals:
        at = f" at {refusal.stage}" + (f" on {refusal.rung}" if refusal.rung else "")
        print(f"refused{at}: {refusal.subject}: {refusal.why}", file=sys.stderr)
    for contract, outcome in result.outcomes:
        print(f"{contract.id}: {outcome.outcome.value}")
    for contract_id, sha in result.commits:
        print(f"committed: {contract_id} -> {sha[:12]}")
    if result.test is not None:
        print(f"test: {' '.join(result.test.command)} -> {result.test.returncode}")
    print(f"record: {result.record}")
    print(
        f"{result.delivered} of {len(result.outcomes)} contract(s) delivered; the "
        "record carries no verdict — that is the month's review (#365)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
