""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from mcgyvr.config import (
    Config,
)

if TYPE_CHECKING:  #
    pass


def _live(config: Config) -> bool:
    ""
    from mcgyvr.fleet.roots import runs_live

    return runs_live(config.path)


def _admitted_live(config: Config) -> str | None:
    ""
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
