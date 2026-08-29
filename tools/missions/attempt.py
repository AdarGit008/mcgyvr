"""The attempt: one :class:`~mcgyvr.route.Try` becomes a prompt, a dispatch, a
file, a gate run and a judgement — with the acceptance narrowed to the task's tests.

`#365 <https://github.com/AdarGit008/mcgyvr/issues/365>`_, item 3. Off-SURFACE:
the product pin (``tools/bench/product.py --check``) does not move for this file.

:func:`mcgyvr.escalate.escalate` takes ``attempt: Callable[[Try], Judgement[T]]``
and says of it: "it assembles a prompt, dispatches, applies, gates and calls
:func:`~mcgyvr.escalate.judge`. Keeping it a parameter is what lets every rule
here be asserted without a model, a backend or a sandbox." Nothing in the tree
binds that parameter to a live rung — the breadth rig (``tools/breadth/measure``)
walks the same prompt → dispatch → parse → gate loop but dispatches to one worker
and never escalates. This module is the first binding, and it is built from the
shipped assembly and nothing else: :func:`~mcgyvr.worker.prompt.build_prompt`
renders, :func:`~mcgyvr.worker.reply.parse_reply` reads, the sandbox is E4's,
the scorer is :meth:`~mcgyvr.gate.Gate.run`, and the verdict is
:func:`~mcgyvr.escalate.judge`'s. A rung is never told where it runs: the Try's
rung name goes through the caller's dispatch, which is the seam
:mod:`mcgyvr.pool` draws.

**The defect this module prevents is an acceptance that is not the task's.** A
mission's base is the *parent* tree of a real commit (item 1) and its bar is the
*child's* test files — the ones the commit added. The adapter's conventional
test command (``pytest``, ``npm test``) runs the repository's whole suite, and on
a real repository that suite has three ways of lying about one attempt: a test
elsewhere in the tree that was already red at the parent (rejecting the worker
for a failure it did not cause), a suite that takes ten minutes for a change one
file wide (the timeout fires, and a kill is not a verdict), and a suite that
passes wholesale because the child's test was never on the path at all. So the
command is **narrowed to the task's test paths** — :func:`narrow_test_command`
appends them, and refuses by name a stack that offers no command, because
"no acceptance ran" must never read as "accepted". The child's tests are not in
the base by construction (item 1's leakage rule), so they are supplied here as
``acceptance_files`` and written into the sandbox **after** the change set is
computed: the gate lints, scopes and secret-scans the worker's diff alone, and
the acceptance command then finds the bar beside it. A test path in neither the
base nor ``acceptance_files`` is refused before a token is spent.

**What is the worker's and what is not, by verdict.** A reply the parser refuses
is the worker's: ``FAILED``, with the parser's own words as the retry notes, so
a second attempt on the same rung is told what shape was wrong. A reply whose
fenced block carries no code is the parser's named ``refusal`` (#174), and its
routing consequence is the one :mod:`mcgyvr.worker.reply` states — "escalate
rather than retrying this rung" — which in :mod:`mcgyvr.route`'s vocabulary is
``DECLINED``: the climb leaves the rung at once. A prompt that does not fit the
contract's ceiling is nobody's: :class:`PromptDoesNotFit` is raised, since a
preflight issue is an orchestration error and charging it to a rung would put a
failure on the ladder that no rung could clear. A dispatch that raises is not
caught, for :func:`~mcgyvr.route.climb`'s reason: a dead socket folded into a
judgement would report "this family cannot do the work" about a machine that
was never asked.

**Every try is traced, whatever it came to.** :func:`~mcgyvr.escalate.judge`
carries a value only on ``PASSED``, and the mission record (item 5) wants the
output beside the spec whether or not the gate accepted it — the owner's judge
reads output against the issue body, blind, and a failed attempt's file is
evidence too. So the callable is an :class:`Attempt` object whose
:attr:`~Attempt.trace` keeps, per Try, the completion, the parse outcome, the
gate result and the judgement; :meth:`Trace.as_dict` lays it out with every
pass/fail-shaped field under ``gate``, which is the one place the record lets a
verdict live.

**The acceptance imports the sandbox's sources, not the host's.** E4's
temp-directory mode runs a command on the host with the host's environment,
which is what lets it find a toolchain at all — and is also how a src-layout
repository would score the wrong tree: mcgyvr itself is installed editable
from the primary checkout, so ``import mcgyvr`` inside a sandbox populated
from a *mission* worktree resolves to the host's ``src``, and the child's test
would run the host's code against the worker's file. :class:`MissionSandbox`
is the default factory for that reason: it puts ``<workspace>/src`` and
``<workspace>`` ahead of any inherited ``PYTHONPATH`` for every command it
runs, so the sources the worker's file sits beside are the ones the test
imports. A caller who binds another factory takes that property with it.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.catalog import Family
from mcgyvr.deliver import Accepted
from mcgyvr.escalate import Judgement, RetryNotes, judge
from mcgyvr.gate import Acceptance, ChangeSet, Gate, GateResult, LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.route import Try, Verdict
from mcgyvr.runner import Completion, Request, dispatch
from mcgyvr.sandbox.base import CommandResult, Sandbox
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.worker.prompt import build_prompt
from mcgyvr.worker.reply import ParsedFile, ReplyError, parse_reply

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.pool import SourceMap

__all__ = [
    "ACCEPTANCE_TIMEOUT_S",
    "AcceptanceNotTheTasks",
    "Attempt",
    "AttemptError",
    "Dispatch",
    "MissionSandbox",
    "NoAdapterForTarget",
    "NoTestCommand",
    "PromptDoesNotFit",
    "TargetOutsideWorkspace",
    "TestPathMissing",
    "Trace",
    "acceptance_files_from",
    "acceptance_for",
    "adapter_for",
    "dispatch_via",
    "make_attempt",
    "narrow_test_command",
]

#: The wall-clock ceiling on the narrowed acceptance command, per run. The
#: breadth rig's figure (``tools/bench/score.ACCEPTANCE_TIMEOUT_S``), adopted
#: rather than re-derived: one test file on one change is the same shape of
#: work that figure was set for.
ACCEPTANCE_TIMEOUT_S = 120.0

#: The parser's code for a fenced block that carries no code (#174). Named here
#: so the routing consequence below is keyed on the parser's word, not a copy.
_REFUSAL = "refusal"

#: What a test runner writes beside the code it runs. The acceptance rung
#: snapshots the tree before and after its command and rejects a command that
#: changed it (``tree-altering``), honouring ``.gitignore``; a repository that
#: never ignored its bytecode would then reject every attempt for pytest's
#: litter. The bench rig's ``IGNORED`` list, appended to the workspace's own
#: ``.gitignore`` after the change set is computed, so it enters no diff.
_RUNNER_LITTER = "__pycache__/\n*.pyc\nnode_modules/\n"

#: How a Try reaches a rung: the Try (whose ``rung`` and ``capacity`` name where
#: and under what bound) and the assembled request, to a completion. A fake is
#: this shape too, which is what makes the loop assertable without a backend.
type Dispatch = Callable[[Try, Request], Completion]


class AttemptError(Exception):
    """An attempt could not be assembled, with the offending thing named."""


class NoTestCommand(AttemptError):  # noqa: N818
    """The target's stack offers no test command, so no acceptance could run."""


class NoAdapterForTarget(AttemptError):  # noqa: N818
    """No shipped language adapter owns the contract's target."""


class TestPathMissing(AttemptError):  # noqa: N818
    """A test path is in neither the base tree nor ``acceptance_files``."""


class PromptDoesNotFit(AttemptError):  # noqa: N818
    """The assembled prompt is over the contract's ceiling — nobody's failure."""


class TargetOutsideWorkspace(AttemptError):  # noqa: N818
    """The contract's target would be written outside the sandbox workspace."""


class AcceptanceNotTheTasks(AttemptError):  # noqa: N818
    """The contract declares an acceptance other than the narrowed command."""


# --- the narrowing -----------------------------------------------------------


def narrow_test_command(
    cmd: list[str] | None, test_paths: tuple[str, ...]
) -> list[str]:
    """The adapter's test command, narrowed to the task's test files.

    ``pytest`` becomes ``pytest tests/test_mod.py``; ``npm test --`` becomes
    ``npm test -- src/a.test.ts``. The paths are appended as given — relative
    to the sandbox workspace, which is the repository root — and the command's
    own shape is not inspected: whether the runner takes paths positionally is
    the adapter's to know when it chooses the command.

    ``None`` is refused rather than returned: an adapter answering ``None``
    means this stack declares no test runner, and an attempt with no
    acceptance would be scored by lint and syntax alone while reading as
    accepted. An empty ``test_paths`` is refused for the mirror reason — a
    command with nothing appended is the whole suite, the thing this function
    exists to avoid running.
    """
    if cmd is None:
        raise NoTestCommand(
            f"no test command: the target's stack declares no test runner, so "
            f"the acceptance for {', '.join(test_paths) or '(no test paths)'} "
            f"cannot run and the attempt would be scored by no bar"
        )
    if not test_paths:
        raise AttemptError(
            f"no test paths to narrow {cmd!r} to: unnarrowed, it would run the "
            f"whole suite, which is not this task's acceptance"
        )
    return [*cmd, *test_paths]


def adapter_for(
    target: str, adapters: Sequence[LanguageAdapter] | None = None
) -> LanguageAdapter:
    """The adapter that owns ``target``, from the shipped pair by default."""
    candidates = (
        tuple(adapters)
        if adapters is not None
        else (PythonAdapter(), JavaScriptAdapter())
    )
    for adapter in candidates:
        if adapter.owns(target):
            return adapter
    offered = ", ".join(a.name for a in candidates) or "none"
    raise NoAdapterForTarget(
        f"no language adapter owns target {target!r} (adapters: {offered}); "
        f"without one there is no test command to narrow and no lint to apply"
    )


def acceptance_for(
    target: str,
    base: Path,
    test_paths: tuple[str, ...],
    adapters: Sequence[LanguageAdapter] | None = None,
) -> tuple[str, ...]:
    """The narrowed command for ``target``'s stack in ``base``, as argv.

    What :func:`make_attempt` will run, computed the same way, so a caller
    building the contract can declare it (``acceptance: [shlex.join(...)]``)
    and the two cannot disagree — a contract that names a different command is
    refused there rather than quietly overridden.
    """
    adapter = adapter_for(target, adapters)
    return tuple(narrow_test_command(adapter.locate_test_command(base), test_paths))


# --- the two seams a caller binds ---------------------------------------------


def dispatch_via(pool: SourceMap) -> Dispatch:
    """A :data:`Dispatch` that sends each Try to its rung through the pool.

    The binding :func:`make_attempt` expects in production: the rung name and
    the capacity are the Try's, the endpoint and the model are the pool's, and
    nothing here learns where the rung runs — the seam is
    :func:`mcgyvr.runner.dispatch`'s.
    """

    def send(this: Try, request: Request) -> Completion:
        return dispatch(pool, this.rung.name, request, capacity=this.capacity)

    return send


def acceptance_files_from(
    repo_root: Path, sha: str, test_paths: tuple[str, ...]
) -> dict[str, str]:
    """The child's test files, read from the canonical clone at ``sha``.

    Item 1 checks out the *parent* and keeps the child's tests off disk (the
    leakage rule); this is how they reach the sandbox instead — by content,
    from the commit that added them, never from a working tree. A path the
    commit does not carry is refused by name.
    """
    files: dict[str, str] = {}
    for path in test_paths:
        shown = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{sha}:{path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if shown.returncode != 0:
            raise TestPathMissing(
                f"test path {path!r} is not in commit {sha} of {repo_root}: "
                f"{shown.stderr.strip()}"
            )
        files[path] = shown.stdout
    return files


# --- the sandbox -------------------------------------------------------------


#: The workspace-relative roots a command must import from first: a src-layout
#: package, then the repository root for a flat layout. Only the ones that
#: exist are layered, so a repository with no ``src/`` gets no phantom entry.
_IMPORT_ROOTS = ("src", ".")


class MissionSandbox(TempDirSandbox):
    """E4's temp-directory sandbox with the workspace's sources first on the path.

    The weaker mode runs on the host with the host's environment, and the
    host's Python has the *primary* checkout's package installed editable
    (a ``.pth`` entry naming its ``src``). A test in a sandbox populated from
    a mission worktree then imports the host's package, not the archived copy
    the worker's file was just written into — and the acceptance would score
    a tree the worker never touched. ``PYTHONPATH`` entries precede
    ``site-packages`` on ``sys.path``, and a ``.pth`` entry is appended after
    it, so layering ``<workspace>/src`` and ``<workspace>`` in front of
    whatever ``PYTHONPATH`` the host or the caller carries is what makes the
    sandbox's sources the ones an import finds. A caller's own ``env`` is
    still layered and still vetted by the base class; only ``PYTHONPATH`` is
    composed here rather than replaced.
    """

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        extra = dict(env or {})
        inherited = extra.get("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
        ahead = [
            str(root)
            for root in ((self.workspace / name).resolve() for name in _IMPORT_ROOTS)
            if root.is_dir()
        ]
        extra["PYTHONPATH"] = os.pathsep.join(
            [*ahead, *([inherited] if inherited else [])]
        )
        return super().run(command, timeout=timeout, env=extra)


# --- the trace ---------------------------------------------------------------


@dataclass(frozen=True)
class Trace:
    """Everything one Try produced, kept whatever the judgement was.

    ``gate`` is ``None`` when the reply never became a file — there was no
    change to gate — and ``reply`` then carries the parser's refusal.
    """

    rung: str
    attempt: int
    of: int
    target: str
    completion: Completion
    reply: ParsedFile | ReplyError
    gate: GateResult | None
    judgement: Judgement[ParsedFile]

    @property
    def content(self) -> str | None:
        """The file the worker produced, or ``None`` when no file was parsed."""
        return self.reply.content if isinstance(self.reply, ParsedFile) else None

    def as_dict(self) -> dict[str, Any]:
        """The trace as plain data, with every pass/fail under ``gate``.

        The mission record (item 5) refuses a verdict-shaped key anywhere but
        ``output.gate``; the judgement's verdict and assurance *are* the gate's
        reading (:func:`~mcgyvr.escalate.judge` reads nothing else here), so
        they are laid out inside that block rather than beside it.
        """
        files = {self.target: self.content} if self.content is not None else {}
        gate: dict[str, Any] = {
            "ran": self.gate is not None,
            "accepted": self.gate.accepted if self.gate is not None else False,
            "findings": [str(f) for f in self.gate.findings] if self.gate else [],
            "environment_issues": (
                list(self.gate.environment_issues) if self.gate else []
            ),
            "inconclusive": [str(i) for i in self.gate.inconclusive]
            if self.gate
            else [],
            "observations": (
                [str(o) for o in self.gate.observations] if self.gate else []
            ),
            "verdict": self.judgement.verdict.value,
            "assurance": (
                self.judgement.assurance.value
                if self.judgement.assurance is not None
                else None
            ),
            "policy": self.judgement.policy,
            "upgraded": self.judgement.upgraded,
            "detail": self.judgement.detail,
        }
        return {
            "rung": self.rung,
            "attempt": self.attempt,
            "of": self.of,
            "model": self.completion.model,
            "source": self.completion.source,
            "stop_reason": self.completion.stop_reason.value,
            "input_tokens": self.completion.input_tokens,
            "output_tokens": self.completion.output_tokens,
            "latency_s": round(self.completion.latency_s, 3),
            "reply": {
                "parsed": isinstance(self.reply, ParsedFile),
                "error": None
                if isinstance(self.reply, ParsedFile)
                else self.reply.code,
                "text": self.completion.text,
            },
            "files": files,
            "gate": gate,
        }


# --- the attempt -------------------------------------------------------------


class Attempt:
    """The callable :func:`~mcgyvr.escalate.escalate` is handed, with its trace.

    Built by :func:`make_attempt`; call it with a Try. Each call opens a fresh
    sandbox from ``base`` — nothing from one try survives into the next, and
    two rungs never share a workspace — and appends one :class:`Trace`.
    """

    def __init__(
        self,
        *,
        contract: Contract,
        base: Path,
        command: tuple[str, ...],
        acceptance_files: Mapping[str, str],
        dispatch: Dispatch,
        family_of: Callable[[str], Family],
        sandbox_factory: Callable[[Path], Sandbox],
        adapters: Sequence[LanguageAdapter] | None,
        gate: Gate,
        timeout_s: float | None,
        quality_sensitive: bool,
    ) -> None:
        self._contract = contract
        self._base = base
        self._command = command
        self._acceptance_files = dict(acceptance_files)
        self._dispatch = dispatch
        self._family_of = family_of
        self._sandbox_factory = sandbox_factory
        self._adapters = adapters
        self._gate = gate
        self._timeout_s = timeout_s
        self._quality_sensitive = quality_sensitive
        self._retry: dict[str, RetryNotes | None] = {}
        self._trace: list[Trace] = []

    @property
    def command(self) -> tuple[str, ...]:
        """The narrowed acceptance command every try runs."""
        return self._command

    @property
    def trace(self) -> tuple[Trace, ...]:
        """Every try so far, in the order the climb made them."""
        return tuple(self._trace)

    def __call__(self, this: Try) -> Judgement[ParsedFile]:
        contract = self._contract
        family = self._family_of(this.rung.name)

        # A second attempt on the same rung is told what the last one got
        # wrong and nothing else — RetryNotes are #43's rule, rendered by the
        # prompt. A first attempt on any rung carries none.
        retry = self._retry.get(this.rung.name) if this.attempt > 1 else None
        prompt = build_prompt(contract, adapters=self._adapters, retry=retry)
        if prompt.fit_issue is not None:
            raise PromptDoesNotFit(
                f"the prompt for {contract.id!r} on rung {this.rung.name!r} does "
                f"not fit: {prompt.fit_issue} (an orchestration error, not the "
                f"rung's)"
            )

        request = Request(
            prompt=prompt.user,
            system=prompt.system,
            max_output_tokens=contract.limits.max_output_tokens,
            quality_sensitive=self._quality_sensitive,
        )
        completion = self._dispatch(this, request)

        reply = parse_reply(
            completion.text,
            output_schema=contract.output_schema,
            stop_reason=completion.stop_reason,
            target=contract.target,
        )
        if isinstance(reply, ReplyError):
            judgement = self._unparsed(reply)
            gate: GateResult | None = None
        else:
            gate, bound = self._gate_run(reply)
            judgement = judge(contract, family, gate, reply)
            if bound is not None:
                # The binding is attached here rather than passed into `judge`,
                # because `judge` decides a verdict and has no tree to read from
                # — minting inside it would mean handing it content, which is the
                # substitution `Accepted` exists to make unconstructable. Every
                # accepted try overwrites the last, so what survives the climb is
                # the binding for the try `escalate` actually returned on.
                judgement = replace(judgement, accepted=bound)

        self._retry[this.rung.name] = judgement.retry
        self._trace.append(
            Trace(
                rung=this.rung.name,
                attempt=this.attempt,
                of=this.of,
                target=contract.target,
                completion=completion,
                reply=reply,
                gate=gate,
                judgement=judgement,
            )
        )
        return judgement

    def _unparsed(self, error: ReplyError) -> Judgement[ParsedFile]:
        """The judgement for a reply that never became a file.

        The parser's ``refusal`` is the one code with its own routing
        consequence — leave the rung — and every other code is the rung's
        failure to follow the protocol, retried with the parser's words.
        """
        if error.code == _REFUSAL:
            return Judgement(verdict=Verdict.DECLINED, detail=str(error))
        return Judgement(
            verdict=Verdict.FAILED,
            retry=RetryNotes(checks=("reply",), lines=(str(error),)),
            detail=f"the reply did not parse as one file: {error}",
        )

    def _gate_run(self, reply: ParsedFile) -> tuple[GateResult, Accepted | None]:
        """Write the file into a fresh sandbox, gate it, and bind what it read.

        The change set is computed **before** the acceptance files land, so
        the gate's own rungs see the worker's diff and nothing else; the
        narrowed command then runs with the child's tests beside the change.

        **The binding is minted here because here is the only place it can be.**
        This sandbox is opened per try and torn down when the ``with`` closes —
        ``Sandbox.__exit__`` removes the workspace tree outright — so by the time
        ``escalate`` returns a ``Delivered`` there is no tree anywhere holding
        the accepted bytes. Delivery used to be handed the caller's copy of the
        reply instead, which is a string nothing had re-read since the gate ran
        (pattern B). :meth:`~mcgyvr.deliver.Accepted.read` takes the bytes off
        the workspace the verdict was reached over, one line after it was
        reached and while it still exists.

        ``None`` on a rejected verdict, and deliberately: an ``Accepted`` is a
        binding between bytes and an *acceptance*, so minting one for a rejection
        would make the type mean "some bytes and some verdict" and give a caller
        something to mistake for a licence to write.
        """
        contract = self._contract
        with self._sandbox_factory(self._base) as sandbox:
            workspace = sandbox.workspace
            _write(workspace, contract.target, reply.content)
            changeset = ChangeSet.detect(workspace, sandbox.base_changeset_ref())
            for path, content in self._acceptance_files.items():
                _write(workspace, path, content)
            _ignore_runner_litter(workspace)
            acceptance = Acceptance(
                sandbox=sandbox,
                commands=(self._command,),
                timeout=self._timeout_s,
            )
            result = self._gate.run(
                changeset,
                contract.scope,
                semantic=None,
                acceptance=acceptance,
            )
            if not result.accepted:
                return result, None
            return result, Accepted.read(
                repo=workspace, contract=contract, result=result
            )


def _ignore_runner_litter(workspace: Path) -> None:
    """Append :data:`_RUNNER_LITTER` to the workspace's ``.gitignore``."""
    ignore = workspace / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    joiner = "" if not existing or existing.endswith("\n") else "\n"
    ignore.write_text(existing + joiner + _RUNNER_LITTER, encoding="utf-8")


def _write(workspace: Path, relative: str, content: str) -> None:
    """Write ``content`` at ``relative`` under ``workspace``, and nowhere else."""
    destination = (workspace / relative).resolve()
    if not destination.is_relative_to(workspace.resolve()):
        raise TargetOutsideWorkspace(
            f"{relative!r} resolves to {destination}, outside the sandbox "
            f"workspace {workspace}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def make_attempt(
    *,
    contract: Contract,
    base: Path,
    test_paths: tuple[str, ...],
    dispatch: Dispatch,
    family_of: Callable[[str], Family],
    acceptance_files: Mapping[str, str] | None = None,
    sandbox_factory: Callable[[Path], Sandbox] = MissionSandbox,
    adapters: Sequence[LanguageAdapter] | None = None,
    gate: Gate | None = None,
    timeout_s: float | None = ACCEPTANCE_TIMEOUT_S,
    quality_sensitive: bool = True,
) -> Attempt:
    """Bind one task to the loop :func:`~mcgyvr.escalate.escalate` drives.

    ``base`` is the parent tree (item 1's worktree) every sandbox is populated
    from. ``test_paths`` narrow the adapter's test command; ``acceptance_files``
    are those paths' contents when the base does not hold them, which for a
    mission is always (:func:`acceptance_files_from` reads them off the child
    commit). ``dispatch`` is how a Try reaches its rung — :func:`dispatch_via`
    in production, a fake in a test — and ``family_of`` maps a rung name to
    its family for :func:`~mcgyvr.escalate.judge`; in production that is
    ``functools.partial(mcgyvr.route.family_of, config)``.

    Everything that can refuse without a model does so here, before the first
    Try: no adapter for the target, no test command for the stack, a test path
    with no content anywhere, and a contract whose declared commands —
    ``acceptance`` or, for ``bug_fix``, ``demonstration`` — are anything but
    the narrowed command (the schema requires one for a model-run type, so the
    caller declares :func:`acceptance_for`'s answer and nothing else).
    ``quality_sensitive`` defaults to ``True`` because a mission's output is
    read as a measurement of the pool (CAV-01: the caveated path refuses
    rather than answering). ``sandbox_factory`` defaults to
    :class:`MissionSandbox` so the acceptance imports the sandbox's sources
    and not the host's installed copy of the same package.
    """
    supplied = dict(acceptance_files or {})
    command = acceptance_for(contract.target, base, test_paths, adapters)
    for path in test_paths:
        if path not in supplied and not (base / path).is_file():
            raise TestPathMissing(
                f"test path {path!r} is neither in the base tree {base} nor in "
                f"acceptance_files; the narrowed command {' '.join(command)!r} "
                f"would run against nothing"
            )
    # A bug_fix contract carries the bar as its demonstration (the catalog
    # requires one and refuses the same command in both lists), the
    # pass-at-baseline types as their acceptance; either way the one command a
    # mission runs is the narrowed one, so the union is checked against it.
    declared = {
        tuple(shlex.split(c)) for c in (*contract.acceptance, *contract.demonstration)
    }
    if declared and declared != {command}:
        raise AcceptanceNotTheTasks(
            f"contract {contract.id!r} declares "
            f"{list(contract.acceptance) + list(contract.demonstration)!r}, but "
            f"the task's acceptance is {shlex.join(command)!r}; the record would "
            f"name a bar that did not run"
        )
    return Attempt(
        contract=contract,
        base=base,
        command=command,
        acceptance_files=supplied,
        dispatch=dispatch,
        family_of=family_of,
        sandbox_factory=sandbox_factory,
        adapters=adapters,
        gate=gate if gate is not None else Gate(adapters),
        timeout_s=timeout_s,
        quality_sensitive=quality_sensitive,
    )
