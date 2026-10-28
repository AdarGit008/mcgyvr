"""Turning a request into proposals through the orchestrator role.

Two proposers live here. ``proposer_for`` renders the evidence as a prose
prompt, dispatches it to the ``orchestrator`` role and parses the JSON reply
into proposals. ``classifier_proposer_for`` asks the jev role one typed Choice
per field — ``task_type``, ``target``, ``symbol``, ``interface``, ``deps``,
``allow`` — in dependency order, and turns the answers into one proposal,
declining when a load-bearing answer falls short. ``refining_proposer_for``
puts the classifier behind ``mcgyvr.refine``, which splits its proposal until
each is on one file and jev says it cannot be split further.
``proposer_by_authoring`` picks between them for the configured strategy.

``NO_ORCHESTRATOR_ROLE`` is what a caller prints when no orchestrator unit is
bound, so no prompt can be turned into contracts.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.catalog import TaskType
from mcgyvr.config import MAX_REFINE_DEPTH_DEFAULT, MAX_REFINE_FANOUT_DEFAULT
from mcgyvr.decision import (
    JEV_ROLE,
    BoolAnswer,
    ChoiceAnswer,
    Decision,
    DecisionError,
    Question,
    classify_for,
    jev_bound,
)
from mcgyvr.delegate_log import DelegateKind, json_type
from mcgyvr.orchestrator.candidates import (
    _NO_SYMBOL,
    CandidateSet,
    Provenance,
    candidate_targets,
    choose,
    collapse,
    completable,
    deps_candidates,
    enumerate_candidates,
    interface_candidates,
    kind_for,
    scope_candidates,
    stop_condition,
    symbol_candidates,
    target_candidates,
    task_candidates,
    task_type_candidates,
    without,
)
from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal, Proposer, Refusal
from mcgyvr.orchestrator.fields import (
    abstain_line,
    abstain_value,
    criterion,
    render_choice,
    value_by_id,
)
from mcgyvr.orchestrator.telemetry import DecisionRecord, ShadowSink
from mcgyvr.refine import RefiningProposer
from mcgyvr.replan import render as render_replan
from mcgyvr.runner import Completion, Request, dispatch_role
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
    "`mcgyvr direct`."
)


class DelegationError(RuntimeError):
    """Base for every way delegation can fail to produce proposals.

    `kind` is the `mcgyvr.delegate_log` kind the failure is logged as, and
    `detail` the facts behind it as data; each subclass, or each raise site of
    `UnreadableProposalError`, states both, so nothing reads them off the text.
    """

    kind: DelegateKind = DelegateKind.INTERNAL_ERROR

    def __init__(self, message: str, *, detail: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.detail: dict[str, Any] = dict(detail or {})


class OrchestratorUnavailableError(DelegationError):
    """The role resolves to no unit, so its prompt cannot be dispatched."""

    kind = DelegateKind.ORCHESTRATOR_UNAVAILABLE


class UnreadableProposalError(DelegationError):
    """A reply that cannot be read as proposals: not JSON, or the wrong shape.

    `reply` is the orchestrator's raw reply, whole, when the error came from
    reading one (else None), so a caller can keep it for diagnosis: `mcgyvr
    delegate` prints it, delimited, on stderr after the error. `kind` says which
    way it could not be read (a `reply_*` or `proposal_*` kind).
    """

    def __init__(
        self,
        message: str,
        *,
        kind: DelegateKind,
        reply: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.kind = kind
        self.reply = reply


class OrchestratorReplyCutOffError(UnreadableProposalError):
    """A reply the backend stopped at a length limit, so it is not read at all.

    Raised from the stop reason, before the text is parsed: a proposal array cut
    off mid-entry opens as valid JSON, and reporting it as "not JSON" would point
    at the model's format rather than at the room the unit gave the reply.
    """

    def __init__(
        self,
        message: str,
        *,
        reply: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message, kind=DelegateKind.REPLY_CUT_OFF, reply=reply, detail=detail
        )


def build_prompt(evidence: Evidence) -> str:
    """Render the evidence as the prose prompt the orchestrator replies to.

    The request comes first — on a re-plan followed by the spent contract and
    the failure notes its climb left, as data (`mcgyvr.replan.render`) — then
    the resolution's candidates with each one's
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
    if evidence.spent is not None:
        # A re-plan: the request is a spent contract's own work, and what its
        # climb observed is shown as evidence, never as orders.
        sections.append(render_replan(evidence.spent))

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
        "expose. When another proposal depends on a symbol this one creates "
        "or renames, state that symbol's signature here.\n"
        '- "deps" (array of objects, optional): dependencies the target may '
        'call, each {"path", "symbol", "note"} where path and symbol name a '
        "symbol shown in RESOLUTION or READ REGIONS and note says how the "
        "target uses it. Propose a dependency only when its symbol is named "
        "there; otherwise omit the field rather than guessing a name. A "
        "dependency is an existing symbol, or one another proposal in this "
        "array creates or renames at that path — that proposal states its "
        "signature as its interface, and this one waits on it. Never name the "
        "symbol this proposal's own target creates — it is the target's "
        "output, not a dependency.\n"
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
        "Omit optional fields rather than writing null. Return [] when nothing "
        "can be proposed."
    )


def proposals_from_reply(reply: str) -> tuple[Proposal, ...]:
    """Read an orchestrator reply as proposals, in the order it listed them.

    The body is unwrapped from any code fence and read as one JSON value; a
    single object is read as a one-item array. Prose before the value's first
    `[` or `{` and text after the complete value are ignored, but nothing inside
    it is repaired: a trailing comma, a comment or a bad escape is not JSON.
    Raises `UnreadableProposalError`, carrying the raw reply as its `reply`,
    when the body holds no JSON value, the value is not an array, or any entry
    fails validation. The "not JSON" error names the decoder's message, the line
    and column in the body, an excerpt either side of that point and the reply's
    length.
    """
    try:
        data = _json_value(reply)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise UnreadableProposalError(
                f"the orchestrator's reply is a {type(data).__name__}, not an "
                f"array of proposals",
                kind=DelegateKind.REPLY_NOT_ARRAY,
                detail={"found": json_type(data)},
            )
        proposals: list[Proposal] = []
        for index, item in enumerate(data):
            try:
                proposals.append(_proposal_of(item))
            except UnreadableProposalError as exc:
                exc.detail.setdefault("index", index)
                raise
        return tuple(proposals)
    except UnreadableProposalError as exc:
        if exc.reply is None:
            exc.reply = reply
        raise


#: How many characters either side of the point the decoder stopped at the
#: "not JSON" error quotes.
_EXCERPT = 120


def _json_value(reply: str) -> object:
    """The one JSON value the reply's body holds, prose around it ignored.

    The body (`_fenced_body`) is decoded from its first `[` or `{`, and anything
    after the complete value is left unread. Only the first bracket is tried: a
    later one could open an entry inside a malformed array, which would read as
    fewer proposals than the reply holds. A body with no bracket at all is
    decoded whole, so the error names its first character.
    """
    body = _fenced_body(reply)
    starts = [at for at in (body.find("["), body.find("{")) if at >= 0]
    start = min(starts) if starts else 0
    try:
        if not starts:
            return json.loads(body)
        value, _end = json.JSONDecoder().raw_decode(body, start)
        return value
    except json.JSONDecodeError as exc:
        raise UnreadableProposalError(
            _not_json(reply, body, exc),
            kind=DelegateKind.REPLY_NOT_JSON,
            detail={
                "decoder": exc.msg,
                "line": exc.lineno,
                "column": exc.colno,
                "pos": exc.pos,
                "body_chars": len(body),
            },
        ) from exc


def _not_json(reply: str, body: str, exc: json.JSONDecodeError) -> str:
    """The "not JSON" message: the decoder's reason, where, and what is there."""
    at = exc.pos
    before = body[max(0, at - _EXCERPT) : at]
    after = body[at : at + _EXCERPT]
    return (
        f"the orchestrator's reply is not JSON, so it cannot be read as "
        f"proposals: {exc.msg} at line {exc.lineno} column {exc.colno} (char "
        f"{at} of the {len(body)}-char body read; the reply is {len(reply)} "
        f"chars). Around that point: {before!r} [HERE] {after!r}. It opens "
        f"{body[:_EXCERPT]!r}"
    )


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
            f"a proposal entry is a {type(item).__name__}, not an object",
            kind=DelegateKind.PROPOSAL_NOT_OBJECT,
            detail={"found": json_type(item)},
        )
    return Proposal(
        task_type=_required_str(item, "task_type"),
        task=_required_str(item, "task"),
        target=_required_str(item, "target"),
        interface=_optional_str(item, "interface"),
        deps=_deps(item),
        allow=_strings(item, "allow"),
        forbid=_strings(item, "forbid"),
        stop_conditions=_strings(item, "stop_conditions"),
        acceptance=_strings(item, "acceptance"),
        demonstration=_strings(item, "demonstration"),
        no_semantic_change=_optional_bool(item, "no_semantic_change"),
        type_check=_optional_bool(item, "type_check"),
        operation=_optional_str(item, "operation"),
        sources=_strings(item, "sources"),
        depends_on=_depends_on(item),
    )


def _invalid(message: str, key: str) -> UnreadableProposalError:
    """The error for a proposal field `key` of the wrong type or shape."""
    return UnreadableProposalError(
        message, kind=DelegateKind.PROPOSAL_FIELD_INVALID, detail={"field": key}
    )


def _required_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UnreadableProposalError(
            f"a proposal is missing a non-empty string {key!r}",
            kind=DelegateKind.PROPOSAL_FIELD_MISSING,
            detail={"field": key, "found": json_type(value)},
        )
    return value


def _optional_str(item: dict[str, object], key: str) -> str:
    value = item.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _invalid(f"{key!r} must be a string, when present", key)
    return value


def _optional_bool(item: dict[str, object], key: str) -> bool:
    """Read a boolean flag: absent means false, and a non-boolean is refused."""
    value = item.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _invalid(f"{key!r} must be a boolean, when present", key)
    return value


def _strings(item: dict[str, object], key: str) -> tuple[str, ...]:
    value = item.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _invalid(f"{key!r} must be an array of strings", key)
    return tuple(value)


def _depends_on(item: dict[str, object]) -> tuple[int, ...]:
    """Read `depends_on`: absent means (), else an array of whole-number indexes."""
    value = item.get("depends_on")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _invalid(
            "depends_on must be an array of whole-number proposal indexes",
            "depends_on",
        )
    indexes: list[int] = []
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, int) or entry < 0:
            raise _invalid(
                f"depends_on: {entry!r} is not a whole-number proposal index",
                "depends_on",
            )
        indexes.append(entry)
    return tuple(indexes)


def _deps(item: dict[str, object]) -> tuple[DepRef, ...]:
    value = item.get("deps")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _invalid("deps must be an array of objects", "deps")
    deps: list[DepRef] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise _invalid("each dep must be an object", "deps")
        path = entry.get("path")
        symbol = entry.get("symbol")
        note = entry.get("note", "")
        if not isinstance(path, str) or not path.strip():
            raise _invalid("each dep needs a non-empty string 'path'", "deps")
        if not isinstance(symbol, str) or not symbol.strip():
            raise _invalid("each dep needs a non-empty string 'symbol'", "deps")
        if not isinstance(note, str):
            raise _invalid("a dep's 'note' must be a string", "deps")
        deps.append(DepRef(path=path, symbol=symbol, note=note))
    return tuple(deps)


def proposer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
) -> Proposer | None:
    """Build the prose proposer on the `orchestrator` role, or None if unbound.

    The role has to name a model, else nothing can propose. The returned
    callable renders the evidence with `build_prompt`, dispatches it to the
    role — through `capacity`, when one is given, and at the unit's maximum
    reply within the room the prompt leaves (`runner.at_unit_max`) — and
    parses the reply with `proposals_from_reply`. A reply stopped at a length
    limit is not parsed: it raises `OrchestratorReplyCutOffError`. Either way,
    an unreadable reply's error carries the raw reply as its `reply`.
    """
    if source_map.role_model(ORCHESTRATOR_ROLE) is None:
        return None

    def propose(evidence: Evidence) -> Sequence[Proposal]:
        completion = dispatch_role(
            source_map,
            ORCHESTRATOR_ROLE,
            # No cap is stated: the runner sends the unit's maximum.
            Request(prompt=build_prompt(evidence), max_output_tokens=None),
            capacity=capacity,
        )
        if completion is None:  # The role lists a model but resolves to no unit.
            raise OrchestratorUnavailableError(
                f"the {ORCHESTRATOR_ROLE!r} role has no unit to dispatch to"
            )
        cut_off = _cut_off(completion)
        if cut_off is not None:
            raise cut_off
        return proposals_from_reply(completion.text)

    return propose


def _cut_off(completion: Completion) -> OrchestratorReplyCutOffError | None:
    """The error for an orchestrator reply stopped at a length limit, else None.

    It says the reply was cut off and after how many output tokens (and how
    many of them were reasoning) where the backend reported them, names the
    unit and the cap it was sent with the cap's basis, and says what to change:
    more reply room for the unit, or less of it spent thinking.
    """
    if not completion.truncated:
        return None
    cap = completion.max_output_tokens
    if completion.output_tokens is not None:
        where = f"at its reply cap after {completion.output_tokens} output tokens"
    elif cap is not None:
        where = f"at its {cap}-token cap"
    else:
        where = "at the backend's own length limit"
    reasoning = (
        f", {completion.reasoning_tokens} of them reported as reasoning"
        if completion.reasoning_tokens is not None
        else ""
    )
    sent = (
        f"was sent a cap of {cap} tokens"
        if cap is not None
        else "was sent no cap, so the backend stopped at its own limit"
    )
    basis = f" ({completion.cap_basis})" if completion.cap_basis else ""
    return OrchestratorReplyCutOffError(
        f"the orchestrator's reply was cut off {where}{reasoning}, so it is "
        f"not read as proposals: unit {completion.source!r} {sent}{basis}. "
        f"Give the orchestrator unit more reply room (raise its "
        f"`output_tokens`, or its `window`, which less the prompt bounds the "
        f"reply) or a smaller thinking budget",
        reply=completion.text,
        detail={
            "unit": completion.source,
            "output_tokens": completion.output_tokens,
            "reasoning_tokens": completion.reasoning_tokens,
            "max_output_tokens": cap,
            "cap_basis": completion.cap_basis or None,
        },
    )


#: The confidence a typed answer must reach for its proposal to be trusted. A
#: classifier answering below it counts as having declined to choose: nothing is
#: proposed, and the caller can fall back to the prose proposer.
MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class ClassifierProposer:
    """A proposer that asks one typed Choice per field, in dependency order.

    `classify` is the seam — it answers named questions about a state — and
    `confidence` is the floor each answer must clear. One call asks the seven
    jev-decided fields (`task_type`, `target`, `symbol`, `task`, `interface`,
    `deps`, `allow`) in that order, re-enumerating each downstream set against
    the values already chosen, and folds the picks into one proposal. `task`
    chooses between the request as asked and the deterministic directive line,
    and the pick goes into the contract unchanged. A
    load-bearing answer (`task_type`/`target`) that is unusable, falls short of
    the floor, or names a type this ladder cannot serve declines the whole
    proposal; an optional field degrades to its rank-0 candidate instead. No
    reply cap is asked for or stated: the work is sent its unit's maximum.
    Each decision is appended to `sink`, when one is wired.

    For the W6 retry loop, a decline returns a `Refusal` field/directive as
    follows: no targets or no vocabulary → `target`/`task_type`; `task_type`
    below the confidence floor or not servable → `task_type`; `target` below
    the confidence floor → `target`. `__call__` still returns `()` for any
    decline so the prose proposer stands in exactly as it did before.
    """

    classify: Callable[[Any, Mapping[str, Question]], Decision]
    confidence: float = MIN_CONFIDENCE
    sink: ShadowSink | None = None
    model: str = ""
    seed: str = ""

    def propose(
        self,
        evidence: Evidence,
        *,
        decided: Mapping[str, Any] | None = None,
        constraints: Mapping[str, str] | None = None,
        rejected: Mapping[str, Collection[Any]] | None = None,
    ) -> Proposal | Refusal:
        """Ask the seven fields once and fold them into one proposal, or refuse.

        `decided` carries fields already chosen on a prior attempt (skipped
        without a jev call), `constraints` supplies a per-field directive
        rendered in the CONSTRAINTS section, and `rejected` lists per-field
        candidate values to drop from the question.
        """
        decided = decided or {}
        constraints = constraints or {}
        rejected = rejected or {}

        targets = candidate_targets(evidence)
        vocabulary = completable(evidence.vocabulary)
        if not targets:
            return Refusal(
                "request",
                "the request names no target the index holds, so there is no "
                "file to propose work on",
                field="target",
                what_to_change="name a target the index holds",
            )
        if not vocabulary:
            return Refusal(
                "request",
                "no servable task type is available to propose — bind a rung, "
                "or ask for work of a type this ladder can serve",
                field="task_type",
                what_to_change="pick a servable type",
            )

        state = _state(evidence, targets, vocabulary)

        if "task_type" in decided:
            task_type = decided["task_type"]
        else:
            task_type = self._decide(
                state,
                task_type_candidates(evidence),
                constraints=constraints.get("task_type", ""),
                rejected=rejected.get("task_type"),
            )
        if task_type is None:
            return Refusal(
                "request",
                "the task_type answer was unusable or fell below the confidence floor",
                field="task_type",
                what_to_change="answer with a candidate above the confidence floor",
            )
        kind = kind_for(str(task_type), vocabulary)
        if kind is None:
            return Refusal(
                "request",
                f"the chosen task type {task_type!r} is not one this ladder can "
                "serve, so the request is handed to the prose proposer",
                field="task_type",
                what_to_change="pick a servable type",
            )

        if "target" in decided:
            target = str(decided["target"])
        else:
            chosen_target = self._decide(
                state,
                target_candidates(evidence),
                constraints=constraints.get("target", ""),
                rejected=rejected.get("target"),
            )
            if chosen_target is None:
                return Refusal(
                    "request",
                    "the target answer was unusable or fell below the confidence floor",
                    field="target",
                    what_to_change="answer with a candidate above the confidence floor",
                )
            target = str(chosen_target)

        if "symbol" in decided:
            symbol = decided["symbol"]
            symbol_provenance = Provenance.MODEL
        else:
            symbol_set = symbol_candidates(evidence, target)
            symbol = self._decide(
                state,
                symbol_set,
                target=target,
                constraints=constraints.get("symbol", ""),
                rejected=rejected.get("symbol"),
            )
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
        if "task" in decided:
            task = decided["task"]
            task_provenance = Provenance.MODEL
        else:
            task_set = task_candidates(kind, target, symbol_name, evidence.prompt)
            task = self._decide(
                state,
                task_set,
                constraints=constraints.get("task", ""),
                rejected=rejected.get("task"),
            )
            task_provenance = Provenance.MODEL
            if task is None:
                rank0 = task_set.rank0
                task = rank0.value if rank0 is not None else ""
                task_provenance = Provenance.DETERMINISTIC
        plan = choose(plan, "task", task, provenance=task_provenance)
        plan = choose(
            plan,
            "stop_conditions",
            stop_condition(kind, target, symbol_name),
            provenance=Provenance.DETERMINISTIC,
        )

        if "interface" in decided:
            interface = decided["interface"]
        else:
            interface = self._decide(
                state,
                interface_candidates(evidence, target, symbol_name),
                constraints=constraints.get("interface", ""),
                rejected=rejected.get("interface"),
            )
        if interface is not None:
            plan = choose(plan, "interface", interface)

        if "deps" in decided:
            deps = decided["deps"]
        else:
            deps = self._decide(
                state,
                deps_candidates(evidence, target),
                constraints=constraints.get("deps", ""),
                rejected=rejected.get("deps"),
            )
        if deps is not None:
            plan = choose(plan, "deps", deps)

        if "allow" in decided:
            allow = decided["allow"]
        else:
            allow = self._decide(
                state,
                scope_candidates(evidence, target)[0],
                constraints=constraints.get("allow", ""),
                rejected=rejected.get("allow"),
            )
        if allow is not None:
            plan = choose(plan, "allow", allow)

        return collapse(plan)

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        """The `Proposer` seam: a decline is `()`, so the prose proposer stands in."""
        result = self.propose(evidence)
        return () if isinstance(result, Refusal) else (result,)

    def _decide(
        self,
        state: Any,
        set: CandidateSet,
        *,
        target: str | None = None,
        constraints: str = "",
        rejected: Collection[Any] | None = None,
    ) -> Any | None:
        """Ask jev one field's Choice and read the pick back.

        Returns the chosen candidate's value, or None when the answer is
        unusable (missing, unreadable, below the confidence floor, or a choice
        id not among the field's candidates). `rejected` candidates are dropped
        from the question first; `constraints` is rendered in its instructions.
        Exactly one `DecisionRecord` is written to `sink` per call, with the
        decision's candidate order, pick, rank-0, abstain flag, confidence,
        parse-fail flag, latency, model and seed. Transport errors propagate
        unchanged; only `DecisionError` is caught and recorded as a parse
        failure.
        """
        if rejected:
            set = without(set, rejected)
        question = render_choice(
            set,
            criterion=criterion(set.field, target=target),
            abstain_line=abstain_line(set.field),
            constraints=constraints,
        )
        return self.ask(state, set, question)

    def ask(self, state: Any, set: CandidateSet, question: Question) -> Any | None:
        """Put `question` to jev under `set.field` and read the pick back from `set`.

        A Choice is read by the option key answered, a Noul by the candidate
        whose value is the bool answered. Returns that candidate's value, or
        None when the answer is unusable (missing, unreadable, below the
        confidence floor, or naming no candidate of `set`). Exactly one
        `DecisionRecord` is written to `sink` per call, as `_decide` describes.
        """
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

        answer = decision.answers.get(set.field)
        if not isinstance(answer, ChoiceAnswer | BoolAnswer):
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

        key = (
            answer.choice if isinstance(answer, ChoiceAnswer) else _key_of(set, answer)
        )
        try:
            value = value_by_id(set, key)
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
            pick=key,
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

    This is the fallback when no jev unit is opted in, not a tuned default: it
    picks the first completable type, first target, first symbol (a real
    definition, not the whole file), the request as the task, the reply cap
    that type and target need, and the empty defaults for every optional
    field. No decision is made, so nothing is recorded. With no target or no
    completable type it proposes nothing, and prose stands in.
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
    deterministically and asks nothing — the gate, reviewer and wake decisions
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


def refining_proposer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    confidence: float = MIN_CONFIDENCE,
    sink: ShadowSink | None = None,
    max_depth: int = MAX_REFINE_DEPTH_DEFAULT,
    max_fanout: int = MAX_REFINE_FANOUT_DEFAULT,
) -> Proposer | None:
    """Classifier authoring: the classifier, refined until no proposal splits further.

    With a unit bound to the jev role, the classifier `classifier_proposer_for`
    builds is put behind `RefiningProposer` with the two bounds, so every
    proposal is split until it is on one file and jev answers that it cannot be
    split further (`mcgyvr.refine`). Without jev there is no one to say whether
    a proposal splits, so the rank-0 collapse comes back as it was.
    """
    typed = classifier_proposer_for(
        source_map, capacity=capacity, confidence=confidence, sink=sink
    )
    if not isinstance(typed, ClassifierProposer):
        return typed
    return RefiningProposer(typed, max_depth=max_depth, max_fanout=max_fanout)


# Reading one decision into one proposal.


def _symbol_of(name: Any) -> str | None:
    """The chosen symbol name, or None when the no-symbol option was picked."""
    return None if name == _NO_SYMBOL else str(name)


def _key_of(set: CandidateSet, answer: BoolAnswer) -> str:
    """The id of the candidate whose value is the bool answered, or "" when none is."""
    return next((c.id for c in set.candidates if c.value is answer.value), "")


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

    def propose(evidence: Evidence) -> Sequence[Proposal | Refusal]:
        proposals = typed(evidence)
        return proposals if proposals else prose(evidence)

    return propose
