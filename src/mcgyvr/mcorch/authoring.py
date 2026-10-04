"""How mcorch turns a request into a contract: the strategy the config names.

``orchestrator.authoring`` is a measured choice, not a default shipped here
(the config loader refuses a file that leaves it unbound). Each strategy is an
internal tool set — functions the rung may call that run inside one request
and are never shown to the harness — so the rung's wire is one shape whatever
the strategy, and the loop treats a strategy as "a tool the harness does not
have".

* ``direct``: the rung writes the contract. ``author_contract`` validates the
  document through the public loader, :func:`mcgyvr.contract.loads` — the same
  entry direct mode uses, so an authored contract is one ``mcgyvr run``
  accepts — then asks Jev whether it is ready to run (J2). A refused document
  comes back naming the key; a doubted one comes back with the doubt; a ready
  one comes back canonical, for the rung to write to the tree verbatim.
* ``prose`` and ``classifier`` need the repository's index
  (:mod:`mcgyvr.orchestrator`) to shortlist targets and read regions. The
  server holds no path to the user's repository, so the evidence rides the
  harness (owner ruling: what a pi agent does, mcorch does): the loop has the
  harness run ``mcgyvr read "<request>" --json`` and
  :class:`Evidenced` assembles the index from the document that comes back
  (:mod:`mcgyvr.mcorch.evidence`), asks the proposer — the rung for prose
  proposals, Jev for typed ones with prose behind it — and runs the
  deterministic decomposer over that index. The contracts come back to the
  rung as a digest, ready to write, the same ``ready:`` shape ``direct``
  answers with; the rung's internal tool ``gather_evidence`` asks for a fresh
  read when a replan needs one.
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

#: The strategies the config may name, as the schema spells them.
STRATEGIES = ("direct", "prose", "classifier")

#: The name of the question J2 asks, stable so a transcript reads it by key.
READY_QUESTION = "ready_to_run"

#: The question itself: one Noul over the contract's own summary.
READY = Noul(
    "Is this contract ready to run as written: one target, a task a worker can "
    "carry out from the fields alone, and a way to judge the result?"
)


class AuthoringUnavailableError(RuntimeError):
    """The named strategy cannot run on this server, and the message says why."""


#: What an internal tool answers to say "the harness must read the repository
#: for this request": the loop turns it into a shell call.
GATHER = "gather:"


class Authoring(Protocol):
    """An internal tool set: what it offers the rung, and how it answers a call."""

    @property
    def name(self) -> str: ...

    @property
    def needs_evidence(self) -> bool:
        """Whether a work request is answered by reading the repository first."""
        ...

    def tools(self) -> tuple[dict[str, Any], ...]:
        """OpenAI function tools, offered beside the harness's."""
        ...

    def handle(self, call: RungToolCall) -> str | None:
        """The result text for a call this strategy owns, or ``None`` if not its."""
        ...


@dataclass(frozen=True)
class Direct:
    """The rung authors the contract; the loader and Jev judge it."""

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
    """What J2 is asked over: the contract's shape, never its file contents."""
    return {
        "id": authored.id,
        "task_type": authored.task_type,
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
    """``prose`` or ``classifier``: the index rides the harness, the server proposes.

    ``rung`` answers the prose proposer's prompt (the orchestrator unit, the
    same one that converses); ``jev`` answers the classifier's typed choices
    and J2; ``config`` says which task types the ladder can serve.
    """

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
        """The digest the rung reads in place of the document: contracts to write."""
        index = evidence.index_from(document)
        prompt = document.prompt
        decomposition = decompose(
            index, prompt, propose=self._proposer(max_output_tokens), config=self.config
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
        assert chosen is not None  # prose is always there to fall back to
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
    """The named strategy as an internal tool set, or a refusal naming why not."""
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
