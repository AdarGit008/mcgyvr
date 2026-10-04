"""``mcgyvr rig``: join a hub, run the agent, say where it stands, leave.

* ``join <hub-url> --token <token>`` keeps the rig token the hub showed when
  the rig was created (``--token -`` reads it from stdin, out of the shell's
  history and the process list), then runs the agent in the foreground.
* ``run`` runs the agent again from what ``join`` kept (after a reboot, say).
* ``status`` says what is kept, what the agent last heard from the hub, and
  what this machine reads as now — never the token's secret.
* ``leave`` forgets the token here. The rig stays on the hub until it is
  deleted there, or its token rotated.
* ``rungs sync`` keeps the relief rungs the hub matched this rider to
  (hitchhike) in the setup's ``relief.yaml`` (:mod:`mcgyvr.rig.rungs`), asking
  with the rider's personal key, read from a variable it names and never
  shown or written; the hub's privacy warning is shown every time.
* ``share`` says what this rig lends to the hub's pooled-inference sessions,
  and changes it (:mod:`mcgyvr.rig.sharing`): nothing until the owner turns
  it on, and then only the roles, cards, memory and models folder allowed.
  While it lends, the agent runs each session in containers that hold no
  privilege and reach no network but the session's tunnel
  (:mod:`mcgyvr.rig.session`), and tears every one down when the session,
  the hub's channel or the agent ends.

A token or key is never sent in clear past this machine: a hub reached over
the network is ``https://``; ``http://`` is taken only for a hub on this
machine (:func:`hub_address`).

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
#: The user a session's containers run as when the agent runs as root: none.
NOBODY = 65534

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


def hub_address(
    address: str, *, carrying: str = "the rig token"
) -> urllib.parse.SplitResult:
    """``address`` split, when it is a hub's that ``carrying`` may be sent to.

    The one rule for every credential this machine sends a hub — the rig
    token over the agent channel, the personal key a sync and a relief rung
    carry: ``https://`` (``wss://``), or ``http://`` (``ws://``) only for a hub
    on this machine. ``ValueError`` when ``address`` is not a hub's address,
    :class:`_RefusalError` when the credential would cross the network in
    clear.
    """
    parts = urllib.parse.urlsplit(address.strip())
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
        _ = parts.port
    except ValueError as exc:
        raise ValueError("the hub's address has a port that is not one") from exc
    if scheme == "ws" and not _is_this_machine(host):
        raise _RefusalError(
            f"{carrying} would cross the network in clear; use the hub's "
            "https:// address (http:// is taken only for a hub on this machine)"
        )
    return parts


def agent_url(hub: str) -> str:
    """The agent channel of the hub at ``hub``; ``ValueError`` when ``hub``
    is not a hub's address, :class:`_RefusalError` when it is not a safe one."""
    parts = hub_address(hub)
    scheme = _SCHEMES[parts.scheme.lower()]
    host = (parts.hostname or "").lower()
    port = parts.port
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
    from mcgyvr.fleet import roots
    from mcgyvr.rig import (
        agent,
        commands,
        credentials,
        hardware,
        hitchhike,
        inventory,
        outbox,
        probe,
        protocol,
        relay,
        rungs,
        session,
        sharing,
        state,
        tunnel,
        websocket,
    )
    from mcgyvr.sandbox import pooled

    try:
        sharing.load()
    except sharing.SharingError as exc:
        print(f"error: {exc}; fix it or run `mcgyvr rig share --off`", file=sys.stderr)
        return int(Exit.REFUSED)
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

    def lending() -> sharing.Sharing:
        try:
            return sharing.load()
        except sharing.SharingError:
            return sharing.Sharing()  # a file that does not read lends nothing

    read: list[hardware.Report] = []

    def read_hardware() -> hardware.Report:
        report = hardware.read()
        read[:] = [report]
        return lending().lendable(report)

    def last_report() -> hardware.Report:
        return read[0] if read else hardware.read()

    held: dict[str | None, inventory.Inventory] = {}

    def models() -> inventory.Inventory:
        folder = lending().models_dir
        if folder not in held:
            held.clear()
            held[folder] = inventory.read(folder)
        return held[folder]

    uid, gid = os.getuid(), os.getgid()
    owner = pooled.Owner(
        uid=uid or NOBODY, gid=gid if uid else NOBODY, agent_pid=os.getpid()
    )
    box = outbox.Outbox()
    sessions = session.Sessions(
        docker=pooled.Pool(),
        machine=session.Machine(
            sharing=lending,
            report=last_report,
            inventory=models,
            interfaces=tunnel.read_interfaces,
            owner=owner,
            cache_dir=roots.data_home() / "rpc-cache" if uid else None,
            free_port=session.free_port,
            head_health=session.head_health,
            warm_up=session.warm_up,
            bind_relay=session.bind_relay,
        ),
        send=box.put,
    )
    # The units this host shares with riders (hitchhike), read from its own
    # setup: advertised once the hello is acked, then kept fresh on the
    # heartbeat and a ticker of their own; a ride to one is a relay.
    units = hitchhike.Units(send=box.put)
    relays = relay.Relays(heads=sessions, send=box.put, units=units)
    sessions.on_end(relays.session_ended)
    probes = probe.Probes(
        send=box.put,
        port=lambda: None if sessions.running() else lending().listen_port,
        hosts=lambda: session.endpoint_hosts(lending(), tunnel.read_interfaces),
        own=lambda: tuple(i.ip for _, i in tunnel.read_interfaces()),
        lending=lambda: bool(lending().offered_roles()),
    )
    sessions.before_prepare(lambda: probes.release(lending().listen_port))
    dispatcher = commands.Dispatcher()
    session.register(dispatcher, sessions)
    relay.register(dispatcher, relays)
    probe.register(dispatcher, probes)
    try:
        for name in sessions.sweep():
            print(f"removed {name}, left by an agent that is gone", file=sys.stderr)
    except pooled.PoolError as exc:
        if lending().enabled:
            print(
                f"note: this machine's containers were not read: {exc}", file=sys.stderr
            )

    # With the rider's personal key in the environment, the heartbeat keeps
    # the relief rungs fresh too (`mcgyvr rig rungs sync`, on the agent's tick).
    refresher = rungs.refresher_for(kept.hub)
    if refresher is not None:
        print(
            f"relief rungs: kept fresh from {kept.hub} with ${rungs.KEY_ENV}",
            file=sys.stderr,
        )

    if units.shares():
        print("hitchhike: sharing units of this setup with riders", file=sys.stderr)

    def offer() -> protocol.Offer | None:
        share = lending()
        hosts = session.endpoint_hosts(share, tunnel.read_interfaces)
        return session.offer(share, models(), hosts, sessions.running())

    def online() -> None:
        sessions.online()
        units.online()

    def offline() -> None:
        relays.cancel_all()
        probes.close()
        sessions.offline()
        units.offline()

    def on_exit() -> None:
        relays.cancel_all()
        probes.close()
        sessions.close()
        units.close()

    def beat() -> None:
        if refresher is not None:
            refresher.tick()
        units.soon()

    running = agent.Agent(
        connect=connect,
        read_hardware=read_hardware,
        agent_version=version,
        on_status=on_status,
        dispatcher=dispatcher,
        outbox=box,
        offer=offer,
        on_online=online,
        on_offline=offline,
        on_exit=on_exit,
        hurry=sessions.waiting,
        on_hub_error=sessions.hub_error,
        on_beat=beat,
    )
    sessions.on_end(lambda ended: running.beat_soon())

    def stop(signum: int, frame: FrameType | None) -> None:
        running.stop()

    print(
        f"agent for {kept.hub} as {credentials.shown(kept.token)}; Ctrl-C stops it",
        file=sys.stderr,
    )
    share = lending()
    if share.offered_roles():
        print(
            f"lending: {', '.join(share.offered_roles())} on {share.image}",
            file=sys.stderr,
        )
    for note in share.notes:
        print(f"note: {note}", file=sys.stderr)
    previous = {
        sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGHUP)
    }
    units.run_ticker()
    try:
        ended = running.run()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
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


def _rungs_sync(args: argparse.Namespace) -> int:
    import re

    from mcgyvr.config import ConfigError, config_path, load
    from mcgyvr.rig import credentials, rungs

    key_env: str = args.key_env
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
        print(
            f"error: {key_env!r} is not a variable's name; --key-env takes the "
            "NAME of the variable holding your personal hub key, never the key",
            file=sys.stderr,
        )
        return int(Exit.USAGE)
    hub: str | None = args.hub
    if hub is None:
        try:
            kept = credentials.load()
        except credentials.CredentialsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return int(Exit.REFUSED)
        if kept is None:
            print(
                "error: this machine has joined no hub; name the hub with --hub",
                file=sys.stderr,
            )
            return int(Exit.ERROR)
        hub = kept.hub
    try:
        hub_address(hub, carrying=rungs.CARRYING)
    except _RefusalError as refused:
        print(f"error: {refused}", file=sys.stderr)
        return int(Exit.REFUSED)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.USAGE)
    key = os.environ.get(key_env)
    if not key:
        print(
            f"error: ${key_env} is not set; export your personal hub key in it "
            "(or name another variable with --key-env), never on the command line",
            file=sys.stderr,
        )
        return int(Exit.ERROR)
    try:
        folder = config_path()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.ERROR)
    try:
        rides, where = rungs.sync(folder, hub, key, key_env)
    except rungs.HubAnswerError as exc:
        print(f"error: {exc}; the relief rungs kept are unchanged", file=sys.stderr)
        return int(Exit.REFUSED)
    except (rungs.SyncError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.ERROR)
    print(rides.privacy)
    if not rides.ride:
        print("riding is off on the hub, so no relief rung is kept; turn it on there")
    print(f"kept {len(rides.rungs)} relief rung(s) in {where}")
    for each in rides.rungs:
        print(
            f"  {each.name}  {each.position}  x{each.width}  {each.served_model}, "
            f"hosted by {each.hosted_by}"
        )
    try:
        fanout = load(folder).ladder.fanout
    except ConfigError:
        fanout = "idle"
    if rides.rungs and fanout != "idle":
        print(
            f"note: relief rungs take work only under `fanout: idle`; this "
            f"ladder's is `{fanout}`"
        )
    return int(Exit.OK)


def _maybe_number(text: str) -> int | None:
    return None if text == "none" else int(text)


def _share(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from mcgyvr.rig import sharing

    try:
        kept = sharing.load()
    except sharing.SharingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.on is None or args.on:
            return int(Exit.REFUSED)
        kept = sharing.Sharing()
    changes: dict[str, object] = {}
    try:
        if args.on is not None:
            changes["enabled"] = args.on
        if args.image is not None:
            changes["image"] = None if args.image == "none" else args.image
        if args.roles is not None:
            changes["roles"] = tuple(r for r in args.roles.split(",") if r)
        if args.cards is not None:
            changes["cards"] = (
                None
                if args.cards == "all"
                else tuple(int(c) for c in args.cards.split(",") if c)
            )
        if args.max_ram_mb is not None:
            changes["max_ram_mb"] = _maybe_number(args.max_ram_mb)
        if args.models is not None:
            changes["models_dir"] = (
                None if args.models == "none" else os.path.abspath(args.models)
            )
        if args.endpoints is not None:
            changes["endpoints"] = (
                () if args.endpoints == "none" else tuple(args.endpoints.split(","))
            )
        if args.listen_port is not None:
            changes["listen_port"] = args.listen_port
        if args.cache is not None:
            changes["cache"] = args.cache
        if args.cache_max_mb is not None:
            changes["cache_max_mb"] = args.cache_max_mb
    except ValueError:
        print("error: a number was asked for and something else given", file=sys.stderr)
        return int(Exit.USAGE)
    wanted = replace(kept, **changes)  # type: ignore[arg-type]
    if wanted.enabled and wanted.image is None:
        print(
            "error: lending runs in an engine image; name it with --image",
            file=sys.stderr,
        )
        return int(Exit.USAGE)
    if changes:
        try:
            where = sharing.save(wanted)
        except sharing.SharingError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return int(Exit.USAGE)
        print(f"kept in {where}")
    roles = wanted.offered_roles()
    print(f"lending: {'on' if wanted.enabled else 'off'}")
    print(f"roles:   {', '.join(roles) if roles else 'none offered'}")
    print(f"image:   {wanted.image or 'none'}")
    cards = "all" if wanted.cards is None else ", ".join(map(str, wanted.cards))
    print(f"cards:   {cards} (each lent whole)")
    print(f"ram:     {wanted.container_mb()} MiB per container")
    print(f"models:  {wanted.models_dir or 'none (no head)'}")
    endpoints = (
        ", ".join(wanted.endpoints) if wanted.endpoints else "this machine's LAN"
    )
    ports = wanted.tunnel_ports()
    udp = f"{ports[0]}" if len(ports) == 1 else f"{ports[0]}-{ports[-1]}"
    print(f"tunnel:  udp {udp} on {endpoints} (one port per session at once)")
    cache = f"up to {wanted.cache_max_mb} MiB" if wanted.cache else "off"
    print(f"cache:   {cache}")
    for note in wanted.notes:
        print(f"note:    {note}")
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
    rungs = verbs.add_parser(
        "rungs", help="the relief rungs the hub matched you to (hitchhike)"
    )
    rung_verbs = rungs.add_subparsers(dest="rungs_command", required=True)
    sync = rung_verbs.add_parser(
        "sync",
        help="keep the hub's relief rungs in the setup's relief.yaml, replacing "
        "the ones kept",
    )
    sync.add_argument(
        "--hub",
        metavar="HUB_URL",
        help="the hub to ask (default: the one this machine joined)",
    )
    sync.add_argument(
        "--key-env",
        default="MCGYVR_HUB_API_KEY",
        metavar="NAME",
        help="the NAME of the variable holding your personal hub key "
        "(default: MCGYVR_HUB_API_KEY)",
    )
    sync.set_defaults(func=_rungs_sync)
    share = verbs.add_parser(
        "share", help="what this rig lends to the hub's sessions; change it"
    )
    switch = share.add_mutually_exclusive_group()
    switch.add_argument("--on", dest="on", action="store_const", const=True)
    switch.add_argument("--off", dest="on", action="store_const", const=False)
    share.add_argument("--image", help="the engine image sessions run in (none)")
    share.add_argument("--roles", help="worker, head, or worker,head")
    share.add_argument(
        "--cards", help="card indexes lent, each whole, comma separated, or all"
    )
    share.add_argument(
        "--max-ram-mb", help="the memory each container may take, or none"
    )
    share.add_argument("--models", help="the folder models are served from, or none")
    share.add_argument("--endpoints", help="LAN addresses to be reached at, or none")
    share.add_argument(
        "--listen-port",
        type=int,
        help="the first tunnel UDP port; each further session at once takes the next",
    )
    cache = share.add_mutually_exclusive_group()
    cache.add_argument("--cache", dest="cache", action="store_const", const=True)
    cache.add_argument("--no-cache", dest="cache", action="store_const", const=False)
    share.add_argument("--cache-max-mb", type=int, help="the worker cache's size")
    share.set_defaults(func=_share, on=None, cache=None)
