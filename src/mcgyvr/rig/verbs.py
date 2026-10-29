"""The `mcgyvr rig` verbs: the agent that holds a channel to a hub, and the
commands that join, run, inspect, leave, sync relief rungs and crew units and set
what this machine lends.

`run_agent` is the substance: it wires sessions, relays, probes and hitchhike
units together behind one outbox and runs `agent.Agent` until a signal stops it
or the hub refuses it. `add_parser` registers the verbs; each `_<verb>` function
is what a parsed command line runs, and each returns the `Exit` code of its
outcome.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import signal
import sys
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from mcgyvr.exits import Exit

if TYPE_CHECKING:
    from mcgyvr.rig.credentials import Credentials

#: The path on a hub under which an agent is given its channel.
AGENT_PATH = "/api/v1/agent"
#: How long opening the hub's websocket may take, in seconds.
CONNECT_TIMEOUT_S = 15.0
#: The uid and gid containers take as root: the unprivileged nobody account.
NOBODY = 65534

_SCHEMES = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}


class _RefusalError(Exception):
    "A well-formed address refused on policy; callers answer Exit.REFUSED."


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
    """Check a hub's address and hand it back split into parts.

    The scheme must be http, https, ws or wss; the address must name a host,
    carry no credentials, no query and no fragment, and give a port that is a
    number. A plain ws:// address for a hub off this machine is refused rather
    than rejected, since `carrying` (a token or a key) would cross the network in
    clear. Anything malformed raises ValueError.
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
    """The websocket URL to reach the hub `hub` names as its agent.

    The scheme becomes ws or wss, an IPv6 host is bracketed, the port is kept,
    and the agent path is appended unless the path already ends with it. The
    address goes through `hub_address`, then `websocket.parse_url` approves the
    URL that comes out.
    """
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


def run_agent(kept: Credentials, config: Path | None = None) -> int:
    """Run an agent for `kept` in the foreground and return its `Exit` code.

    What this machine lends comes from the sharing settings, so settings that
    will not load refuse the run. `config` is the setup folder whose units are
    shared, or None to let the loader default.

    Everything a hub can ask of this rig is built here and joined: sessions run
    in a pooled docker pool on a machine whose sharing, hardware report, model
    inventory, interfaces, ports and cache folder are read only when asked;
    hitchhike units share a setup's units; relays carry a session's traffic;
    probes measure the paths to peers. Each answers envelopes through one
    dispatcher and sends through one outbox. Containers left by a gone agent are
    swept first, a relief-rungs refresher starts only when the hub key is in the
    environment, and SIGTERM and SIGHUP are routed to the agent's stop, with the
    earlier handlers put back after it ends. The code is Exit.OK when the agent
    was asked to stop and Exit.ERROR otherwise.
    """
    from mcgyvr.fleet import roots
    from mcgyvr.rig import (
        agent,
        commands,
        credentials,
        hardware,
        hitchhike,
        inventory,
        outbox,
        pooled,
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
            return sharing.Sharing()  # unreadable settings lend nothing

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
    # The parts of a rig: hitchhike units ride other rigs and offer this setup's
    # units to riders, relays carry what a session sends and receives, probes
    # measure the paths to peers. Each of them speaks through the one outbox.
    units = hitchhike.Units(send=box.put, setup=lambda: hitchhike.load_setup(config))
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

    # The relief rungs kept beside the setup are refreshed from the hub only
    # while the personal hub key is in the environment.
    refresher = rungs.refresher_for(kept.hub, folder=config)
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
    return run_agent(wanted, _named(args))


def _named(args: argparse.Namespace) -> Path | None:
    """The setup folder --config named, or None to let the caller default."""
    named: str | None = getattr(args, "config", None)
    return Path(named) if named else None


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
    return kept if isinstance(kept, int) else run_agent(kept, _named(args))


def _ago(at: float) -> str:
    seconds = max(0, round(time.time() - at))
    return f"{seconds} s ago"


def _status(args: argparse.Namespace) -> int:
    from mcgyvr.rig import agent, credentials, hardware, session, state

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
        running = "running" if session._alive(last.pid) else "not running"
        # A state file outlives the agent that wrote it, so the pid it names
        # is checked for life; the hub's rig id is masked before printing.
        rig = (
            f"the hub's rig {agent.shown(last.rig_id)}"
            if last.rig_id
            else "no hub rig id yet"
        )
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


def _hub_sync(args: argparse.Namespace) -> tuple[str, str, str, Path] | int:
    """The hub, the key, its variable's name and the setup folder a sync of
    ``rungs`` or ``crew`` names, or the exit code it refuses with."""
    import re

    from mcgyvr.config import ConfigError, config_path
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
        folder = _named(args) or config_path()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.ERROR)
    return hub, key, key_env, folder


def _rungs_sync(args: argparse.Namespace) -> int:
    from mcgyvr.config import ConfigError, load
    from mcgyvr.rig import rungs

    named = _hub_sync(args)
    if isinstance(named, int):
        return named
    hub, key, key_env, folder = named
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


def _crew_sync(args: argparse.Namespace) -> int:
    from mcgyvr.rig import crew, rungs

    named = _hub_sync(args)
    if isinstance(named, int):
        return named
    hub, key, key_env, folder = named
    try:
        lent, where = crew.sync(folder, hub, key, key_env)
    except rungs.HubAnswerError as exc:
        print(f"error: {exc}; the crew units kept are unchanged", file=sys.stderr)
        return int(Exit.REFUSED)
    except (rungs.SyncError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(Exit.ERROR)
    print(f"kept {len(lent)} crew unit(s) in {where}")
    for each in lent:
        print(f"  {each.name}  x{each.width}  {each.model}")
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


def _sync_parser(
    verbs: argparse._SubParsersAction[argparse.ArgumentParser],
    add_config: Callable[..., None],
    *,
    help: str,
    written: str,
    func: Callable[[argparse.Namespace], int],
) -> None:
    """Add a `sync` verb under `verbs`: the hub to ask, the key's variable and
    the setup whose `written` file it rewrites."""
    sync = verbs.add_parser("sync", help=help)
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
    add_config(sync, what=f"setup whose {written} is written")
    sync.set_defaults(func=func)


def add_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    add_config: Callable[..., None],
) -> None:
    """Add the `rig` verb and the verbs under it: join, run, status, leave,
    rungs sync, crew sync and share, each with the defaults its parser starts
    from.

    `add_config` attaches the setup option to the verbs that read a setup.
    """
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
    add_config(join, what="setup whose units the agent shares")
    join.set_defaults(func=_join)
    run = verbs.add_parser("run", help="run the agent again from the kept token")
    add_config(run, what="setup whose units the agent shares")
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
    _sync_parser(
        rung_verbs,
        add_config,
        help="keep the hub's relief rungs in the setup's relief.yaml, replacing "
        "the ones kept",
        written="relief.yaml",
        func=_rungs_sync,
    )
    crew = verbs.add_parser(
        "crew", help="the units your crews lend you through the hub"
    )
    crew_verbs = crew.add_subparsers(dest="crew_command", required=True)
    _sync_parser(
        crew_verbs,
        add_config,
        help="keep the units your crews lend you in the setup's crew.yaml, "
        "replacing the ones kept",
        written="crew.yaml",
        func=_crew_sync,
    )
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
