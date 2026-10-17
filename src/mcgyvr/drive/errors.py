""

from __future__ import annotations


class DriveError(Exception):
    ""


class UnrunnableStepError(DriveError):
    ""


class PromptTooLargeError(DriveError):
    ""


class OutputCapUnstatedError(DriveError):
    ""


class OutputCapTooLargeError(DriveError):
    ""


class UnitCeilingUnknownError(DriveError):
    ""


class ContractTooLargeForRungError(DriveError):
    ""
