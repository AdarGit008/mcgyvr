"""Turning a request into proposals through the orchestrator role.

Two proposers live here. ``proposer_for`` renders the evidence as a prose
prompt, dispatches it to the ``orchestrator`` role and parses the JSON reply
into proposals. ``classifier_proposer_for`` asks the jev role one typed Choice
per field — ``task_type``, ``target``, ``symbol``, ``interface``, ``deps``,
``allow`` — in dependency order, and turns the answers into one proposal,
declining when a load-bearing answer falls short. ``proposer_by_authoring``
picks between them for the configured strategy.

``NO_ORCHESTRATOR_ROLE`` is what a caller prints when no orchestrator unit is
bound, so no prompt can be turned into contracts.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.catalog import TaskType
from mcgyvr.decision import (
    JEV_ROLE,
    ChoiceAnswer,
    Decision,
    DecisionError,
    Question,
    classify_for,
    jev_bound,
)
from mcgyvr.orchestrator.candidates import (
    _NO_SYMBOL,
    CandidateSet,
    Provenance,
    candidate_targets,
    choose,
    collapse,
    completable,
    deps_candidates,
    directive,
    enumerate_candidates,
    interface_candidates,
    kind_for,
    scope_candidates,
    stop_condition,
    symbol_candidates,
    target_candidates,
    task_type_candidates,
)
from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal, Proposer
from mcgyvr.orchestrator.fields import (
    abstain_line,
    abstain_value,
    criterion,
    render_choice,
    value_by_id,
)
from mcgyvr.orchestrator.telemetry import DecisionRecord, ShadowSink
from mcgyvr.runner import Request, dispatch_role
from mcgyvr.worker.reply import FENCE_OPEN as _FENCE_OPEN

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.local_pool import SourceMap

#: The role whose bound unit turns a prompt into contracts: `proposer_for`
#: dispatches the prose prompt there, `classifier_proposer_for` asks the typed
#: questions there. No binding means nothing here can propose.
ORCHESTRATOR_ROLE = "orchestrator"

#: Printed, with a refusal exit, when no orchestrator unit is bound and so no
#: prompt can be turned into contracts: the text names the ways forward.
NO_ORCHESTRATOR_ROLE = (
    "the orchestrator role is not configured, so a prompt cannot be turned "
    "into contracts here. Bind `orchestrator.unit` and `orchestrator.model` "
    "in the config, or author a contract yourself and run it with "
    "`mcgyvr run`."
)


class DelegationError(RuntimeError):
    """Base for every way delegation can fail to produce proposals."""


class OrchestratorUnavailableError(DelegationError):
    """The role resolves to no unit, so its prompt cannot be dispatched."""


class UnreadableProposalError(DelegationError):
    """A reply that cannot be read as proposals: not JSON, or the wrong shape."""


def build_prompt(evidence: Evidence) -> str:
    """Render the evidence as the prose prompt the orchestrator replies to.

    The request comes first, then the resolution's candidates with each one's
    score and the signals that matched it, then the regions already read —
    labelled with their file, line span, selection reason and the candidate
    that motivated them — then the regions deferred for budget, the task-type
    vocabulary and the reply format. Sections that would carry nothing (no
    candidates, no deferred regions) are omitted, and the rest are joined with
    blank lines.
    """
    resolution = evidence.resolution
    exploration = evidence.exploration
    sections: list[str] = []

    sections.append(
        "You are the orchestrator. Given a request and the deterministic "
        "evidence below — a ranked shortlist and the file regions the "
        "shortlist justified reading — propose the units of work that satisfy "
        "the request. You name references only; the repository supplies the "
        "facts. Return the JSON array described at the end and nothing else."
    )
    sections.append(f"REQUEST:\n{evidence.prompt}")

    if resolution.candidates:
        candidates = "\n".join(
            f"- {c.path} (score {c.score:g}): {', '.join(c.evidence)}"
            for c in resolution.candidates
        )
    else:
        candidates = "(no candidate matched the request)"
    sections.append(f"RESOLUTION ({resolution.verdict.value}):\n{candidates}")

    if exploration.reads:
        reads: list[str] = []
        for read in exploration.reads:
            reads.append(
                f"### {read.path}:{read.start}-{read.end} "
                f"[{read.reason}, shortlist #{read.candidate_rank}]\n{read.text}"
            )
        sections.append("READ REGIONS:\n" + "\n\n".join(reads))

    if exploration.deferred:
        deferred = "\n".join(
            f"- {d.path}:{d.start}-{d.end} [{d.reason}]" for d in exploration.deferred
        )
        sections.append(
            f"DEFERRED (outside the read budget, so not shown):\n{deferred}"
        )

    sections.append(f"TASK TYPES:\n{_vocabulary(evidence.vocabulary)}")
    sections.append(_reply_format())
    return "\n\n".join(sections)


def _vocabulary(vocabulary: Sequence[Any]) -> str:
    """List the servable task types with the facts a proposal has to respect.

    Each block names the type, its doc and its guarantee, then either the
    evidence derived from the contract (for evidence-derived types, rule by
    rule) or the evidence it requires, flagged when the type also needs
    acceptance or demonstration commands. An empty vocabulary renders "(none)".
    """
    blocks: list[str] = []
    for task in vocabulary:
        lines = [f"- {task.name}: {task.doc}"]
        lines.append(f"    guarantee: {task.guarantee}")
        if getattr(task, "evidence_derived", False):
            lines.append("    evidence is DERIVED from the contract, never chosen:")
            lines.append("        always: gate")
            lines.append("        demonstration non-empty -> failing_test_first")
            lines.append("        acceptance non-empty -> tests_pass")
            lines.append("        no_semantic_change: true -> no_semantic_change")
            lines.append("        type_check: true -> type_check")
        else:
            evidence = ", ".join(e.name for e in task.required_evidence)
            lines.append(f"    evidence: {evidence}")
            if task.needs_acceptance_commands:
                lines.append("    REQUIRES acceptance commands (pass at baseline).")
            if task.needs_demonstration_commands:
                lines.append(
                    "    REQUIRES demonstration commands (fail before the change, "
                    "pass after)."
                )
        blocks.append("\n".join(lines))
    return "\n".join(blocks) or "(none)"


def _reply_format() -> str:
    """Describe the JSON array `proposals_from_reply` reads, field by field.

    It states the keys every object needs — plus the output cap a code type must
    also carry — what each optional key means and what it derives downstream,
    that optional keys are omitted rather than written as null, and that `[]` is
    the reply when nothing can be proposed.
    """
    return (
        "REPLY FORMAT:\n"
        "Return one JSON array of proposal objects and no prose. Each object "
        "has these fields:\n"
        '- "task_type" (string, required): one of the TASK TYPES above.\n'
        '- "task" (string, required): the directive — what to change.\n'
        '- "target" (string, required): a path exactly as it appears in '
        "RESOLUTION or READ REGIONS.\n"
        '- "interface" (string, optional): the exact interface the result must '
        "expose.\n"
        '- "deps" (array of objects, optional): dependencies the target may '
        'call, each {"path", "symbol", "note"} where path and symbol name a '
        "symbol shown in RESOLUTION or READ REGIONS and note says how the "
        "target uses it. Propose a dependency only when its symbol is named "
        "there; otherwise omit the field rather than guessing a name. A "
        "dependency is an existing symbol: never name the symbol the REQUEST "
        "asks you to create — it is the target's output, not a dependency.\n"
        '- "operation" (string, optional): a deterministic operation a tool '
        "performs instead of a model, for task_type code.\n"
        '- "sources" (array of strings, optional): other repo files to give '
        "the worker whole, beside the target.\n"
        '- "depends_on" (array of whole numbers, optional): 0-based indexes '
        "into this same array of proposals — the contracts that must complete "
        "before this one may run. Index 0 is the first proposal in the reply. "
        "Omit when this proposal waits on nothing.\n"
        '- "allow" (array of strings, optional): paths the change may touch; '
        "omit to allow the target alone.\n"
        '- "forbid" (array of strings, optional): paths the change must not '
        "touch.\n"
        '- "stop_conditions" (array of strings): things that, if true, mean the '
        "worker must stop rather than guess. Required for every model-executed "
        "type.\n"
        '- "acceptance" (array of command strings, optional): commands that must '
        "pass after the change. For task_type code a non-empty list derives "
        "tests_pass evidence. Each entry runs with no shell: no `|`, `&&`, "
        "`||`, `;`, `<`, `>` or a leading `VAR=` — name one program per "
        "entry, or commit a script that does the pipeline.\n"
        '- "demonstration" (array of command strings, optional): a command that '
        "must fail before the change and pass after. For task_type code a "
        "non-empty list derives failing_test_first evidence. Same no-shell "
        "rule as acceptance.\n"
        '- "no_semantic_change" (boolean, optional): true when the change must '
        "leave the parsed structure untouched apart from the region touched; "
        "derives no_semantic_change evidence for task_type code.\n"
        '- "type_check" (boolean, optional): true when the project\'s own type '
        "checker must pass; derives type_check evidence for task_type code, "
        "and the located checker command is filled in as acceptance.\n"
        '- "max_output_tokens" (whole number, required for task_type code): '
        "the reply cap, what the reply is worth in output tokens; a code "
        "proposal without one is refused.\n"
        "Omit optional fields rather than writing null. Return [] when nothing "
        "can be proposed."
    )


def proposals_from_reply(reply: str) -> tuple[Proposal, ...]:
    """Read an orchestrator reply as proposals, in the order it listed them.

    The body is unwrapped from any code fence and parsed as JSON; a single
    object is read as a one-item array. Raises `UnreadableProposalError` when
    the body is not JSON, is not an array, or any entry fails validation.
    """
    body = _fenced_body(reply)
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise UnreadableProposalError(
            f"the orchestrator's reply is not JSON, so it cannot be read as "
            f"proposals — it opens {body[:120]!r}"
        ) from exc

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise UnreadableProposalError(
            f"the orchestrator's reply is a {type(data).__name__}, not an "
            f"array of proposals"
        )

    proposals: list[Proposal] = []
    for item in data:
        proposals.append(_proposal_of(item))
    return tuple(proposals)


def _fenced_body(reply: str) -> str:
    """Return the reply's body, without the first fenced block around it.

    Line endings are normalised and the text trimmed first. A fence opens with
    up to three spaces then three or more backticks and closes with a line of
    at least as many backticks and nothing else; the lines between them are
    returned. Without a closed fence, the whole trimmed reply is returned.
    """
    text = reply.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = text.split("\n")
    for index, line in enumerate(lines):
        opened = _FENCE_OPEN.match(line)
        if opened is None:
            continue
        width = len(opened.group(1))
        for close_index in range(index + 1, len(lines)):
            stripped = lines[close_index].strip()
            if stripped.startswith("`" * width) and stripped.rstrip("`").strip() == "":
                return "\n".join(lines[index + 1 : close_index]).strip()
        break
    return text


def _proposal_of(item: object) -> Proposal:
    """Build one `Proposal` from one reply entry, validating each field."""
    if not isinstance(item, dict):
        raise UnreadableProposalError(
            f"a proposal entry is a {type(item).__name__}, not an object"
        )
    return Proposal(
        task_type=_required_str(item, "task_type"),
        task=_required_str(item, "task"),
        target=_required_str(item, "target"),
        interface=_optional_str(item, "interface"),
        deps=_deps(item),
        allow=_strings(item, "allow"),
        forbid=_strings(item, "forbid"),
        max_output_tokens=_optional_cap(item),
        stop_conditions=_strings(item, "stop_conditions"),
        acceptance=_strings(item, "acceptance"),
        demonstration=_strings(item, "demonstration"),
        no_semantic_change=_optional_bool(item, "no_semantic_change"),
        type_check=_optional_bool(item, "type_check"),
        operation=_optional_str(item, "operation"),
        sources=_strings(item, "sources"),
        depends_on=_depends_on(item),
    )


def _required_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UnreadableProposalError(
            f"a proposal is missing a non-empty string {key!r}"
        )
    return value


def _optional_cap(item: dict[str, object]) -> int | None:
    """Read `max_output_tokens`: absent means no cap.

    Anything present but not a whole number of at least 1 is refused.
    """
    value = item.get("max_output_tokens")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise UnreadableProposalError(
            f"max_output_tokens: {value!r} is not a whole number of at least 1"
        )
    return value


def _optional_str(item: dict[str, object], key: str) -> str:
    value = item.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise UnreadableProposalError(f"{key!r} must be a string, when present")
    return value


def _optional_bool(item: dict[str, object], key: str) -> bool:
    """Read a boolean flag: absent means false, and a non-boolean is refused."""
    value = item.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise UnreadableProposalError(f"{key!r} must be a boolean, when present")
    return value


def _strings(item: dict[str, object], key: str) -> tuple[str, ...]:
    value = item.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise UnreadableProposalError(f"{key!r} must be an array of strings")
    return tuple(value)


def _depends_on(item: dict[str, object]) -> tuple[int, ...]:
    """Read `depends_on`: absent means (), else an array of whole-number indexes."""
    value = item.get("depends_on")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnreadableProposalError(
            "depends_on must be an array of whole-number proposal indexes"
        )
    indexes: list[int] = []
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, int) or entry < 0:
            raise UnreadableProposalError(
                f"depends_on: {entry!r} is not a whole-number proposal index"
            )
        indexes.append(entry)
    return tuple(indexes)


def _deps(item: dict[str, object]) -> tuple[DepRef, ...]:
    value = item.get("deps")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnreadableProposalError("deps must be an array of objects")
    deps: list[DepRef] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise UnreadableProposalError("each dep must be an object")
        path = entry.get("path")
        symbol = entry.get("symbol")
        note = entry.get("note", "")
        if not isinstance(path, str) or not path.strip():
            raise UnreadableProposalError("each dep needs a non-empty string 'path'")
        if not isinstance(symbol, str) or not symbol.strip():
            raise UnreadableProposalError("each dep needs a non-empty string 'symbol'")
        if not isinstance(note, str):
            raise UnreadableProposalError("a dep's 'note' must be a string")
        deps.append(DepRef(path=path, symbol=symbol, note=note))
    return tuple(deps)


def proposer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    max_output_tokens: int | None = None,
) -> Proposer | None:
    """Build the prose proposer on the `orchestrator` role, or None if unbound.

    The role has to name a model, else nothing can propose. The returned
    callable renders the evidence with `build_prompt`, dispatches it to the
    role — through `capacity`, when one is given, and capped by
    `max_output_tokens` — and parses the reply with `proposals_from_reply`.
    """
    if source_map.role_model(ORCHESTRATOR_ROLE) is None:
        return None

    def propose(evidence: Evidence) -> Sequence[Proposal]:
        completion = dispatch_role(
            source_map,
            ORCHESTRATOR_ROLE,
            Request(
                prompt=build_prompt(evidence),
                max_output_tokens=max_output_tokens,
            ),
            capacity=capacity,
        )
        if completion is None:  # The role lists a model but resolves to no unit.
            raise OrchestratorUnavailableError(
                f"the {ORCHESTRATOR_ROLE!r} role has no unit to dispatch to"
            )
        return proposals_from_reply(completion.text)

    return propose


#: The confidence a typed answer must reach for its proposal to be trusted. A
#: classifier answering below it counts as having declined to choose: nothing is
#: proposed, and the caller can fall back to the prose proposer.
MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class ClassifierProposer:
    """A proposer that asks one typed Choice per field, in dependency order.

    `classify` is the seam — it answers named questions about a state — and
    `confidence` is the floor each answer must clear. One call asks the six
    jev-decided fields (`task_type`, `target`, `symbol`, `interface`, `deps`,
    `allow`) in that order, re-enumerating each downstream set against the
    values already chosen, and folds the picks into one proposal. A
    load-bearing answer (`task_type`/`target`) that is unusable, falls short of
    the floor, or names a type needing an output cap declines the whole
    proposal; an optional field degrades to its rank-0 candidate instead. Each
    decision is appended to `sink`, when one is wired.

    For the W6 retry loop, a decline maps to a `Refusal` field/directive as
    follows: no targets or no vocabulary → `target`/`task_type`; `task_type`
    below the confidence floor → `task_type`; `target` below the confidence
    floor → `target`; `kind.needs_output_cap` mismatch → `task_type`. (Behavior
    is unchanged here; this is the mapping the classifier's empty answer will
    be annotated with.)
    """

    classify: Callable[[Any, Mapping[str, Question]], Decision]
    confidence: float = MIN_CONFIDENCE
    sink: ShadowSink | None = None
    model: str = ""
    seed: str = ""

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        targets = candidate_targets(evidence)
        vocabulary = completable(evidence.vocabulary)
        if not targets or not vocabulary:
            return ()

        state = _state(evidence, targets, vocabulary)

        task_type_set = task_type_candidates(evidence)
        task_type = self._decide(state, task_type_set)
        if task_type is None:
            return ()
        kind = kind_for(str(task_type), vocabulary)
        if kind is None or kind.needs_output_cap:
            # A type needing an output cap gets no proposal here: the cap says
            # what a reply is worth in tokens, and this proposer has no way to
            # judge that, so it declines instead of guessing.
            return ()

        target_set = target_candidates(evidence)
        target = self._decide(state, target_set)
        if target is None:
            return ()
        target = str(target)

        symbol_set = symbol_candidates(evidence, target)
        symbol = self._decide(state, symbol_set, target=target)
        symbol_provenance = Provenance.MODEL
        if symbol is None:
            rank0 = symbol_set.rank0
            symbol = rank0.value if rank0 is not None else _NO_SYMBOL
            symbol_provenance = Provenance.DETERMINISTIC
        symbol_name = _symbol_of(symbol)

        plan = enumerate_candidates(evidence)
        plan = choose(plan, "task_type", kind.name)
        plan = choose(plan, "target", target)
        plan = choose(
            plan, "symbol", symbol_name or _NO_SYMBOL, provenance=symbol_provenance
        )
        plan = choose(
            plan,
            "task",
            directive(kind, target, symbol_name),
            provenance=Provenance.DETERMINISTIC,
        )
        plan = choose(
            plan,
            "stop_conditions",
            stop_condition(kind, target, symbol_name),
            provenance=Provenance.DETERMINISTIC,
        )

        interface_set = interface_candidates(evidence, target, symbol_name)
        interface = self._decide(state, interface_set)
        if interface is not None:
            plan = choose(plan, "interface", interface)

        deps_set = deps_candidates(evidence, target)
        deps = self._decide(state, deps_set)
        if deps is not None:
            plan = choose(plan, "deps", deps)

        allow_set, _ = scope_candidates(evidence, target)
        allow = self._decide(state, allow_set)
        if allow is not None:
            plan = choose(plan, "allow", allow)

        return (collapse(plan),)

    def _decide(
        self,
        state: Any,
        set: CandidateSet,
        *,
        target: str | None = None,
    ) -> Any | None:
        """Ask jev one field's Choice and read the pick back.

        Returns the chosen candidate's value, or None when the answer is
        unusable (missing, unreadable, below the confidence floor, or a choice
        id not among the field's candidates). Exactly one `DecisionRecord` is
        written to `sink` per call, with the decision's candidate order, pick,
        rank-0, abstain flag, confidence, parse-fail flag, latency, model and
        seed. Transport errors propagate unchanged; only `DecisionError` is
        caught and recorded as a parse failure.
        """
        question = render_choice(
            set,
            criterion=criterion(set.field, target=target),
            abstain_line=abstain_line(set.field),
        )
        t0 = time.monotonic()
        try:
            decision = self.classify(state, {set.field: question})
        except DecisionError:
            latency_ms = round((time.monotonic() - t0) * 1000)
            self._record(
                set,
                pick=None,
                abstain=True,
                confidence=0.0,
                parse_fail=True,
                latency_ms=latency_ms,
            )
            return None
        latency_ms = round((time.monotonic() - t0) * 1000)

        answer = _choice(decision, set.field)
        if answer is None:
            self._record(
                set,
                pick=None,
                abstain=True,
                confidence=0.0,
                parse_fail=False,
                latency_ms=latency_ms,
            )
            return None
        if answer.confidence < self.confidence:
            self._record(
                set,
                pick=None,
                abstain=True,
                confidence=answer.confidence,
                parse_fail=False,
                latency_ms=latency_ms,
            )
            return None

        try:
            value = value_by_id(set, answer.choice)
        except KeyError:
            self._record(
                set,
                pick=None,
                abstain=True,
                confidence=answer.confidence,
                parse_fail=True,
                latency_ms=latency_ms,
            )
            return None
        sentinel = abstain_value(set.field)
        self._record(
            set,
            pick=answer.choice,
            abstain=sentinel is not None and value == sentinel,
            confidence=answer.confidence,
            parse_fail=False,
            latency_ms=latency_ms,
        )
        return value

    def _record(
        self,
        set: CandidateSet,
        *,
        pick: str | None,
        abstain: bool,
        confidence: float,
        parse_fail: bool,
        latency_ms: int,
    ) -> None:
        """Append one `DecisionRecord` to `sink`, or do nothing when unwired."""
        if self.sink is None:
            return
        rank0 = set.rank0
        self.sink.append(
            DecisionRecord(
                field=set.field,
                candidates=tuple(c.id for c in set.candidates),
                pick=pick,
                rank1=rank0.id if rank0 is not None else "",
                abstain=abstain,
                confidence=confidence,
                parse_fail=parse_fail,
                latency_ms=latency_ms,
                model=self.model,
                seed=self.seed,
            )
        )


def deterministic_proposer() -> Proposer:
    """The no-jev degrade: rank-0 collapse per field, with no model asked.

    This is a fallback so the shadow loop and later calibration can run, not a
    tuned default: it picks the first completable type, first target, first
    symbol (a real definition, not the whole file) and the empty defaults for
    every optional field. No decision is made, so nothing is recorded.
    """

    def propose(evidence: Evidence) -> Sequence[Proposal]:
        if not candidate_targets(evidence) or not completable(evidence.vocabulary):
            return ()
        return (collapse(enumerate_candidates(evidence)),)

    return propose


def classifier_proposer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    confidence: float = MIN_CONFIDENCE,
    sink: ShadowSink | None = None,
) -> Proposer | None:
    """Build the classifier proposer on the jev role, or its no-jev degrade.

    With a unit bound to the jev role the questions go through `classify_for`
    (which prefers jev over the `orchestrator` role named here), and each
    decision is recorded in `sink` with the jev role's model. Without jev there
    is nothing to decide, so the returned proposer collapses rank-0 per field
    deterministically and asks nothing — the gate/reviewer/wake/ladder decisions
    keep asking their pre-jev roles, unchanged.
    """
    if not jev_bound(source_map):
        return deterministic_proposer()

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        return classify_for(
            source_map,
            state,
            questions,
            role=ORCHESTRATOR_ROLE,
            capacity=capacity,
        )

    return ClassifierProposer(
        classify=classify,
        confidence=confidence,
        sink=sink,
        model=source_map.role_model(JEV_ROLE) or "",
    )


# Reading one decision into one proposal.


def _symbol_of(name: Any) -> str | None:
    """The chosen symbol name, or None when the no-symbol option was picked."""
    return None if name == _NO_SYMBOL else str(name)


def _choice(decision: Decision, name: str) -> ChoiceAnswer | None:
    """Read the typed answer filed under `name`, or None if absent or not a choice."""
    answer = decision.answers.get(name)
    return answer if isinstance(answer, ChoiceAnswer) else None


def _state(
    evidence: Evidence, targets: tuple[str, ...], vocabulary: Sequence[TaskType]
) -> dict[str, Any]:
    """The state the typed questions are about: request, targets, type names."""
    return {
        "request": evidence.prompt,
        "candidates": list(targets),
        "task_types": [task.name for task in vocabulary],
    }


def proposer_by_authoring(
    strategy: str | None, *, typed: Proposer | None, prose: Proposer | None
) -> Proposer | None:
    """Pick the proposer for the configured `strategy`.

    Only "classifier" opts into the typed proposer, and even then only in front
    of a prose proposer: the typed one answers first and prose stands in when it
    declines. Every other strategy proposes in prose. None means nothing can
    propose — no prose proposer, or a typed one with no prose to fall back on.
    """
    if strategy != "classifier" or typed is None:
        return prose
    if prose is None:
        return None

    def propose(evidence: Evidence) -> Sequence[Proposal]:
        proposals = typed(evidence)
        return proposals if proposals else prose(evidence)

    return propose
