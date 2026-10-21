"""Turning a request into proposals through the orchestrator role.

Two proposers live here. ``proposer_for`` renders the evidence as a prose
prompt, dispatches it to the ``orchestrator`` role and parses the JSON reply
into proposals. ``classifier_proposer_for`` asks the same role a short series
of typed multiple-choice questions — task type, target, then symbol — and
turns the answers into one proposal, declining when a confidence falls short.
``proposer_by_authoring`` picks between them for the configured strategy.

``NO_ORCHESTRATOR_ROLE`` is what a caller prints when no orchestrator unit is
bound, so no prompt can be turned into contracts.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.catalog import TaskType
from mcgyvr.contract import generic_stop_condition
from mcgyvr.decision import (
    Choice,
    ChoiceAnswer,
    Decision,
    Question,
    classify_for,
    jev_bound,
)
from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal, Proposer
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind
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

#: The option that picks no symbol, because the whole file is the work.
_NO_SYMBOL = ""

#: One typed question carries at most 62 options: the single-token labels read
#: back are A-Z, a-z and 0-9. Targets are truncated to this, and the symbol
#: question keeps one slot back for the "no specific symbol" option.
_MAX_CHOICE_OPTIONS = 62


@dataclass(frozen=True)
class ClassifierProposer:
    """A proposer that asks typed multiple-choice questions rather than prose.

    `classify` is the seam — it answers named questions about a state — and
    `confidence` is the floor each answer must clear. A call asks the task type
    and the target, then a symbol inside the target, and returns one proposal
    built from those answers, or nothing when any of them is unusable, falls
    short of the floor, or names a type needing an output cap this proposer
    cannot supply.
    """

    classify: Callable[[Any, Mapping[str, Question]], Decision]
    confidence: float = MIN_CONFIDENCE

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        targets = _candidate_targets(evidence)
        vocabulary = completable(evidence.vocabulary)
        if not targets or not vocabulary:
            return ()

        state = _state(evidence, targets, vocabulary)
        decision = self.classify(
            state,
            {
                "kind": Choice(
                    instructions="Which task type does this request call for?",
                    options={task.name: task.doc for task in vocabulary},
                ),
                "target": Choice(
                    instructions="Which file should the change land in?",
                    options={path: path for path in targets},
                ),
            },
        )
        kind_answer = _choice(decision, "kind")
        target_answer = _choice(decision, "target")
        if kind_answer is None or target_answer is None:
            return ()
        if (
            kind_answer.confidence < self.confidence
            or target_answer.confidence < self.confidence
        ):
            return ()
        kind = _kind_for(kind_answer.choice, vocabulary)
        if kind is None:  # The name is not a type this config can serve.
            return ()
        if kind.needs_output_cap:
            # A type needing an output cap gets no proposal here: the cap says
            # what a reply is worth in tokens, and this proposer has no way to
            # judge that, so it declines instead of guessing.
            return ()
        target = target_answer.choice

        symbols = _symbols_of(evidence, target)
        symbol_decision = self.classify(
            state,
            {
                "symbol": Choice(
                    instructions=f"Which symbol in {target} does the task work on?",
                    options=_symbol_options(symbols),
                )
            },
        )
        symbol_answer = _choice(symbol_decision, "symbol")
        if symbol_answer is None or symbol_answer.confidence < self.confidence:
            return ()
        symbol = None if symbol_answer.choice == _NO_SYMBOL else symbol_answer.choice

        return (
            Proposal(
                task_type=kind.name,
                task=_directive(kind, target, symbol),
                target=target,
                stop_conditions=_stop_condition(kind, target, symbol),
            ),
        )


def classifier_proposer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    confidence: float = MIN_CONFIDENCE,
) -> Proposer | None:
    """Build the typed proposer, or None when neither Jev nor a role is bound.

    The questions go through `classify_for`, which reads them with the `jev`
    role when that one is bound and with the `orchestrator` role — the role
    named here — otherwise. `capacity` gates each question, `confidence` is the
    floor the returned proposer holds its answers to.
    """
    if not jev_bound(source_map) and source_map.role_model(ORCHESTRATOR_ROLE) is None:
        return None

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        return classify_for(
            source_map,
            state,
            questions,
            role=ORCHESTRATOR_ROLE,
            capacity=capacity,
        )

    return ClassifierProposer(classify=classify, confidence=confidence)


# Reading one decision into one proposal.


def _choice(decision: Decision, name: str) -> ChoiceAnswer | None:
    """Read the typed answer filed under `name`, or None if absent or not a choice."""
    answer = decision.answers.get(name)
    return answer if isinstance(answer, ChoiceAnswer) else None


def _candidate_targets(evidence: Evidence) -> tuple[str, ...]:
    """Paths the evidence points at: candidates first, then reads, deduplicated.

    Truncated to `_MAX_CHOICE_OPTIONS`, since each becomes one option of a
    single typed question.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for candidate in evidence.resolution.candidates:
        if candidate.path not in seen:
            seen.add(candidate.path)
            paths.append(candidate.path)
    for read in evidence.exploration.reads:
        if read.path not in seen:
            seen.add(read.path)
            paths.append(read.path)
    return tuple(paths[:_MAX_CHOICE_OPTIONS])


def _symbols_of(evidence: Evidence, target: str) -> tuple[Symbol, ...]:
    """The symbols the index holds as definitions in `target`, in index order."""
    return tuple(
        symbol
        for symbol in evidence.index.symbols.all()
        if symbol.path == target and symbol.kind is SymbolKind.DEFINITION
    )


def _symbol_options(symbols: Sequence[Symbol]) -> dict[str, str]:
    """Render up to 61 symbols as question options, plus one for "no symbol".

    A symbol's detail is its option text, falling back to "symbol", and a name
    appears once. `_NO_SYMBOL` is added last and means the whole file is the
    work, so the question never exceeds `_MAX_CHOICE_OPTIONS` options.
    """
    options: dict[str, str] = {}
    for symbol in symbols[: _MAX_CHOICE_OPTIONS - 1]:
        if symbol.name not in options:
            options[symbol.name] = symbol.detail or "symbol"
    options[_NO_SYMBOL] = "no specific symbol — the whole file is the work"
    return options


def _kind_for(name: str, vocabulary: Sequence[TaskType]) -> TaskType | None:
    """Find the servable type named `name`, or None when this config cannot serve it."""
    return next((task for task in vocabulary if task.name == name), None)


def _directive(kind: TaskType, target: str, symbol: str | None) -> str:
    """The task line: the type's doc up to its first full stop, then the subject."""
    return f"{kind.doc.split('.', 1)[0]}: {_subject(target, symbol)}."


def _stop_condition(kind: TaskType, target: str, symbol: str | None) -> tuple[str, ...]:
    """Stop conditions: none for a deterministic type, else the generic one.

    A deterministic type starts on a gate and needs no stop condition; any other
    gets `generic_stop_condition`, which tells the worker to report BLOCKED
    rather than decide something the contract does not state.
    """
    if kind.deterministic:
        return ()
    return (generic_stop_condition(kind.name, _subject(target, symbol)),)


def _subject(target: str, symbol: str | None) -> str:
    """Name the work's subject: the file alone, or the symbol within it."""
    return target if symbol is None else f"{symbol} in {target}"


def _state(
    evidence: Evidence, targets: tuple[str, ...], vocabulary: Sequence[TaskType]
) -> dict[str, Any]:
    """The state the typed questions are about: request, targets, type names."""
    return {
        "request": evidence.prompt,
        "candidates": list(targets),
        "task_types": [task.name for task in vocabulary],
    }


def completable(vocabulary: Sequence[TaskType]) -> tuple[TaskType, ...]:
    """The servable types a classifier can propose: those needing no commands.

    A type whose evidence requires acceptance or demonstration commands is left
    out, because a typed answer cannot supply the commands themselves.
    """
    return tuple(
        task
        for task in vocabulary
        if not task.needs_acceptance_commands and not task.needs_demonstration_commands
    )


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
