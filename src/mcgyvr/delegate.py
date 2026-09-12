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
draws the line (ADR-0007). The role is *not* shown a contract document and is
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
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal, Proposer
from mcgyvr.runner import Request, dispatch_role

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.pool import SourceMap

#: What the pool calls the orchestrator. One name, in one place, because a role
#: spelled differently here than in :mod:`mcgyvr.pool` is a role that is
#: silently never found.
ORCHESTRATOR_ROLE = "orchestrator"

#: How much room the orchestrator's reply is given. A decomposition is a JSON
#: array of proposals — several short directives, not a file — and a cap that
#: cuts a proposal in half costs the whole decomposition: nothing downstream
#: can read half a JSON array. Generous enough for a handful of contracts,
#: small enough that a runaway reply is still bounded (ADR-0009).
ORCHESTRATOR_OUTPUT_TOKENS = 4096

#: The documented answer a keyless install gets. ``proposer_for`` returns
#: ``None``; the CLI prints this and exits REFUSED, never a traceback.
NO_ORCHESTRATOR_ROLE = (
    "the orchestrator role is not configured, so a prompt cannot be turned "
    "into contracts here. Bind `orchestrator.source` and `orchestrator.model` "
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
    the repository for more, which is ADR-0001 boundary 2 expressed as a
    prompt rather than as a type.
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
        "Omit optional fields rather than writing null. Return [] when nothing "
        "can be proposed."
    )


def proposals_from_reply(reply: str) -> tuple[Proposal, ...]:
    """The proposals a reply carries, or a named failure.

    Accepts the JSON array bare or wrapped in a markdown fence, so a model that
    fences its answer is still read rather than refused. Anything else — prose,
    a JSON scalar, a proposal missing its required fields — is an
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
    """The JSON inside one markdown fence, or the reply itself when unfenced.

    Mirrors the worker reply parser's fence rule without its file judgements:
    one fence or the bare text, never a hunt through prose.
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


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,})[ \t]*([A-Za-z0-9_+.#-]*)[ \t]*$")


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
    max_output_tokens: int = ORCHESTRATOR_OUTPUT_TOKENS,
) -> Proposer | None:
    """The install's orchestrator role as a :class:`Proposer`, or ``None``.

    ``None`` mirrors :meth:`~mcgyvr.pool.SourceMap.role_model` and is an
    ordinary answer: a keyless install has no orchestrator, which the CLI
    answers with :data:`NO_ORCHESTRATOR_ROLE` rather than by failing. The
    request is not marked ``quality_sensitive`` for the same reason the
    verifier's is not — a proposal is work, and refusing a caveated backend
    would turn the ordinary local install into one with no orchestrator at all
    while telling the operator nothing.
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
                f"the {ORCHESTRATOR_ROLE!r} role has no source to dispatch to"
            )
        return proposals_from_reply(completion.text)

    return propose
