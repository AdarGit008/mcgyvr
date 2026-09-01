"""Pre-flight: what must be true before the first worker attempt.

Some failures are not the worker's and would look identical on every rung of
the ladder — a starting tree that was already dirty, an acceptance suite that
already failed before anything was changed, a prompt too large to fit the
rung's context window at all. Catching these once, before any attempt, means
they consume no attempt and are named as what they are: orchestration errors,
distinct from a worker's rejected change.

A :class:`PreflightIssue` is deliberately *not* a
:class:`~mcgyvr.gate.findings.Finding`.
A finding says the worker's change was not acceptable; an issue says the run
should not have started. Conflating them would charge the worker for the
environment's faults.

The dirty-tree check only reads: a starting tree that was already dirty is
reported, never destroyed, so a user is never surprised by lost work.
"""

from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mcgyvr.contract import Contract


class TokenCount(StrEnum):
    """How a prompt's token count was arrived at. Reported, never assumed.

    The distinction is the whole of #117's second acceptance bullet: a rejection
    has to be attributable to the proxy rather than to the prompt, and it cannot
    be if the check does not know which it was handed.
    """

    ESTIMATE = "estimate"
    """The model-free proxy, :func:`~mcgyvr.orchestrator.read.estimate_tokens`."""

    TOKENIZER = "tokenizer"
    """A real tokenizer's count. Exact, so nothing is reserved against it."""


# How much room a proxy count must leave for its own error, as a fraction of
# the estimate. Measured, not chosen: CLM-0011 puts the estimator's 5th-
# percentile error at -31.1% on the worst of the three distinct vocabularies
# the shipped capability table's models use (DeepSeek-Coder-V2), over 2,387
# units of the text production actually asks it to count. Rounded up to the
# next whole percent, and *only* the under-estimating tail matters here:
# over-estimation costs context, under-estimation costs a rejected request, and
# a reserve is protection against the second.
#
# It leaves a stated ~5% residual rather than an unquantified one, which is the
# improvement — a hard cap enforced by an unmeasured proxy could not say which
# way it was failing. Re-derive with `tools/tokens/measure.py`.
ESTIMATE_RESERVE = 0.32


@dataclass(frozen=True)
class PreflightIssue:
    """A precondition that failed before any attempt was spent."""

    reason: str
    message: str

    def __str__(self) -> str:
        return f"preflight[{self.reason}]: {self.message}"


def check_clean_tree(repo: str | os.PathLike[str]) -> PreflightIssue | None:
    """Report — never mutate — a working tree that is dirty before the worker runs.

    A dirty start means the change set could not cleanly attribute the worker's
    diff, and it also risks the user's uncommitted work. We name the offending
    paths and stop; we do not stash, reset or clean.
    """
    root = Path(repo)
    proc = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        return PreflightIssue("not-a-repo", f"cannot read git status: {detail}")

    entries = [e for e in proc.stdout.split(b"\x00") if e]
    if not entries:
        return None
    paths = [e[3:].decode("utf-8", "surrogateescape") for e in entries]
    shown = ", ".join(paths[:5])
    more = "" if len(paths) <= 5 else f" (+{len(paths) - 5} more)"
    return PreflightIssue(
        "dirty-tree",
        f"working tree has uncommitted changes before the attempt: {shown}{more}",
    )


def check_prompt_fits(
    prompt_tokens: int,
    context_window: int,
    output_reserve: int = 0,
    *,
    counted_by: TokenCount = TokenCount.ESTIMATE,
) -> PreflightIssue | None:
    """Reject a prompt that cannot fit its rung's context window before any spend.

    ``output_reserve`` is the room the rung must keep for the worker's reply;
    a prompt that leaves less than that has no chance of a usable completion,
    so it is a routing error to send it rather than a worker failure to expect.

    ``counted_by`` says where ``prompt_tokens`` came from, and it changes the
    arithmetic rather than only the wording. A count from the model-free proxy
    is charged :data:`ESTIMATE_RESERVE` on top of itself, because CLM-0011
    measured the proxy under-counting more often than it over-counts and the
    two directions are not interchangeable: over-estimation costs context,
    under-estimation ships a prompt the backend then rejects. A count from a
    real tokenizer is exact and reserves nothing.

    Either way the issue names which count it enforced with, so a rejection can
    be attributed to the proxy rather than to the prompt.
    """
    budget = context_window - output_reserve
    charged = (
        math.ceil(prompt_tokens * (1 + ESTIMATE_RESERVE))
        if counted_by is TokenCount.ESTIMATE
        else prompt_tokens
    )
    if charged <= budget:
        return None
    basis = (
        f"{prompt_tokens} estimated tokens, charged as {charged} to reserve "
        f"{ESTIMATE_RESERVE:.0%} for the estimator's measured error (CLM-0011)"
        if counted_by is TokenCount.ESTIMATE
        else f"{prompt_tokens} tokens, counted exactly"
    )
    return PreflightIssue(
        "prompt-too-large",
        f"prompt is {basis}, but the rung allows {budget} "
        f"({context_window} window minus {output_reserve} reserved for output)",
    )


def check_contract_fits(
    contract: Contract, prompt: str, context_window: int
) -> PreflightIssue | None:
    """Refuse a contract whose prompt and its own reply cannot share a window.

    The contract already states how large its reply may be
    (``limits.max_output_tokens``, sized to the task type by
    :func:`~mcgyvr.contract.output_cap`), so whether the two fit together is
    knowable from the contract, the prompt text and the rung — with no backend
    reached and no attempt spent. A refusal that arrives here therefore arrives
    at zero spend, which is what makes it worth having: the same request sent
    is a rung's tokens burnt for a rejection that was certain before it left.

    Returned rather than raised, and naming both halves of the budget it
    enforced, because the three answers a caller has to tell apart — "this
    prompt is too big for this rung", "this rung is fine", "the check did not
    run" — are one repairable case and two that are not. Only the first is
    fixed by re-decomposing into smaller contracts, and a bare falsy result
    would hide which one happened.

    The verifier's copy of this question — the original file, plus a change no
    larger than the cap, against the verifier's own window — is the same
    arithmetic, and is deliberately not written here: nothing in mcgyvr yet
    declares a verifier's context window, and a number invented for it would be
    exactly the unsourced constant this project refuses elsewhere.
    """
    # Imported, rather than re-derived, because `estimate_tokens` is the one
    # proxy in the system: a second copy of "four characters to a token" here
    # could drift from the one the read plan and the decomposer already spend
    # against, and two budgets sized "the same way" would then disagree.
    #
    # Imported here rather than at module scope because the two packages point
    # at each other — `mcgyvr.orchestrator`'s init builds the decomposer, which
    # imports the gate's adapters — so at module scope every `import
    # mcgyvr.gate` would build the whole orchestrator to reach one arithmetic
    # helper.
    from mcgyvr.orchestrator.read import estimate_tokens

    return check_prompt_fits(
        estimate_tokens(prompt),
        context_window,
        contract.limits.max_output_tokens,
    )
