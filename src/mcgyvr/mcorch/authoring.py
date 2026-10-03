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
  server executes nothing and holds no path to the user's repository, so it
  has no index; asking for either is refused by name when the server starts
  rather than failing mid-conversation. How the rung could hand evidence over
  is a design question that is asked, not guessed at here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from mcgyvr import contract
from mcgyvr.decision import BoolAnswer, Noul
from mcgyvr.mcorch.wire import Jev, RungToolCall

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


class Authoring(Protocol):
    """An internal tool set: what it offers the rung, and how it answers a call."""

    @property
    def name(self) -> str: ...

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


def authoring_for(strategy: str, *, jev: Jev) -> Authoring:
    """The named strategy as an internal tool set, or a refusal naming why not."""
    if strategy == "direct":
        return Direct(jev=jev)
    if strategy in STRATEGIES:
        raise AuthoringUnavailableError(
            f"orchestrator.authoring: {strategy!r} needs the repository's index to "
            "shortlist targets and read regions, and this server holds no index: "
            "it executes nothing and knows no path to the user's repository. "
            "Bind `direct`, or wait for the evidence seam that hands the index "
            "over through the harness."
        )
    raise ValueError(
        f"orchestrator.authoring: {strategy!r} is not one of {', '.join(STRATEGIES)}"
    )
