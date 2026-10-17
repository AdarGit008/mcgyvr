"""The authoring strategies mcorch binds as its internal tools.

Two kinds. `Direct` proposes from the request alone: the model calls
`author_contract` with a whole YAML document, `Direct.handle` validates it with
`contract.loads`, asks the jev whether it is ready to run, and answers with a
refusal, a doubt to address, or the canonical document to write. `Evidenced`
proposes from a reading of the repository: `handle` answers `gather_evidence`
with a `GATHER`-prefixed request the loop turns into a `mcgyvr read`, and
`propose` runs the decomposer over that reading through a prose or classifier
proposer and digests the contracts and refusals back to the model.

`authoring_for` picks one of `STRATEGIES` over the `Jev` and `Rung` seams wired
by `wire.bind`; `READY_QUESTION` and `READY` are the single jev question both
kinds ask before handing a contract over.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from mcgyvr import contract, delegate
from mcgyvr.config import Config
from mcgyvr.decision import BoolAnswer, Noul
from mcgyvr.mcorch import evidence
from mcgyvr.mcorch.wire import Jev, Rung, RungCall, RungToolCall
from mcgyvr.orchestrator.decompose import (
    Decomposition,
    Evidence,
    Proposal,
    Proposer,
    decompose,
)

#: The names `authoring_for` accepts: "direct" authors from the request alone,
#: the other two propose from a reading of the repository.
STRATEGIES = ("direct", "prose", "classifier")

#: The key the readiness question is asked under, and read back from the decision.
READY_QUESTION = "ready_to_run"

#: The one question asked of every contract before it is handed to the model: it
#: must name a single target, carry a task a worker can do from the fields alone,
#: and give the gate something to judge the result by.
READY = Noul(
    "Is this contract ready to run as written: one target, a task a worker can "
    "carry out from the fields alone, and a way to judge the result?"
)


class AuthoringUnavailableError(RuntimeError):
    """`authoring_for` was asked for a strategy that proposes through the rung,
    and the server was bound without one."""


#: Prefix `Evidenced.handle` puts in front of a gather request; the loop strips it
#: and serves the rest as a `mcgyvr read` before the model is asked again.
GATHER = "gather:"


class Authoring(Protocol):
    """One authoring strategy as the loop uses it: the tool specs it offers, the
    answer it gives a call to one of them, and whether it proposes from a
    reading of the repository."""

    @property
    def name(self) -> str: ...

    @property
    def needs_evidence(self) -> bool:
        """Whether the strategy proposes from a reading of the repository, and so
        waits for a `mcgyvr read` before it can author anything."""
        ...

    def tools(self) -> tuple[dict[str, Any], ...]:
        """The tool specs the loop adds to the model's own tools, so a call of
        one of them is answered here instead of being forwarded to the harness."""
        ...

    def handle(self, call: RungToolCall) -> str | None:
        """The text answering `call`, or None when the tool is not this
        strategy's and the next strategy should be asked."""
        ...


@dataclass(frozen=True)
class Direct:
    """Author from the request alone: the model calls `author_contract`, and gets
    the validated document back to write to the tree. `jev` decides whether the
    contract is ready to run."""

    jev: Jev

    @property
    def name(self) -> str:
        return "direct"

    @property
    def needs_evidence(self) -> bool:
        return False

    def tools(self) -> tuple[dict[str, Any], ...]:
        return (
            {
                "type": "function",
                "function": {
                    "name": "author_contract",
                    "description": (
                        "Validate a mcgyvr contract before writing it. Pass the "
                        "whole YAML document. Returns `refused:` with the key "
                        "that is wrong, `Jev:` with a doubt to address, or `ready:` "
                        "with the canonical document to write to the tree verbatim."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contract": {
                                "type": "string",
                                "description": "The contract as one YAML document.",
                            }
                        },
                        "required": ["contract"],
                    },
                },
            },
        )

    def handle(self, call: RungToolCall) -> str | None:
        if call.name != "author_contract":
            return None
        arguments = _arguments(call.arguments)
        document = arguments.get("contract") if arguments is not None else None
        if not isinstance(document, str) or not document.strip():
            return "refused: `contract` must be the whole YAML document as a string."
        try:
            authored = contract.loads(document)
        except contract.ContractError as exc:
            return f"refused: {exc}"
        decision = self.jev(_summary(authored), {READY_QUESTION: READY})
        answer = decision.answers.get(READY_QUESTION)
        if isinstance(answer, BoolAnswer) and not answer.value:
            return (
                f"Jev: contract {authored.id!r} is not ready to run "
                f"(probability ready {answer.probability_true:.2f}). Revise it: "
                "name the one target, state the task from the fields alone, and "
                "give the gate a way to judge it (acceptance or demonstration)."
            )
        return (
            f"ready: contract {authored.id!r} validates. Write exactly this document "
            f"to {authored.id}.yaml with the harness, then run it:\n"
            f"{contract.dumps(authored)}"
        )


def _summary(authored: contract.Contract) -> dict[str, Any]:
    """The fields of `authored` the readiness question is decided on: what the
    contract is, what a worker is asked to do and to which target, how the result
    is judged, and the scope's allow list."""
    return {
        "id": authored.id,
        "task_type": authored.task_type,
        "operation": authored.operation,
        "task": authored.task,
        "target": authored.target,
        "interface": authored.interface,
        "stop_conditions": list(authored.stop_conditions),
        "acceptance": list(authored.acceptance),
        "demonstration": list(authored.demonstration),
        "scope_allow": list(authored.scope.allow),
    }


def _arguments(text: str) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(text) if text.strip() else {}
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass(frozen=True)
class Evidenced:
    """Author from a reading of the repository, in the configured `strategy`:
    "prose" builds a prompt from the evidence and parses the rung's reply into
    proposals, "classifier" asks the jev typed questions. `rung` makes the
    proposal calls, `jev` decides readiness, and `config` bounds which task types
    are offered."""

    strategy: str
    jev: Jev
    rung: Rung
    config: Config | None = None

    @property
    def name(self) -> str:
        return self.strategy

    @property
    def needs_evidence(self) -> bool:
        return True

    def tools(self) -> tuple[dict[str, Any], ...]:
        return (
            {
                "type": "function",
                "function": {
                    "name": "gather_evidence",
                    "description": (
                        "Have the repository read for a request: mcorch runs "
                        "`mcgyvr read` through the harness and proposes contracts "
                        "from what it finds. Call it when a replan needs fresh "
                        "evidence; a new request is read without asking."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "request": {
                                "type": "string",
                                "description": "What to find, in words.",
                            }
                        },
                        "required": ["request"],
                    },
                },
            },
        )

    def handle(self, call: RungToolCall) -> str | None:
        if call.name != "gather_evidence":
            return None
        arguments = _arguments(call.arguments)
        request = arguments.get("request") if arguments is not None else None
        if not isinstance(request, str) or not request.strip():
            return "refused: `request` must say, in words, what to find."
        return f"{GATHER}{request.strip()}"

    def propose(self, document: evidence.Document, *, max_output_tokens: int) -> str:
        """The digest the model reads in place of one `mcgyvr read` document: index
        its files, decompose its prompt through this strategy's proposer with
        `config` and the checker commands the read already found, and report every
        contract as ready or in doubt and every refusal with its reason.
        `max_output_tokens` is the room one prose proposal call gets."""
        index = evidence.index_from(document)
        prompt = document.prompt
        decomposition = decompose(
            index,
            prompt,
            propose=self._proposer(max_output_tokens),
            config=self.config,
            # The checker commands the read already located, so a `type_check`
            # acceptance is derived without probing the disk again.
            located=document.located,
        )
        return self._digest(decomposition)

    def _proposer(self, max_output_tokens: int) -> Proposer:
        def prose(found: Evidence) -> Sequence[Proposal]:
            reply = self.rung(
                RungCall(
                    system="",
                    turns=({"role": "user", "content": delegate.build_prompt(found)},),
                    tools=(),
                    max_output_tokens=max_output_tokens,
                )
            )
            try:
                return delegate.proposals_from_reply(reply.text)
            except delegate.UnreadableProposalError:
                return ()

        typed = delegate.ClassifierProposer(classify=self.jev)
        chosen = delegate.proposer_by_authoring(self.strategy, typed=typed, prose=prose)
        assert chosen is not None  # prose is always given, so something proposes
        return chosen

    def _digest(self, decomposition: Decomposition) -> str:
        lines: list[str] = []
        for authored, document in zip(
            decomposition.contracts, decomposition.documents, strict=True
        ):
            decision = self.jev(_summary(authored), {READY_QUESTION: READY})
            answer = decision.answers.get(READY_QUESTION)
            if isinstance(answer, BoolAnswer) and not answer.value:
                lines.append(
                    f"Jev: contract {authored.id!r} is not ready to run "
                    f"(probability ready {answer.probability_true:.2f}); revise it "
                    "before writing it:\n" + document
                )
                continue
            lines.append(
                f"ready: contract {authored.id!r} validates. Write exactly this "
                f"document to {authored.id}.yaml with the harness, validate it with "
                "`mcgyvr contract`, then run it:\n" + document
            )
        for refusal in decomposition.refusals:
            lines.append(f"refused: {refusal.subject}: {refusal.reason}")
        if not lines:
            lines.append(
                "refused: nothing could be proposed from the evidence; narrow the "
                "request or name the target file."
            )
        return "\n\n".join(lines)


def authoring_for(
    strategy: str,
    *,
    jev: Jev,
    rung: Rung | None = None,
    config: Config | None = None,
) -> Authoring:
    """The strategy named `strategy`, wired to the given seams.

    `direct` needs only `jev`. The other names in `STRATEGIES` propose through the
    rung, so they raise `AuthoringUnavailableError` when `rung` is None. A name
    outside `STRATEGIES` raises `ValueError`."""
    if strategy == "direct":
        return Direct(jev=jev)
    if strategy in STRATEGIES:
        if rung is None:
            raise AuthoringUnavailableError(
                f"orchestrator.authoring: {strategy!r} proposes through the rung, "
                "and this server was bound without one."
            )
        return Evidenced(strategy=strategy, jev=jev, rung=rung, config=config)
    raise ValueError(
        f"orchestrator.authoring: {strategy!r} is not one of {', '.join(STRATEGIES)}"
    )
