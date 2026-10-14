"""D07 — the output cap is the one the contract states, and a prompt that cannot fit
is refused unspent.

``limits.max_output_tokens`` has no default and is never derived: owner
decision (2026-10-14, e2e run 3 T1) — a model-written ``code`` contract states
what its reply is worth, and one that states nothing is refused at dispatch
(``tests/test_a_code_contract_states_its_cap_or_is_refused_at_dispatch.py``).
The sizing this file used to pin, a cap derived from the contract's evidence,
is gone with that decision.

*A contract that cannot fit is refused before dispatch* is asserted on a
returned refusal rather than a raised one, and on a value produced from the
contract and a window alone: nothing here has a backend to reach, so a refusal
that arrives at all arrives at zero spend. The refusal must name the budget it
enforced — a caller handed a bare falsy result cannot tell "your prompt is too
big for this rung" from "this rung is fine" and cannot tell either from "the
check was not run", and the first of those is repairable by re-decomposing
while the others are not.

That test also pins :data:`~mcgyvr.gate.preflight.ESTIMATE_RESERVE`, the reserve
charged against the model-free estimator's under-counting tail: the prompt it is
given fits comfortably on a raw count and only fails once the reserve is
applied. A budget check written against the raw estimate would pass every other
assertion in this file.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.contract import loads
from mcgyvr.gate.preflight import ESTIMATE_RESERVE
from mcgyvr.orchestrator.read import estimate_tokens
from tests.red_port.conftest import required

BEHAVIOR = (
    "refuse a contract whose prompt plus its own output cap cannot fit the rung's "
    "context window, before anything is dispatched"
)

#: A model-written change that states its cap, as every one must.
CONTRACT = """
id: cap-probe
task_type: code
task: Do the one thing this contract describes.
target: src/pkg/fetch.py
stop_conditions:
  - The intended behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/**/*.py"]
"""


def _budget_check() -> Any:
    return required(
        BEHAVIOR,
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_fits"]
            ).check_contract_fits
        ),
    )


def test_a_contract_that_cannot_fit_its_window_is_refused_at_zero_spend() -> None:
    """The refusal is a value, it names the budget, and it charges the measured reserve.

    Sized so the prompt fits the window on a raw estimate and does not fit once
    mcgyvr's 32% estimator reserve is charged: a budget check that dropped the
    reserve would let this prompt through, and every other assertion here would
    still pass while the rung rejected the request instead.

    A contract that comfortably fits is checked in the same test, because a check
    that refuses everything satisfies a refusal assertion perfectly.
    """
    check = _budget_check()
    contract = loads(CONTRACT)
    cap = contract.limits.max_output_tokens
    assert cap == 1024

    prompt = "x" * (4 * 4000)
    estimated = estimate_tokens(prompt)
    charged = int(estimated * (1 + ESTIMATE_RESERVE))
    window = estimated + cap + 16
    assert charged + cap > window, "fixture no longer straddles the reserve"

    refused = check(contract=contract, prompt=prompt, context_window=window)

    assert refused is not None, (
        f"a prompt of ~{estimated} estimated tokens plus a {cap}-token cap was allowed "
        f"into a {window}-token window: the {ESTIMATE_RESERVE:.0%} estimator reserve "
        f"was "
        f"not charged"
    )
    said = str(refused)
    assert str(window) in said and str(cap) in said, (
        f"the refusal must name the window it enforced and the output it reserved, "
        f"said: {said!r}"
    )

    fits = check(contract=contract, prompt=prompt, context_window=window * 4)
    assert fits is None, f"a prompt with room to spare was refused anyway: {fits}"
