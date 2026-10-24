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


class UnitCeilingUnknownError(DriveError):
    """The unit serving the rung states neither the window it serves nor the
    room its replies are given, so there is no maximum to send a model-written
    reply. Raised for preflight issues whose reason is `unit-ceiling-unknown`.
    """


class ContractTooLargeForRungError(DriveError):
    """The catch-all refusal for a contract that does not fit the rung for any
    reason the more specific classes do not name, such as declared input tokens
    exceeding the rung's window or prompt plus reserve exceeding the run's
    share of the window.
    """
