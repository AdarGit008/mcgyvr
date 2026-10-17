"""The last word this machine's agent left about itself.

The agent writes this file whenever its status changes, so `mcgyvr rig status`
can say where the rig stands without a channel to the hub: the hub it runs for,
the pid it runs as, whether its channel is up, the rig id the hub bound, the
heartbeat interval the hub asked for, and when the last ack arrived. It is JSON
under the data home, written through :func:`mcgyvr.atomic.write` so it is
replaced whole, and read back through shape checks rather than trust: a file
that is missing, will not parse, or is shaped unlike a :class:`State` reads as
no state at all.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.fleet import roots

# The file's name under the data home; the whole document lives in this one file.
STATE_FILE = "rig-state.json"


@dataclass(frozen=True, kw_only=True)
class State:
    """One agent's account of itself, as written to the state file.

    `hub` is the hub it runs for, so a status read can tell a stale file from
    the hub the machine is joined to now; `pid` names the process that wrote it,
    which outlives that process and is checked for life separately. The three
    fields the hub supplies stay None while the channel is down, since a status
    is written disconnected too. `written_at` is when :func:`write` was called.
    """

    hub: str
    pid: int
    connected: bool
    # What the hub last told the agent: the rig it is bound to, the heartbeat
    # interval it asked for, and when its last ack arrived. All three are None
    # until the hub acks the hello.
    rig_id: str | None
    heartbeat_s: int | None
    last_ack_at: float | None
    written_at: float


def path() -> Path:
    """The state file's path: its name under the data home."""
    return roots.data_home() / STATE_FILE


def write(state: State) -> None:
    """Write `state` over the state file, replacing it whole.

    The file's folder is made if it is missing; :func:`mcgyvr.atomic.write`
    stages the JSON beside the file and renames it into place, so a concurrent
    :func:`read` sees either the previous document or this one, never a partial
    write.
    """
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, json.dumps(asdict(state)) + "\n")


def read() -> State | None:
    """The state written last, or None when there is nothing worth believing.

    None covers a missing or unreadable file, JSON that will not parse, keys
    that do not fit :class:`State`, and fields of the wrong shape: `pid`,
    `connected` and `heartbeat_s` are checked by exact type so a bool where an
    int belongs (or the reverse) is refused, the optional fields may be None but
    otherwise hold their type, and the timestamps may be int or float.
    """
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
    """Delete the state file if there is one, as leaving a hub does."""
    path().unlink(missing_ok=True)
