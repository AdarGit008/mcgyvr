""

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

if TYPE_CHECKING:  #
    from mcgyvr.capacity import Capacity
    from mcgyvr.local_pool import SourceMap

#
#
#
ORCHESTRATOR_ROLE = "orchestrator"

#
#
NO_ORCHESTRATOR_ROLE = (
    "the orchestrator role is not configured, so a prompt cannot be turned "
    "into contracts here. Bind `orchestrator.unit` and `orchestrator.model` "
    "in the config, or author a contract yourself and run it with "
    "`mcgyvr run`."
)


class DelegationError(RuntimeError):
    ""


class OrchestratorUnavailableError(DelegationError):
    ""


class UnreadableProposalError(DelegationError):
    ""


def build_prompt(evidence: Evidence) -> str:
    ""
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
    ""
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
    ""
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
        'call, each {"path", "symbol", "note"} where path and symbol are the '
        "names the index holds and note says how the target uses it.\n"
        '- "allow" (array of strings, optional): paths the change may touch; '
        "omit to allow the target alone.\n"
        '- "forbid" (array of strings, optional): paths the change must not '
        "touch.\n"
        '- "stop_conditions" (array of strings): things that, if true, mean the '
        "worker must stop rather than guess. Required for every model-executed "
        "type.\n"
        '- "acceptance" (array of command strings, optional): commands that must '
        "pass after the change. For task_type code a non-empty list derives "
        "tests_pass evidence.\n"
        '- "demonstration" (array of command strings, optional): a command that '
        "must fail before the change and pass after. For task_type code a "
        "non-empty list derives failing_test_first evidence.\n"
        '- "no_semantic_change" (boolean, optional): true when the change must '
        "leave the parsed structure untouched apart from the region touched; "
        "derives no_semantic_change evidence for task_type code.\n"
        '- "type_check" (boolean, optional): true when the project\'s own type '
        "checker must pass; derives type_check evidence for task_type code, "
        "and the located checker command is filled in as acceptance.\n"
        '- "risk" (string, optional): "low", "medium" or "high"; omit to take '
        "the default.\n"
        '- "max_output_tokens" (whole number, required for task_type code): '
        "the reply cap, what the reply is worth in output tokens; a code "
        "proposal without one is refused.\n"
        "Omit optional fields rather than writing null. Return [] when nothing "
        "can be proposed."
    )


def proposals_from_reply(reply: str) -> tuple[Proposal, ...]:
    ""
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
    ""
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
    ""
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
        risk=_optional_str(item, "risk"),
    )


def _required_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UnreadableProposalError(
            f"a proposal is missing a non-empty string {key!r}"
        )
    return value


def _optional_cap(item: dict[str, object]) -> int | None:
    ""
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
    ""
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
    ""
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
        if completion is None:  #
            raise OrchestratorUnavailableError(
                f"the {ORCHESTRATOR_ROLE!r} role has no unit to dispatch to"
            )
        return proposals_from_reply(completion.text)

    return propose


#
#
#
#
MIN_CONFIDENCE = 0.5

#k.
_NO_SYMBOL = ""

#
#
#
_MAX_CHOICE_OPTIONS = 62


@dataclass(frozen=True)
class ClassifierProposer:
    ""

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
        if kind is None:  #
            return ()
        if kind.needs_output_cap:
            #
            #
            #
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
    ""
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


#


def _choice(decision: Decision, name: str) -> ChoiceAnswer | None:
    ""
    answer = decision.answers.get(name)
    return answer if isinstance(answer, ChoiceAnswer) else None


def _candidate_targets(evidence: Evidence) -> tuple[str, ...]:
    ""
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
    ""
    return tuple(
        symbol
        for symbol in evidence.index.symbols.all()
        if symbol.path == target and symbol.kind is SymbolKind.DEFINITION
    )


def _symbol_options(symbols: Sequence[Symbol]) -> dict[str, str]:
    ""
    options: dict[str, str] = {}
    for symbol in symbols[: _MAX_CHOICE_OPTIONS - 1]:
        if symbol.name not in options:
            options[symbol.name] = symbol.detail or "symbol"
    options[_NO_SYMBOL] = "no specific symbol — the whole file is the work"
    return options


def _kind_for(name: str, vocabulary: Sequence[TaskType]) -> TaskType | None:
    ""
    return next((task for task in vocabulary if task.name == name), None)


def _directive(kind: TaskType, target: str, symbol: str | None) -> str:
    ""
    return f"{kind.doc.split('.', 1)[0]}: {_subject(target, symbol)}."


def _stop_condition(kind: TaskType, target: str, symbol: str | None) -> tuple[str, ...]:
    ""
    if kind.deterministic:
        return ()
    return (generic_stop_condition(kind.name, _subject(target, symbol)),)


def _subject(target: str, symbol: str | None) -> str:
    ""
    return target if symbol is None else f"{symbol} in {target}"


def _state(
    evidence: Evidence, targets: tuple[str, ...], vocabulary: Sequence[TaskType]
) -> dict[str, Any]:
    ""
    return {
        "request": evidence.prompt,
        "candidates": list(targets),
        "task_types": [task.name for task in vocabulary],
    }


def completable(vocabulary: Sequence[TaskType]) -> tuple[TaskType, ...]:
    ""
    return tuple(
        task
        for task in vocabulary
        if not task.needs_acceptance_commands and not task.needs_demonstration_commands
    )


def proposer_by_authoring(
    strategy: str | None, *, typed: Proposer | None, prose: Proposer | None
) -> Proposer | None:
    ""
    if strategy != "classifier" or typed is None:
        return prose
    if prose is None:
        return None

    def propose(evidence: Evidence) -> Sequence[Proposal]:
        proposals = typed(evidence)
        return proposals if proposals else prose(evidence)

    return propose
