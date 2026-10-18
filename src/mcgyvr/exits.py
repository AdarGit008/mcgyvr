"""The process exit codes mcgyvr commands return.

Every command resolves to one of these five ``int`` values, so a script can
branch on the outcome without parsing stderr:

``OK`` (0)
    The command did what was asked.
``ERROR`` (1)
    Something failed while doing it -- a config that would not load, a host
    that did not answer, a file that could not be written.
``USAGE`` (2)
    The invocation itself was wrong: an argument that cannot be used as given.
``REFUSED`` (3)
    The command was understood and declined to act, because the declared
    configuration or the recorded state does not admit it (a host that has
    never been scanned, a unit this config does not plan, a lock already
    held). Nothing is wrong with the code path; the answer is no.
``MISMATCH`` (4)
    The command ran and produced its output, but the machine no longer
    matches the record it was read against -- drift worth reporting rather
    than a failure.
"""

from __future__ import annotations

from enum import IntEnum


class Exit(IntEnum):
    """The exit code a command hands back to the shell.

    An ``IntEnum``, so the members compare and print as the plain integers a
    process returns, while callers can still name the outcome (``Exit.REFUSED``)
    instead of spelling a number. The values are stable: they are part of the
    command-line contract scripts branch on.
    """

    OK = 0
    ERROR = 1
    USAGE = 2
    REFUSED = 3
    MISMATCH = 4
