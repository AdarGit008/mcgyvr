"""A rig's part in a hub's pooled-inference session: one state machine per session.

The hub runs one model's layers across several rigs: one rig is the *head*
(it serves the model and takes the requests the hub relays), the others are
*workers* (their cards run the head's layers over an RPC server). It tells
each rig what to do with session commands, and this module is a rig's side
of them (:func:`register` puts its handlers on the dispatcher):

* ``session_prepare`` starts the session's tunnel container
  (:mod:`mcgyvr.sandbox.pooled`), which makes the session's WireGuard key on
  this rig; it is answered ``session_prepared`` with the public key, the
  listen port and the LAN endpoints (none when the rig has no LAN address:
  a session of one rig needs none), once the tunnel says it is ready. When
  it carries ``traversal`` (the hub's token and binding responders), the
  tunnel's own port — before WireGuard takes it — asks the responders where
  it is seen from, and keeps asking until the tunnel comes up, so the
  address the hub hands this rig's peers is the one WireGuard's packets will
  leave by; the answer carries the round trip (``stun_rtt_us``);
* ``tunnel_up`` brings the tunnel up to the peers the hub names, as far as
  :func:`mcgyvr.rig.tunnel.plan` allows, and walks each peer's candidates in
  the hub's order, :attr:`Timing.attempt_s` each (or the hub's
  ``attempt_s``), until a WireGuard handshake confirms one — both rigs walk
  at once, so each side's handshakes open its own NAT for the other's — then
  the peer's relay, bound from this machine (:func:`bind_relay`), which it
  stays pointed at until :attr:`Timing.connect_s` (or the hub's
  ``connect_timeout_s``) is over: the peer may reach the relay later. A
  path a handshake confirms is sent a ping as large as the tunnel's interface
  carries (:data:`mcgyvr.sandbox.pooled.PING_SCRIPT`): one that answers a
  small ping and loses those cannot carry a model, so a candidate found so
  is spent like one that never answered, and a relay found so ends the walk
  at once. It is
  answered ``tunnel_report``: each peer's path (``lan``, ``direct``,
  ``relay`` or ``none``), the endpoint WireGuard uses and the round trip
  over the tunnel (also sent as ``peer_rtt``). The tunnel's table lets
  WireGuard reach only the candidate being tried, then only the confirmed
  endpoint; a peer no path reaches fails the session as ``no_path``;
* ``worker_start`` starts one RPC server per lent card, bound to the tunnel
  address and reachable by the session's peers only, and says ``ready`` when
  each listens;
* ``head_start`` starts the model server on a model of this rig's own
  inventory, on lent cards and the session's workers, and says ``loading``,
  then ``ready`` once its API answers and has answered one warm-up request
  of the agent's own (:func:`warm_up`: the first request a fresh engine
  answers pays for what it does once per process, and that is not the
  user's to wait for). While it starts, loads and serves, the head watches
  its workers over the tunnel (:meth:`Sessions._watch`): a worker not heard
  from for :attr:`Timing.peer_lost_s` fails the session as ``no_path`` (the
  hub's code for a peer no path reaches) — an engine whose worker's rig is
  gone is never told so, and would wait out its whole load. While it loads,
  it also counts what the tunnel sends its workers (:meth:`Sessions._moving`):
  a load that has not sent them :data:`LOAD_STALL_BYTES` in
  :attr:`Timing.stall_s` fails the session as ``load_stalled`` — a path that
  carries a ping and loses a full packet leaves the worker heard from and
  the weights standing still. A head on this
  rig's cards alone (a session of one rig) needs no ``tunnel_up``, only the
  prepared tunnel container its head runs in;
* ``session_query`` is answered with where the session stands;
  ``session_stop`` tears it down.

A rig may be in several sessions at once, one unit per card: each session
holds the cards its ``worker_start`` or ``head_start`` named until it is torn
down, and a command naming a card another session holds is refused ``busy``
(as is a ``session_prepare`` when every lent card is held). Each session has
its own tunnel container, its own tunnel port and its own head API port, so
nothing of one is shared with another (the ``multi_session`` feature).

Each session is one state (:data:`TRANSITIONS` is the whole table) and one
thread that does its docker work in order. A handler reads its command
(:mod:`mcgyvr.rig.sessionwire`), decides on this rig whether it may be done,
and answers at once — ``ack`` for done or accepted, or ``error`` with the
hub's code — while the work is queued to the session's thread. Every command
is idempotent: the same command again is answered the same and starts
nothing more; the same session asked for something else is refused.

When the agent's channel drops, a session waits for the hub for
:attr:`Timing.grace_s` (the hub's own grace) while the agent hurries back
(:meth:`Sessions.waiting`); the agent's hello names the sessions still
running and the hub resumes those it knows. On the hub's return each says
where it stands now (:meth:`Sessions.online`), since what it said while the
channel was down was lost with it; one the hub does not know is torn down,
whether the hub stops it or answers what it said of it with
``unknown_session`` (:meth:`Sessions.hub_error`).

Teardown is guaranteed, not hoped for. Whatever ends a session — a stop, a
failure (the hub is told ``failed`` with a code and an excerpt of what the
engine said), a hub that stays away past :attr:`Timing.grace_s`, the agent's
own exit (:meth:`Sessions.close`) — every container of it is removed, found
by its labels as well as its names. An agent killed without a word cannot
remove anything, so its tunnels outlive it only by their lease, which only a
living session renews, and the next agent removes what a dead one left
(:meth:`Sessions.sweep`).
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
    protocol,
    sessionwire,
    tensorcache,
    tunnel,
    udpwire,
)
from mcgyvr.rig import sharing as sharing_module
from mcgyvr.rig.sessionwire import SessionCode
from mcgyvr.sandbox import pooled

#: Every state a session moves through, and where it may go from each.
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
#: The states of a session that holds containers.
LIVE = frozenset(TRANSITIONS) - {"failed", "stopped"}
#: How many ended sessions are remembered, for a query or a repeated stop.
ENDED_KEPT = 16
#: How many of the frames the sessions said are remembered by id, so a hub
#: that answers one with ``unknown_session`` names the session it means.
SAID_KEPT = 64
#: How many lines of a container's output a failure carries.
LOG_LINES = 60
#: How much of a model file is read at a time for its digest, in bytes.
DIGEST_CHUNK = 1 << 22
#: How long a health check of the head's API waits, in seconds.
HEALTH_TIMEOUT_S = 2.0
#: How many times teardown looks again for what is left of a session.
TEARDOWN_ROUNDS = 3
#: The feature a rig that shares units with riders speaks: it advertises them
#: (``unit_advert``) and serves rides to them (:mod:`mcgyvr.rig.hitchhike`).
HITCHHIKE_FEATURE = "hitchhike_units"
#: The feature a rig that runs several sessions at once speaks: one unit per
#: card, never two sessions on one card (:meth:`Sessions.prepare`).
MULTI_SESSION_FEATURE = "multi_session"
#: The optional behaviours of the hub's protocol this agent speaks while it
#: lends: the latency probe (:mod:`mcgyvr.rig.probe`), the traversal of a
#: session's tunnel through the rigs' NATs (``tunnel_up`` is answered
#: ``tunnel_report``), a head of several slots (``head_start``'s ``slots``;
#: :func:`mcgyvr.sandbox.pooled.head_argv`), the shared units, and a session
#: per card.
FEATURES = (
    "probe",
    "traversal",
    "head_slots",
    HITCHHIKE_FEATURE,
    MULTI_SESSION_FEATURE,
)
#: How many sessions may live on this rig at once: one per tunnel port
#: (:meth:`mcgyvr.rig.sharing.Sharing.tunnel_ports`), the most a hello names.
MAX_LIVE_SESSIONS = sharing_module.TUNNEL_PORTS
#: How many times the machine is asked for a free loopback port for a head's
#: API before the session is refused: a port another session holds is not
#: taken.
API_PORT_TRIES = 8
#: The tunnel port's binding requests to the hub's responders: how long each
#: round waits, in milliseconds; then one request each this many seconds
#: until the tunnel comes up, for at most this long.
STUN_WAIT_MS = 500
KEEP_EVERY_S = 15
KEEP_FOR_S = 600
#: The warm-up: at most this many words of prompt (about a token each, so
#: more than one batch of the engine's), and this many tokens out.
WARM_UP_WORDS = 600
WARM_UP_TOKENS = 32
#: The share of the session's context the warm-up's prompt may take, as a
#: divisor: a quarter, so prompt, template and answer fit any context.
WARM_UP_CONTEXT_SHARE = 4
#: The code of a head whose load stopped moving. The hub's list does not name
#: it: a session's ``error_code`` is an open set, which the hub passes on.
LOAD_STALLED = "load_stalled"
#: What a loading head sends its workers over the tunnel, in bytes, within
#: :attr:`Timing.stall_s`, to count as moving: far above what pings,
#: keepalives and a stuck connection's retries send in that time, far below
#: what a load sends over the slowest link that finishes one.
LOAD_STALL_BYTES = 1 << 20


class Docker(Protocol):
    """What a session needs of the daemon: :class:`mcgyvr.sandbox.pooled.Pool`."""

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
    """How long a session's steps may take and how often it looks, in seconds."""

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
    ping_s: float = 30.0
    peer_lost_s: float = 45.0
    stall_s: float = 240.0
    warm_s: float = 300.0
    attempt_s: float = 5.0
    connect_s: float = 60.0

    @classmethod
    def quick(cls) -> Timing:
        """Timing for tests: every step a fraction of a second."""
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
            ping_s=0.5,
            peer_lost_s=0.2,
            stall_s=5.0,
            warm_s=1.0,
            attempt_s=0.05,
            connect_s=2.0,
        )


@dataclass(frozen=True, kw_only=True)
class Machine:
    """What a session needs of this machine, each read when it is needed."""

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
    """A session's step failed; ``code`` is the hub's, ``excerpt`` the engine's."""

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
    workers: tuple[tuple[int, int, int], ...] = ()  # card index, gpu, port
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
    sent: int | None = None  # the bytes the tunnel sent its workers, last look
    moved: tuple[int, float] | None = None  # ``sent`` a stall's worth ago, when
    quiet_s: float = 0.0  # the longest a load took to send a stall's worth
    traversal: sessionwire.Traversal | None = None
    stun_rtt_us: int | None = None
    report: tuple[sessionwire.PeerPath, ...] | None = None
    reported_to: list[str] = field(default_factory=list)
    released: bool = False  # its teardown is done: it holds nothing now

    @property
    def tunnel_name(self) -> str:
        return pooled.container_name(self.id, "tunnel")

    @property
    def cards(self) -> frozenset[int]:
        """The cards this session holds: those its ``worker_start`` or its
        ``head_start`` named, from when it was taken until teardown."""
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
    """A port no one listens on on this machine's loopback, now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def head_health(port: int) -> str:
    """``ok``, ``loading`` or ``down``: what the head's API on loopback ``port``
    says of itself."""
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
    """Send the head's loopback API on ``port`` one small chat completion of
    the agent's own, sized to fit a context of ``ctx``; whether it answered
    200. Nothing a user sent is in it, and nothing it answers is kept."""
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
    """The port a relay bound this rig's side of a peer to, from a socket of
    this machine's own; ``None`` when it refused or never answered."""
    try:
        answer = udpwire.bind_relay(grant.host, grant.port, grant.ticket)
    except (OSError, ValueError):
        return None
    return answer if isinstance(answer, int) else None


@cache
def _udpwire_source() -> str:
    """:mod:`mcgyvr.rig.udpwire`'s text, which the tunnel container runs."""
    return Path(udpwire.__file__).read_text(encoding="utf-8")


@dataclass
class _Walk:
    """One peer's walk over its candidates, then its relay."""

    peer: tunnel.PeerPlan
    step: int
    aim: tuple[str, int] | None
    since: float
    relayed: bool = False
    result: sessionwire.PeerPath | None = None
    held: tuple[str, int] | None = None  # the confirmed endpoint
    moved: bool = False
    rtt_us: int | None = None  # the round trip over the confirmed path
    # A path of this peer lost full-size packets: the handshake made on it
    # still stands, so what is tried after it is proved by a ping, not by it.
    narrowed: bool = False
    why: str = ""  # what was lost, for the failure of a peer left no path


def _log(line: str) -> None:
    """Say ``line`` where the agent says what it does: its standard error."""
    print(line, file=sys.stderr, flush=True)


def _ipv4(text: str) -> ipaddress.IPv4Address | None:
    try:
        return ipaddress.IPv4Address(text)
    except ValueError:
        return None


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
    """Remove the oldest files under ``folder`` until it holds at most
    ``max_mb`` MiB; nothing outside it, and no link, is ever followed."""
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
    """This rig's sessions: the handlers, the threads, and the teardown."""

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
        self._closed = False
        self._grace: threading.Timer | None = None
        self._ended_hooks: list[Callable[[str], None]] = []
        self._prepare_hooks: list[Callable[[], None]] = []
        self._said: dict[str, str] = {}  # frame id -> session id
        # The worker session whose workers mount the rig's cache, until its
        # teardown hands it to the check: the engine writes a cached tensor in
        # place and reads one back unchecked, so two sessions sent the same
        # tensors would each load the other's half-written file as whole.
        self._cache_holder: _Session | None = None
        # The files of the cache this agent hashed, and the thread hashing
        # and trimming it now, which holds it until it is done: a worker
        # killed mid-write leaves a torn file under a whole tensor's name.
        self._cache_ledger = tensorcache.Ledger()
        self._cache_check: threading.Thread | None = None
        self._cache_stop = threading.Event()

    # -- what the agent asks -------------------------------------------------

    def before_prepare(self, hook: Callable[[], None]) -> None:
        """Call ``hook`` before a new session's tunnel is started (a probe
        holding the tunnel's port lets it go)."""
        self._prepare_hooks.append(hook)

    def on_end(self, hook: Callable[[str], None]) -> None:
        """Call ``hook`` with a session's id when it ends (its relays end too)."""
        self._ended_hooks.append(hook)

    def running(self) -> tuple[str, ...]:
        """The sessions holding containers now, as a hello names them."""
        with self._lock:
            live = [s.id for s in self._sessions.values() if s.state in LIVE]
        return tuple(live[: protocol.MAX_SESSIONS_REPORTED])

    def head_port(self, session_id: str) -> int | None:
        """The loopback port of the session's head API when it is ready."""
        with self._lock:
            found = self._sessions.get(session_id)
            if found and found.role == "head" and found.state == "ready":
                return found.api_port
        return None

    def head_slots(self, session_id: str) -> int:
        """How many requests the session's head serves at once: the
        ``slots`` it was started with, one when it was not."""
        with self._lock:
            found = self._sessions.get(session_id)
            if found is not None and found.head_asked is not None:
                return found.head_asked.slots
        return sessionwire.DEFAULT_SLOTS

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        """Where session ``session_id`` stands, and its role."""
        with self._lock:
            found = self._sessions.get(session_id)
            return (found.state, found.role) if found else ("absent", None)

    def settle(self, timeout: float) -> bool:
        """Wait until no session has work queued or under way; whether it did."""
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
        """The hub is back: a session waiting out the grace is kept, and says
        where it stands now."""
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
        """Whether a session waits out the grace for the hub to return."""
        with self._lock:
            return self._grace is not None and self._live() is not None

    def hub_error(self, error: protocol.Error) -> None:
        """The hub refused a frame: one a session said, as ``unknown_session``,
        means the hub does not know that session, and it is torn down."""
        if error.code != SessionCode.UNKNOWN_SESSION or error.re is None:
            return
        with self._lock:
            session_id = self._said.get(error.re)
            found = self._sessions.get(session_id) if session_id else None
            if found is not None and found.state in LIVE:
                self._ask_stop(found)

    def offline(self) -> None:
        """The hub is gone: every session ends unless it returns within the
        grace."""
        with self._lock:
            if self._grace is None and not self._closed:
                self._grace = threading.Timer(self.timing.grace_s, self._hub_lost)
                self._grace.daemon = True
                self._grace.start()

    def close(self) -> None:
        """The agent ends: every session is torn down before this returns, and
        whatever this agent started is removed."""
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
        """Remove what an agent that is not running left; the names removed."""
        left = [
            o.name
            for o in self._docker.owned()
            if o.agent_pid is None
            or o.agent_pid == self.machine.owner.agent_pid
            or not _alive(o.agent_pid)
        ]
        self._docker.remove(left)
        return left

    # -- the handlers --------------------------------------------------------

    def prepare(self, envelope: protocol.Envelope) -> str | None:
        """``session_prepare``: answered ``session_prepared`` when the tunnel is."""
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
            # None is no refusal: a session of one rig needs no tunnel, and
            # one of several with nothing to aim at fails at tunnel_up.
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
        """``tunnel_up``: answered ``tunnel_report`` once each peer's path is
        found, or found to be none."""
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
        """``worker_start``: acked once the cards are taken; ``ready`` follows."""
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
        """``head_start``: acked once the model and devices are taken;
        ``loading`` and ``ready`` follow."""
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
        """``session_query``: answered ``session_status``."""
        asked = sessionwire.read_session_query(envelope)
        with self._lock:
            found = self._sessions.get(asked.session_id)
            if found is None:
                return sessionwire.session_status(
                    envelope.id, session_id=asked.session_id, state="absent"
                )
            return self._status(found, envelope.id)

    def stop(self, envelope: protocol.Envelope) -> str:
        """``session_stop``: acked; ``stopped`` follows once it is torn down."""
        asked = sessionwire.read_session_stop(envelope)
        with self._lock:
            found = self._sessions.get(asked.session_id)
            if found is not None and found.state in LIVE:
                self._ask_stop(found)
        return sessionwire.ack(envelope.id)

    # -- under the lock ------------------------------------------------------

    def _live(self) -> _Session | None:
        for found in self._sessions.values():
            if found.state in LIVE:
                return found
        return None

    def _holding(self, but: _Session | None = None) -> list[_Session]:
        """The sessions that hold what they took — live, or ended and not yet
        torn down — but ``but``."""
        return [
            found
            for found in self._sessions.values()
            if found is not but and not found.released
        ]

    def _held(self, but: _Session | None = None) -> frozenset[int]:
        """The cards the sessions but ``but`` hold now."""
        return frozenset(card for found in self._holding(but) for card in found.cards)

    def _tunnel_port(self, share: sharing_module.Sharing) -> int | None:
        """The tunnel port of a new session: the lowest of the owner's
        (:meth:`mcgyvr.rig.sharing.Sharing.tunnel_ports`) no session holds;
        ``None`` when every one is held, or as many sessions live as a hello
        names."""
        holding = self._holding()
        if sum(found.state in LIVE for found in holding) >= MAX_LIVE_SESSIONS:
            return None
        held = {found.listen_port for found in holding}
        return next((p for p in share.tunnel_ports() if p not in held), None)

    def _api_port(self) -> int | None:
        """A loopback port for a new head's API that no session holds."""
        held = {found.api_port for found in self._holding()}
        for _ in range(API_PORT_TRIES):
            port = self.machine.free_port()
            if port not in held:
                return port
        return None

    def _taken(self, session: _Session, cards: Sequence[int]) -> str | None:
        """Why ``session`` may not have ``cards``: one another session holds;
        ``None`` when it may."""
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

    # -- the session's thread ------------------------------------------------

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
                except Exception as failure:  # the session ends; the agent goes on
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
        """Wait one poll, renewing the lease; whether the session was stopped."""
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
        """A head's look at its workers, each :attr:`Timing.monitor_s`: a
        worker the tunnel received bytes from since the last look is heard
        from; one quiet since then is pinged over the tunnel first; one not
        heard from for :attr:`Timing.peer_lost_s` is lost."""
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
        """A loading head's look at what the tunnel sent its workers, all of
        them together (they take their layers one after another, so one
        waits while another loads): a load that has not sent them
        :data:`LOAD_STALL_BYTES` in :attr:`Timing.stall_s` has stalled. The
        longest it took to send that much is kept (``quiet_s``). A head
        alone has no worker and is never looked at. What the head reads
        from its own disk is not counted — the engine maps the file, and a
        read the machine has cached reaches no counter — so the time must
        cover the longest a head reads without sending."""
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
                LOAD_STALLED,
                f"the load stalled: the tunnel sent the workers "
                f"{max(0, session.sent - before)} bytes in {now - at:.1f} s, "
                f"under the {LOAD_STALL_BYTES} that count as moving in "
                f"{self.timing.stall_s:g} s",
                self._docker.logs(pooled.container_name(session.id, "head"), LOG_LINES),
            )

    def _loaded(self, session: _Session, started: float, how: str) -> None:
        """Say how a split load went: how long it took, and the longest it
        took to send its workers :data:`LOAD_STALL_BYTES`, which is what
        :attr:`Timing.stall_s` is to be set above."""
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
        """Warm the loaded head (:func:`warm_up`) while the session lives on:
        its lease renewed, its head and its workers watched. The warm-up is
        one request, which one slot serves, so it is sized to one slot's
        context (``ctx``), never the whole cache's."""
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
        """Ask the hub's responders from the tunnel's port, then keep the
        port's mapping alive until the tunnel comes up; the least round trip,
        or ``None``. A responder this rig may not send to is not asked, and a
        step that fails costs the round trip, never the session."""
        assert session.traversal is not None
        own = [interface for _, interface in self.machine.interfaces()]
        own.append(ipaddress.IPv4Interface(hello.address))
        servers: list[tuple[str, int]] = []
        for endpoint in session.traversal.stun[: sessionwire.MAX_STUN_ENDPOINTS]:
            host = _ipv4(endpoint.host)
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
                    not walk.relayed and now - walk.since >= attempt
                ):
                    # A candidate has its time; the relay, the last resort,
                    # is held until the deadline: the peer, walking a longer
                    # list, may only reach it later.
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
        """Point ``walk`` at the peer's next candidate, then its relay, or,
        with no relay to bind, at nothing: the peer has no path."""
        walk.moved = True
        candidates = walk.peer.candidates
        if walk.aim is not None and not walk.relayed:
            walk.step += 1  # the candidate aimed at is spent
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
        """What a ping over the tunnel to ``walk``'s peer says of the path a
        handshake just confirmed: its round trip, and whether it carries a
        full-size packet. ``None`` when the peer has no address to ping or
        the ping could not be run or answered."""
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
        """Leave the path ``walk`` is aimed at, which answers a small ping
        and loses every full-size one: a candidate is spent and the walk
        goes on; the relay, with nothing after it, leaves the peer no path —
        now, not at the deadline: waiting does not widen a path."""
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
            return
        self._next_aim(walk)
        walk.since = self._clock()

    def _confirmed(
        self, walk: _Walk, endpoint: tuple[str, int]
    ) -> sessionwire.PeerPath:
        """The path a handshake confirmed at ``endpoint``, named for what was
        aimed at (or, when WireGuard followed the peer elsewhere, for the
        candidate at that address)."""
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
        """Write the table for every peer — the confirmed endpoint alone, or
        the address being tried — and point the peers that moved."""
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
        """Answer every ``tunnel_up`` waiting with the report — each
        confirmed path with the round trip measured over it when it was
        confirmed — and fail the session when a peer has no path."""
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
        if not lost:
            # Up before the report says so: the hub acts on the report at once.
            self._move(session, "tunnel_up")
        with self._lock:
            session.report = tuple(paths)
            waiting, session.reported_to = session.reported_to, []
        for re in waiting:
            self._say(sessionwire.tunnel_report(re, session_id=session.id, peers=paths))
        if samples:
            self._say(sessionwire.peer_rtt(samples[: sessionwire.MAX_RTT_SAMPLES]))
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
        """The rig's cache folder for ``session``'s workers, which then hold
        it until their teardown; ``None`` while another session holds it or
        the agent checks it, and while it holds a file the agent has not
        hashed (the check is started then)."""
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
        """Hash ``folder``, removing every file that is not whole, then trim
        it; the check holds the folder until it is done. Called under the
        lock, with no session holding the folder."""
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
        # A head alone has no tunnel address, and no worker pair to open for
        # it: the namespace's own address stands in.
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
        # The engines first, the tunnel last; then whatever the daemon still
        # labels as this session's, found again, until nothing is left.
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
        # The holder hands the cache to the check (the hashing, then the
        # trim), which holds it until it is done: no worker mounts a file
        # the engine left torn, or reads one while it is removed.
        with self._lock:
            session.released = True
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
    """Handle the hub's session commands with ``sessions``."""
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
    """The LAN addresses a rig offers its tunnel at: the owner's, else its own."""
    hosts = share.endpoints or tuple(str(h) for h in tunnel.lan_hosts(interfaces()))
    return hosts[: protocol.MAX_ENDPOINTS]


def endpoint_kind(host: str) -> str:
    """``lan`` for an address on a LAN, ``public`` for one the owner named
    beyond it (a forwarded port, a public address)."""
    found = _ipv4(host)
    return "lan" if found is not None and tunnel.is_lan(found) else "public"


def offer(
    share: sharing_module.Sharing,
    held: inventory.Inventory,
    hosts: Sequence[str],
    running: tuple[str, ...],
) -> protocol.Offer:
    """What a hello says this rig lends.

    A rig that lends no session offers no role, so the hub sends it no
    session, and speaks the one feature of the units it shares with riders
    (:mod:`mcgyvr.rig.hitchhike`), whether it shares any now or not: sharing
    is policy the owner may turn on while the rig is connected, and the hub
    takes adverts only from a rig whose hello named the feature.
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
