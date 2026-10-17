""

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

#
STRATEGIES = ("direct", "prose", "classifier")

#
READY_QUESTION = "ready_to_run"

#
READY = Noul(
    "Is this contract ready to run as written: one target, a task a worker can "
    "carry out from the fields alone, and a way to judge the result?"
)


class AuthoringUnavailableError(RuntimeError):
    ""


#
#
GATHER = "gather:"


class Authoring(Protocol):
    ""

    @property
    def name(self) -> str: ...

    @property
    def needs_evidence(self) -> bool:
        ""
        ...

    def tools(self) -> tuple[dict[str, Any], ...]:
        ""
        ...

    def handle(self, call: RungToolCall) -> str | None:
        ""
        ...


@dataclass(frozen=True)
class Direct:
    ""

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
    ""
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
    ""

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
        ""
        index = evidence.index_from(document)
        prompt = document.prompt
        decomposition = decompose(
            index,
            prompt,
            propose=self._proposer(max_output_tokens),
            config=self.config,
            #
            #
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
        assert chosen is not None  #
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
    ""
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
