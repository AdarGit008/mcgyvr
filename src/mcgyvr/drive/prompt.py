"""Send an assembled prompt to a rung: refuse what cannot be sent, then dispatch.

:func:`refuse_unsendable` raises the refusal named for the preflight issue when
a contract or its prompt does not fit a rung; :func:`refuse_unsendable_climb`
applies the same check to every climbable rung of the climb before the first
attempt, so a rung that cannot be sent to ends the run before anything is spent
on the rungs below it. :func:`dispatch_prompt` sizes the reply cap and hands the
request to the runner. `_base_content` reads the contract target's current
content out of the sandbox, and `_as_sent` renders a prompt as the chat messages
a runner is given, for recording the dispatch.
"""

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
    """Raise the refusal for a contract that cannot be sent to `rung`, else return.

    Session contracts are exempt and return at once. Otherwise the contract must
    state a `limits.max_output_tokens` (`OutputCapUnstatedError`), the assembled
    prompt must fit its own ceiling (`PromptTooLargeError`), and the contract must
    fit the rung as `check_contract_against_rung` judges it, where the issue's
    reason picks the class: `output-cap` is `OutputCapTooLargeError`,
    `unit-ceiling-unknown` is `UnitCeilingUnknownError`, and any other reason is
    `ContractTooLargeForRungError`. The message names the contract, the rung, the
    window served, and the issue.
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
    """Check every climbable rung of the climb before the first attempt.

    Contracts that do not need an output cap return at once. For those that do,
    each plan `ascent` offers is walked and each of its climbable steps bound and
    put through :func:`refuse_unsendable`. The first refusal is re-raised as the
    same type with a note that it was found before the first attempt: a rung of
    the climb that cannot be sent to ends the run before anything is spent on
    the rungs below it.
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
    """Refuse an unsendable prompt, then send it to `rung` and return the reply.

    The rung is bound and put through :func:`refuse_unsendable` first, so nothing
    reaches the runner for a contract or prompt that cannot be sent. The reply cap
    is then sized from the contract and the rung, with the prompt's measured
    tokens as the room this request leaves, and the `Request` carries the prompt's
    system and user text, that cap, the cap's basis, the response schema, and the
    timeout and temperature when they are not None — those two fields are omitted
    from the request rather than sent as nulls. `capacity`, when given, is passed
    on to the drive layer's dispatch, which holds it across the call.
    """
    endpoint = source_map.bind(rung)
    refuse_unsendable(rung, endpoint, prompt, contract, window_fraction=window_fraction)
    # Every refusal happens here, before the runner is touched: a contract the
    # rung cannot take costs nothing.
    # Session contracts skip those checks entirely and reach the wire unchecked.
    cap = sized_reply_cap(contract, endpoint, prompt=prompt.measured)
    # The cap is the contract's declared tokens bounded by what the rung can
    # serve, and it is sent as a hard limit on the reply.
    # Its basis travels with it so the journal can say where the number came from.
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
    """The contract target's content as it stands in the sandbox, before the edit.

    The path is resolved against the sandbox workspace with
    :func:`mcgyvr.scope.inside`, so an absolute path or one inside `.git` is
    refused. A target that is not a file reads as the empty string, which serves
    the contract's own `target_content` or nothing. The bytes are decoded with
    `surrogateescape` so content that is not valid UTF-8 round-trips unchanged.
    """
    target = inside(sandbox.workspace, contract.target)
    if not target.is_file():
        return ""
    return target.read_bytes().decode("utf-8", "surrogateescape")


def _as_sent(prompt: WorkerPrompt) -> list[dict[str, str]]:
    """The prompt as the chat messages a runner is handed, for the recording.

    The system message comes first and only when `prompt.system` is non-empty;
    the user message always follows it.
    """
    messages: list[dict[str, str]] = []
    if prompt.system:
        messages.append({"role": "system", "content": prompt.system})
    messages.append({"role": "user", "content": prompt.user})
    return messages
