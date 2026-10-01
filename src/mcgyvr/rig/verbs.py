"""``mcgyvr rig``: join a hub, run the agent, say where it stands, leave.

* ``join <hub-url> --token <token>`` keeps the rig token the hub showed when
  the rig was created (``--token -`` reads it from stdin, out of the shell's
  history and the process list), then runs the agent in the foreground.
* ``run`` runs the agent again from what ``join`` kept (after a reboot, say).
* ``status`` says what is kept, what the agent last heard from the hub, and
  what this machine reads as now — never the token's secret.
* ``leave`` forgets the token here. The rig stays on the hub until it is
  deleted there, or its token rotated.

A token is never sent in clear past this machine: a hub reached over the
network is ``https://``; ``http://`` is taken only for a hub on this machine.

:func:`add_parser` is all ``mcgyvr.cli`` knows of this: it adds the ``rig``
group, and every handler imports what it needs when it runs.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import signal
import sys
import time
import urllib.parse
from types import FrameType
from typing import TYPE_CHECKING

from mcgyvr.exits import Exit

if TYPE_CHECKING:
    from mcgyvr.rig.credentials import Credentials

#: The agent channel's path under a hub's address.
AGENT_PATH = "/api/v1/agent"
#: How long reaching the hub and the upgrade may take, in seconds.
CONNECT_TIMEOUT_S = 15.0

_SCHEMES = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}


class _RefusalError(Exception):
    """A hub address this machine will not send a token to."""


def _is_this_machine(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def agent_url(hub: str) -> str:
    """The agent channel of the hub at ``hub``; ``ValueError`` when ``hub``
    is not a hub's address, :class:`_RefusalError` when it is not a safe one."""
    parts = urllib.parse.urlsplit(hub.strip())
    scheme = _SCHEMES.get(parts.scheme.lower())
    if scheme is None:
        raise ValueError("a hub's address starts https:// (or http:// on this machine)")
    if parts.username is not None or parts.password is not None:
        raise ValueError("a hub's address carries no credentials")
    if parts.query or parts.fragment:
        raise ValueError("a hub's address has no query and no fragment")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("the hub's address names no host")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("the hub's address has a port that is not one") from exc
    if scheme == "ws" and not _is_this_machine(host):
        raise _RefusalError(
            "the rig token would cross the network in clear; use the hub's "
            "https:// address (http:// is taken only for a hub on this machine)"
        )
    path = parts.path.rstrip("/")
    if not path.endswith(AGENT_PATH):
        path += AGENT_PATH
    shown_host = f"[{host}]" if ":" in host else host
    netloc = shown_host if port is None else f"{shown_host}:{port}"
    url = urllib.parse.urlunsplit((scheme, netloc, path, "", ""))
    from mcgyvr.rig import websocket

    websocket.parse_url(url)
    return url


def _agent_version() -> str:
    from mcgyvr import __version__
    from mcgyvr.rig import protocol

    if protocol.AGENT_VERSION.fullmatch(__version__):
        return __version__
    return "0.0.0+unknown"


def run_agent(kept: Credentials) -> int:
    """Run the agent for ``kept`` in the foreground until stopped or refused."""
    from mcgyvr.rig import agent, credentials, hardware, protocol, state, websocket

    url = agent_url(kept.hub)
    version = _agent_version()
    headers = {
        "Authorization": f"Bearer {kept.token}",
        "User-Agent": f"mcgyvr/{version}",
    }

    def connect() -> websocket.WebSocket:
        return websocket.connect(
            url,
            headers=headers,
            timeout=CONNECT_TIMEOUT_S,
            max_message=protocol.MAX_MESSAGE_BYTES,
        )

    def on_status(status: agent.Status) -> None:
        try:
            state.write(
                state.State(
                    hub=kept.hub,
                    pid=os.getpid(),
                    connected=status.connected,
                    rig_id=status.rig_id,
                    heartbeat_s=status.heartbeat_s,
                    last_ack_at=status.last_ack_at,
                    written_at=time.time(),
                )
            )
        except OSError as exc:
            print(f"note: the agent's state was not written: {exc}", file=sys.stderr)

    running = agent.Agent(
        connect=connect,
        read_hardware=hardware.read,
        agent_version=version,
        on_status=on_status,
    )

    def stop(signum: int, frame: FrameType | None) -> None:
        running.stop()

    print(
        f"agent for {kept.hub} as {credentials.shown(kept.token)}; Ctrl-C stops it",
        file=sys.stderr,
    )
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        ended = running.run()
    finally:
        signal.signal(signal.SIGTERM, previous)
    return int(Exit.OK if ended.stopped else Exit.ERROR)


def _join(args: argparse.Namespace) -> int:
    from mcgyvr.rig import credentials

    token: str = args.token
    if token == "-":
        token = sys.stdin.readline().strip()
    hub: str = args.hub.strip().rstrip("/")
    try:
        agent_url(hub)
    except _RefusalError as refused:
        print(f"error: {refused}", file=sys.stderr)
        return int(Exit.REFUSED)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.USAGE)
    wanted = credentials.Credentials(hub=hub, token=token)
    try:
        kept = credentials.load()
    except credentials.CredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.REFUSED)
    if kept is not None and kept != wanted:
        print(
            f"error: this machine is joined to {kept.hub} as "
            f"{credentials.shown(kept.token)}; run `mcgyvr rig leave` first",
            file=sys.stderr,
        )
        return int(Exit.REFUSED)
    try:
        where = credentials.save(wanted)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.USAGE)
    except credentials.CredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.REFUSED)
    print(
        f"joined {hub} as {credentials.shown(token)}; the token is kept in {where}",
        flush=True,
    )
    return run_agent(wanted)


def _kept() -> Credentials | int:
    from mcgyvr.rig import credentials

    try:
        kept = credentials.load()
    except credentials.CredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.REFUSED)
    if kept is None:
        print(
            "error: this machine has joined no hub; "
            "`mcgyvr rig join <hub-url> --token <token>`",
            file=sys.stderr,
        )
        return int(Exit.ERROR)
    return kept


def _run(args: argparse.Namespace) -> int:
    kept = _kept()
    return kept if isinstance(kept, int) else run_agent(kept)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _ago(at: float) -> str:
    seconds = max(0, round(time.time() - at))
    return f"{seconds} s ago"


def _status(args: argparse.Namespace) -> int:
    from mcgyvr.rig import agent, credentials, hardware, state

    try:
        kept = credentials.load()
    except credentials.CredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.REFUSED)
    if kept is None:
        print("not joined to a hub")
        return int(Exit.ERROR)
    print(f"hub:     {kept.hub}")
    print(f"token:   {credentials.shown(kept.token)} (kept in {credentials.path()})")
    last = state.read()
    if last is None or last.hub != kept.hub:
        print("agent:   no word from an agent yet")
    else:
        running = "running" if _alive(last.pid) else "not running"
        rig = agent.shown(last.rig_id) if last.rig_id else "no rig id yet"
        heard = f"; last ack {_ago(last.last_ack_at)}" if last.last_ack_at else ""
        link = "online" if last.connected else "offline"
        print(f"agent:   {running} (pid {last.pid}), {link} as {rig}{heard}")
    try:
        report = hardware.read()
    except hardware.HardwareError as exc:
        print(f"machine: not read: {exc}")
        return int(Exit.OK)
    print(
        f"machine: {report.machine_id}; {len(report.cards)} cards; "
        f"{report.ram_total_mb} MiB RAM"
    )
    for card in report.cards:
        print(
            f"  card {card.index}: {card.name}, {card.vram_total_mb} MiB "
            f"({card.vram_free_mb} MiB free)"
        )
    for note in report.notes:
        print(f"  note: {note}")
    return int(Exit.OK)


def _leave(args: argparse.Namespace) -> int:
    from mcgyvr.rig import credentials, state

    had = credentials.remove()
    state.remove()
    if not had:
        print("not joined to a hub; nothing to leave")
        return int(Exit.OK)
    print(
        "left: the rig token is forgotten here. The rig stays on the hub until "
        "you delete it there or rotate its token, and an agent still running "
        "keeps its channel until it is stopped."
    )
    return int(Exit.OK)


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add the ``rig`` group to ``mcgyvr``'s subcommands."""
    rig = sub.add_parser("rig", help="publish this machine as a rig of a hub")
    verbs = rig.add_subparsers(dest="rig_command", required=True)
    join = verbs.add_parser(
        "join",
        help="keep a hub's rig token and run the agent in the foreground",
    )
    join.add_argument(
        "hub",
        metavar="HUB_URL",
        help="the hub's address, https:// (http:// only for a hub on this machine)",
    )
    join.add_argument(
        "--token",
        required=True,
        metavar="TOKEN",
        help="the rig token the hub showed when the rig was created; - reads it "
        "from stdin",
    )
    join.set_defaults(func=_join)
    run = verbs.add_parser("run", help="run the agent again from the kept token")
    run.set_defaults(func=_run)
    status = verbs.add_parser(
        "status", help="what is kept, what the agent last heard, what this reads as"
    )
    status.set_defaults(func=_status)
    leave = verbs.add_parser("leave", help="forget the rig token here")
    leave.set_defaults(func=_leave)
