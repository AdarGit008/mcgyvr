"""The rig agent's sessions: the containers a session runs and what the hub hears.

A session begins with ``session_prepare``, which checks that this rig lends the
role asked for, takes a tunnel port and, for a head, a loopback port for its API,
and starts a thread that runs the session's operations one at a time. That thread
prepares the tunnel container and reads the WireGuard key, address and gateway it
printed; ``tunnel_up`` then plans a path to every peer, and the thread walks each
peer's candidates and last its relay, pinging the peer's tunnel address to tell a
path that carries a full-size packet from one that does not, and reports the paths
and their round trips to the hub.

``worker_start`` starts one worker container per card asked for, opens the
tunnel's rules to those workers and waits for them to listen. ``head_start``
checks the model's digest, opens the tunnel to the head's rpc devices, starts the
head and follows its ``/health`` route, failing the load as stalled when the
tunnel stops sending the head's workers a mebibyte at a time, warming the head
with one chat completion, and then saying ready.

Once ready, the thread renews the tunnel's lease, checks that every container still
runs, and fails the session when a worker's tunnel traffic stops arriving. Ending a
session removes its containers, rests its tunnel port, frees the tensor cache, and
keeps its final state long enough for a late query to read it. Every fact about the
machine — the setup being lent, the cards, the interfaces, the tensor cache — is
handed in through ``Machine``, so the whole of this runs off a fake docker.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import ipaddress
import json
import os
import queue
import socket
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Protocol

from mcgyvr.rig import (
    commands,
    hardware,
    inventory,
    pooled,
    protocol,
    sessionwire,
    tensorcache,
    tunnel,
    udpwire,
)
from mcgyvr.rig import sharing as sharing_module
from mcgyvr.rig.sessionwire import SessionCode

# The session state machine, which ``_move`` enforces: the states a session may enter.
TRANSITIONS: dict[str, frozenset[str]] = {
    "preparing": frozenset({"prepared", "failed", "stopped"}),
    "prepared": frozenset({"tunnel_up", "starting", "failed", "stopped"}),
    "tunnel_up": frozenset({"starting", "failed", "stopped"}),
    "starting": frozenset({"loading", "ready", "failed", "stopped"}),
    "loading": frozenset({"ready", "failed", "stopped"}),
    "ready": frozenset({"failed", "stopped"}),
    "failed": frozenset({"stopped"}),
    "stopped": frozenset(),
}
# The states in which a session still holds its cards, ports and containers.
LIVE = frozenset(TRANSITIONS) - {"failed", "stopped"}
# How many ended sessions stay in the table, so a late query still reads theirs.
ENDED_KEPT = 16
# How many ids of the frames this agent sent are remembered, so a hub error
# that names one can be traced back to the session the frame was about.
SAID_KEPT = 64
# How many tail lines of a container's log are kept as the excerpt of a failure.
LOG_LINES = 60
# How many bytes of a head's model file are hashed before the lease is renewed again.
DIGEST_CHUNK = 1 << 22
# How long the head's ``/health`` request may take before the head counts as down.
HEALTH_TIMEOUT_S = 2.0
# How many rounds teardown lists and removes the session's containers in.
TEARDOWN_ROUNDS = 3
# The feature that says this rig advertises the units it shares, with their slots,
# in ``unit_advert`` frames; a rig names it even when it lends no session.
HITCHHIKE_FEATURE = "hitchhike_units"
# The feature that says this rig runs one session per card, never two on one card.
# A rig that names it may hold several sessions at once, one per card.
MULTI_SESSION_FEATURE = "multi_session"
# Every feature the hello and the offer name, within ``MAX_FEATURES``, no repeats:
# ``probe`` and ``traversal``: it answers UDP probes and walks STUN candidates,
# ``head_slots``: it reads the slots of the head it runs,
# and the hitchhike units and the several sessions a card rig holds.
# ``offer`` names only ``HITCHHIKE_FEATURE`` for a rig that lends nothing.
# The hub publishes these names, so a name it does not publish refuses the hello.
FEATURES = (
    "probe",
    "traversal",
    "head_slots",
    HITCHHIKE_FEATURE,
    MULTI_SESSION_FEATURE,
)
# How many sessions a rig runs at once: one per tunnel port, each with its own.
# The live session count and the tunnel port count are the same number.
MAX_LIVE_SESSIONS = sharing_module.TUNNEL_PORTS
# How many attempts of time is kept back for a peer's relay by ``candidate_time``.
RELAY_ATTEMPTS = 2
# How many free loopback ports are drawn for a head's API before a head is
# refused: a port another session holds is drawn again, and a drawn port is
# free now, since ``free_port`` binds and closes a kernel-chosen port.
API_PORT_TRIES = 8
# The traversal timings: how long one STUN attempt waits for its answer, in ms,
# how often the keepalive sends a packet to hold the NAT binding open, in seconds,
# and how long that keepalive keeps sending before it stops, in seconds.
STUN_WAIT_MS = 500
KEEP_EVERY_S = 15
KEEP_FOR_S = 600
# The warm-up request: this many words of filler, answered with this many tokens,
# so the head loads its weights and its cache before the session says ready.
WARM_UP_WORDS = 600
WARM_UP_TOKENS = 32
# The warm-up prompt is kept to this share of the head's context, less the tokens
# asked for, so a warm-up never fills the head's window; a smaller one gets a word.
WARM_UP_CONTEXT_SHARE = 4
# How many bytes the tunnel must send a head's workers within ``stall_s`` for the
# load to count as moving: fewer fails it as ``load_stalled``, naming the bytes
# sent, the time they took, and the longest stretch without moving; the tunnel's
# own transfer counts decide, so a thinking head is told from a stopped one.
LOAD_STALL_BYTES = 1 << 20


class Docker(Protocol):
    """The container calls a session makes, by container name.

    A call that fails raises ``pooled.PoolError``, which the session's thread turns
    into a tunnel or start failure for the hub; ``try_script`` and ``renew_lease``
    report failure as ``False`` instead, so a poll can answer "not yet" without
    failing the session.
    """

    def ensure_tunnel_image(self) -> str: ...

    def start(self, argv: Sequence[str]) -> None: ...

    def run_script(self, name: str, script: str, *args: str) -> str: ...

    def try_script(self, name: str, script: str, *args: str) -> bool: ...

    def run_python(self, name: str, source: str, *args: str) -> str: ...

    def start_python(self, name: str, source: str, *args: str) -> None: ...

    def renew_lease(self, name: str) -> bool: ...

    def logs(self, name: str, tail: int) -> str: ...

    def state(self, name: str) -> str | None: ...

    def remove(self, names: Sequence[str]) -> None: ...

    def owned(self) -> list[pooled.Owned]: ...


@dataclass(frozen=True, kw_only=True)
class Timing:
    """Every wait a session makes, in seconds.

    ``tick_s`` is how long the session's thread waits for an operation before it
    ticks; ``lease_s`` and ``renew_s`` how long the tunnel's lease lasts and how
    often it is touched; ``monitor_s`` how often the containers and the peers are
    checked; ``prepare_s``, ``start_s`` and ``load_s`` how long the tunnel, the
    workers and the head may take; ``poll_s`` how long one step waits before looking
    again; ``grace_s`` how long the hub may be away before the sessions are stopped;
    ``stop_wait_s`` how long ``close`` waits for a session's thread and the cache
    check; ``peer_lost_s`` how long a worker may go unheard; ``stall_s`` how long a
    load may send nothing; ``warm_s`` how long the head's warm-up may run;
    ``attempt_s`` and ``connect_s`` how long one candidate and the whole walk may
    take; and ``port_rest_s`` how long a tunnel port rests before another session
    prefers a port that rested longer.
    """

    tick_s: float = 1.0
    lease_s: int = 60
    renew_s: float = 10.0
    monitor_s: float = 5.0
    prepare_s: float = 120.0
    start_s: float = 120.0
    load_s: float = 1800.0
    poll_s: float = 1.0
    grace_s: float = 30.0
    stop_wait_s: float = 120.0
    peer_lost_s: float = 45.0
    stall_s: float = 240.0
    warm_s: float = 300.0
    # The walk's budget: the default time one candidate is aimed at, and the whole walk.
    attempt_s: float = 6.0
    connect_s: float = 60.0
    # How long a tunnel port rests after its session before another session prefers
    # a port that rested longer; a shorter rest is taken when every free port was
    # used within this time, and the log then says how short that rest was.
    port_rest_s: float = 120.0

    @classmethod
    def quick(cls) -> Timing:
        """A timing short enough for a test.

        Every wait on a container is a fraction of a second, and a tunnel port does
        not rest before it is taken again.
        """
        return cls(
            tick_s=0.01,
            lease_s=60,
            renew_s=0.02,
            monitor_s=0.02,
            prepare_s=0.5,
            start_s=0.5,
            load_s=1.0,
            poll_s=0.01,
            grace_s=0.1,
            stop_wait_s=5.0,
            peer_lost_s=0.2,
            stall_s=5.0,
            warm_s=1.0,
            attempt_s=0.05,
            connect_s=2.0,
            port_rest_s=0.0,
        )


@dataclass(frozen=True, kw_only=True)
class Machine:
    """The machine a session runs on, handed in so sessions run off a fake host.

    ``sharing`` is what this rig lends now, ``report`` the cards it has,
    ``inventory`` the models it holds, ``interfaces`` the addresses the tunnel is
    advertised on, ``owner`` the user the containers run as, and ``cache_dir`` the
    tensor cache a head and its workers may mount. The rest is how a session reaches
    its own host: ``free_port`` for the head's API, ``head_health`` and ``warm_up``
    for the head's health and its warm-up, and ``bind_relay`` for this rig's side of
    a relay socket.
    """

    sharing: Callable[[], sharing_module.Sharing]
    report: Callable[[], hardware.Report]
    inventory: Callable[[], inventory.Inventory]
    interfaces: Callable[[], tuple[tuple[str, ipaddress.IPv4Interface], ...]]
    owner: pooled.Owner
    cache_dir: Path | None
    free_port: Callable[[], int]
    head_health: Callable[[int], str]
    warm_up: Callable[[int, int], bool]
    bind_relay: Callable[[sessionwire.RelayGrant], int | None]


class _FailureError(Exception):
    """A failure that ends a session with ``code`` on the wire.

    ``message`` is the one line the hub is told and ``excerpt`` the container log
    tail kept beside it; ``_fail`` joins the two into the state's log excerpt.
    """

    def __init__(self, code: str, message: str, excerpt: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.excerpt = excerpt


@dataclass(eq=False)
class _Session:
    id: str
    role: str
    sharing: sharing_module.Sharing
    listen_port: int
    api_port: int | None
    endpoints: tuple[sessionwire.Endpoint, ...]
    state: str = "preparing"
    error_code: str | None = None
    log_excerpt: str = ""
    hello: pooled.TunnelHello | None = None
    pending: list[str] = field(default_factory=list)
    tunnel_asked: sessionwire.TunnelUp | None = None
    plan: tunnel.TunnelPlan | None = None
    workers_asked: sessionwire.WorkerStart | None = None
    workers: tuple[tuple[int, int, int], ...] = ()  # the card, its GPU number and port
    head_asked: sessionwire.HeadStart | None = None
    head: pooled.HeadSpec | None = None
    head_file: Path | None = None
    rpc: tuple[tuple[str, int], ...] = ()
    containers: list[str] = field(default_factory=list)
    ops: queue.Queue[str] = field(default_factory=queue.Queue)
    outstanding: int = 0
    stopping: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    renewed_at: float = 0.0
    checked_at: float = 0.0
    watched_at: float = 0.0
    heard: dict[str, tuple[int, float]] = field(default_factory=dict)
    sent: int | None = None  # the bytes the tunnel sent the head's rpc peers
    moved: tuple[int, float] | None = None  # that count and when it was seen
    quiet_s: float = 0.0  # the longest the load went without moving, for the log
    traversal: sessionwire.Traversal | None = None
    stun_rtt_us: int | None = None
    report: tuple[sessionwire.PeerPath, ...] | None = None
    reported_to: list[str] = field(default_factory=list)
    released: bool = False  # whether teardown has run and the cards are free

    @property
    def tunnel_name(self) -> str:
        return pooled.container_name(self.id, "tunnel")

    @property
    def cards(self) -> frozenset[int]:
        """The card indexes this session holds.

        The cards its workers were asked for and the local cards its head was asked
        for; a card another rig lends for a peer of this session is not held here.
        """
        held: set[int] = set()
        if self.workers_asked is not None:
            held.update(card.card_index for card in self.workers_asked.cards)
        if self.head_asked is not None:
            held.update(
                device.card_index
                for device in self.head_asked.devices
                if isinstance(device, sessionwire.LocalDevice)
            )
        return frozenset(held)


def free_port() -> int:
    """A loopback port the kernel hands out free now, bound and closed again.

    The head's API is published on such a port, so only this host can reach it.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def head_health(port: int) -> str:
    """Ask the head's ``/health`` on a loopback port for its state.

    ``ok`` for a 200, ``loading`` for a 503, and ``down`` for any other answer, a
    refused connection, or a request that took longer than ``HEALTH_TIMEOUT_S``.
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=HEALTH_TIMEOUT_S)
    try:
        connection.request("GET", "/health")
        status = connection.getresponse().status
    except (OSError, http.client.HTTPException):
        return "down"
    finally:
        connection.close()
    if status == http.HTTPStatus.OK:
        return "ok"
    return "loading" if status == http.HTTPStatus.SERVICE_UNAVAILABLE else "down"


def warm_up(port: int, ctx: int, timeout: float = Timing().warm_s) -> bool:
    """Warm the head at this port with one chat completion of filler words.

    The prompt is ``WARM_UP_WORDS`` words or as many as fit in the head's context,
    and the answer is asked for without streaming; true when the head answered 200,
    false when it answered anything else or the request could not be made.
    """
    words = max(1, min(WARM_UP_WORDS, ctx // WARM_UP_CONTEXT_SHARE - WARM_UP_TOKENS))
    body = json.dumps(
        {
            "messages": [{"role": "user", "content": " ".join(["warm"] * words)}],
            "max_tokens": WARM_UP_TOKENS,
            "temperature": 0,
            "stream": False,
        }
    ).encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(
            "POST",
            sessionwire.RELAY_PATHS["chat_completions"],
            body=body,
            headers={"Content-Type": "application/json"},
        )
        answer = connection.getresponse()
        answer.read()
        return answer.status == http.HTTPStatus.OK
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def bind_relay(grant: sessionwire.RelayGrant) -> int | None:
    """Bind this rig's side of the hub's UDP relay to the granted ticket.

    The port the relay answered on, or ``None`` when no bind answer came — a socket
    error, a refused ticket or an expired one — which leaves the peer without a
    relay path.
    """
    try:
        answer = udpwire.bind_relay(grant.host, grant.port, grant.ticket)
    except (OSError, ValueError):
        return None
    return answer if isinstance(answer, int) else None


@cache
def _udpwire_source() -> str:
    """The source of :mod:`mcgyvr.rig.udpwire`, read once and kept.

    The tunnel container runs it with the tunnel image's own python, so the STUN and
    keepalive code sent there is the same code this agent runs here.
    """
    return Path(udpwire.__file__).read_text(encoding="utf-8")


@dataclass
class _Walk:
    """One peer's walk through its candidates and then its relay.

    ``aim`` is the endpoint the tunnel is aimed at for this peer now, ``attempt`` how
    long that aim is given, ``held`` the endpoint a handshake came back from, and
    ``result`` what the peer is finally reported as.
    """

    peer: tunnel.PeerPlan
    step: int
    aim: tuple[str, int] | None
    since: float
    attempt: float  # how long this peer's one candidate is aimed at
    relayed: bool = False
    result: sessionwire.PeerPath | None = None
    held: tuple[str, int] | None = None  # the endpoint a handshake came back from
    moved: bool = False
    rtt_us: int | None = None  # the ping's round trip on the working path, in us
    # Set when an endpoint answered small pings but lost every full-size one, so
    # from then on only an answer with a full-size packet is taken as the path.
    narrowed: bool = False
    why: str = ""  # why this peer's path was given up on, logged and told to the hub
    # Set when the walk ended with no path right after an endpoint was too narrow.
    too_narrow: bool = False


def candidate_time(
    attempt: float, connect: float, *, candidates: int, relay: bool
) -> float:
    """How long one candidate of this peer may be aimed at.

    The connect budget is split evenly over the candidates, and a peer that has a
    relay keeps back time for ``RELAY_ATTEMPTS`` of its attempts, at most half the
    budget; a candidate never gets more than the plain attempt either.
    """
    kept = min(RELAY_ATTEMPTS * attempt, connect / 2) if relay else 0.0
    return min(attempt, (connect - kept) / max(candidates, 1))


def _log(line: str) -> None:
    """Say one line of this agent's log on stderr, flushed as it is written."""
    print(line, file=sys.stderr, flush=True)


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


def trim_cache(folder: Path, max_mb: int) -> None:
    """Remove the oldest files of this folder until what is left fits ``max_mb``.

    Symlinks and anything that is not a regular file are left alone, and a file that
    will not stat or will not unlink is skipped rather than failing the trim.
    """
    found: list[tuple[float, int, Path]] = []
    for root, _dirs, files in os.walk(folder, followlinks=False):
        for name in files:
            path = Path(root) / name
            with contextlib.suppress(OSError):
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                found.append((stat.st_mtime, stat.st_size, path))
    total = sum(size for _, size, _ in found)
    budget = max_mb << 20
    for _, size, path in sorted(found):
        if total <= budget:
            return
        with contextlib.suppress(OSError):
            path.unlink()
            total -= size


class Sessions:
    """The sessions this agent runs, and the handlers the hub's frames reach.

    Each session has a row, a thread that runs its operations one at a time, and the
    containers it owns. The handlers — ``prepare``, ``tunnel_up``, ``worker_start``,
    ``head_start``, ``query`` and ``stop`` — answer the hub at once from under the
    lock and leave the work to the session's thread, so a docker call never blocks
    the frame loop. The class keeps what the sessions share as well: which cards,
    tunnel ports and API ports are taken, the tensor cache and its ledger, and the
    grace timer that stops every session when the hub goes away.
    """

    def __init__(
        self,
        *,
        docker: Docker,
        machine: Machine,
        send: Callable[[str], bool],
        timing: Timing | None = None,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = _log,
    ) -> None:
        self.machine = machine
        self._log = log
        self.timing = timing or Timing()
        self._docker = docker
        self._send = send
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, _Session] = {}
        # The clock time each tunnel port went back into the pool, so a port can rest.
        self._port_left: dict[int, float] = {}
        self._closed = False
        self._grace: threading.Timer | None = None
        self._ended_hooks: list[Callable[[str], None]] = []
        self._prepare_hooks: list[Callable[[], None]] = []
        self._said: dict[str, str] = {}  # the session each frame id was about
        # The session whose containers have the tensor cache mounted, if any: one at a
        # time, since the folder is trimmed between holders, and a session that asks
        # while another holds it starts without one. Only a folder the ledger vouches
        # for is mounted, and it is made with mode 0700 when it is not there yet.
        self._cache_holder: _Session | None = None
        # The ledger of the tensor cache: the identity of every file the folder held
        # when it was last checked, saved beside it until the next boot. A folder that
        # the ledger does not vouch for is not mounted until a background check has
        # hashed what it does not know and removed what changed, so a head never loads
        # a file something else wrote. ``_cache_check`` is that check while it runs.
        self._cache_ledger = tensorcache.Ledger(
            None
            if machine.cache_dir is None
            else tensorcache.saved_beside(machine.cache_dir)
        )
        self._cache_check: threading.Thread | None = None
        self._cache_stop = threading.Event()

    # The hooks the agent hangs on a session's preparation and on its end.

    def before_prepare(self, hook: Callable[[], None]) -> None:
        """Take a hook to call before a session prepares its tunnel container.

        The session calls it on its own thread and ignores whatever it raises.
        """
        self._prepare_hooks.append(hook)

    def on_end(self, hook: Callable[[str], None]) -> None:
        """Take a hook to call with a session's id once its containers are removed.

        It is called whether the session stopped or failed, after its cards and its
        port are free.
        """
        self._ended_hooks.append(hook)

    def running(self) -> tuple[str, ...]:
        """The ids of the sessions that are still live.

        As many as a hello may list, so a rig with more live sessions than the wire
        carries reports the first of them.
        """
        with self._lock:
            live = [s.id for s in self._sessions.values() if s.state in LIVE]
        return tuple(live[: protocol.MAX_SESSIONS_REPORTED])

    def head_port(self, session_id: str) -> int | None:
        """The loopback port of this session's head API, while the head is ready.

        ``None`` for another role, for a state other than ready, and for a session
        this rig does not know.
        """
        with self._lock:
            found = self._sessions.get(session_id)
            if found and found.role == "head" and found.state == "ready":
                return found.api_port
        return None

    def head_slots(self, session_id: str) -> int:
        """The slots this session's head was asked for.

        The wire's default while no head was asked for, and for a session this rig
        does not know.
        """
        with self._lock:
            found = self._sessions.get(session_id)
            if found is not None and found.head_asked is not None:
                return found.head_asked.slots
        return sessionwire.DEFAULT_SLOTS

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        """This session's state and role.

        The state is ``absent`` and the role ``None`` when this rig knows no such
        session.
        """
        with self._lock:
            found = self._sessions.get(session_id)
            return (found.state, found.role) if found else ("absent", None)

    def settle(self, timeout: float) -> bool:
        """Wait for the sessions to settle, or until the timeout passes.

        They have settled when no session has an operation in flight and no cache
        check is running; true when that was seen before the timeout, false when it
        was not.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._cache_check is None and all(
                    s.outstanding == 0 for s in self._sessions.values()
                ):
                    return True
            time.sleep(min(self.timing.poll_s, 0.01))
        return False

    def online(self) -> None:
        """The hub is back: cancel the grace timer and say the live sessions' state."""
        with self._lock:
            if self._grace is not None:
                self._grace.cancel()
                self._grace = None
            frames = [
                self._status(found, None)
                for found in self._sessions.values()
                if found.state in LIVE
            ]
        for frame in frames:
            self._say(frame)

    def waiting(self) -> bool:
        """Whether the agent is waiting for the hub to come back.

        True while a grace timer runs over a session that is still live, which is
        when the agent keeps running instead of stopping its sessions at once.
        """
        with self._lock:
            return self._grace is not None and self._live() is not None

    def hub_error(self, error: protocol.Error) -> None:
        """A frame the hub refused for a session it does not know.

        The frame this agent sent is looked up, and the live session it was about is
        asked to stop, since the hub has forgotten a session this rig still runs. Any
        other refusal is left alone.
        """
        if error.code != SessionCode.UNKNOWN_SESSION or error.re is None:
            return
        with self._lock:
            session_id = self._said.get(error.re)
            found = self._sessions.get(session_id) if session_id else None
            if found is not None and found.state in LIVE:
                self._ask_stop(found)

    def offline(self) -> None:
        """The hub is gone: start the grace timer, if one is not already running.

        When the timer fires, every live session is asked to stop; a hub that comes
        back first cancels it.
        """
        with self._lock:
            if self._grace is None and not self._closed:
                self._grace = threading.Timer(self.timing.grace_s, self._hub_lost)
                self._grace.daemon = True
                self._grace.start()

    def close(self) -> None:
        """Stop this agent's sessions and the work that outlives them.

        Every live session is asked to stop and its thread waited for, the cache
        check is ended, and the containers this agent's own process made are
        removed, so nothing this agent started keeps running after it exits.
        """
        with self._lock:
            self._closed = True
            if self._grace is not None:
                self._grace.cancel()
                self._grace = None
            live = [s for s in self._sessions.values() if s.state in LIVE]
            for found in live:
                self._ask_stop(found)
        for found in live:
            if found.thread is not None:
                found.thread.join(self.timing.stop_wait_s)
        self._cache_stop.set()
        with self._lock:
            check = self._cache_check
        if check is not None:
            check.join(self.timing.stop_wait_s)
        with contextlib.suppress(pooled.PoolError):
            mine = [
                o.name
                for o in self._docker.owned()
                if o.agent_pid == self.machine.owner.agent_pid
            ]
            self._docker.remove(mine)

    def sweep(self) -> list[str]:
        """Remove the containers no live agent owns, and name the ones removed.

        A container is swept when it carries no agent pid, when it is this agent's
        own, or when the agent that made it is gone — the leftovers of an agent that
        was killed.
        """
        left = [
            o.name
            for o in self._docker.owned()
            if o.agent_pid is None
            or o.agent_pid == self.machine.owner.agent_pid
            or not _alive(o.agent_pid)
        ]
        self._docker.remove(left)
        return left

    # The frames the hub sends: the three that start a session's parts, and two more.

    def prepare(self, envelope: protocol.Envelope) -> str | None:
        """Answer a ``session_prepare``: lend this rig to the session asked for.

        A new session gets a tunnel port, the endpoints the tunnel is reached on and,
        for a head, a free loopback port for its API, and then a thread that prepares
        its tunnel container; a further prepare of the same session is queued behind
        the one in flight, and all of them are answered once the tunnel's hello is
        read. The hub is refused when this agent is stopping, when the role is not
        offered, when every card this rig lends is held by other sessions, when no
        tunnel port is free, or when no API port is free for a head. ``None`` means
        the answer comes later, from the session's thread.
        """
        asked = sessionwire.read_session_prepare(envelope)
        with self._lock:
            if self._closed:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_CAPABLE, "this agent is stopping"
                )
            share = self.machine.sharing()
            if asked.role not in share.offered_roles():
                return sessionwire.refusal(
                    envelope.id,
                    SessionCode.NOT_CAPABLE,
                    f"role: this rig does not lend the {asked.role} role",
                )
            live = self._live_named(asked.session_id)
            if live is not None:
                if live.role != asked.role:
                    return sessionwire.refusal(
                        envelope.id,
                        protocol.ErrorCode.BAD_MESSAGE,
                        "role: the session was prepared as the other role",
                    )
                if live.hello is not None:
                    return self._prepared(live, envelope.id)
                live.pending.append(envelope.id)
                return None
            report = self.machine.report()
            lent = {
                card.index
                for card in report.cards
                if share.lends(card.index, report) is not None
            }
            if lent and lent <= self._held():
                return sessionwire.refusal(
                    envelope.id,
                    SessionCode.BUSY,
                    "every card this rig lends is in another session",
                )
            # The addresses the tunnel is reached on: the setup's names, else every LAN
            # address of this host, cut to the endpoints the wire carries.
            hosts = endpoint_hosts(share, self.machine.interfaces)
            listen_port = self._tunnel_port(share)
            if listen_port is None:
                return sessionwire.refusal(
                    envelope.id,
                    SessionCode.BUSY,
                    "every tunnel port of this rig is in another session",
                )
            api_port = None
            if asked.role == "head":
                api_port = self._api_port()
                if api_port is None:
                    return sessionwire.refusal(
                        envelope.id,
                        SessionCode.BUSY,
                        "no loopback port is free for the head's API",
                    )
            session = _Session(
                id=asked.session_id,
                role=asked.role,
                traversal=asked.traversal,
                sharing=share,
                listen_port=listen_port,
                api_port=api_port,
                endpoints=tuple(
                    sessionwire.Endpoint(
                        host=h, port=listen_port, kind=endpoint_kind(h)
                    )
                    for h in hosts
                ),
                pending=[envelope.id],
            )
            self._sessions.pop(asked.session_id, None)
            self._sessions[asked.session_id] = session
            self._forget_ended()
            session.thread = threading.Thread(
                target=self._run, args=(session,), daemon=True
            )
            self._queue(session, "prepare")
            session.thread.start()
            return None

    def tunnel_up(self, envelope: protocol.Envelope) -> str | None:
        """Answer a ``tunnel_up``: plan a tunnel to the session's peers, then walk it.

        The plan is made here, against every address this host has and the tunnel's
        own, so a plan the settings do not allow is refused at once; the walk itself
        runs on the session's thread, and this frame is answered when the walk is
        done — with the paths it found, or with a refusal naming the first peer no
        path reached. A repeated ask gets the report already made, or a place in the
        queue for it. ``None`` means the answer comes later.
        """
        asked = sessionwire.read_tunnel_up(envelope)
        with self._lock:
            session = self._live_named(asked.session_id)
            if session is None:
                return self._unknown(envelope.id)
            if session.hello is None:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_READY, "the session is being prepared"
                )
            if session.tunnel_asked is not None:
                if session.tunnel_asked != asked:
                    return sessionwire.refusal(
                        envelope.id,
                        protocol.ErrorCode.BAD_MESSAGE,
                        "the session's tunnel is up with other settings",
                    )
                if session.report is not None:
                    return sessionwire.tunnel_report(
                        envelope.id, session_id=session.id, peers=session.report
                    )
                session.reported_to.append(envelope.id)
                return None
            own = [interface for _, interface in self.machine.interfaces()]
            own.append(ipaddress.IPv4Interface(session.hello.address))
            try:
                plan = tunnel.plan(asked, listen_port=session.listen_port, own=own)
            except tunnel.RefusedError as refused:
                return sessionwire.refusal(envelope.id, refused.code, refused.message)
            session.tunnel_asked = asked
            session.plan = plan
            session.reported_to.append(envelope.id)
            self._queue(session, "tunnel")
            return None

    def worker_start(self, envelope: protocol.Envelope) -> str:
        """Answer a ``worker_start``: lend the cards the session's workers start on.

        Each card must be one this rig lends, its port must be one an unprivileged
        server can bind, and no card may be held by another session. The work is
        queued on the session's thread and acked here; a repeat of the same ask is
        acked again.
        """
        asked = sessionwire.read_worker_start(envelope)
        with self._lock:
            session = self._live_named(asked.session_id)
            if session is None:
                return self._unknown(envelope.id)
            if session.role != "worker":
                return sessionwire.refusal(
                    envelope.id,
                    SessionCode.NOT_CAPABLE,
                    "this rig is the session's head",
                )
            if session.plan is None:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_READY, "the session's tunnel is not up"
                )
            if session.workers_asked is not None:
                if session.workers_asked == asked:
                    return sessionwire.ack(envelope.id)
                return sessionwire.refusal(
                    envelope.id,
                    protocol.ErrorCode.BAD_MESSAGE,
                    "the session's workers are started on other cards",
                )
            share = self.machine.sharing()
            report = self.machine.report()
            workers = []
            for card in asked.cards:
                gpu = share.lends(card.card_index, report)
                if gpu is None:
                    return sessionwire.refusal(
                        envelope.id,
                        SessionCode.NOT_CAPABLE,
                        "cards: a card this rig does not lend",
                    )
                if card.port < sharing_module.LOWEST_PORT:
                    return sessionwire.refusal(
                        envelope.id,
                        protocol.ErrorCode.BAD_MESSAGE,
                        "cards.port: below the ports an unprivileged server binds",
                    )
                workers.append((card.card_index, gpu, card.port))
            taken = self._taken(session, [card.card_index for card in asked.cards])
            if taken is not None:
                return sessionwire.refusal(envelope.id, SessionCode.BUSY, taken)
            session.workers_asked = asked
            session.workers = tuple(workers)
            session.sharing = share
            self._queue(session, "worker")
            return sessionwire.ack(envelope.id)

    def head_start(self, envelope: protocol.Envelope) -> str:
        """Answer a ``head_start``: check the model and the cards, then start the head.

        A head with any rpc device needs the session's tunnel up, so its plan must be
        made first; the model must be one this rig holds, and every local card must be
        one it lends and no other session holds. The work is queued on the session's
        thread and acked here; a repeat of the same ask is acked again.
        """
        asked = sessionwire.read_head_start(envelope)
        with self._lock:
            session = self._live_named(asked.session_id)
            if session is None:
                return self._unknown(envelope.id)
            if session.role != "head":
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_CAPABLE, "this rig is a session worker"
                )
            if session.hello is None:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_READY, "the session is being prepared"
                )
            needs_tunnel = any(
                not isinstance(device, sessionwire.LocalDevice)
                for device in asked.devices
            )
            if session.plan is None and needs_tunnel:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_READY, "the session's tunnel is not up"
                )
            if session.head_asked is not None:
                if session.head_asked == asked:
                    return sessionwire.ack(envelope.id)
                return sessionwire.refusal(
                    envelope.id,
                    protocol.ErrorCode.BAD_MESSAGE,
                    "the session's head is started with other settings",
                )
            taken = self._taken(
                session,
                [
                    device.card_index
                    for device in asked.devices
                    if isinstance(device, sessionwire.LocalDevice)
                ],
            )
            if taken is not None:
                return sessionwire.refusal(envelope.id, SessionCode.BUSY, taken)
            planned = self._plan_head(session, asked, envelope.id)
            if isinstance(planned, str):
                return planned
            session.head_asked = asked
            session.head = planned
            session.sharing = self.machine.sharing()
            self._queue(session, "head")
            return sessionwire.ack(envelope.id)

    def query(self, envelope: protocol.Envelope) -> str:
        """Answer a ``session_query`` with the session's state and role.

        A session the rig does not know answers ``absent``, and one that has failed
        carries its error code and log excerpt; any other state says neither.
        """
        asked = sessionwire.read_session_query(envelope)
        with self._lock:
            found = self._sessions.get(asked.session_id)
            if found is None:
                return sessionwire.session_status(
                    envelope.id, session_id=asked.session_id, state="absent"
                )
            return self._status(found, envelope.id)

    def stop(self, envelope: protocol.Envelope) -> str:
        """Answer a ``session_stop`` by asking the session's thread to stop.

        The session tears its containers down and says ``stopped``; a session that is
        unknown or already ended is acked all the same.
        """
        asked = sessionwire.read_session_stop(envelope)
        with self._lock:
            found = self._sessions.get(asked.session_id)
            if found is not None and found.state in LIVE:
                self._ask_stop(found)
        return sessionwire.ack(envelope.id)

    # What is taken by whom, and the frames the sessions say.

    def _live(self) -> _Session | None:
        for found in self._sessions.values():
            if found.state in LIVE:
                return found
        return None

    def _holding(self, but: _Session | None = None) -> list[_Session]:
        """The sessions that have not torn down yet, bar the one named.

        A session that has torn down has released its cards and its port, so it no
        longer holds anything even while it is still in the table.
        """
        return [
            found
            for found in self._sessions.values()
            if found is not but and not found.released
        ]

    def _held(self, but: _Session | None = None) -> frozenset[int]:
        """The card indexes every session holds, bar the one named."""
        return frozenset(card for found in self._holding(but) for card in found.cards)

    def _tunnel_port(self, share: sharing_module.Sharing) -> int | None:
        """A tunnel port for a new session, or ``None`` when none can be had.

        No port may be held by a session that has not torn down, and the live
        sessions are capped at ``MAX_LIVE_SESSIONS``. A port rests ``port_rest_s``
        after its last session before another session prefers it; when every free
        port is still resting the one that rested longest is taken, and the log says
        how short that rest was.
        """
        holding = self._holding()
        if sum(found.state in LIVE for found in holding) >= MAX_LIVE_SESSIONS:
            return None
        held = {found.listen_port for found in holding}
        free = [p for p in share.tunnel_ports() if p not in held]
        if not free:
            return None
        now, rest = self._clock(), self.timing.port_rest_s
        for port in free:
            left = self._port_left.get(port)
            if left is None or now - left >= rest:
                return port
        port = min(free, key=lambda p: self._port_left[p])
        self._log(
            f"tunnel port {port} is taken again {now - self._port_left[port]:.0f} s "
            f"after its last session: every free port was held in the last "
            f"{rest:.0f} s"
        )
        return port

    def _api_port(self) -> int | None:
        """A loopback port no session holds yet, or ``None`` when none is drawn.

        The machine is asked for a free port ``API_PORT_TRIES`` times, and a port a
        session that has not torn down holds is drawn again; every draw taken means
        no head can start here now.
        """
        held = {found.api_port for found in self._holding()}
        for _ in range(API_PORT_TRIES):
            port = self.machine.free_port()
            if port not in held:
                return port
        return None

    def _taken(self, session: _Session, cards: Sequence[int]) -> str | None:
        """The refusal that names the first of these cards another session holds.

        ``None`` when none of the cards is held, which is when the session may have
        them.
        """
        held = self._held(session)
        for card in cards:
            if card in held:
                return f"cards: card {card} is in another session"
        return None

    def _live_named(self, session_id: str) -> _Session | None:
        found = self._sessions.get(session_id)
        return found if found is not None and found.state in LIVE else None

    def _unknown(self, re: str) -> str:
        return sessionwire.refusal(
            re,
            SessionCode.UNKNOWN_SESSION,
            "session_id: this rig is in no such session",
        )

    def _forget_ended(self) -> None:
        ended = [
            s.id for s in self._sessions.values() if s.state not in LIVE and s.released
        ]
        for session_id in ended[: max(0, len(ended) - ENDED_KEPT)]:
            del self._sessions[session_id]

    def _queue(self, session: _Session, op: str) -> None:
        session.outstanding += 1
        session.ops.put(op)

    def _ask_stop(self, session: _Session) -> None:
        if not session.stopping.is_set():
            session.stopping.set()
            self._queue(session, "stop")

    def _prepared(self, session: _Session, re: str) -> str:
        assert session.hello is not None
        return sessionwire.session_prepared(
            re,
            session_id=session.id,
            public_key=session.hello.public_key,
            listen_port=session.listen_port,
            endpoints=session.endpoints,
            stun_rtt_us=session.stun_rtt_us,
        )

    def _status(self, session: _Session, re: str | None) -> str:
        failed = session.state == "failed"
        return sessionwire.session_status(
            re,
            session_id=session.id,
            state=session.state,
            role=session.role,
            error_code=session.error_code if failed else None,
            log_excerpt=session.log_excerpt if failed else "",
        )

    def _move(self, session: _Session, to: str) -> None:
        with self._lock:
            if to not in TRANSITIONS[session.state]:
                raise _FailureError(
                    SessionCode.START_FAILED,
                    f"a session cannot move from {session.state} to {to}",
                )
            session.state = to

    def _plan_head(
        self, session: _Session, asked: sessionwire.HeadStart, re: str
    ) -> pooled.HeadSpec | str:
        assert session.hello is not None
        share = self.machine.sharing()
        report = self.machine.report()
        held = self.machine.inventory()
        relative = inventory.resolve(held, asked.model)
        if relative is None or held.folder is None or share.image is None:
            return sessionwire.refusal(
                re, SessionCode.MODEL_MISSING, "model: not a model this rig holds"
            )
        local: list[int] = []
        for device in asked.devices:
            if isinstance(device, sessionwire.LocalDevice):
                gpu = share.lends(device.card_index, report)
                if gpu is None:
                    return sessionwire.refusal(
                        re,
                        SessionCode.NOT_CAPABLE,
                        "devices: a card this rig does not lend",
                    )
                local.append(gpu)
        gpus = sorted(local)
        names: list[str] = []
        rpc: list[tuple[str, int]] = []
        for device in asked.devices:
            if isinstance(device, sessionwire.LocalDevice):
                gpu = share.lends(device.card_index, report)
                assert gpu is not None
                names.append(f"CUDA{gpus.index(gpu)}")
                continue
            if (
                session.plan is None
                or session.plan.peer_of(device.host) is None
                or device.host == session.plan.address.ip
            ):
                return sessionwire.refusal(
                    re,
                    protocol.ErrorCode.BAD_MESSAGE,
                    "devices: an rpc device outside the session's tunnel",
                )
            names.append(f"RPC{len(rpc)}")
            rpc.append((str(device.host), device.port))
        session.rpc = tuple(rpc)
        session.head_file = held.folder / relative
        return pooled.HeadSpec(
            session_id=session.id,
            image=share.image,
            binary=share.head_binary,
            gpus=tuple(gpus),
            models_dir=held.folder,
            model=relative,
            name=asked.model,
            ctx=asked.ctx,
            slots=asked.slots,
            n_gpu_layers=asked.n_gpu_layers,
            devices=tuple(names),
            tensor_split=asked.tensor_split,
            rpc=tuple(f"{host}:{port}" for host, port in rpc),
            bind=str(ipaddress.IPv4Interface(session.hello.address).ip),
            memory_mb=share.container_mb(),
        )

    def _hub_lost(self) -> None:
        with self._lock:
            self._grace = None
            for found in list(self._sessions.values()):
                if found.state in LIVE:
                    self._ask_stop(found)

    # Saying frames, running one operation of a session, and the failures that end one.

    def _say(self, frame: str) -> None:
        try:
            message = json.loads(frame)
            said = message["id"], message["body"]["session_id"]
        except (ValueError, KeyError, TypeError):
            said = None
        if said is not None:
            with self._lock:
                self._said[said[0]] = said[1]
                while len(self._said) > SAID_KEPT:
                    del self._said[next(iter(self._said))]
        self._send(frame)

    def _run(self, session: _Session) -> None:
        try:
            while True:
                try:
                    op = session.ops.get(timeout=self.timing.tick_s)
                except queue.Empty:
                    op = None
                try:
                    if session.stopping.is_set():
                        self._end(session)
                        return
                    if op is None:
                        self._tick(session)
                    else:
                        self._do(session, op)
                except _FailureError as failure:
                    self._fail(session, failure)
                    return
                except pooled.PoolError as failure:
                    code = (
                        SessionCode.TUNNEL_FAILED
                        if op in ("prepare", "tunnel")
                        else SessionCode.START_FAILED
                    )
                    self._fail(session, _FailureError(code, str(failure)))
                    return
                except Exception as failure:  # a bug here, not a docker failure
                    self._fail(
                        session,
                        _FailureError(
                            SessionCode.START_FAILED,
                            f"the agent failed ({failure.__class__.__name__})",
                        ),
                    )
                    return
                finally:
                    if op is not None:
                        with self._lock:
                            session.outstanding = max(0, session.outstanding - 1)
        finally:
            with self._lock:
                session.outstanding = 0

    def _do(self, session: _Session, op: str) -> None:
        steps: dict[str, Callable[[_Session], None]] = {
            "prepare": self._do_prepare,
            "tunnel": self._do_tunnel,
            "worker": self._do_worker,
            "head": self._do_head,
        }
        if op in steps:
            steps[op](session)

    def _pause(self, session: _Session) -> bool:
        """Wait one poll, renewing the tunnel's lease first.

        True when the session has been asked to stop, which is how a long step ends
        early.
        """
        self._renew(session)
        return session.stopping.wait(self.timing.poll_s)

    def _renew(self, session: _Session) -> None:
        now = self._clock()
        if session.hello is None or now - session.renewed_at < self.timing.renew_s:
            return
        session.renewed_at = now
        if not self._docker.renew_lease(session.tunnel_name):
            raise _FailureError(
                SessionCode.TUNNEL_FAILED
                if session.state != "ready"
                else SessionCode.UPSTREAM_FAILED,
                "the session's tunnel ended",
                self._docker.logs(session.tunnel_name, LOG_LINES),
            )

    def _tick(self, session: _Session) -> None:
        self._renew(session)
        if session.state == "ready":
            self._watch(session)
        now = self._clock()
        if session.state != "ready" or now - session.checked_at < self.timing.monitor_s:
            return
        session.checked_at = now
        for name in list(session.containers):
            if self._docker.state(name) != "running":
                raise _FailureError(
                    SessionCode.UPSTREAM_FAILED,
                    f"{name.rsplit('-', 1)[-1]}: the container ended",
                    self._docker.logs(name, LOG_LINES),
                )

    def _watch(self, session: _Session) -> None:
        """Follow the traffic to this head's rpc peers.

        Each peer is watched by the transfer count the tunnel reports for its key: a
        count that grew since the last look is the peer being heard, and a peer not
        heard for ``peer_lost_s`` fails the session as ``no_path``. The counts of the
        watched peers are also the ``sent`` total the stall check reads.
        """
        if session.role != "head" or not session.rpc or session.plan is None:
            return
        now = self._clock()
        if now - session.watched_at < self.timing.monitor_s:
            return
        session.watched_at = now
        watched: dict[str, str] = {}
        for host, _ in session.rpc:
            peer = session.plan.peer_of(ipaddress.IPv4Address(host))
            if peer is not None:
                watched.setdefault(peer.public_key, host)
        for key in watched:
            session.heard.setdefault(key, (-1, now))
        quiet = [
            host
            for key, host in watched.items()
            if now - session.heard[key][1] >= self.timing.monitor_s
        ]
        try:
            said = self._docker.run_script(
                session.tunnel_name, pooled.TRANSFER_SCRIPT, *quiet
            )
        except pooled.PoolError:
            said = ""
        received = pooled.read_transfer(said)
        sent = pooled.read_sent(said)
        if any(key in sent for key in watched):
            session.sent = sum(sent.get(key, 0) for key in watched)
        now = self._clock()
        for key, host in watched.items():
            last, at = session.heard[key]
            got = received.get(key)
            if got is not None and got > last:
                session.heard[key] = (got, now)
            elif now - at > self.timing.peer_lost_s:
                raise _FailureError(
                    SessionCode.NO_PATH,
                    f"the worker at {host} was not heard from over the tunnel "
                    f"for {now - at:.0f} s",
                    self._docker.logs(
                        pooled.container_name(session.id, "head"), LOG_LINES
                    ),
                )

    def _moving(self, session: _Session) -> None:
        """Fail the load as stalled when the tunnel stops sending the head's workers.

        The transfer total is compared with the one seen last: a mebibyte more means
        the load is moving and the wait starts again, and less than that for longer
        than ``stall_s`` fails the session as ``load_stalled``. The longest stretch
        the load went without moving is kept for the log line.
        """
        if session.sent is None:
            return
        now = self._clock()
        if session.moved is None:
            session.moved = (session.sent, now)
            return
        before, at = session.moved
        if session.sent - before >= LOAD_STALL_BYTES:
            session.quiet_s = max(session.quiet_s, now - at)
            session.moved = (session.sent, now)
        elif now - at > self.timing.stall_s:
            session.quiet_s = max(session.quiet_s, now - at)
            raise _FailureError(
                SessionCode.LOAD_STALLED,
                f"the load stalled: the tunnel sent the workers "
                f"{max(0, session.sent - before)} bytes in {now - at:.1f} s, "
                f"under the {LOAD_STALL_BYTES} that count as moving in "
                f"{self.timing.stall_s:g} s",
                self._docker.logs(pooled.container_name(session.id, "head"), LOG_LINES),
            )

    def _loaded(self, session: _Session, started: float, how: str) -> None:
        """Say in the log how the head's load went.

        How long it took, how it ended, and the longest it went without sending its
        workers ``LOAD_STALL_BYTES``; a load whose transfer counts were never read
        says nothing.
        """
        if session.sent is None:
            return
        now = self._clock()
        if session.moved is not None:
            session.quiet_s = max(session.quiet_s, now - session.moved[1])
        self._log(
            f"session {session.id}: the head's load {how} after "
            f"{now - started:.0f} s; the longest it took to send its workers "
            f"{LOAD_STALL_BYTES} bytes was {session.quiet_s:.0f} s "
            f"(stalled past {self.timing.stall_s:g} s)"
        )

    def _warm(self, session: _Session, name: str) -> None:
        """Warm the head, watching the session while the warm-up request runs.

        The request runs on a thread of its own, since it can take minutes; until it
        is done the head must still be running and its rpc peers are watched. The
        wait ends when the warm-up is done, when ``warm_s`` passes, or when the
        session is asked to stop.
        """
        assert session.api_port is not None and session.head is not None
        port, ctx = session.api_port, session.head.ctx
        done = threading.Event()

        def run() -> None:
            try:
                self.machine.warm_up(port, ctx)
            finally:
                done.set()

        threading.Thread(target=run, daemon=True).start()
        deadline = self._clock() + self.timing.warm_s
        while True:
            if self._docker.state(name) != "running":
                raise _FailureError(
                    SessionCode.START_FAILED,
                    "the head ended while it was warmed",
                    self._docker.logs(name, LOG_LINES),
                )
            if done.is_set() or self._clock() > deadline:
                return
            self._watch(session)
            if self._pause(session):
                return

    def _do_prepare(self, session: _Session) -> None:
        for hook in self._prepare_hooks:
            with contextlib.suppress(Exception):
                hook()
        image = self._docker.ensure_tunnel_image()
        name = session.tunnel_name
        self._docker.remove([name])
        spec = pooled.TunnelSpec(
            session_id=session.id,
            image=image,
            listen_port=session.listen_port,
            publish=tuple(e.host for e in session.endpoints),
            api_port=session.api_port,
            lease_s=self.timing.lease_s,
        )
        session.containers.append(name)
        self._docker.start(pooled.tunnel_argv(spec, self.machine.owner))
        deadline = self._clock() + self.timing.prepare_s
        while True:
            hello = pooled.read_tunnel_hello(self._docker.logs(name, LOG_LINES))
            if hello is not None:
                break
            if self._docker.state(name) != "running":
                raise _FailureError(
                    SessionCode.TUNNEL_FAILED,
                    "the tunnel container ended before it was ready",
                    self._docker.logs(name, LOG_LINES),
                )
            if self._clock() > deadline:
                raise _FailureError(
                    SessionCode.TUNNEL_FAILED, "the tunnel was not ready in time"
                )
            if session.stopping.wait(self.timing.poll_s):
                return
        if not sessionwire.WIREGUARD_KEY.fullmatch(hello.public_key):
            raise _FailureError(
                SessionCode.TUNNEL_FAILED, "the tunnel's key does not read"
            )
        try:
            ipaddress.IPv4Interface(hello.address)
            ipaddress.IPv4Address(hello.gateway)
        except ValueError as exc:
            raise _FailureError(
                SessionCode.TUNNEL_FAILED, "the tunnel's addresses do not read"
            ) from exc
        if session.traversal is not None:
            session.stun_rtt_us = self._ask_responders(session, hello)
        with self._lock:
            session.hello = hello
            session.renewed_at = self._clock()
            self._move(session, "prepared")
            waiting, session.pending = session.pending, []
        for re in waiting:
            self._say(self._prepared(session, re))

    def _ask_responders(
        self, session: _Session, hello: pooled.TunnelHello
    ) -> int | None:
        """Ask this session's STUN servers for a round trip, from inside the tunnel.

        Only the first ``MAX_STUN_ENDPOINTS`` servers that may be aimed at are asked,
        over the tunnel's own listen port; the keepalive then holds the binding open
        for ``KEEP_FOR_S``. The answer is the shortest round trip in microseconds, or
        ``None`` when no server answered or the container could not be run — a
        session without a traversal reading is still a session.
        """
        assert session.traversal is not None
        own = [interface for _, interface in self.machine.interfaces()]
        own.append(ipaddress.IPv4Interface(hello.address))
        servers: list[tuple[str, int]] = []
        for endpoint in session.traversal.stun[: sessionwire.MAX_STUN_ENDPOINTS]:
            host = sessionwire._ipv4(endpoint.host)
            if host is not None and tunnel.may_aim_at(host, None, own):
                servers.append((str(host), endpoint.port))
        if not servers:
            return None
        pairs = [word for host, port in servers for word in (host, str(port))]
        port, token = str(session.listen_port), session.traversal.token.hex()
        name = session.tunnel_name
        try:
            self._docker.run_script(name, pooled.STUN_SCRIPT, port, *pairs)
            said = self._docker.run_python(
                name,
                _udpwire_source(),
                "stun",
                port,
                token,
                str(udpwire.STUN_ATTEMPTS),
                str(STUN_WAIT_MS),
                *pairs,
            )
            self._docker.start_python(
                name,
                _udpwire_source(),
                "keep",
                port,
                token,
                str(KEEP_EVERY_S),
                str(KEEP_FOR_S),
                pooled.KEEPER_PID_FILE,
                *pairs,
            )
        except pooled.PoolError:
            return None
        rtts = []
        for line in said.splitlines():
            words = line.split()
            if (
                len(words) == 4
                and words[0] == "rtt"
                and (words[1], words[2]) in {(h, str(p)) for h, p in servers}
                and words[3].isdigit()
            ):
                rtts.append(min(int(words[3]), sessionwire.MAX_RTT_US))
        return min(rtts) if rtts else None

    def _do_tunnel(self, session: _Session) -> None:
        assert session.plan is not None and session.tunnel_asked is not None
        plan, asked = session.plan, session.tunnel_asked
        self._docker.run_script(
            session.tunnel_name, pooled.TUNNEL_SCRIPT, *plan.script_args()
        )
        attempt = (
            asked.attempt_s if asked.attempt_s is not None else self.timing.attempt_s
        )
        connect = (
            asked.connect_timeout_s
            if asked.connect_timeout_s is not None
            else self.timing.connect_s
        )
        now = self._clock()
        deadline = now + connect
        walks = []
        for peer in plan.peers:
            first = peer.candidates[0] if peer.candidates else None
            walks.append(
                _Walk(
                    peer=peer,
                    step=0,
                    aim=(str(first.host), first.port) if first else None,
                    since=now,
                    attempt=candidate_time(
                        attempt,
                        connect,
                        candidates=len(peer.candidates),
                        relay=peer.relay is not None,
                    ),
                )
            )
        while True:
            open_ = [w for w in walks if w.result is None]
            if not open_:
                break
            pokes = [
                str(w.peer.tunnel_host)
                for w in open_
                if w.aim is not None and w.peer.tunnel_host is not None
            ]
            try:
                seen = pooled.read_peers(
                    self._docker.run_script(
                        session.tunnel_name, pooled.PEERS_SCRIPT, *pokes
                    )
                )
            except pooled.PoolError:
                seen = None
            now = self._clock()
            changed = False
            for walk in open_:
                key = walk.peer.public_key
                shaken = (
                    seen.endpoints.get(key)
                    if seen is not None
                    and walk.aim is not None
                    and seen.handshakes.get(key, 0) > 0
                    else None
                )
                ping = self._ping(session, walk) if shaken is not None else None
                if ping is not None and ping.narrow:
                    self._spend(session, walk, ping)
                    changed = True
                elif shaken is not None and (
                    not walk.narrowed or (ping is not None and ping.full)
                ):
                    walk.held = shaken
                    walk.result = self._confirmed(walk, shaken)
                    if ping is not None and ping.rtt_ms is not None:
                        walk.rtt_us = min(
                            round(ping.rtt_ms * 1000), sessionwire.MAX_RTT_US
                        )
                    changed = True
                elif walk.aim is None or (
                    not walk.relayed and now - walk.since >= walk.attempt
                ):
                    # Neither a handshake nor a ping came back from the aim, so it has
                    # had its time: the walk moves to the next candidate, and then to
                    # the peer's relay.
                    self._next_aim(walk)
                    walk.since = self._clock()
                    changed = True
            if now >= deadline:
                for walk in walks:
                    if walk.result is None:
                        walk.aim = None
                        walk.result = sessionwire.PeerPath(
                            rig_id=walk.peer.rig_id, path="none"
                        )
                changed = True
            if changed:
                self._aim(session, walks)
            if all(w.result is not None for w in walks):
                break
            if self._pause(session):
                return
        self._report(session, walks)

    def _next_aim(self, walk: _Walk) -> None:
        """Aim the tunnel at this peer's next candidate, or at its relay, or at nothing.

        The candidate after the one aimed at is taken; once the candidates are used up
        the peer's relay is bound and aimed at, and when there is no relay or the bind
        fails the peer is reported with no path at all.
        """
        walk.moved = True
        candidates = walk.peer.candidates
        if walk.aim is not None and not walk.relayed:
            walk.step += 1  # the aim that was tried is done with
        if not walk.relayed and walk.step < len(candidates):
            found = candidates[walk.step]
            walk.aim = (str(found.host), found.port)
            return
        relay = walk.peer.relay
        if relay is not None and not walk.relayed:
            walk.relayed = True
            bound = self.machine.bind_relay(relay.grant)
            if bound is not None and 1 <= bound <= sessionwire.MAX_PORT:
                walk.aim = (str(relay.host), bound)
                return
        walk.aim = None
        walk.result = sessionwire.PeerPath(rig_id=walk.peer.rig_id, path="none")

    def _ping(self, session: _Session, walk: _Walk) -> pooled.PingSeen | None:
        """Ping this peer's tunnel address from inside the tunnel container.

        What the ping read: its round trip on the small packets, and whether a
        full-size packet got through. ``None`` when the peer has no tunnel address or
        the ping could not be run.
        """
        host = walk.peer.tunnel_host
        if host is None:
            return None
        try:
            return pooled.read_ping(
                self._docker.run_script(
                    session.tunnel_name, pooled.PING_SCRIPT, str(host)
                )
            )
        except pooled.PoolError:
            return None

    def _spend(self, session: _Session, walk: _Walk, ping: pooled.PingSeen) -> None:
        """Give up on an endpoint that answered small pings but lost the full-size ones.

        The path's MTU is too small for the tunnel, so the walk moves on — to the next
        candidate, or, for the relay, to no path — and the reason is kept for the log
        and for the refusal the hub is sent.
        """
        assert walk.aim is not None
        host, port = walk.aim
        what = "its relay" if walk.relayed else "a candidate"
        walk.why = (
            f"{what} answered a small ping and lost every full-size one "
            f"({ping.size} bytes of data): the path's MTU is too small for "
            "the tunnel"
        )
        self._log(
            f"session {session.id}: peer {walk.peer.rig_id} at {host}:{port}: "
            f"{walk.why}"
        )
        walk.narrowed = True
        if walk.relayed:
            walk.aim = None
            walk.result = sessionwire.PeerPath(rig_id=walk.peer.rig_id, path="none")
        else:
            self._next_aim(walk)
            walk.since = self._clock()
        # The walk ended with no path right after a narrow endpoint, so the report
        # refuses with ``path_too_narrow``, not with a plain no path.
        walk.too_narrow = walk.result is not None

    def _confirmed(
        self, walk: _Walk, endpoint: tuple[str, int]
    ) -> sessionwire.PeerPath:
        """The path a handshake from this endpoint reports.

        An endpoint that answered on the peer's relay is a relay path; any other is
        direct and takes its kind and its path from the candidate it was planned as,
        so an address no candidate named is reported as reflexive and direct.
        """
        host, port = endpoint
        relay = walk.peer.relay
        if walk.relayed and relay is not None and host == str(relay.host):
            kind, path = "relay", "relay"
        else:
            kind, path = "reflexive", "direct"
            for found in walk.peer.candidates:
                if str(found.host) == host:
                    kind, path = found.endpoint.kind, found.path
                    break
        return sessionwire.PeerPath(
            rig_id=walk.peer.rig_id,
            path=path,
            endpoint=sessionwire.Endpoint(host=host, port=port, kind=kind),
        )

    def _aim(self, session: _Session, walks: Sequence[_Walk]) -> None:
        """Aim the tunnel: write the routing rules and peer endpoints of every walk.

        A walk that found an endpoint keeps the tunnel aimed at it exactly, so the
        peer's traffic keeps coming back the way it worked; a walk still looking gets
        a rule for the address aimed at, and the peer's endpoint is moved to it, which
        is what makes the tunnel try a new candidate.
        """
        args = [str(session.listen_port)]
        for walk in walks:
            if walk.held is not None:
                host, port = walk.held
                args += [walk.peer.public_key, host, str(port), "exact", "0"]
            elif walk.aim is not None:
                host, port = walk.aim
                moved = "1" if walk.moved else "0"
                args += [walk.peer.public_key, host, str(port), "host", moved]
            else:
                args += [walk.peer.public_key, "-", "0", "host", "0"]
            walk.moved = False
        self._docker.run_script(session.tunnel_name, pooled.PATH_SCRIPT, *args)

    def _report(self, session: _Session, walks: Sequence[_Walk]) -> None:
        """Settle the walk: report the paths found, or fail the session with no path.

        A session with a path to every peer moves to ``tunnel_up``, and the waiting
        ``tunnel_up`` frames are answered with the paths, followed by one frame of
        round trips for the peers that have them. A peer given up on only because its
        endpoint answered small pings alone refuses those frames with
        ``path_too_narrow`` and the reason, and any other lost peer fails the session
        as ``no_path``.
        """
        paths = []
        samples = []
        for walk in walks:
            result = walk.result
            assert result is not None
            rtt = walk.rtt_us
            if result.path != "none" and rtt is not None:
                result = sessionwire.PeerPath(
                    rig_id=result.rig_id,
                    path=result.path,
                    endpoint=result.endpoint,
                    rtt_us=rtt,
                )
                samples.append((walk.peer.rig_id, rtt))
            paths.append(result)
        lost = [p.rig_id for p in paths if p.path == "none"]
        narrow = next(
            (w for w in walks if w.too_narrow and w.peer.rig_id in lost), None
        )
        if not lost:
            # Every peer has a path, so the session's tunnel is up.
            self._move(session, "tunnel_up")
        with self._lock:
            session.report = tuple(paths)
            waiting, session.reported_to = session.reported_to, []
        for re in waiting:
            if narrow is not None:
                self._say(
                    sessionwire.refusal(re, SessionCode.PATH_TOO_NARROW, narrow.why)
                )
                continue
            self._say(sessionwire.tunnel_report(re, session_id=session.id, peers=paths))
        if samples:
            self._say(sessionwire.peer_rtt(samples[: sessionwire.MAX_RTT_SAMPLES]))
        if narrow is not None:
            raise _FailureError(
                SessionCode.PATH_TOO_NARROW,
                f"no path to peer {narrow.peer.rig_id} carries a full-size "
                f"packet: {narrow.why}",
            )
        if lost:
            why = next(
                (f"; {w.why}" for w in walks if w.peer.rig_id == lost[0] and w.why),
                "",
            )
            raise _FailureError(
                SessionCode.NO_PATH,
                f"no path reached peer {lost[0]}: no candidate answered and no "
                f"relay carried it{why}",
            )

    def _cache(self, session: _Session) -> Path | None:
        """The tensor cache folder to mount in this session's containers, or ``None``.

        The cache is mounted only when the setup shares it and the machine has that
        folder, and only by one session at a time: a session that asks while another
        holds it starts without a cache. A folder the ledger does not vouch for is not
        mounted until a background check has run, so a head never loads a file that
        changed under it.
        """
        folder = self.machine.cache_dir
        if not session.sharing.cache or folder is None:
            return None
        with self._lock:
            if self._cache_holder is not session:
                if self._cache_holder is not None or self._cache_check is not None:
                    return None
                if not self._cache_ledger.trusted(folder):
                    self._check_cache(folder, session.sharing.cache_max_mb)
                    return None
                self._cache_holder = session
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        return folder

    def _check_cache(self, folder: Path, max_mb: int) -> None:
        """Check the tensor cache folder off this thread, then trim it.

        One check runs at a time, and ``_cache_stop`` ends it when the agent closes.
        The check hashes the files the ledger does not know and removes what the
        ledger says changed or what is not a cache entry; the folder is then trimmed
        to ``max_mb``.
        """
        if self._cache_check is not None or self._closed:
            return

        def run() -> None:
            try:
                with contextlib.suppress(OSError):
                    if folder.is_dir():
                        self._cache_ledger.check(folder, self._cache_stop)
                        if not self._cache_stop.is_set():
                            trim_cache(folder, max_mb)
            finally:
                with self._lock:
                    self._cache_check = None

        self._cache_check = threading.Thread(
            target=run, name="mcgyvr-cache-check", daemon=True
        )
        self._cache_check.start()

    def _do_worker(self, session: _Session) -> None:
        share = session.sharing
        image = share.image
        assert session.plan is not None and image is not None
        self._move(session, "starting")
        own = str(session.plan.address.ip)
        nets = [str(net) for net in session.plan.peer_nets()]
        cache = self._cache(session)
        names: dict[tuple[int, int, int], str] = {}
        for worker in session.workers:
            _, gpu, port = worker
            name = pooled.container_name(session.id, f"worker-{gpu}")
            names[worker] = name
            self._docker.remove([name])
            session.containers.append(name)
            self._docker.start(
                pooled.worker_argv(
                    pooled.WorkerSpec(
                        session_id=session.id,
                        image=image,
                        binary=share.worker_binary,
                        gpu=gpu,
                        bind=own,
                        port=port,
                        cache_dir=cache,
                        memory_mb=share.container_mb(),
                    ),
                    self.machine.owner,
                )
            )
            self._docker.run_script(
                session.tunnel_name, pooled.OPEN_WORKER_SCRIPT, own, str(port), *nets
            )
        waiting = set(session.workers)
        deadline = self._clock() + self.timing.start_s
        while waiting:
            for worker in sorted(waiting):
                name = names[worker]
                if self._docker.state(name) != "running":
                    raise _FailureError(
                        SessionCode.START_FAILED,
                        f"the worker on card {worker[0]} ended while starting",
                        self._docker.logs(name, LOG_LINES),
                    )
                if self._docker.try_script(
                    session.tunnel_name, pooled.LISTENING_SCRIPT, own, str(worker[2])
                ):
                    waiting.discard(worker)
            if not waiting:
                break
            if self._clock() > deadline:
                worker = min(waiting)
                raise _FailureError(
                    SessionCode.START_FAILED,
                    f"the worker on card {worker[0]} did not listen in time",
                    self._docker.logs(names[worker], LOG_LINES),
                )
            if self._pause(session):
                return
        self._move(session, "ready")
        self._say(self._status(session, None))

    def _digest(self, session: _Session, path: Path) -> str | None:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(DIGEST_CHUNK):
                if session.stopping.is_set():
                    return None
                digest.update(chunk)
                self._renew(session)
        return f"sha256:{digest.hexdigest()}"

    def _do_head(self, session: _Session) -> None:
        assert (
            session.head is not None
            and session.hello is not None
            and session.head_asked is not None
            and session.api_port is not None
        )
        self._move(session, "starting")
        wanted = session.head_asked.digest
        if wanted is not None and session.head_file is not None:
            found = self._digest(session, session.head_file)
            if found is None:
                return
            if found != wanted:
                raise _FailureError(
                    SessionCode.MODEL_MISSING,
                    "model: this rig's file is not the one the digest names",
                )
        pairs = [part for host, port in session.rpc for part in (host, str(port))]
        # The address the head binds: the session's tunnel address when it has one, else
        # the tunnel container's own, for a head whose devices are all local.
        own = (
            session.plan.address.ip
            if session.plan is not None
            else ipaddress.IPv4Interface(session.hello.address).ip
        )
        self._docker.run_script(
            session.tunnel_name,
            pooled.OPEN_HEAD_SCRIPT,
            str(own),
            session.hello.gateway,
            *pairs,
        )
        name = pooled.container_name(session.id, "head")
        self._docker.remove([name])
        session.containers.append(name)
        self._docker.start(pooled.head_argv(session.head, self.machine.owner))
        self._move(session, "loading")
        self._say(self._status(session, None))
        started = self._clock()
        deadline = started + self.timing.load_s
        how = "ended"
        try:
            while True:
                if self._docker.state(name) != "running":
                    raise _FailureError(
                        SessionCode.START_FAILED,
                        "the head ended while loading",
                        self._docker.logs(name, LOG_LINES),
                    )
                self._watch(session)
                if self.machine.head_health(session.api_port) == "ok":
                    how = "was done"
                    break
                self._moving(session)
                if self._clock() > deadline:
                    raise _FailureError(
                        SessionCode.START_FAILED,
                        "the head did not load in time",
                        self._docker.logs(name, LOG_LINES),
                    )
                if self._pause(session):
                    return
        finally:
            self._loaded(session, started, how)
        self._warm(session, name)
        if session.stopping.is_set():
            return
        self._move(session, "ready")
        self._say(self._status(session, None))

    def _teardown(self, session: _Session) -> None:
        # The containers are removed newest first, so a head goes before its tunnel.
        # The list is deduplicated, since a container may be named twice.
        names = list(dict.fromkeys(reversed(session.containers)))
        for _ in range(TEARDOWN_ROUNDS):
            with contextlib.suppress(pooled.PoolError):
                names += [
                    o.name for o in self._docker.owned() if o.session_id == session.id
                ]
            names = list(dict.fromkeys(names))
            if not names:
                break
            self._docker.remove(names)
            names = []
        # The session holds nothing from now: its port rests from this moment, the
        # tensor cache is free for the next session if this one held it, and the hooks
        # are told the session ended.
        with self._lock:
            session.released = True
            self._port_left[session.listen_port] = self._clock()
            if self._cache_holder is session:
                self._cache_holder = None
                if self.machine.cache_dir is not None:
                    self._check_cache(
                        self.machine.cache_dir, session.sharing.cache_max_mb
                    )
        for hook in self._ended_hooks:
            with contextlib.suppress(Exception):
                hook(session.id)

    def _fail(self, session: _Session, failure: _FailureError) -> None:
        with self._lock:
            if session.state not in LIVE:
                return
            session.error_code = failure.code
            session.log_excerpt = sessionwire.scrub(
                f"{failure.message}\n{failure.excerpt}".strip()
            )
            session.state = "failed"
        self._teardown(session)
        self._say(self._status(session, None))

    def _end(self, session: _Session) -> None:
        self._teardown(session)
        with self._lock:
            session.state = "stopped"
        self._say(self._status(session, None))


def register(dispatcher: commands.Dispatcher, sessions: Sessions) -> None:
    """Register the session handlers, so the hub's frames reach this ``Sessions``."""
    dispatcher.register(
        "session_prepare", lambda envelope, _: sessions.prepare(envelope)
    )
    dispatcher.register("tunnel_up", lambda envelope, _: sessions.tunnel_up(envelope))
    dispatcher.register(
        "worker_start", lambda envelope, _: sessions.worker_start(envelope)
    )
    dispatcher.register("head_start", lambda envelope, _: sessions.head_start(envelope))
    dispatcher.register("session_query", lambda envelope, _: sessions.query(envelope))
    dispatcher.register("session_stop", lambda envelope, _: sessions.stop(envelope))


def endpoint_hosts(
    share: sharing_module.Sharing,
    interfaces: Callable[[], tuple[tuple[str, ipaddress.IPv4Interface], ...]],
) -> tuple[str, ...]:
    """The hosts this rig is reached on, cut to what the wire carries.

    The endpoints the setup names when it names any, else every LAN address of this
    host.
    """
    hosts = share.endpoints or tuple(str(h) for h in tunnel.lan_hosts(interfaces()))
    return hosts[: protocol.MAX_ENDPOINTS]


def endpoint_kind(host: str) -> str:
    """``lan`` for an address on a private network, ``public`` for anything else."""
    found = sessionwire._ipv4(host)
    return "lan" if found is not None and tunnel.is_lan(found) else "public"


def offer(
    share: sharing_module.Sharing,
    held: inventory.Inventory,
    hosts: Sequence[str],
    running: tuple[str, ...],
) -> protocol.Offer:
    """The offer this rig answers a probe with: what it lends and where to reach it.

    A setup that lends nothing has no roles, no runtime, no models and no endpoints,
    yet still names ``HITCHHIKE_FEATURE``, since it may advertise the units it
    shares. Models are offered only to a rig that lends the head role.
    """
    roles = share.offered_roles()
    if not roles:
        return protocol.Offer(
            roles=(),
            runtime=None,
            endpoints=(),
            models=(),
            sessions=running,
            features=(HITCHHIKE_FEATURE,),
        )
    return protocol.Offer(
        roles=roles,
        runtime=share.image,
        endpoints=tuple(
            (host, share.listen_port, endpoint_kind(host)) for host in hosts
        ),
        models=held.models if "head" in roles else (),
        sessions=running,
        features=FEATURES,
    )
