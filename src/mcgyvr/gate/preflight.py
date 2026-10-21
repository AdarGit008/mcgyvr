"""Pre-flight: the cheap checks a contract and its prompt pass before anything is sent.

Every check here returns a `PreflightIssue` or `None` rather than raising, so the
caller decides what a refusal costs and what class it is reported under. Nothing
here spends or writes: `check_clean_tree` reads `git status` and leaves the tree
alone, and the sizing checks count the prompt with the model-free estimator and
compare that count against what the rung serves — the window, the reply ceiling,
and the share of the window the contract and the run between them allow.
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
    """How a prompt's tokens were counted, so a refusal can say what enforced it."""

    ESTIMATE = "estimate"
    """The model-free proxy, :func:`~mcgyvr.orchestrator.read.estimate_tokens`."""

    TOKENIZER = "tokenizer"
    """A real tokenizer's count. Exact, so nothing is reserved against it."""


# `estimate_tokens` counts four characters to a token, and it under-counts on
# the worker views a prompt budget is enforced against, so an estimate is not
# the number a backend will charge for the same text. The error has been
# measured rather than assumed (CLM-0011, over 2,387 captured units), and the
# reserve below is the worst vocabulary's p05 of it, rounded up: a prompt
# counted by the estimator is charged this much on top of itself before it is
# held to a window. Only the under-counting tail is reserved, because the two
# directions are not interchangeable — over-estimating costs context that then
# goes unused, while under-estimating ships a prompt the backend refuses after
# the spend — and an exact tokenizer count is charged nothing, which is why
# `_charged` is the one place the two counts are told apart. The number is
# deliberately not a round share: a round one would be invented where a measured
# one exists, and a wider reserve would take context away from prompts the proxy
# already counts well.
ESTIMATE_RESERVE = 0.32


class ServingWindow(Protocol):
    """The part of a bound endpoint these checks read.

    A rung is judged from these numbers alone, so a pre-flight answer never
    costs a request to the backend behind it.
    """

    @property
    def source(self) -> str:
        """The rung's name, as the config and every refusal spell it."""

    @property
    def context_window(self) -> int | None:
        """Tokens the unit serves in one request, prompt and reply together.

        `None` when the unit states no window.
        """

    @property
    def output_tokens(self) -> int | None:
        """Room the unit states one reply is given; `None` if the unit states none."""

    @property
    def output_ceiling(self) -> int | None:
        """The reply ceiling a contract's cap is held to.

        `None` when nothing caps the reply.
        """


@dataclass(frozen=True)
class PreflightIssue:
    """One reason a contract or a prompt must not be sent.

    `reason` is the stable key a caller maps to its own refusal type; `message`
    is the sentence a person reads, naming the limit that was missed and the
    ways to meet it.
    """

    reason: str
    message: str

    def __str__(self) -> str:
        return f"preflight[{self.reason}]: {self.message}"


def check_clean_tree(repo: str | os.PathLike[str]) -> PreflightIssue | None:
    """The issue for a repository with uncommitted work, or `None` when it is clean.

    `git status --porcelain -z --untracked-files=all` is read, and the tree
    itself is never touched. The check exists so that an attempt starts from a
    state a gate can attribute to itself. A non-zero exit is `not-a-repo`,
    carrying git's own stderr, because a directory git cannot read is a
    different fault from a checkout with work in it. Up to five paths are named,
    with a count of the rest, so the refusal stays readable in a long-changed
    tree.
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
    """The issue for a prompt that claims more of the window than the rung leaves it.

    The budget is `context_window` less `output_reserve`, both in the rung's own
    tokens. `prompt_tokens` is put through `_charged`, so an estimate carries
    `ESTIMATE_RESERVE` and an exact tokenizer count does not, and the message
    states which of the two counts it enforced with — a rejection can then be
    attributed to the proxy rather than to the prompt.
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
    """`prompt_tokens` as the window is charged for them, by how they were counted.

    An estimate is charged `ESTIMATE_RESERVE` on top of itself, rounded up so the
    charge is never short of the reserve. A tokenizer count is exact and passes
    through unchanged.
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
    """The issue for a contract and its prompt that outgrow a rung's window.

    The prompt is counted with the model-free estimator, and the reply reserve is
    the cap the call will actually travel with: the caller's `cap` where one has
    already been narrowed to what the rung can serve, otherwise the contract's
    own `limits.max_output_tokens`. Two questions are then asked in order — the
    charged prompt plus that reserve must fit the window at all
    (`check_prompt_fits`), and the same total must not claim more of the window
    than `held_share` allows, between the contract's `limits.max_window_fraction`
    and the run's `default_fraction`. `None` means the contract fits.
    """
    # `estimate_tokens` is imported where it is used rather than at module
    # scope, so this module's import list carries no orchestrator dependency.
    # The count is model-free on purpose: pre-flight runs before any model is
    # called, so no question here may be answered by spending a request on it.
    # The reserve is taken from the cap rather than derived again, so the fit is
    # judged against the reply budget the request will be sent with. A contract
    # that states no cap and is handed none reserves nothing, which is right: it
    # also sends no cap.
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
        # Returned ahead of the share check: a total too large for the window as
        # a whole is the prompt's own failure, and reporting it as a share would
        # blame the declared fraction for a prompt that is simply bigger than
        # the rung, sending the reader off to raise the wrong number.
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


#: Which declaration may hold a contract to a share of the rung's window. The
#: contract's own `limits.max_window_fraction` and the run's
#: `max_window_fraction` from config both apply, the stricter one wins, and a
#: refusal names whichever declared it, so the number can be traced back to the
#: document that set it and raised there.
CONTRACT_SHARE = "the contract's own `limits.max_window_fraction`"
RUN_SHARE = "the run's `max_window_fraction` (config)"
#: Equal values name both, since raising either one alone would change nothing.
BOTH_SHARES = f"{CONTRACT_SHARE} and {RUN_SHARE}"


def held_share(
    contract_share: float | None, run_share: float | None
) -> tuple[float | None, str]:
    """The fraction that holds, and the declaration that set it.

    The stricter of the two wins. A contract that declares none is held to the
    run's; a contract stricter than the run keeps its own; equal values return
    that value labelled with both names, because either one alone could be
    raised without loosening anything.
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
    """The issue for a contract claiming more than `fraction` of the window.

    `contract_tokens` is the whole claim: the prompt as charged plus the reply
    reserve. `fraction` is the share `declared_by` allows, and a `None` fraction
    means no share is declared, so nothing is checked. A window of zero or less
    is a routing error rather than an oversized contract, and is reported rather
    than divided by.
    """
    if fraction is None:
        return None
    if context_window <= 0:
        # No share can be computed from a window that is not positive, and the
        # fault is the rung's declaration rather than the contract's size. It is
        # reported under the same reason so a caller needs no second mapping to
        # turn it into a refusal.
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
    """The reply cap a request is sent with, and where the number came from.

    `tokens` is `None` when nothing caps the reply, which is what a contract that
    states no cap and a rung that serves no ceiling together mean. `basis` is the
    sentence recorded beside the number, so an answer's cap can be read back
    against the limit that produced it.
    """

    tokens: int | None
    basis: str


@dataclass(frozen=True)
class UnitCeiling:
    """What one unit has room to give a reply, for a prompt already counted.

    `window` and `output_tokens` are as the unit states them, and either may be
    unknown. `prompt` is that prompt's tokens as charged, so `room` is what the
    window has left once it has been paid for.
    """

    unit: str
    window: int | None
    prompt: int
    output_tokens: int | None

    @property
    def room(self) -> int | None:
        """The window left after the prompt, or `None` when no window is stated."""
        return None if self.window is None else self.window - self.prompt

    @property
    def tokens(self) -> int | None:
        """The ceiling: the smaller of the room and the stated reply room, or `None`."""
        known = [n for n in (self.room, self.output_tokens) if n is not None]
        return min(known) if known else None

    @property
    def terms(self) -> str:
        """The stated terms behind `tokens`, in prose, for a refusal to quote."""
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
    """`rung` and `prompt` as a `UnitCeiling`, the prompt counted by the estimator.

    The count is the charged one, so the room reported is what the window has
    left once `ESTIMATE_RESERVE` has been kept back for the estimator's measured
    error — the same room the fit checks work from.
    """
    # Imported at use, as in `check_contract_fits`, so the estimator reaches this
    # module only where a ceiling is actually sized.
    from mcgyvr.orchestrator.read import estimate_tokens

    return UnitCeiling(
        unit=rung.source,
        window=rung.context_window,
        prompt=_charged(estimate_tokens(prompt), TokenCount.ESTIMATE),
        output_tokens=rung.output_tokens,
    )


def reply_cap(contract: Contract, rung: ServingWindow) -> int | None:
    """The reply cap for `contract` on `rung`, or `None` when nothing caps it.

    The number without its basis, for callers that only need to know what the cap
    is; :func:`sized_reply_cap` gives both.
    """
    return sized_reply_cap(contract, rung).tokens


def sized_reply_cap(
    contract: Contract,
    rung: ServingWindow,
    *,
    prompt: str | None = None,
) -> ReplyCap:
    """The reply cap for `contract` on `rung`, with the sentence explaining it.

    A contract that states `limits.max_output_tokens` is sent that number,
    narrowed to the rung's `output_ceiling` where the ceiling is smaller: a
    ceiling is what the rung can serve, never a cap the contract asked for. A
    contract that states nothing is uncapped, unless the rung serves a ceiling,
    in which case that ceiling stands in for the cap the contract never stated.
    With `prompt` given for a contract that must state a cap, the basis also
    names the room its unit leaves for the reply, which is what the cap was
    measured against.
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
    """The issue for model-written work that states no `limits.max_output_tokens`.

    A model-written change that something then judges has to say what its reply
    is worth, and a contract that says nothing gets no model called for it at
    all. Deterministic work is not, and passes: a tool produces it.
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
    """The issue for a stated reply cap the unit has no room to give.

    The unit's ceiling is the smaller of what its window leaves after `prompt` is
    paid for and the reply room it states; a cap at or under that passes. A unit
    that states neither is `unit-ceiling-unknown` rather than a pass, since a cap
    with nothing above it is truncation at a boundary nobody chose, and the
    refusal names the config keys that would supply the number. A unit with no
    ceiling here but an `output_ceiling` set — another person's unit standing in
    for a local one — is left to the reply-cap path rather than judged
    against nothing.
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
    """The issue for a contract `rung` cannot take, or `None` when it can.

    The questions are asked in the order of what costs most to learn late. The
    window must be able to hold the input the contract declares it may read.
    Then, for a contract whose work is model-written and judged, the stated cap
    must be inside what the unit has room for — except where the prompt already
    fills the window, in which case there is no room a cap could exceed and the
    prompt's own fit names that failure instead. For any other contract the reply
    cap is sized from the contract and the rung, and a cap that fills the whole
    window leaves nothing for a prompt. Whichever branch runs, the cap it settles
    on is handed to `check_contract_fits` as the reply reserve, so the fit is
    judged against the number the request will carry. A rung that states no
    window skips the window checks but not the unit's ceiling.
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
