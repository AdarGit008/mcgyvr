"""The drive layer's refusal types: a base `DriveError` plus one subclass per
reason a contract or tool step is refused. Refusals are raised with the text
explaining what was refused and why, and callers such as the run command catch
`DriveError` as a group to report `str(exc)` instead of a traceback.
"""

from __future__ import annotations


class DriveError(Exception):
    """Base class for the drive layer's refusals; carries the refusal message.

    Callers catch this type rather than the subclasses when they only need to
    stop the run and show the reason.
    """


class UnrunnableStepError(DriveError):
    """A tool step names an operation with no command to run and no in-process
    executor in mcgyvr, so the step cannot be performed — and reporting it
    complete would claim a file changed that nothing opened.
    """


class PromptTooLargeError(DriveError):
    """The assembled prompt does not fit its own ceiling, so the request is
    refused before it is sent instead of being truncated; the message includes
    the prompt's fit issue.
    """


class OutputCapUnstatedError(DriveError):
    """A model-written contract states no `limits.max_output_tokens`, so there
    is no cap to send and no model is called for it; the message is the stated
    preflight issue.
    """


class OutputCapTooLargeError(DriveError):
    """The contract's output cap is more than the rung can honour — above the
    unit's ceiling for this prompt, or at least as large as the rung's window,
    leaving no room for the prompt. Raised for preflight issues whose reason is
    `output-cap`.
    """


class UnitCeilingUnknownError(DriveError):
    """The unit serving the rung states neither the window it serves nor the
    room its replies are given, so the contract's cap has no ceiling to be held
    to. Raised for preflight issues whose reason is `unit-ceiling-unknown`.
    """


class ContractTooLargeForRungError(DriveError):
    """The catch-all refusal for a contract that does not fit the rung for any
    reason the more specific classes do not name, such as declared input tokens
    exceeding the rung's window or prompt plus reserve exceeding the run's
    share of the window.
    """
