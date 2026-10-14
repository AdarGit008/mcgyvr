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
# the estimate. Measured, not chosen: the lab's token-estimator measurement
# puts the estimator's 5th-percentile error at -31.1% on the worst of the
# three distinct
# vocabularies the shipped capability table's models use (DeepSeek-Coder-V2),
# over 2,387 units of the text production actually asks it to count. Rounded up
# to the next whole percent, and *only* the under-estimating tail matters here:
# over-estimation costs context, under-estimation costs a rejected request, and
# a reserve is protection against the second.
#
# It leaves a stated ~5% residual rather than an unquantified one, which is the
# improvement — a hard cap enforced by an unmeasured proxy could not say which
# way it was failing. Re-derive with the lab's token measurement instrument.
ESTIMATE_RESERVE = 0.32


class ServingWindow(Protocol):
    """What this module needs of the thing a rung resolves to, and no more.

    Structural rather than :class:`mcgyvr.local_pool.Endpoint` itself, because
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

    @property
    def output_tokens(self) -> int | None:
        """Room this rung's replies are given, or ``None`` when it declared none.

        A ceiling on the contract's cap, beside the window (:class:`UnitCeiling`)
        — never a number sent in its place. Still not a way to dispatch — it is
        a number, like the window beside it.
        """

    @property
    def output_ceiling(self) -> int | None:
        """The most room a reply on this rung is given whatever else was
        declared, or ``None`` when nothing bounds it. Carried by a rung that
        stands in for another unit and declares nothing of its own: a bound,
        read after the contract's cap, that can only lower it."""


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
    is charged :data:`ESTIMATE_RESERVE` on top of itself, because the proxy
    under-counts more often than it over-counts and the two directions are not
    interchangeable: over-estimation costs context, under-estimation ships a
    prompt the backend then rejects. A count from a real tokenizer is exact and
    reserves nothing.

    Either way the issue names which count it enforced with, so a rejection can
    be attributed to the proxy rather than to the prompt.
    """
    budget = context_window - output_reserve
    charged = _charged(prompt_tokens, counted_by)
    if charged <= budget:
        return None
    basis = (
        f"{prompt_tokens} estimated tokens, charged as {charged} to reserve "
        f"{ESTIMATE_RESERVE:.0%} for the estimator's measured error"
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
    cap: int | None = None,
) -> PreflightIssue | None:
    """Refuse a contract whose prompt and its own reply cannot share a window.

    ``cap`` is the reply the window must hold room for, and ``None`` means the
    contract's own ``limits.max_output_tokens`` — what every caller that
    reaches this without a rung in hand gets. A contract whose reply is
    uncapped (a raw-text reply) has ``limits.max_output_tokens`` of ``None``,
    so ``None`` also resolves to reserving nothing for output. A caller that
    *has* a rung passes :func:`reply_cap`'s answer, because the number
    reserved here has to be the number dispatched: reserving the contract's
    cap and sending a larger one from the rung is a fit check that passes on a
    request the window cannot hold.

    The contract already states how large its reply may be
    (``limits.max_output_tokens``), so whether the two fit together is
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
    declared = contract.limits.max_output_tokens if cap is None else cap
    reserve = declared if declared is not None else 0
    does_not_fit = check_prompt_fits(
        estimated,
        context_window,
        reserve,
    )
    if does_not_fit is not None:
        # The harder failure is reported first and alone. A contract that
        # cannot fit at all is not also usefully described as claiming too
        # large a share: one of those is fixed by re-decomposing and the other
        # might be fixed by re-declaring, and naming both invites the second.
        return does_not_fit
    share, declared_by = held_share(
        contract.limits.max_window_fraction, default_fraction
    )
    return check_window_fraction(
        _charged(estimated, TokenCount.ESTIMATE) + reserve,
        context_window,
        share,
        declared_by=declared_by,
    )


#: Who declared the share a contract is held to, as a refusal names it. The
#: fix lives in a different file for each — the contract's ``limits`` or the
#: run's config — so a refusal that did not say which would send the operator
#: to a key that may not be set.
CONTRACT_SHARE = "the contract's own `limits.max_window_fraction`"
RUN_SHARE = "the run's `max_window_fraction` (config)"
#: Both, when they allow the same share: raising either alone frees nothing.
BOTH_SHARES = f"{CONTRACT_SHARE} and {RUN_SHARE}"


def held_share(
    contract_share: float | None, run_share: float | None
) -> tuple[float | None, str]:
    """The share a contract is held to, and who declared it.

    The stricter of the two (owner ruling, after #621): the run's share is a
    hard ceiling that a contract cannot raise, and a contract may still hold
    itself to less. Either may be unset, and an unset one bounds nothing, so
    the other applies alone; both unset is ``None``, no share enforced. Two
    equal shares are both named, because the refusal says what to raise and
    raising one of them alone would not let the contract through.
    """
    if contract_share is None:
        return run_share, RUN_SHARE
    if run_share is None or contract_share < run_share:
        return contract_share, CONTRACT_SHARE
    if run_share < contract_share:
        return run_share, RUN_SHARE
    return contract_share, BOTH_SHARES


def check_window_fraction(
    contract_tokens: int,
    context_window: int,
    fraction: float | None,
    *,
    declared_by: str = RUN_SHARE,
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
    decides the fix: a contract to re-decompose, or a share to re-declare. So
    is ``declared_by`` — :data:`CONTRACT_SHARE`, :data:`RUN_SHARE` or
    :data:`BOTH_SHARES`, as :func:`held_share` chose — because a share to
    re-declare is re-declared where it was declared.
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
    allow = "allow" if declared_by == BOTH_SHARES else "allows"
    return PreflightIssue(
        "window-share",
        f"contract claims {claimed:.2f} of the rung's window "
        f"({contract_tokens} tokens of {context_window}), but {declared_by} "
        f"{allow} {fraction:.2f}. Either decompose into smaller contracts or "
        f"raise {declared_by}",
    )


@dataclass(frozen=True)
class ReplyCap:
    """The output cap a dispatch sends, and the sentence saying where it came from.

    ``tokens`` is ``None`` for an uncapped request. ``basis`` is what the
    journal row records beside the number (``cap_basis``), so a reply cut at
    the cap can be traced to the term that sized it without re-deriving it.
    """

    tokens: int | None
    basis: str


@dataclass(frozen=True)
class UnitCeiling:
    """The most room one unit can give a reply beside one prompt, and its terms.

    Owner decision (2026-10-14, e2e run 3 T1): the prompt is a constant and the
    output cap is what adjusts, so the ceiling is what the unit's served
    ``window`` leaves once the prompt is charged — ``window - prompt`` — where
    the window is known; the unit's ``output_tokens`` where only that is set (a
    hosted unit, whose window setup cannot read); the smaller of the two where
    both are. Neither known is ``None``: a ceiling nobody stated, which
    :func:`check_cap_within_ceiling` refuses rather than guesses.

    ``prompt`` is charged as every window check charges it (:func:`_charged`:
    the model-free estimate plus :data:`ESTIMATE_RESERVE`), so a cap within
    this ceiling is a cap the fit checks agree fits.
    """

    unit: str
    window: int | None
    prompt: int
    output_tokens: int | None

    @property
    def room(self) -> int | None:
        """What the window leaves beside the prompt, or ``None`` with no window."""
        return None if self.window is None else self.window - self.prompt

    @property
    def tokens(self) -> int | None:
        """The ceiling: the smaller of the known terms, or ``None`` for neither."""
        known = [n for n in (self.room, self.output_tokens) if n is not None]
        return min(known) if known else None

    @property
    def terms(self) -> str:
        """The terms the ceiling was reached from, in the words a refusal uses."""
        said = []
        if self.window is not None:
            said.append(
                f"its {self.window}-token window less this prompt's "
                f"{self.prompt} tokens as charged leaves {self.room}"
            )
        if self.output_tokens is not None:
            said.append(f"its `output_tokens` is {self.output_tokens}")
        return "; ".join(said)


def unit_ceiling(rung: ServingWindow, prompt: str) -> UnitCeiling:
    """The ceiling of a reply on ``rung`` beside the assembled ``prompt``."""
    # Imported here for the reason `check_contract_fits` imports it.
    from mcgyvr.orchestrator.read import estimate_tokens

    return UnitCeiling(
        unit=rung.source,
        window=rung.context_window,
        prompt=_charged(estimate_tokens(prompt), TokenCount.ESTIMATE),
        output_tokens=rung.output_tokens,
    )


def reply_cap(contract: Contract, rung: ServingWindow) -> int | None:
    """The output cap that will actually be sent: :func:`sized_reply_cap`'s number."""
    return sized_reply_cap(contract, rung).tokens


def sized_reply_cap(
    contract: Contract,
    rung: ServingWindow,
    *,
    prompt: str | None = None,
) -> ReplyCap:
    """The output cap that will actually be sent, and the sentence saying why.

    The contract's ``limits.max_output_tokens``, exactly. Owner decision
    (2026-10-14, e2e run 3 T1): the contract's cap is what the work is worth,
    written by whoever wrote the work, and a unit's ``output_tokens`` is how
    much room its backend has — a ceiling (:class:`UnitCeiling`), never a
    number that replaces the contract's. It used to replace it, and a contract
    capped at 16 was sent the 32768 ``setup --api`` writes on a hosted unit.
    Whether the cap is within the ceiling is :func:`check_cap_within_ceiling`'s
    question, asked before dispatch; a cap above it is refused by name rather
    than lowered to fit, because a lowered cap is a number nobody chose. Given
    the ``prompt``, the basis says what the ceiling was, for the journal.

    A contract that states no cap is sent none: a raw connection (``chat``,
    ``agent``) and a ``media_artifact`` reply carry none, and a model-written
    ``code`` contract that states none never reaches here, because
    :func:`check_cap_stated` refuses it before dispatch.

    **A carried ceiling is the one place the lower of two numbers is sent.** A
    rung may carry an ``output_ceiling``
    (:attr:`mcgyvr.local_pool.Endpoint.output_ceiling`): the room the local
    unit gives its replies, on another person's unit that stands in for it and
    declares nothing of its own. That bound is not the product's harness and
    is kept as it was: the contract's cap is sent, or the ceiling where that is
    smaller, and a contract with no cap is sent the ceiling, so another
    person's unit is not asked for a reply nothing bounds — a raw connection
    included. Where the local unit declares none either, nothing is sent.
    """
    declared = contract.limits.max_output_tokens
    ceiling = rung.output_ceiling
    riding = f"the ceiling of the unit rung {rung.source!r} stands in for"
    if declared is None:
        if ceiling is None:
            return ReplyCap(None, "uncapped: the contract states no cap")
        return ReplyCap(ceiling, f"uncapped contract, sent {riding}")
    basis = "the contract's limits.max_output_tokens"
    if prompt is not None and contract.needs_output_cap:
        room = unit_ceiling(rung, prompt).tokens
        if room is not None:
            basis += f", within unit {rung.source!r}'s ceiling of {room}"
    if ceiling is not None and ceiling < declared:
        return ReplyCap(ceiling, f"{basis}; bounded by {riding}")
    return ReplyCap(declared, basis)


def check_cap_stated(contract: Contract) -> PreflightIssue | None:
    """Refuse a model-written ``code`` contract that states no output cap.

    Owner decision (2026-10-14, e2e run 3 T1): the work mcgyvr's harness runs
    is bounded by a number somebody wrote, and the contract's is what the work
    is worth — only its author can say it, so nothing here invents one. The
    contract still loads, and ``mcgyvr contract`` says what it is missing; this
    is the refusal ``mcgyvr run`` makes before any model is called.
    """
    if not contract.needs_output_cap or contract.limits.max_output_tokens is not None:
        return None
    return PreflightIssue(
        "output-cap-unstated",
        f"contract {contract.id!r} is model-written {contract.task_type!r} work "
        f"and states no limits.max_output_tokens, so no model is called for it. "
        f"State limits.max_output_tokens: what the reply is worth, in output "
        f"tokens, within the ceiling of the unit it runs on",
    )


def check_cap_within_ceiling(
    contract: Contract, rung: ServingWindow, prompt: str
) -> PreflightIssue | None:
    """Refuse a contract cap the unit cannot give room for beside this prompt.

    The two refusals of the cap model (owner, 2026-10-14): a unit that states
    no ceiling at all — neither the ``window`` it serves nor the
    ``output_tokens`` its replies are given — and a contract cap above the
    ceiling the unit does state (:class:`UnitCeiling`). Both name what to set:
    a ceiling nobody stated is not guessed, and a cap above the ceiling is not
    lowered to fit, because either would send a number nobody chose. A
    contract that states no cap is :func:`check_cap_stated`'s to refuse.

    A rung that states neither but carries an ``output_ceiling`` — another
    person's unit standing in for a local one — is bounded by that, as it
    always was (:func:`sized_reply_cap`), and is not refused here.
    """
    cap = contract.limits.max_output_tokens
    if cap is None:
        return None
    ceiling = unit_ceiling(rung, prompt)
    unit = ceiling.unit
    if ceiling.tokens is None and rung.output_ceiling is not None:
        return None
    if ceiling.tokens is None:
        return PreflightIssue(
            "unit-ceiling-unknown",
            f"unit {unit!r} states neither the window it serves nor the room "
            f"its replies are given, so contract {contract.id!r}'s "
            f"limits.max_output_tokens: {cap} has no ceiling to be held to and "
            f"no model is called. Set `units.{unit}.window` (the context "
            f"length its backend serves, read off the running process) or "
            f"`units.{unit}.output_tokens`",
        )
    if cap <= ceiling.tokens:
        return None
    return PreflightIssue(
        "output-cap",
        f"contract {contract.id!r} states limits.max_output_tokens: {cap}, but "
        f"unit {unit!r} has a ceiling of {ceiling.tokens} for this prompt "
        f"({ceiling.terms}). Lower the contract's limits.max_output_tokens to "
        f"{max(ceiling.tokens, 0)} or less, decompose the work so its prompt is "
        f"smaller, or run it on a unit that serves more",
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
    supplied — ``context.max_input_tokens``, a number an operator typed into a
    file about the work. A contract measured only against the window it was
    written for fails in two opposite ways: one declaring more than the rung
    serves is truncated by the engine at a boundary nobody chose, and one
    declaring less is refused on a rung that had room. This check measures it
    against the window it reaches.

    Three questions, asked in this order because they have different repairs:

    1. **What the contract declared it may read**, against what the rung
       serves. A ceiling larger than the window is a promise the rung cannot
       keep whatever this particular prompt turned out to weigh, and the
       refusal names the *rung's* number — the operator's next move is to
       decompose against the real window, and a message quoting the contract's
       own ceiling tells them the opposite.

    2. **What the reply is given room for.** For model-written ``code``, the
       contract's cap against the unit's ceiling
       (:func:`check_cap_within_ceiling`): the room the window leaves beside
       this prompt, or the unit's ``output_tokens``, or the smaller of the two
       — and a unit that states neither is refused, since a ceiling nobody
       stated cannot be checked. For any other reply, the cap that will be
       sent (:func:`reply_cap`) against the whole window: a cap as large as
       the window has left nothing for a prompt whatever the prompt weighs.
       Either is a number to re-declare rather than a contract to
       re-decompose. A prompt that alone fills the window is not asked this:
       that is a contract too big for the rung, and question 3 says so rather
       than blaming the cap.

    3. **What the prompt actually weighs**, through :func:`check_contract_fits`
       — the prompt beside the cap, and the share of the window the two claim
       together (:func:`held_share`).

    A rung that declared no window enforces questions 1 and 3 on nothing, the
    same answer and for the same reason as ``fraction=None`` in
    :func:`check_window_fraction`: the number would have to be invented.
    Declaring ``window`` on the unit — which setup reads off the running
    backend — is what turns them on. Question 2 still holds model-written
    ``code`` to the unit's ``output_tokens`` there, and refuses a unit that
    states neither.
    """
    window = rung.context_window
    harnessed = contract.needs_output_cap
    if window is not None and contract.max_input_tokens > window:
        return PreflightIssue(
            "rung-window",
            f"the contract declares it may read {contract.max_input_tokens} "
            f"tokens, but rung {rung.source!r} serves a window of {window}. "
            f"Decompose against {window}, or point the rung at a machine that "
            f"serves more — a ceiling the rung cannot keep is truncation at a "
            f"boundary nobody chose",
        )
    if harnessed:
        cap = contract.limits.max_output_tokens
        room = unit_ceiling(rung, prompt).room
        if room is None or room > 0:
            over = check_cap_within_ceiling(contract, rung, prompt)
            if over is not None:
                return over
    else:
        cap = reply_cap(contract, rung)
        if window is not None and cap is not None and cap >= window:
            return PreflightIssue(
                "output-cap",
                f"the contract declares a reply of {cap} tokens, but rung "
                f"{rung.source!r} serves a window of {window}, leaving nothing "
                f"for a prompt. Lower the contract's `limits.max_output_tokens`, "
                f"or point the rung at a machine that serves more — a reply cap "
                f"the window cannot hold is the truncation a per-rung cap "
                f"exists to prevent",
            )
    if window is None:
        return None
    return check_contract_fits(
        contract, prompt, window, default_fraction=default_fraction, cap=cap
    )
