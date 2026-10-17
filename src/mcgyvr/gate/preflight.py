""

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
    ""

    ESTIMATE = "estimate"
    """The model-free proxy, :func:`~mcgyvr.orchestrator.read.estimate_tokens`."""

    TOKENIZER = "tokenizer"
    """A real tokenizer's count. Exact, so nothing is reserved against it."""


#
#
#
#
#
#
#
#
#
#
#
#ch
#
ESTIMATE_RESERVE = 0.32


class ServingWindow(Protocol):
    ""

    @property
    def source(self) -> str:
        ""

    @property
    def context_window(self) -> int | None:
        ""

    @property
    def output_tokens(self) -> int | None:
        ""

    @property
    def output_ceiling(self) -> int | None:
        ""


@dataclass(frozen=True)
class PreflightIssue:
    ""

    reason: str
    message: str

    def __str__(self) -> str:
        return f"preflight[{self.reason}]: {self.message}"


def check_clean_tree(repo: str | os.PathLike[str]) -> PreflightIssue | None:
    ""
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
    ""
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
    ""
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
    ""
    #
    #
    #
    #
    #
    #
    #ch
    #rt
    #
    #
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
        #
        #
        #
        #
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


#
#he
#or
#
CONTRACT_SHARE = "the contract's own `limits.max_window_fraction`"
RUN_SHARE = "the run's `max_window_fraction` (config)"
#
BOTH_SHARES = f"{CONTRACT_SHARE} and {RUN_SHARE}"


def held_share(
    contract_share: float | None, run_share: float | None
) -> tuple[float | None, str]:
    ""
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
    ""
    if fraction is None:
        return None
    if context_window <= 0:
        #
        #
        #
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
    ""

    tokens: int | None
    basis: str


@dataclass(frozen=True)
class UnitCeiling:
    ""

    unit: str
    window: int | None
    prompt: int
    output_tokens: int | None

    @property
    def room(self) -> int | None:
        ""
        return None if self.window is None else self.window - self.prompt

    @property
    def tokens(self) -> int | None:
        ""
        known = [n for n in (self.room, self.output_tokens) if n is not None]
        return min(known) if known else None

    @property
    def terms(self) -> str:
        ""
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
    ""
    #
    from mcgyvr.orchestrator.read import estimate_tokens

    return UnitCeiling(
        unit=rung.source,
        window=rung.context_window,
        prompt=_charged(estimate_tokens(prompt), TokenCount.ESTIMATE),
        output_tokens=rung.output_tokens,
    )


def reply_cap(contract: Contract, rung: ServingWindow) -> int | None:
    ""
    return sized_reply_cap(contract, rung).tokens


def sized_reply_cap(
    contract: Contract,
    rung: ServingWindow,
    *,
    prompt: str | None = None,
) -> ReplyCap:
    ""
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
    ""
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
    ""
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
    ""
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
