""

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

if TYPE_CHECKING:  #
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
    ""
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
    ""
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
    ""
    endpoint = source_map.bind(rung)
    refuse_unsendable(rung, endpoint, prompt, contract, window_fraction=window_fraction)
    #
    #
    cap = sized_reply_cap(contract, endpoint, prompt=prompt.measured)
    #
    #
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
    ""
    target = inside(sandbox.workspace, contract.target)
    if not target.is_file():
        return ""
    return target.read_bytes().decode("utf-8", "surrogateescape")


def _as_sent(prompt: WorkerPrompt) -> list[dict[str, str]]:
    ""
    messages: list[dict[str, str]] = []
    if prompt.system:
        messages.append({"role": "system", "content": prompt.system})
    messages.append({"role": "user", "content": prompt.user})
    return messages
