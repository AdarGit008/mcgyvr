"""Drive one session's ``mcgyvr-wg`` helper: typed verbs in, strictly read replies out.

The helper (:mod:`mcgyvr.rig.wgpin`) is a child of the agent, one per native
pooled session. It owns the session's UDP socket and WireGuard key, runs the
netstack the tunnel lives in, starts the session's engines as its own
children and forwards to them only what the session names. It is started
detached (:func:`mcgyvr.hostos.popen_detached_kwargs`) and, on Windows, put in
a Job Object that ends it with the agent (:func:`mcgyvr.hostos.kill_on_close_job`);
it ends itself, and its children, when its stdin closes or its lease lapses.

The grammar is the helper spec's (proto :data:`mcgyvr.rig.wgpin.PROTO`): one
JSON object a line each way. The helper first writes a banner naming itself,
its version and its proto, which must be the pinned ones. Each request names
its ``id`` and ``verb`` and exactly the verb's fields; each reply carries the
same ``id`` and either ``"ok": true`` with exactly the verb's result fields, or
``"ok": false`` with an ``error`` from :data:`ERRORS` and a short ``why``. A
reply that is anything else — another id, a key too many or too few, a value
of the wrong type or out of range, a line that is not one object, a line too
long, no reply in time — is not believed: the call raises
:class:`HelperError` and the helper is ended. No raw configuration line ever
reaches the helper: every value is checked here before it is sent, so a
peer's key or a host cannot carry a second instruction.

:class:`HelperError` is a :class:`mcgyvr.rig.pooled.PoolError`, so the session
fails exactly as it does when a container step fails.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from mcgyvr import hostos
from mcgyvr.rig import pooled, sessionwire, wgpin

#: The longest line either side may write, in bytes.
LINE_MAX = 65536
#: The longest ``why`` a refusal may carry.
WHY_MAX = 300
#: Why the helper may refuse a request (the spec's closed set for proto 1).
ERRORS = frozenset(
    {
        "bad_request",
        "bad_state",
        "bind_failed",
        "no_answer",
        "unknown_part",
        "spawn_failed",
        "internal",
    }
)
#: The parts a session runs through the helper: a head (workers come later).
PARTS = ("head",)
#: The states a part may be in.
PART_STATES = ("running", "exited", "absent")
#: How long the banner, and any one reply, may take.
BANNER_S = 10.0
REPLY_S = 30.0
#: How long the helper may take to exit after ``teardown`` before it is killed.
EXIT_S = 15.0
#: The most of each list the grammar carries.
MAX_HOSTS = sessionwire.MAX_ENDPOINTS
MAX_SERVERS = sessionwire.MAX_STUN_ENDPOINTS
MAX_PEERS = sessionwire.MAX_PEERS
MAX_ALLOWED = sessionwire.MAX_ALLOWED_IPS
MAX_ARGV = 256
MAX_ENV = 512
#: The lowest port a forward may dial, and a socket may listen on: as low as an
#: unprivileged server binds.
LOWEST_PORT = 1024
#: The MTU range ``up`` takes.
MTU_RANGE = (576, 1420)
#: A port as a reply writes it: ASCII digits, no leading zero.
PORT = re.compile(r"[1-9][0-9]{0,4}")
#: The largest whole number either side writes (counters, epoch seconds, ids).
MAX_COUNT = 2**63 - 1
MAX_ID = 2**31 - 1


class HelperError(pooled.PoolError):
    """The helper refused a request, broke the grammar, or is gone.

    ``code`` is the helper's error (one of :data:`ERRORS`), or ``protocol``
    when its reply was not believed, or ``gone`` when it is not running.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class UpPeer:
    """A peer as ``up`` names it: key, first endpoint (host ``None`` for none),
    keepalive seconds and allowed networks."""

    key: str
    host: str | None
    port: int
    keepalive: int
    allowed: tuple[str, ...]


@dataclass(frozen=True)
class AimPeer:
    """A peer as ``aim`` names it: key, the host and port aimed at (``None``
    and 0 for none), whether the source port must match, whether the endpoint
    moves."""

    key: str
    host: str | None
    port: int
    exact: bool
    moved: bool


# --- value checks, the same both ways ------------------------------------------


def _int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _ipv4(value: object) -> bool:
    if type(value) is not str or len(value) > 15:
        return False
    try:
        return str(ipaddress.IPv4Address(value)) == value
    except ValueError:
        return False


def _bindable(value: object) -> bool:
    """An address a session's socket may bind: this host's own unicast
    address, not the wildcard, the loopback, a multicast or the broadcast."""
    if not _ipv4(value):
        return False
    found = ipaddress.IPv4Address(str(value))
    return not (
        found.is_unspecified
        or found.is_loopback
        or found.is_multicast
        or found == ipaddress.IPv4Address("255.255.255.255")
    )


def _cidr(value: object) -> bool:
    if type(value) is not str or "/" not in value or len(value) > 18:
        return False
    try:
        return str(ipaddress.IPv4Interface(value)) == value
    except ValueError:
        return False


def _key(value: object) -> bool:
    return type(value) is str and bool(sessionwire.WIREGUARD_KEY.fullmatch(value))


def _endpoint(value: object) -> bool:
    if type(value) is not str:
        return False
    host, colon, port = value.rpartition(":")
    return (
        bool(colon)
        and _ipv4(host)
        and PORT.fullmatch(port) is not None
        and int(port) <= 65535
    )


def _text(value: object, most: int) -> bool:
    return type(value) is str and len(value) <= most and value.isprintable()


def _token(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 32
        and all(c in "0123456789abcdef" for c in value)
    )


def _path(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= 4096
        and "\x00" not in value
        and os.path.isabs(value)
    )


def _list(value: object, most: int, item: Callable[[object], bool]) -> bool:
    return type(value) is list and len(value) <= most and all(item(v) for v in value)


def _record(value: object, fields: Mapping[str, Callable[[object], bool]]) -> bool:
    return (
        type(value) is dict
        and set(value) == set(fields)
        and all(check(value[name]) for name, check in fields.items())
    )


def _milliseconds(value: object) -> bool:
    if type(value) is int:
        return 0 <= value <= 10**9
    return type(value) is float and math.isfinite(value) and 0.0 <= value <= 1e9


def _part(value: object) -> bool:
    return value in PARTS


#: Each verb's result fields and how each is checked.
RESULTS: dict[str, dict[str, Callable[[object], bool]]] = {
    "prepare": {"public_key": _key},
    "stun": {
        "rtts": lambda v: _list(
            v,
            MAX_SERVERS,
            lambda r: (
                type(r) is list
                and len(r) == 3
                and _ipv4(r[0])
                and _int(r[1], 1, 65535)
                and _int(r[2], 0, MAX_COUNT)
            ),
        )
    },
    "keep": {},
    "up": {},
    "aim": {},
    "peers": {
        "now": lambda v: _int(v, 0, MAX_COUNT),
        "peers": lambda v: _list(
            v,
            MAX_PEERS,
            lambda p: _record(
                p,
                {
                    "key": _key,
                    "handshake": lambda h: _int(h, 0, MAX_COUNT),
                    "endpoint": lambda e: e is None or _endpoint(e),
                },
            ),
        ),
    },
    "ping": {
        "rtt_ms": lambda v: v is None or _milliseconds(v),
        "full": lambda v: type(v) is bool,
        "size": lambda v: _int(v, 1, MTU_RANGE[1]),
    },
    "transfer": {
        "peers": lambda v: _list(
            v,
            MAX_PEERS,
            lambda p: _record(
                p,
                {
                    "key": _key,
                    "rx": lambda n: _int(n, 0, MAX_COUNT),
                    "tx": lambda n: _int(n, 0, MAX_COUNT),
                },
            ),
        )
    },
    "spawn": {"pid": lambda v: _int(v, 1, MAX_ID)},
    "forward": {"port": lambda v: _int(v, LOWEST_PORT, 65535)},
    "state": {
        "state": lambda v: v in PART_STATES,
        "exit": lambda v: v is None or _int(v, -(2**31), 2**32 - 1),
    },
    "kill": {},
    "lease": {},
    "teardown": {},
}


def read_reply(line: bytes, expected_id: int, verb: str) -> dict[str, Any]:
    """The result fields of one reply line, or :class:`HelperError`.

    A refusal raises with the helper's own code; anything that is not exactly a
    reply to request ``expected_id`` of ``verb`` raises with ``protocol`` —
    whatever else reading it raised (a nesting too deep, a key given twice, a
    number too large) included.
    """
    try:
        return _read_reply(line, expected_id, verb)
    except HelperError:
        raise
    except Exception as exc:  # anything a hostile line provokes is not believed
        raise HelperError(
            "protocol", f"{verb}: the helper's reply does not read"
        ) from exc


def _loads(line: bytes) -> Any:
    """One JSON value, with no NaN or Infinity and no key given twice."""
    return json.loads(line, parse_constant=_no_constant, object_pairs_hook=_no_twice)


def _no_twice(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    found = dict(pairs)
    if len(found) != len(pairs):
        raise ValueError("a key given twice")
    return found


def _read_reply(line: bytes, expected_id: int, verb: str) -> dict[str, Any]:
    if len(line) > LINE_MAX or not line.endswith(b"\n"):
        raise HelperError("protocol", f"{verb}: the helper's reply is not one line")
    try:
        reply = _loads(line)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise HelperError(
            "protocol", f"{verb}: the helper's reply is not JSON"
        ) from exc
    if (
        type(reply) is not dict
        or reply.get("id") != expected_id
        or type(reply.get("id")) is not int
    ):
        raise HelperError("protocol", f"{verb}: the helper answered another request")
    ok = reply.get("ok")
    if ok is False:
        if (
            set(reply) != {"id", "ok", "error", "why"}
            or type(reply["error"]) is not str
            or reply["error"] not in ERRORS
            or not _text(reply["why"], WHY_MAX)
        ):
            raise HelperError("protocol", f"{verb}: the helper's refusal does not read")
        raise HelperError(reply["error"], f"{verb}: {reply['error']}: {reply['why']}")
    fields = RESULTS[verb]
    result = {k: v for k, v in reply.items() if k not in ("id", "ok")}
    if ok is not True or not _record(result, fields):
        raise HelperError("protocol", f"{verb}: the helper's reply does not read")
    return result


def read_banner(line: bytes) -> str:
    """The version the helper's banner names, or :class:`HelperError` when the
    banner is not the pinned helper speaking the pinned proto."""
    if len(line) > LINE_MAX or not line.endswith(b"\n"):
        raise HelperError("protocol", "the helper wrote no banner")
    try:
        banner = _loads(line)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise HelperError("protocol", "the helper's banner is not JSON") from exc
    if not _record(
        banner,
        {
            "id": lambda v: v == 0 and type(v) is int,
            "ok": lambda v: v is True,
            "helper": lambda v: v == wgpin.PROGRAM,
            "version": lambda v: _text(v, 64),
            "proto": lambda v: type(v) is int,
        },
    ):
        raise HelperError("protocol", "the helper's banner does not read")
    if banner["proto"] != wgpin.PROTO or banner["version"] != wgpin.TAG:
        raise HelperError(
            "protocol",
            f"the helper is {banner['version']} speaking proto {banner['proto']}; "
            f"this agent pins {wgpin.TAG} speaking proto {wgpin.PROTO}",
        )
    return str(banner["version"])


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise HelperError("bad_request", f"not sent: {what}")


def open_log(path: Path) -> IO[bytes]:
    """``path`` opened to append, in a folder of this user's alone, never
    through a link, readable by this user alone where modes say so."""
    from mcgyvr.userdir import private_dir

    if private_dir(path.parent, make=True) is None:
        raise HelperError(
            "gone", f"{path.parent} is not this user's own folder; no log is kept"
        )
    hostos.chmod_private(path.parent, directory=True)
    try:
        fd = hostos.open_nofollow(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | hostos.open_flags_binary(),
            0o600,
        )
    except OSError as exc:
        raise HelperError("gone", f"{path} could not be opened: {exc}") from exc
    return os.fdopen(fd, "ab")


class Helper:
    """One running helper and the verbs it is asked, one at a time.

    ``argv`` starts the pinned program (``session`` is added); its stderr goes
    to ``log``. Every call holds one lock, since the session's thread and the
    agent's close may ask at once. A call that fails for a reason other than
    the helper's own refusal (``protocol``, ``gone``) ends the helper.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        log: Path,
        env: Mapping[str, str] | None = None,
        banner_s: float = BANNER_S,
        reply_s: float = REPLY_S,
    ) -> None:
        self._argv = [*argv, "session"]
        self._log = log
        self._env = dict(env) if env is not None else None
        self._banner_s = banner_s
        self._reply_s = reply_s
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._job: int | None = None
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._next = 1
        self.version: str | None = None

    # The process.

    def start(self) -> None:
        """Start the helper and read its banner; :class:`HelperError` when it
        cannot be started or is not the pinned helper."""
        with open_log(self._log) as err:
            common: dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": err,
                "close_fds": True,
                "env": self._env,
            }
            try:
                try:
                    proc = subprocess.Popen(
                        self._argv, **common, **hostos.popen_detached_kwargs()
                    )
                except PermissionError:
                    # A job that forbids breaking away refuses the start (Windows).
                    proc = subprocess.Popen(
                        self._argv,
                        **common,
                        **hostos.popen_detached_kwargs(breakaway=False),
                    )
            except OSError as exc:
                raise HelperError("gone", f"the helper did not start: {exc}") from exc
        self._proc = proc
        self._job = hostos.kill_on_close_job(proc)
        assert proc.stdout is not None
        threading.Thread(
            target=_read_lines,
            args=(proc.stdout, self._lines),
            name="mcgyvr-wg-reader",
            daemon=True,
        ).start()
        try:
            self.version = read_banner(self._line(self._banner_s, "the banner"))
        except HelperError:
            self.end()
            raise

    def alive(self) -> bool:
        """Whether the helper process still runs."""
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def end(self) -> None:
        """End the helper: close its stdin (its teardown), then kill it if it has
        not exited within :data:`EXIT_S`."""
        proc = self._proc
        if proc is None:
            return
        with contextlib.suppress(OSError):
            if proc.stdin is not None:
                proc.stdin.close()
        try:
            proc.wait(timeout=EXIT_S)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=EXIT_S)
        job, self._job = self._job, None
        if job is not None and sys.platform == "win32":
            import _winapi

            # The job's last handle: closing it ends whatever is left in it.
            with contextlib.suppress(OSError):
                _winapi.CloseHandle(job)

    def _line(self, budget: float, what: str) -> bytes:
        try:
            line = self._lines.get(timeout=budget)
        except queue.Empty:
            raise HelperError("protocol", f"{what}: no reply in {budget:g} s") from None
        if not line:
            raise HelperError("gone", f"{what}: the helper exited")
        return line

    def call(self, verb: str, **fields: Any) -> dict[str, Any]:
        """Send one request and return its reply's result fields."""
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None or proc.stdin is None:
                raise HelperError("gone", f"{verb}: the helper is not running")
            request_id = self._next
            if request_id > MAX_ID:
                self.end()
                raise HelperError("protocol", f"{verb}: the request ids ran out")
            self._next += 1
            line = (
                json.dumps(
                    {"id": request_id, "verb": verb, **fields},
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            _need(len(line) <= LINE_MAX, f"{verb} is longer than a line")
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
                reply = self._line(self._reply_s, verb)
                return read_reply(reply, request_id, verb)
            except HelperError as exc:
                if exc.code in ("protocol", "gone"):
                    self.end()
                raise
            except OSError as exc:
                self.end()
                raise HelperError("gone", f"{verb}: the helper is gone: {exc}") from exc

    # The verbs, each value checked before it is sent.

    def prepare(self, listen_port: int, hosts: Sequence[str], lease_s: int) -> str:
        _need(_int(listen_port, LOWEST_PORT, 65535), "listen_port")
        _need(0 < len(hosts) <= MAX_HOSTS and all(_bindable(h) for h in hosts), "hosts")
        _need(_int(lease_s, 1, 3600), "lease_s")
        found = self.call(
            "prepare", listen_port=listen_port, hosts=list(hosts), lease_s=lease_s
        )
        return str(found["public_key"])

    def _servers(self, servers: Sequence[tuple[str, int]]) -> list[list[Any]]:
        _need(
            0 < len(servers) <= MAX_SERVERS
            and all(_ipv4(h) and _int(p, 1, 65535) for h, p in servers),
            "servers",
        )
        return [[h, p] for h, p in servers]

    def stun(
        self,
        token: str,
        servers: Sequence[tuple[str, int]],
        attempts: int,
        wait_ms: int,
    ) -> list[tuple[str, int, int]]:
        _need(_token(token), "token")
        _need(_int(attempts, 1, 10) and _int(wait_ms, 1, 10000), "attempts, wait_ms")
        found = self.call(
            "stun",
            token=token,
            servers=self._servers(servers),
            attempts=attempts,
            wait_ms=wait_ms,
        )
        return [(str(h), int(p), int(us)) for h, p, us in found["rtts"]]

    def keep(
        self, token: str, servers: Sequence[tuple[str, int]], every_s: int, for_s: int
    ) -> None:
        _need(_token(token), "token")
        _need(_int(every_s, 1, 300) and _int(for_s, 1, 86400), "every_s, for_s")
        self.call(
            "keep",
            token=token,
            servers=self._servers(servers),
            every_s=every_s,
            for_s=for_s,
        )

    def up(self, address: str, mtu: int, peers: Sequence[UpPeer]) -> None:
        _need(_cidr(address), "address")
        _need(_int(mtu, *MTU_RANGE), "mtu")
        _need(0 < len(peers) <= MAX_PEERS, "peers")
        body = []
        for peer in peers:
            _need(_key(peer.key), "a peer's key")
            _need(peer.host is None or _ipv4(peer.host), "a peer's host")
            _need(_int(peer.port, 0, 65535), "a peer's port")
            _need(_int(peer.keepalive, 0, 65535), "a peer's keepalive")
            _need(
                0 < len(peer.allowed) <= MAX_ALLOWED
                and all(_cidr(net) for net in peer.allowed),
                "a peer's allowed networks",
            )
            body.append(
                {
                    "key": peer.key,
                    "host": peer.host,
                    "port": peer.port,
                    "keepalive": peer.keepalive,
                    "allowed": list(peer.allowed),
                }
            )
        self.call("up", address=address, mtu=mtu, peers=body)

    def aim(self, peers: Sequence[AimPeer]) -> None:
        _need(0 < len(peers) <= MAX_PEERS, "peers")
        body = []
        for peer in peers:
            _need(_key(peer.key), "a peer's key")
            _need(peer.host is None or _ipv4(peer.host), "a peer's host")
            _need(_int(peer.port, 0, 65535), "a peer's port")
            body.append(
                {
                    "key": peer.key,
                    "host": peer.host,
                    "port": peer.port,
                    "exact": bool(peer.exact),
                    "moved": bool(peer.moved),
                }
            )
        self.call("aim", peers=body)

    def _pokes(self, pokes: Sequence[str]) -> list[str]:
        _need(len(pokes) <= MAX_PEERS and all(_ipv4(h) for h in pokes), "pokes")
        return list(pokes)

    def peers(self, pokes: Sequence[str]) -> pooled.PeersSeen:
        found = self.call("peers", pokes=self._pokes(pokes))
        handshakes: dict[str, int] = {}
        endpoints: dict[str, tuple[str, int]] = {}
        for peer in found["peers"]:
            handshakes[peer["key"]] = peer["handshake"]
            if peer["endpoint"] is not None:
                host, _, port = peer["endpoint"].rpartition(":")
                endpoints[peer["key"]] = (host, int(port))
        return pooled.PeersSeen(
            now=found["now"], handshakes=handshakes, endpoints=endpoints
        )

    def ping(self, host: str, size: int, count: int) -> pooled.PingSeen:
        _need(_ipv4(host), "host")
        _need(_int(size, 1, MTU_RANGE[1]) and _int(count, 1, 10), "size, count")
        found = self.call("ping", host=host, size=size, count=count)
        if found["size"] != size:
            self.end()
            raise HelperError("protocol", "ping: the helper pinged another size")
        rtt = found["rtt_ms"]
        return pooled.PingSeen(
            rtt_ms=None if rtt is None else float(rtt),
            full=found["full"],
            size=found["size"],
        )

    def transfer(self, pokes: Sequence[str]) -> tuple[dict[str, int], dict[str, int]]:
        found = self.call("transfer", pokes=self._pokes(pokes))
        received = {p["key"]: p["rx"] for p in found["peers"]}
        sent = {p["key"]: p["tx"] for p in found["peers"]}
        return received, sent

    def spawn(
        self,
        part: str,
        program: Path,
        argv: Sequence[str],
        env: Mapping[str, str],
        cwd: Path,
        log: Path,
    ) -> int:
        _need(_part(part), "part")
        _need(_path(str(program)) and _path(str(cwd)) and _path(str(log)), "paths")
        _need(
            len(argv) <= MAX_ARGV
            and all(type(a) is str and "\x00" not in a for a in argv),
            "argv",
        )
        _need(
            len(env) <= MAX_ENV
            and all(
                type(k) is str
                and type(v) is str
                and k
                and "=" not in k
                and "\x00" not in k + v
                for k, v in env.items()
            ),
            "env",
        )
        found = self.call(
            "spawn",
            part=part,
            program=str(program),
            argv=list(argv),
            env=dict(env),
            cwd=str(cwd),
            log=str(log),
        )
        return int(found["pid"])

    def forward(self, part: str, host: str, port: int) -> int:
        _need(_part(part), "part")
        _need(_ipv4(host) and _int(port, LOWEST_PORT, 65535), "to")
        found = self.call("forward", part=part, to=f"{host}:{port}")
        return int(found["port"])

    def state(self, part: str) -> tuple[str, int | None]:
        _need(_part(part), "part")
        found = self.call("state", part=part)
        return str(found["state"]), found["exit"]

    def kill(self, part: str) -> None:
        _need(_part(part), "part")
        self.call("kill", part=part)

    def lease(self) -> None:
        self.call("lease")

    def teardown(self) -> None:
        """Ask the helper to end everything, then wait for it to exit."""
        with contextlib.suppress(HelperError):
            self.call("teardown")
        self.end()


def _read_lines(stream: IO[bytes], into: queue.Queue[bytes]) -> None:
    """Put each line the helper writes into ``into``; ``b""`` once it closes.

    A line longer than :data:`LINE_MAX` is cut there and put as it is, so the
    parser refuses it rather than this thread waiting for its end.
    """
    try:
        while True:
            line = stream.readline(LINE_MAX + 1)
            if not line:
                break
            into.put(line)
    except (OSError, ValueError):
        pass
    finally:
        into.put(b"")
