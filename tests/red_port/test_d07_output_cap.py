"""D07 — the output cap is sized for the task, and a prompt that cannot fit is refused
unspent.

``limits.max_output_tokens`` defaults to 1024 for every task type
(``contract.py``'s ``LIMITS_FIELDS``), which is the same number for a one-line
docstring and for a function written from nothing. One of those two is wrong, and
which one is wrong changes with the day: too small truncates a reply into a named
failure that costs an attempt, too large steals context from the prompt that would
have made the reply right. A cap that does not know what it is capping cannot be
both.

Three statements, and the second exists to make the first honest.

*A small task type is capped lower than a large one* is asserted on two contracts
that differ in exactly one byte of YAML — the task type — so the only explanation
for a difference is the task type. Asserting a specific number for a specific type
would freeze a table that the port should be free to measure and re-measure; the
ordering is the requirement, the numbers are not.

*The cap is deterministic* would be satisfied by today's flat 1024, which is why it
is not asserted alone. Stability is asserted across repeated loads **and across
separate processes with different hash seeds** — dict iteration order is exactly how
a table-driven cap acquires a per-process wobble, and an in-process loop would never
see it — and then, in the same test, that the caps are not all one value. Together
they say what is actually required: the cap varies with its inputs and with nothing
else. Apart, each is passed by a bug the other catches.

*A contract that cannot fit is refused before dispatch* is asserted on a returned
refusal rather than a raised one, and on a value produced from the contract and a
window alone: nothing here has a backend to reach, so a refusal that arrives at all
arrives at zero spend. The refusal must name the budget it enforced — a caller
handed a bare falsy result cannot tell "your prompt is too big for this rung" from
"this rung is fine" and cannot tell either from "the check was not run", and the
first of those is repairable by re-decomposing while the others are not.

That test also pins :data:`~mcgyvr.gate.preflight.ESTIMATE_RESERVE`. mcgyvr charges a
measured 32% against the model-free estimator's under-counting tail (CLM-0011); the
ported budget check must inherit that reserve rather than a cheerier one, so the
prompt it is given fits comfortably on a raw count and only fails once the reserve is
applied. A budget check written against the raw estimate would pass every other
assertion in this file and quietly regress the one piece of this lever mcgyvr already
does better than the code it is being ported from.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from mcgyvr.contract import loads
from mcgyvr.gate.preflight import ESTIMATE_RESERVE
from mcgyvr.orchestrator.read import estimate_tokens
from tests.red_port.conftest import required

BEHAVIOR = (
    "refuse a contract whose prompt plus its own output cap cannot fit the rung's "
    "context window, before anything is dispatched"
)

# Identical in every field a cap could plausibly depend on except the task type,
# so a difference between two loads of it has exactly one available cause.
CONTRACT = """
id: cap-probe
task_type: {task_type}
task: Do the one thing this contract describes.
target: src/pkg/fetch.py
stop_conditions:
  - The intended behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

SMALL = "docstring"
LARGE = "function_implementation"


def _cap(task_type: str) -> int:
    """The output cap a contract of this task type carries when it declares none."""
    return loads(CONTRACT.format(task_type=task_type)).limits.max_output_tokens


def _cap_in_a_fresh_process(task_type: str, hash_seed: str) -> int:
    """The same cap, read by a process that ordered its dicts differently."""
    program = (
        "from mcgyvr.contract import loads;"
        f"print(loads({CONTRACT.format(task_type=task_type)!r}).limits.max_output_tokens)"
    )
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    done = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return int(done.stdout.strip())


def _budget_check() -> Any:
    return required(
        BEHAVIOR,
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_fits"]
            ).check_contract_fits
        ),
    )


def test_a_small_task_type_is_capped_lower_than_a_large_one() -> None:
    """A docstring needs fewer output tokens than a function written from nothing.

    The two contracts differ only in ``task_type``, so an equal cap is not a
    coincidence to be explained — it is a cap that ignores what it is capping.
    """
    small, large = _cap(SMALL), _cap(LARGE)

    assert small < large, (
        f"{SMALL} is capped at {small} tokens and {LARGE} at {large}: "
        f"the cap does not vary with the task it is capping"
    )


def test_the_cap_is_the_same_every_time_and_is_not_the_same_for_everything() -> None:
    """Stable across runs, and stable because it is derived — not because it is a
    constant.

    Both halves are here on purpose. Stability alone is passed by today's flat
    default; variation alone is passed by a cap that reshuffles with dict order
    between processes. A cap is a budget, and a budget that moves between two runs
    of the same contract makes every refusal downstream unreproducible.
    """
    caps = {
        task_type: _cap(task_type) for task_type in (SMALL, LARGE, "type_annotation")
    }

    for task_type, first in caps.items():
        repeated = {_cap(task_type) for _ in range(20)}
        assert repeated == {first}, (
            f"{task_type} cap wandered within one process: {repeated}"
        )
        for seed in ("0", "1", "12345"):
            fresh = _cap_in_a_fresh_process(task_type, seed)
            assert fresh == first, (
                f"{task_type} cap is {first} here and {fresh} under "
                f"PYTHONHASHSEED={seed}: "
                f"the cap depends on something other than the contract"
            )

    assert len(set(caps.values())) > 1, (
        f"every task type is capped at the same number ({caps}): the cap is stable "
        f"only because it is a constant"
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
    contract = loads(CONTRACT.format(task_type=LARGE))
    cap = contract.limits.max_output_tokens

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
