"""Delegated mode: the orchestrator role turns a prompt and a repository into
proposals.

Direct mode hands mcgyvr a contract it wrote itself. Delegated mode is the
other half of the product: a natural-language prompt plus a repository become
contracts, and this module is where a model first enters that path. It builds
the orchestrator role's prompt from the deterministic pass
(:class:`~mcgyvr.orchestrator.decompose.Evidence`), asks the role through
:func:`mcgyvr.runner.dispatch_role`, and reads the reply back as the
:class:`~mcgyvr.orchestrator.decompose.Proposal` objects
:func:`~mcgyvr.orchestrator.decompose.decompose` consumes.

The shape of the reply is the :class:`~mcgyvr.orchestrator.decompose.Proposal`
type, spelled as JSON — ``task_type``, ``task``, ``target``, and the optional
``interface``, ``deps``, ``allow``, ``forbid``, ``stop_conditions``,
``acceptance``, ``demonstration`` and ``risk``. A proposal names references;
the repository supplies the facts, exactly as the decompose module's seam
draws the line. The role is *not* shown a contract document and is
not asked to author one: the proposal→document→contract round trip
(:func:`mcgyvr.orchestrator.decompose._document` and the public loader) runs in
``decompose``, after the index has resolved each reference, which is what keeps
"an emitted contract is one direct mode accepts" a property of the code path
rather than something this module re-implements.

The verifier role (:mod:`mcgyvr.verify`) is the template. ``proposer_for``
mirrors ``reviewer_for``: ``None`` for a keyless install is an ordinary answer,
not a failure, and a role that is bound but cannot dispatch raises instead of
being silently skipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.catalog import TaskType
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

#: What the pool calls the orchestrator. One name, in one place, because a role
#: spelled differently here than in :mod:`mcgyvr.local_pool` is a role that is
#: silently never found.
ORCHESTRATOR_ROLE = "orchestrator"

#: The documented answer a keyless install gets. ``proposer_for`` returns
#: ``None``; the CLI prints this and exits REFUSED, never a traceback.
NO_ORCHESTRATOR_ROLE = (
    "the orchestrator role is not configured, so a prompt cannot be turned "
    "into contracts here. Bind `orchestrator.unit` and `orchestrator.model` "
    "in the config, or author a contract yourself and run it with "
    "`mcgyvr run`."
)


class DelegationError(RuntimeError):
    """The orchestrator role could not produce proposals."""


class OrchestratorUnavailableError(DelegationError):
    """The orchestrator role had a binding and then had nothing to dispatch to."""


class UnreadableProposalError(DelegationError):
    """The orchestrator's reply could not be read as proposals."""


def build_prompt(evidence: Evidence) -> str:
    """The deterministic pass, written for the orchestrator to judge from.

    The role is shown only what exploration already found — the ranked
    shortlist, the read regions, and the task types this configuration can
    serve — and is told to answer in the proposal shape. It has no way to ask
    the repository for more: exploration is deterministic, and the prompt is
    where that boundary is held.
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
    """The task types on offer, each with what its evidence requires.

    ``vocabulary`` is typed loosely because :data:`Evidence.vocabulary` is a
    tuple of :class:`~mcgyvr.catalog.TaskType` and the fields read here are the
    only ones the prompt needs; importing the catalog for one annotation buys
    nothing.
    """
    blocks: list[str] = []
    for task in vocabulary:
        evidence = ", ".join(e.name for e in task.required_evidence)
        lines = [f"- {task.name}: {task.doc}"]
        lines.append(f"    guarantee: {task.guarantee}")
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
    """The exact proposal shape the role must answer in."""
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
        '- "acceptance" (array of command strings): commands that must pass '
        "after the change. Required when the type says REQUIRES acceptance "
        "commands.\n"
        '- "demonstration" (array of command strings): a command that must fail '
        "before the change and pass after. Required when the type says "
        "REQUIRES demonstration commands.\n"
        '- "risk" (string, optional): "low", "medium" or "high"; omit to take '
        "the default.\n"
        '- "max_output_tokens" (whole number, optional): the reply cap; omit '
        "and the type's own evidence sizes it.\n"
        "Omit optional fields rather than writing null. Return [] when nothing "
        "can be proposed."
    )


def proposals_from_reply(reply: str) -> tuple[Proposal, ...]:
    """The proposals a reply carries, or a named failure.

    Accepts a JSON array of proposals, or a single proposal object, bare or
    inside the first markdown fence of the reply. A reply that is not JSON, a
    JSON scalar, or a proposal missing a required field is an
    :class:`UnreadableProposalError` naming what was wrong, never a guess at a
    proposal.
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
    """The body of the first markdown fence if it closes, else the whole reply.

    Unlike the worker reply parser it accepts an unfenced reply, and ignores
    every fence after the first.
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
    """One reply entry as a :class:`Proposal`, refusing anything malformed."""
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
    """``max_output_tokens`` as a whole number of at least 1, or ``None``."""
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
    """The install's orchestrator role as a :class:`Proposer`, or ``None``.

    ``None`` mirrors :meth:`~mcgyvr.local_pool.SourceMap.role_model` and is an
    ordinary answer: a keyless install has no orchestrator, which the CLI
    answers with :data:`NO_ORCHESTRATOR_ROLE` rather than by failing. The
    request is not marked ``quality_sensitive`` for the same reason the
    verifier's is not — a proposal is work, and refusing a caveated backend
    would turn the ordinary local install into one with no orchestrator at all
    while telling the operator nothing.

    ``max_output_tokens`` is ``None`` (uncapped) by default: the ruling is
    that the orchestrator carries no output cap — a chatty model is a
    prompting/model issue, not a cap issue. A caller that still wants a bound
    on a decomposition may pass one.
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
        if completion is None:  # the role was bound a moment ago
            raise OrchestratorUnavailableError(
                f"the {ORCHESTRATOR_ROLE!r} role has no unit to dispatch to"
            )
        return proposals_from_reply(completion.text)

    return propose


#: How decisively the model must commit before a choice is acted on.
#: :func:`~mcgyvr.decision.confidence` is 0 for a flat answer and 1 for a
#: certain one; below this the proposer refuses rather than guessing, and the
#: caller falls back to the agent or a stronger proposer.
MIN_CONFIDENCE = 0.5

#: The option key that says "no specific symbol" — the whole target is the work.
_NO_SYMBOL = ""

#: How many options one :class:`~mcgyvr.decision.Choice` may carry, matching the
#: decision primitive's 62 single-token labels. Candidate lists are capped at
#: this; the symbol question keeps one label free for the no-symbol sentinel.
_MAX_CHOICE_OPTIONS = 62


@dataclass(frozen=True)
class ClassifierProposer:
    """A proposer whose judgment is typed single-token choices, never prose.

    Where :func:`proposer_for` asks the orchestrator role for a free-text JSON
    reply and parses it, this proposer asks three
    :class:`~mcgyvr.decision.Choice` questions through
    :func:`~mcgyvr.decision.classify_for` — the task type over the servable
    vocabulary, the target file over the resolver's ranked shortlist, and the
    symbol the task works on over that target's definitions — and builds one
    proposal from the answers. The model's contribution is *relevance*; the
    repository supplies the facts downstream in
    :func:`~mcgyvr.orchestrator.decompose.decompose` exactly as before.

    ``classify`` is the bound decision call the factory supplies: it already
    knows the endpoint and model, so this type holds neither — which is what
    keeps it above the seam. On low confidence in any answer the proposer
    returns nothing, a refusal the caller answers by falling back to the agent
    or a stronger proposer, rather than by guessing.
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
        if kind is None:  # the model answered with a name not on offer
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
    """A typed :class:`Proposer` over the ``jev.unit`` or the orchestrator role,
    or ``None`` when neither is bound.

    The same ``None`` contract as :func:`proposer_for`: a keyless install has no
    orchestrator, answered with :data:`NO_ORCHESTRATOR_ROLE` rather than a
    failure. The decisions are dispatched through
    :func:`~mcgyvr.decision.classify_for`, below the seam — to the ``jev.unit``
    when one is bound, which is then all this proposer needs, and to the
    orchestrator role's unit when not — so this factory holds no endpoint and
    the proposer it returns holds none either.
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


# --- the typed decisions, assembled ----------------------------------------


def _choice(decision: Decision, name: str) -> ChoiceAnswer | None:
    """The ``name`` answer as a :class:`ChoiceAnswer`, or ``None`` if unreadable."""
    answer = decision.answers.get(name)
    return answer if isinstance(answer, ChoiceAnswer) else None


def _candidate_targets(evidence: Evidence) -> tuple[str, ...]:
    """The paths the model may pick as the target, best-first.

    The resolver's ranked shortlist, then any file a bounded read actually
    opened, de-duplicated in that order. Capped at the decision primitive's
    :class:`~mcgyvr.decision.Choice` limit.
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
    """The symbols defined in ``target``, in discovery order."""
    return tuple(
        symbol
        for symbol in evidence.index.symbols.all()
        if symbol.path == target and symbol.kind is SymbolKind.DEFINITION
    )


def _symbol_options(symbols: Sequence[Symbol]) -> dict[str, str]:
    """The symbols the model may pick, plus the no-symbol sentinel.

    Keyed by name with the symbol's detail as the description; a name defined
    twice keeps the first. One label is held back for the sentinel, so the
    choice stays within the primitive's 62-option bound.
    """
    options: dict[str, str] = {}
    for symbol in symbols[: _MAX_CHOICE_OPTIONS - 1]:
        if symbol.name not in options:
            options[symbol.name] = symbol.detail or "symbol"
    options[_NO_SYMBOL] = "no specific symbol — the whole file is the work"
    return options


def _kind_for(name: str, vocabulary: Sequence[TaskType]) -> TaskType | None:
    """The vocabulary entry the model's answer names, or ``None``."""
    return next((task for task in vocabulary if task.name == name), None)


def _directive(kind: TaskType, target: str, symbol: str | None) -> str:
    """The worker's directive, rendered from the relevance the model decided.

    The model decided which kind, which file, which symbol; this is that triple
    spelled as one imperative sentence, not new prose the model authored, so the
    directive cannot say something the typed decisions did not.
    """
    return f"{kind.doc.split('.', 1)[0]}: {_subject(target, symbol)}."


def _stop_condition(kind: TaskType, target: str, symbol: str | None) -> tuple[str, ...]:
    """The stop condition a model-executed type must carry, or none for a tool.

    A deterministic type is executed by a tool that cannot guess, so it has no
    trigger to report BLOCKED. A model-executed type must name one — the loader
    refuses a model type with none — and the one this proposer writes is the
    honest default: stop rather than decide anything the typed choices did not
    already settle.
    """
    if kind.deterministic:
        return ()
    subject = _subject(target, symbol)
    return (
        f"{kind.name} on {subject} would require deciding something the "
        "contract does not state — report BLOCKED rather than guess",
    )


def _subject(target: str, symbol: str | None) -> str:
    """How the worker's directive names what it works on."""
    return target if symbol is None else f"{symbol} in {target}"


def _state(
    evidence: Evidence, targets: tuple[str, ...], vocabulary: Sequence[TaskType]
) -> dict[str, Any]:
    """The state the decision prompt carries: the request and what is on offer."""
    return {
        "request": evidence.prompt,
        "candidates": list(targets),
        "task_types": [task.name for task in vocabulary],
    }


def completable(vocabulary: Sequence[TaskType]) -> tuple[TaskType, ...]:
    """The task types whose contract this proposer can complete.

    A type whose evidence needs commands — ``acceptance`` that passes at
    baseline, or a ``demonstration`` that fails there — needs a contract that
    carries them, and this proposer writes neither: its contribution is
    relevance, three single-token choices. A contract of such a type from it
    is one the loader refuses (``contract.py``: "acceptance: is empty, but
    task type ... requires"), and in the pilot every one was. So those types
    are not offered; a vocabulary that leaves none is answered with nothing,
    and the caller falls back to a proposer that writes commands.
    """
    return tuple(
        task
        for task in vocabulary
        if not task.needs_acceptance_commands and not task.needs_demonstration_commands
    )


def proposer_by_authoring(
    strategy: str | None, *, typed: Proposer | None, prose: Proposer | None
) -> Proposer | None:
    """The proposer ``orchestrator.authoring`` names for ``mcgyvr delegate``.

    ``classifier`` asks ``typed`` first and falls back to ``prose`` when it
    returns nothing — a low-confidence refusal or a request outside what it
    can complete. Any other value is ``prose``, the proposer the command has
    always used: ``direct`` is a strategy only a conversing rung carries out,
    and an unbound field is the file not choosing. ``None`` where there is no
    prose proposer to fall back to, which is the ``NO_ORCHESTRATOR_ROLE``
    answer the command already gives.
    """
    if strategy != "classifier" or typed is None:
        return prose
    if prose is None:
        return None

    def propose(evidence: Evidence) -> Sequence[Proposal]:
        proposals = typed(evidence)
        return proposals if proposals else prose(evidence)

    return propose
