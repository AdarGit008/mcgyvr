""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.fleet import roots

#
STATE_FILE = "rig-state.json"


@dataclass(frozen=True, kw_only=True)
class State:
    ""

    hub: str
    pid: int
    connected: bool
    #
    #
    rig_id: str | None
    heartbeat_s: int | None
    last_ack_at: float | None
    written_at: float


def path() -> Path:
    ""
    return roots.data_home() / STATE_FILE


def write(state: State) -> None:
    ""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, json.dumps(asdict(state)) + "\n")


def read() -> State | None:
    ""
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
    ""
    path().unlink(missing_ok=True)
