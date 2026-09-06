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
from typing import Protocol

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


class ServingWindow(Protocol):
    """What this module needs of the thing a rung resolves to, and no more.

    Structural rather than :class:`mcgyvr.pool.Endpoint` itself, because
    ``tests/test_pool.py`` makes importing that type the definition of reaching
    below the seam and this module is above it. The argument the guard asks for
    is that the dependency is real, not that the spelling is clever: what a
    contract is checked against is a window and a name to put in the refusal,
    and neither is a way to dispatch. A base URL, a protocol or a credential
    would be, and none of them is named here — so an ``Endpoint`` satisfies
    this and nothing in this module can send a request with one.

    Read-only on purpose: the endpoint is a frozen dataclass and this is a
    question asked of it, never a place to write a window back.
    """

    @property
    def source(self) -> str:
        """The declared source name, for a refusal that says which rung."""

    @property
    def context_window(self) -> int | None:
        """Tokens served in one request, or ``None`` when nobody declared it."""


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
    charged = _charged(prompt_tokens, counted_by)
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


def _charged(prompt_tokens: int, counted_by: TokenCount) -> int:
    """What a prompt costs against a window, given how it was counted.

    One function because two callers charge the same prompt — the fit check
    and the share check — and a prompt charged one way for "does it fit" and
    another for "how much of the window is that" would be two budgets sized
    the same way that disagree.
    """
    if counted_by is TokenCount.ESTIMATE:
        return math.ceil(prompt_tokens * (1 + ESTIMATE_RESERVE))
    return prompt_tokens


def check_contract_fits(
    contract: Contract,
    prompt: str,
    context_window: int,
    *,
    default_fraction: float | None = None,
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

    estimated = estimate_tokens(prompt)
    does_not_fit = check_prompt_fits(
        estimated,
        context_window,
        contract.limits.max_output_tokens,
    )
    if does_not_fit is not None:
        # The harder failure is reported first and alone. A contract that
        # cannot fit at all is not also usefully described as claiming too
        # large a share: one of those is fixed by re-decomposing and the other
        # might be fixed by re-declaring, and naming both invites the second.
        return does_not_fit
    # The contract's own share wins where it stated one, and the caller's
    # standing default applies where it did not. Never the other way round: a
    # contract that declared a share declared it about itself, and a config
    # that overrode it would make the contract's own text untrue.
    share = contract.limits.max_window_fraction
    if share is None:
        share = default_fraction
    return check_window_fraction(
        _charged(estimated, TokenCount.ESTIMATE) + contract.limits.max_output_tokens,
        context_window,
        share,
    )


def check_window_fraction(
    contract_tokens: int, context_window: int, fraction: float | None
) -> PreflightIssue | None:
    """Refuse a contract that claims more of a rung's window than the run allows.

    A different question from :func:`check_prompt_fits`, which asks whether a
    prompt and its reply can fit at all. This asks how much of the window one
    contract may *want*. The two come apart at the top of the range: a contract
    that fits with nothing to spare has left the rung no room to hold anything
    beside it and no room to absorb an estimate that ran long, and "it fits"
    cannot see either.

    ``fraction`` is the run's, not this module's. ``None`` means the run
    declared no share and none is enforced — deliberately not the same as
    ``1.0``, which is a declaration that a contract may have the whole window.
    A default invented here would bound every install that never asked to be
    bounded, with a number nobody measured; the project's rule against
    unsourced constants is what makes the absence an answer rather than a gap.

    ``contract_tokens`` is the contract's whole footprint — the prompt as
    charged, plus the reply it declared room for — because that is the thing
    that occupies the window. Charging the prompt alone would let a contract
    with a large ``max_output_tokens`` pass a share it will exceed the moment
    the reply arrives.

    Both fractions are named in the refusal, because which one is wrong
    decides the fix: a contract to re-decompose, or a share to re-declare.
    """
    if fraction is None:
        return None
    if context_window <= 0:
        # Not a division. A rung with no window is a routing error, and
        # dividing by it would either raise here or report an infinity that
        # reads as a very greedy contract.
        return PreflightIssue(
            "window-share",
            f"the rung declares a context window of {context_window}, so no "
            f"share of it can be computed; a rung with no window is a routing "
            f"error rather than a contract that is too large",
        )
    claimed = contract_tokens / context_window
    if claimed <= fraction:
        return None
    return PreflightIssue(
        "window-share",
        f"contract claims {claimed:.2f} of the rung's window "
        f"({contract_tokens} tokens of {context_window}), but this run allows "
        f"{fraction:.2f}. Either decompose into smaller contracts or raise "
        f"the share this run allows",
    )


def check_contract_against_rung(
    contract: Contract,
    prompt: str,
    *,
    rung: ServingWindow,
    default_fraction: float | None = None,
) -> PreflightIssue | None:
    """Refuse a contract that cannot fit the window of the rung it will reach.

    Every other budget in this module is spent against a number the *caller*
    supplied, and until this existed the only supplier was the contract:
    ``context.max_input_tokens``, a number an operator typed into a file about
    the work. So a contract was measured against the window it was written for
    and never against the window it reaches, and the two failures that follow
    are opposite. A contract declaring more than the rung serves passes the
    check and is truncated by the engine at a boundary nobody chose. A contract
    declaring less is refused on a rung that had room. Which one happens is
    decided by the file rather than by the machine that will answer.

    Two questions, asked in this order because they have different repairs:

    1. **What the contract declared it may read**, against what the rung
       serves. A ceiling larger than the window is a promise the rung cannot
       keep whatever this particular prompt turned out to weigh, and the
       refusal names the *rung's* number — the operator's next move is to
       decompose against the real window, and a message quoting the contract's
       own 32768 tells them the opposite. Only the input ceiling is compared:
       a contract may declare a reply that, added to a full read, would exceed
       the window, and whether those two actually collide is question 2's,
       measured on the prompt that exists rather than on the one the ceiling
       allows for.

    2. **What the prompt actually weighs**, through :func:`check_contract_fits`
       — which is the truncation the contract's own ceiling cannot see. A
       contract declaring a small ceiling passes question 1 and is still
       assembled into a prompt larger than the rung will hold; today that
       reaches the engine and comes back cut.

    A rung whose source declared no window enforces nothing, the same answer
    and for the same reason as ``fraction=None`` in
    :func:`check_window_fraction`: the number would have to be invented, and an
    invented window is the defect this function exists to end rather than a
    conservative default. Declaring ``context_window`` on the source is what
    turns the check on, and reading it back off the running unit is how the
    number stops being a guess.
    """
    window = rung.context_window
    if window is None:
        return None
    declared = contract.max_input_tokens
    if declared > window:
        return PreflightIssue(
            "rung-window",
            f"the contract declares it may read {declared} tokens, but rung "
            f"{rung.source!r} serves a window of {window}. Decompose against "
            f"{window}, or point the rung at a machine that serves more — a "
            f"ceiling the rung cannot keep is truncation at a boundary "
            f"nobody chose",
        )
    return check_contract_fits(
        contract, prompt, window, default_fraction=default_fraction
    )
