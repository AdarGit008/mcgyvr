"""The live gate the CLI asks before a command touches real rigs.

:func:`_live` answers whether the settled config's setup is live work at all,
and :func:`_admitted_live` asks the live fleet to admit it, printing why not and
returning that reason when it will not. Callers refuse with ``Exit.REFUSED`` on
a returned reason, so nothing is woken, slept, built or served on rigs that are
not locked.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from mcgyvr.config import (
    Config,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


def _live(config: Config) -> bool:
    """Whether `config` is live work: a setup under the staging directory never
    is, a named live fleet or a setup inside the mcgyvr home always is, and a
    folder that cannot be read is called live so the gate still runs."""
    from mcgyvr.fleet.roots import runs_live

    return runs_live(config.path)


def _admitted_live(config: Config) -> str | None:
    """Ask the live fleet to admit `config`'s units, or say why it does not.

    Returns `None` when the rigs read as the locked layout, so there is nothing
    to clean and nothing to restore. Otherwise the reason is printed to stderr
    with the door commands that would do that cleaning and restoring, and the
    same reason is returned for the caller to refuse with.
    """
    from mcgyvr.fleet.admission import admit
    from mcgyvr.fleet.admit import LiveRefusedError

    try:
        admission = admit(units=config.get("units") or {})
    except LiveRefusedError as exc:
        detail = f"live admission: {exc}"
        print(f"refused: {detail}", file=sys.stderr)
        return detail
    if admission.admitted:
        return None
    detail = (
        f"live admission: the rigs of {admission.fleet} do not read as locked; "
        "nothing was cleaned or restored, and these door commands would do it"
    )
    print(f"refused: {detail}:", file=sys.stderr)
    for line in admission.commands:
        print(f"  {line}", file=sys.stderr)
    return detail
