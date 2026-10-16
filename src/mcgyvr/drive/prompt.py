"""Prompt assembly, the refusals that keep a bad prompt off the wire."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mcgyvr.drive as _drive
from mcgyvr.drive.errors import (
    ContractTooLargeForRungError,
    DriveError,
    OutputCapTooLargeError,
    OutputCapUnstatedError,
    PromptTooLargeError,
    UnitCeilingUnknownError,
)
from mcgyvr.escalate import ascent
from mcgyvr.gate.preflight import (
    ServingWindow,
    check_cap_stated,
    check_contract_against_rung,
    sized_reply_cap,
)
from mcgyvr.runner import Completion, Request
from mcgyvr.scope import inside

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.worker.prompt import WorkerPrompt


def refuse_unsendable(
    rung: str,
    endpoint: ServingWindow,
    prompt: WorkerPrompt,
    contract: Contract,
    *,
    window_fraction: float | None = None,
) -> None:
    """Raise, before anything is sent, if this prompt cannot go to this rung.

    First, whether there is a cap to send at all: a model-written ``code``
    contract that states no ``limits.max_output_tokens`` is never sent
    (:class:`OutputCapUnstatedError`). Then two questions, in this order. Does
    the assembled prompt fit the ceiling its
    own contract set (:class:`PromptTooLargeError`)? And does the contract fit
    the window the rung serves —
    :func:`~mcgyvr.gate.preflight.check_contract_against_rung`, which asks
    whether its declared ceiling, its reply cap, and its prompt beside that cap
    fit, and whether it claims more of the window than its share allows?

    ``window_fraction`` is the run's ``max_window_fraction``, read off the
    config by the caller that holds it. It is a ceiling: a contract is held to
    the stricter of it and its own ``limits.max_window_fraction`` (the rule is
    :func:`~mcgyvr.gate.preflight.held_share`'s). ``None`` enforces no
    run-wide share.

    A rung too small for the contract raises :class:`ContractTooLargeForRungError`
    (or :class:`OutputCapTooLargeError` when the reply cap alone fills the
    window), naming the contract, the rung and the preflight issue, which
    carries the tokens and the window. Owner ruling: the task fails on the rung
    it was sent to; it is not moved to a bigger one. Without this the request
    went out and a llama.cpp unit answered ``400``, which reached the operator
    as an HTTP status naming neither number.

    A rung that declared no window enforces only the first question — the check
    has no number to measure against, and inventing one is the defect it ends.

    A session (``chat``, ``agent``) is asked neither question. It is a raw
    connection to a model, and mcgyvr wraps no harness around one (owner,
    2026-10-14, e2e run 3 T1): no output cap, no prompt check, no window check.
    """
    if contract.is_session:
        return
    unstated = check_cap_stated(contract)
    if unstated is not None:
        raise OutputCapUnstatedError(f"{unstated}")
    if not prompt.fits:
        raise PromptTooLargeError(
            f"contract {contract.id!r}: the assembled prompt does not fit its "
            f"own ceiling and was not sent — {prompt.fit_issue}"
        )
    issue = check_contract_against_rung(
        contract, prompt.measured, rung=endpoint, default_fraction=window_fraction
    )
    if issue is None:
        return
    refusal: type[DriveError] = {
        "output-cap": OutputCapTooLargeError,
        "unit-ceiling-unknown": UnitCeilingUnknownError,
    }.get(issue.reason, ContractTooLargeForRungError)
    served = (
        f"{endpoint.context_window}-token window"
        if endpoint.context_window is not None
        else "no window stated"
    )
    raise refusal(
        f"contract {contract.id!r} does not fit rung {rung!r} ({served}) and was "
        f"not sent — {issue}"
    )


def refuse_unsendable_climb(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    prompt: WorkerPrompt,
    *,
    window_fraction: float | None = None,
) -> None:
    """Raise, before the first attempt, if any rung of the climb cannot be sent to.

    Owner decision (2026-10-14, e2e run 3 T1): a model-written ``code``
    contract's cap is held to the ceiling of every unit it reaches. Asked only
    as each rung is reached, a cap the dearer rung cannot hold is found on the
    escalation to it — after the cheaper rungs have spent their attempts on
    work the run could never finish. So the first attempt asks
    :func:`refuse_unsendable` of every rung of the climb, with its own prompt,
    and the first refusal ends the run before anything is dispatched, naming
    the rung it is about.

    The climb is :func:`~mcgyvr.escalate.ascent`'s, from the contract's floor:
    every rung of every family the run may enter. Only for the contracts the
    unit ceiling bounds (:attr:`~mcgyvr.contract.Contract.needs_output_cap`);
    any other reply is measured per rung, as it always was.
    """
    if not contract.needs_output_cap:
        return
    for plan in ascent(config, pool, contract).plans:
        for step in plan.climbable:
            name = step.rung.name
            try:
                refuse_unsendable(
                    name,
                    pool.bind(name),
                    prompt,
                    contract,
                    window_fraction=window_fraction,
                )
            except DriveError as refused:
                raise type(refused)(
                    f"{refused} (checked before the first attempt: a rung of "
                    f"the climb that cannot be sent to ends the run before "
                    f"anything is spent on the rungs below it)"
                ) from refused


def dispatch_prompt(
    source_map: SourceMap,
    rung: str,
    prompt: WorkerPrompt,
    contract: Contract,
    *,
    capacity: Capacity | None = None,
    response_schema: dict[str, Any] | None = None,
    timeout_s: float | None = None,
    temperature: float | None = None,
    window_fraction: float | None = None,
) -> Completion:
    """Send an assembled prompt to a rung, under the contract's own ceilings.

    Both halves of the prompt travel — ``system`` carries the bundle the
    target's language earned and dropping it would send a worker the
    instructions for no language at all — and the output cap is
    :func:`~mcgyvr.gate.preflight.sized_reply_cap`'s: the contract's
    ``limits.max_output_tokens``, exactly, once :func:`refuse_unsendable` has
    found it within the unit's ceiling — a unit's ``output_tokens`` bounds it
    and never replaces it. A contract that states no cap (a raw connection, a
    ``media_artifact`` reply) is uncapped, so ``cap`` is ``None`` there and the
    runner omits the wire field — except on a ride, which is sent the ceiling
    it carries.

    ``contract`` is taken whole rather than as a cap, because a binding given
    only a number cannot be the place the fit refusal happens, and the refusal
    is the point: a prompt that does not fit
    :attr:`~mcgyvr.contract.Contract.max_input_tokens` is refused here, with the
    preflight issue ``build_prompt`` already computed, instead of being sent to
    be truncated somewhere that cannot say why. A per-rung cap adds a second
    refusal of the same kind and for the same reason — a cap the rung's own
    window cannot hold — and it is checked here rather than trusted to the
    ladder's author, because this is the last place that holds both numbers
    before they reach a socket. ``build_prompt`` cannot ask it: a prompt is
    assembled once and may be offered to several rungs, and which window it
    faces is only known here.

    ``temperature`` is the draw's, threaded from ``breadth.temperature`` by the
    caller that knows which draw this is: draw 0 of an attempt is greedy and
    the draws after it sample. ``None`` keeps :class:`~mcgyvr.runner.Request`'s
    own default of ``0.0``.

    Both refusals are :func:`refuse_unsendable`'s, which also measures the
    whole contract against the rung's window — and against ``window_fraction``,
    the run's ``max_window_fraction``, a ceiling over the contract's own share.
    """
    endpoint = source_map.bind(rung)
    refuse_unsendable(rung, endpoint, prompt, contract, window_fraction=window_fraction)
    # Read beside the prompt the refusal above measured, so the basis the
    # journal records names the ceiling the cap was checked against.
    cap = sized_reply_cap(contract, endpoint, prompt=prompt.measured)
    # ``timeout_s`` is the unit's ``request_timeout_s``, passed by the caller
    # that holds the config. ``None`` keeps ``Request``'s own default.
    fields: dict[str, Any] = {
        "prompt": prompt.user,
        "system": prompt.system,
        "max_output_tokens": cap.tokens,
        "cap_basis": cap.basis,
        "response_schema": response_schema,
    }
    if timeout_s is not None:
        fields["timeout_s"] = timeout_s
    if temperature is not None:
        fields["temperature"] = temperature
    request = Request(**fields)
    return _drive.dispatch(source_map, rung, request, capacity=capacity)


def _base_content(sandbox: Sandbox, contract: Contract) -> str:
    """The target as it stands before this attempt writes anything.

    What a reviewer needs to judge an *edit*: without it
    :func:`~mcgyvr.verify.build_prompt` says the original was not supplied and
    asks the model to judge the change on its own, which for a change to an
    existing file is most of the question missing. ``""`` is the other real
    answer and the block below renders it as one — the target is not there, so
    the change creates it.

    Taken from the workspace rather than from ``contract.target_content``,
    which is what ``build_prompt`` falls back to. That field is the
    orchestrator's copy of the file as it stood when the contract was written,
    and a hand-authored contract does not carry it at all; this is the tree the
    gate diffed against a moment ago, in this attempt, which is the only
    original the verdict is actually about.

    Decoded with ``surrogateescape``, so a file holding a byte no decoder can read
    still reaches the reviewer as the rest of its content rather than raising
    out of an attempt that has not failed.
    """
    target = inside(sandbox.workspace, contract.target)
    if not target.is_file():
        return ""
    return target.read_bytes().decode("utf-8", "surrogateescape")


def _as_sent(prompt: WorkerPrompt) -> list[dict[str, str]]:
    """The messages exactly as :func:`dispatch_prompt` has the runner send them.

    Built here rather than inside :func:`~mcgyvr.telemetry.observe` because the
    journal records what was *sent* and only this module knows that: the runner
    adds a system message only when ``Request.system`` is non-empty, so an
    empty bundle is no message at all — not a message with nothing in it, whose
    digest would put a ``bundle_sha256`` on the row for a system prompt nobody
    received.
    """
    messages: list[dict[str, str]] = []
    if prompt.system:
        messages.append({"role": "system", "content": prompt.system})
    messages.append({"role": "user", "content": prompt.user})
    return messages
