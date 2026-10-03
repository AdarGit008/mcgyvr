"""What the running agent last knew of its rig, for ``mcgyvr rig status``.

The agent writes it on every change it hears of (online, an ack, offline) to
``rig-state.json`` in the data folder (:func:`mcgyvr.fleet.roots.data_home`),
written whole each time. It holds no secret: the hub's address, the rig id the
hub gave, the heartbeat interval, when the hub last acked, and the agent's
process id. A file that cannot be read is no state, never an error: the agent
writes it again on its next change.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from mcgyvr.fleet import roots

#: The file's name in the data folder.
STATE_FILE = "rig-state.json"


@dataclass(frozen=True, kw_only=True)
class State:
    """The agent's last word on its rig. Times are seconds since the epoch."""

    hub: str
    pid: int
    connected: bool
    rig_id: str | None
    heartbeat_s: int | None
    last_ack_at: float | None
    written_at: float


def path() -> Path:
    """``rig-state.json`` in the data folder."""
    return roots.data_home() / STATE_FILE


def write(state: State) -> None:
    """Replace the kept state with ``state``."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{STATE_FILE}.{os.getpid()}.part"
    try:
        staging.write_text(json.dumps(asdict(state)) + "\n", encoding="utf-8")
        os.replace(staging, target)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


def read() -> State | None:
    """The kept state, or ``None`` when there is none that reads."""
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        state = State(**data)
    except (OSError, ValueError, TypeError):
        return None
    number = (int, float)
    shaped = (
        isinstance(state.hub, str)
        and type(state.pid) is int
        and type(state.connected) is bool
        and (state.rig_id is None or isinstance(state.rig_id, str))
        and (state.heartbeat_s is None or type(state.heartbeat_s) is int)
        and (state.last_ack_at is None or type(state.last_ack_at) in number)
        and type(state.written_at) in number
    )
    return state if shaped else None


def remove() -> None:
    """Forget the kept state."""
    path().unlink(missing_ok=True)
