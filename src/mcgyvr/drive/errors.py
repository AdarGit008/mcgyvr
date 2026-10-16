"""Errors the drive seam raises before a dispatch or a step runs."""

from __future__ import annotations


class DriveError(Exception):
    """A step could not be executed as planned, for a reason in this module."""


class UnrunnableStepError(DriveError):
    """The step names no program, so a subprocess executor cannot run it."""


class PromptTooLargeError(DriveError):
    """The assembled prompt does not fit the ceiling its own contract set."""


class OutputCapUnstatedError(DriveError):
    """A model-written ``code`` contract states no ``limits.max_output_tokens``.

    Owner decision (2026-10-14, e2e run 3 T1): such a contract loads, and
    ``mcgyvr contract`` says what it is missing, but it is never sent — no
    number is invented for it. Refused at the seam that would have sent it,
    before any model is called, and not a :class:`~mcgyvr.runner.RunnerError`:
    the unit did nothing wrong, so the cooldown does not learn from it.
    """


class OutputCapTooLargeError(DriveError):
    """The contract's reply cap is above the ceiling of the unit it reaches.

    For model-written ``code``, the ceiling is what the unit's window leaves
    beside the prompt, or its ``output_tokens``, or the smaller of the two
    (:class:`~mcgyvr.gate.preflight.UnitCeiling`); for any other reply, the
    whole window. Distinct from :class:`PromptTooLargeError` because the
    repair is: one is a contract to re-decompose, the other is a number to
    re-declare, and the message names the cap, the unit, the window, the
    prompt as charged and the ceiling. A cap above the ceiling is not lowered
    to fit — that would send a number nobody chose — so it is refused at the
    seam that would have sent it.
    """


class UnitCeilingUnknownError(DriveError):
    """The unit states no ceiling a ``code`` contract's cap can be held to.

    Neither ``units.<unit>.window`` nor ``units.<unit>.output_tokens`` is set,
    so whether the contract's cap fits cannot be known (owner, 2026-10-14).
    Setup writes one on every unit it can read; one it could not is listed as
    not configured, and a dispatch to it refuses until either is set.
    """


class ContractTooLargeForRungError(DriveError):
    """The contract does not fit the window of the rung it was sent to.

    Its declared ceiling is larger than the window, its assembled prompt and
    reply do not fit inside it, or it claims more of the window than its share
    allows — the stricter of its own ``limits.max_window_fraction`` and the
    run's ``max_window_fraction``
    (:func:`~mcgyvr.gate.preflight.check_contract_against_rung`). Owner ruling:
    a task too big for the rung it was sent to fails, before it is sent and
    without being moved up the ladder on its own. Not a
    :class:`~mcgyvr.runner.RunnerError`, so the cooldown does not learn the
    source as failing: the source did nothing wrong.
    """
