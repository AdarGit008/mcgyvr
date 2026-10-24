"""Pre-flight: the cheap checks a contract and its prompt pass before anything is sent.

Every check here returns a `PreflightIssue` or `None` rather than raising, so the
caller decides what a refusal costs and what class it is reported under. Nothing
here spends or writes: `check_clean_tree` reads `git status` and leaves the tree
alone, and the sizing checks count the prompt with the model-free estimator and
compare that count against what the rung serves — the window, the reply ceiling,
and the share of the window the contract and the run between them allow. The
reply cap every generating request is sent, the unit's maximum within the room
its window leaves the prompt, is sized here too (`unit_max`).
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
        """On a lent rung, the reply room of the local rung it stands in for.

        `None` on any other rung, and where that local rung states none.
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


#: The least room, in tokens, a prompt must leave its window for the reply. The
#: reply is sent the unit's maximum clamped to the room the prompt leaves
#: (`unit_max`), so the only prompt that cannot be sent is one that leaves no
#: room at all: a cap below one token is no cap.
LEAST_ROOM = 1


def check_contract_fits(
    contract: Contract,
    prompt: str,
    context_window: int,
    *,
    default_fraction: float | None = None,
) -> PreflightIssue | None:
    """The issue for a contract whose prompt leaves a rung's window no room to reply.

    The prompt is counted with the model-free estimator and charged its
    reserve. Nothing is reserved for the reply beyond `LEAST_ROOM`: the reply is
    sent the unit's maximum clamped to the room this prompt leaves
    (`unit_max`), so prompt and cap together never outgrow the window. Two
    questions are then asked in order — the charged prompt must leave the
    reply some room (`check_prompt_fits`), and it must not claim more of the
    window than `held_share` allows, between the contract's
    `limits.max_window_fraction` and the run's `default_fraction`: the share
    bounds the prompt, and the reply is given the rest. `None` means the
    contract fits.
    """
    # `estimate_tokens` is imported where it is used rather than at module
    # scope, so this module's import list carries no orchestrator dependency.
    # The count is model-free on purpose: pre-flight runs before any model is
    # called, so no question here may be answered by spending a request on it.
    from mcgyvr.orchestrator.read import estimate_tokens

    estimated = estimate_tokens(prompt)
    does_not_fit = check_prompt_fits(estimated, context_window, LEAST_ROOM)
    if does_not_fit is not None:
        # Returned ahead of the share check: a prompt too large for the window
        # as a whole is the prompt's own failure, and reporting it as a share
        # would blame the declared fraction for a prompt that is simply bigger
        # than the rung, sending the reader off to raise the wrong number.
        return does_not_fit
    share, declared_by = held_share(
        contract.limits.max_window_fraction, default_fraction
    )
    return check_window_fraction(
        _charged(estimated, TokenCount.ESTIMATE),
        context_window,
        share,
        declared_by=declared_by,
    )


#: Which declaration may hold a contract's prompt to a share of the rung's
#: window. The contract's own `limits.max_window_fraction` and the run's
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
    prompt_tokens: int,
    context_window: int,
    fraction: float | None,
    *,
    declared_by: str = RUN_SHARE,
) -> PreflightIssue | None:
    """The issue for a prompt claiming more than `fraction` of the window.

    `prompt_tokens` is the prompt as charged. The reply is not part of the
    claim: it is sent the unit's maximum within the room the prompt leaves, so
    a share is what keeps that room from being crowded out — a prompt held to
    `fraction` leaves the reply at least the rest of the window. `fraction` is
    the share `declared_by` allows, and a `None` fraction means no share is
    declared, so nothing is checked. A window of zero or less is a routing
    error rather than an oversized contract, and is reported rather than
    divided by.
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
    claimed = prompt_tokens / context_window
    if claimed <= fraction:
        return None
    allow = "allow" if declared_by == BOTH_SHARES else "allows"
    return PreflightIssue(
        "window-share",
        f"contract's prompt claims {claimed:.2f} of the rung's window "
        f"({prompt_tokens} tokens of {context_window}, as charged), but "
        f"{declared_by} {allow} {fraction:.2f}, leaving the rest for the "
        f"reply. Either decompose into smaller contracts or raise {declared_by}",
    )


@dataclass(frozen=True)
class ReplyCap:
    """The reply cap a request is sent with, and where the number came from.

    `tokens` is `None` when nothing caps the reply: the unit states no ceiling,
    or the prompt leaves it no room. `basis` is the sentence recorded beside
    the number, so an answer's cap can be read back against the limit that
    produced it.
    """

    tokens: int | None
    basis: str


@dataclass(frozen=True)
class UnitCeiling:
    """What one unit has room to give a reply, for a prompt already counted.

    `window` and `output_tokens` are as the unit states them, and either may be
    unknown. `lent` is set only on a rung lent through a hub: the room of the local
    rung it stands in for, which holds it as it would hold that rung. `prompt`
    is that prompt's tokens as charged, so `room` is what the window has left
    once it has been paid for.
    """

    unit: str
    window: int | None
    prompt: int
    output_tokens: int | None
    lent: int | None = None

    @property
    def room(self) -> int | None:
        """The window left after the prompt, or `None` when no window is stated."""
        return None if self.window is None else self.window - self.prompt

    @property
    def tokens(self) -> int | None:
        """The ceiling: the least of the room and the stated reply rooms, or `None`."""
        known = [n for n in (self.room, self.output_tokens, self.lent) if n is not None]
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
        if self.lent is not None:
            said.append(f"the local rung it stands in for gives {self.lent}")
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
        lent=rung.output_ceiling,
    )


def unit_max(rung: ServingWindow, prompt: str) -> ReplyCap:
    """The reply cap a generating request on `rung` is sent: the most the unit can give.

    The unit's stated reply ceiling — its `output_tokens`, and on a lent rung
    the room of the local rung it stands in for — clamped to the room its
    window leaves once `prompt` is paid for, as charged (`unit_ceiling`). It is
    not a number a caller picks: a rung's attempt, a decomposition and a review
    are each sent this, so prompt and reply together never outgrow the window.
    `tokens` is `None` where the unit states neither a window nor a reply
    ceiling, and where the prompt as charged leaves the window no room at all;
    such a request carries no cap and the backend's own limit stops it. A
    rung's attempt is refused before either can happen
    (`check_contract_against_rung`).
    """
    ceiling = unit_ceiling(rung, prompt)
    if ceiling.tokens is None:
        return ReplyCap(
            None,
            f"uncapped: unit {ceiling.unit!r} states neither a window nor a "
            f"reply ceiling",
        )
    if ceiling.tokens < LEAST_ROOM:
        return ReplyCap(
            None,
            f"uncapped: this prompt leaves unit {ceiling.unit!r} no room for a "
            f"reply ({ceiling.terms})",
        )
    return ReplyCap(
        ceiling.tokens,
        f"the most unit {ceiling.unit!r} can give: {ceiling.terms}",
    )


def check_unit_ceiling_stated(
    contract: Contract, rung: ServingWindow
) -> PreflightIssue | None:
    """The issue for model-written work on a unit that states no reply ceiling.

    Model-written work that something then judges is sent the unit's maximum
    (`unit_max`), and a unit that states neither the window it serves nor the
    room its replies are given has no maximum to send: the reply would stop at
    a boundary nobody chose. It is `unit-ceiling-unknown`, naming the config
    keys that would supply the number. A lent rung holding the ceiling of the
    local rung it stands in for has one. Deterministic work calls no model and
    passes.
    """
    if not contract.needs_output_cap:
        return None
    stated = (rung.context_window, rung.output_tokens, rung.output_ceiling)
    if any(n is not None for n in stated):
        return None
    unit = rung.source
    return PreflightIssue(
        "unit-ceiling-unknown",
        f"unit {unit!r} states neither the window it serves nor the room its "
        f"replies are given, so there is no maximum to send contract "
        f"{contract.id!r}'s reply and no model is called. Set "
        f"`units.{unit}.window` (the context length its backend serves, read "
        f"off the running process) or `units.{unit}.output_tokens`",
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
    Then, for a contract whose work is model-written and judged, the unit must
    state a reply ceiling for the reply to be sent at its maximum
    (`check_unit_ceiling_stated`). Last, where the rung states a window, the
    prompt must leave the reply room and keep to its share of the window
    (`check_contract_fits`). The reply cap is never a question here: it is
    the unit's maximum within the room the prompt leaves (`unit_max`), so it
    fits whatever room there is.
    """
    window = rung.context_window
    if window is not None and contract.max_input_tokens > window:
        return PreflightIssue(
            "rung-window",
            f"the contract declares it may read {contract.max_input_tokens} "
            f"tokens, but rung {rung.source!r} serves a window of {window}. "
            f"Decompose against {window}, or point the rung at a machine that "
            f"serves more — a ceiling the rung cannot keep is truncation at a "
            f"boundary nobody chose",
        )
    unknown = check_unit_ceiling_stated(contract, rung)
    if unknown is not None:
        return unknown
    if window is None:
        return None
    return check_contract_fits(
        contract, prompt, window, default_fraction=default_fraction
    )
