"""A stand-in for the ``mcgyvr-wg`` helper: the helper spec's grammar, no WireGuard.

Run as ``python -I fake_wg_helper.py <config.json> session``. It writes the
banner, then answers one JSON request a line on stdin with one JSON reply a
line on stdout, refusing any request whose fields are not exactly the verb's
(``bad_request``) or that comes out of order (``bad_state``). The tunnel is
make-believe — every peer it is pointed at shakes hands at once and answers
pings — but the parts are real: ``spawn`` starts the program as this
process's child, and ``forward`` binds 127.0.0.1, accepts a connection only
when its socket belongs to the spawned part's pid (read from ``/proc``, so
Linux only), and pipes it to the address ``routes`` maps the forward's
target to.

The config file names ``record`` (a file each request and each forward event
is appended to as a JSON line), ``routes`` (``"host:port"`` of a tunnel
address to ``"127.0.0.1:port"`` here), ``version`` (the banner's), and
``start_token`` (the start time ``spawn`` answers instead of the child's
own), and ``faults`` (``{verb: how}``, how one of ``refuse``, ``garbage``,
``extra_key``, ``wrong_id``, ``die``, ``silent``) to break the grammar on cue.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from typing import Any

KEY = "C" * 42 + "w="

STATE: dict[str, Any] = {
    "prepared": False,
    "up": False,
    "lease_s": 60,
    "lease_at": 0.0,
    "aims": {},
    "children": {},
    "rx": 0,
}
LOCK = threading.Lock()
OUT = threading.Lock()


def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        found: dict[str, Any] = json.load(handle)
    return found


CONFIG: dict[str, Any] = {}


def record(event: dict[str, Any]) -> None:
    target = CONFIG.get("record")
    if target:
        with LOCK, open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")


def write(reply: dict[str, Any]) -> None:
    with OUT:
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


# The verbs' fields: each a check of one value.


def _ipv4(v: Any) -> bool:
    try:
        return isinstance(v, str) and str(__import__("ipaddress").IPv4Address(v)) == v
    except ValueError:
        return False


def _int(v: Any, low: int, high: int) -> bool:
    return type(v) is int and low <= v <= high


def _str(v: Any) -> bool:
    return isinstance(v, str)


def _key(v: Any) -> bool:
    from mcgyvr.rig.sessionwire import WIREGUARD_KEY

    return isinstance(v, str) and bool(WIREGUARD_KEY.fullmatch(v))


def _cidr(v: Any) -> bool:
    import ipaddress

    try:
        return isinstance(v, str) and str(ipaddress.IPv4Interface(v)) == v
    except ValueError:
        return False


def _token(v: Any) -> bool:
    return (
        isinstance(v, str) and len(v) == 32 and all(c in "0123456789abcdef" for c in v)
    )


def _to(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    host, _, port = v.rpartition(":")
    return _ipv4(host) and port.isdigit() and 1024 <= int(port) <= 65535


def _servers(v: Any) -> bool:
    return (
        isinstance(v, list)
        and 1 <= len(v) <= 2
        and all(
            isinstance(s, list) and len(s) == 2 and _ipv4(s[0]) and _int(s[1], 1, 65535)
            for s in v
        )
    )


def _pokes(v: Any) -> bool:
    return isinstance(v, list) and len(v) <= 15 and all(_ipv4(h) for h in v)


def _up_peer(p: Any) -> bool:
    return (
        isinstance(p, dict)
        and set(p) == {"key", "host", "port", "keepalive", "allowed"}
        and _key(p["key"])
        and all(map(_cidr, p["allowed"]))
        and (p["host"] is None or _ipv4(p["host"]))
        and _int(p["port"], 0, 65535)
        and _int(p["keepalive"], 0, 65535)
        and isinstance(p["allowed"], list)
        and 1 <= len(p["allowed"]) <= 4
    )


def _aim_peer(p: Any) -> bool:
    return (
        isinstance(p, dict)
        and set(p) == {"key", "host", "port", "exact", "moved"}
        and _key(p["key"])
        and (p["host"] is None or _ipv4(p["host"]))
        and type(p["exact"]) is bool
        and type(p["moved"]) is bool
    )


FIELDS: dict[str, dict[str, Any]] = {
    "prepare": {
        "listen_port": lambda v: _int(v, 1024, 65535),
        "hosts": lambda v: (
            isinstance(v, list) and 1 <= len(v) <= 8 and all(map(_ipv4, v))
        ),
        "lease_s": lambda v: _int(v, 1, 3600),
    },
    "stun": {
        "token": _token,
        "servers": _servers,
        "attempts": lambda v: _int(v, 1, 10),
        "wait_ms": lambda v: _int(v, 1, 10000),
    },
    "keep": {
        "token": _token,
        "servers": _servers,
        "every_s": lambda v: _int(v, 1, 300),
        "for_s": lambda v: _int(v, 1, 86400),
    },
    "up": {
        "address": _cidr,
        "mtu": lambda v: _int(v, 576, 1420),
        "peers": lambda v: (
            isinstance(v, list) and 1 <= len(v) <= 15 and all(map(_up_peer, v))
        ),
    },
    "aim": {
        "peers": lambda v: (
            isinstance(v, list) and 1 <= len(v) <= 15 and all(map(_aim_peer, v))
        )
    },
    "peers": {"pokes": _pokes},
    "ping": {
        "host": _ipv4,
        "size": lambda v: _int(v, 1, 1420),
        "count": lambda v: _int(v, 1, 10),
    },
    "transfer": {"pokes": _pokes},
    "spawn": {
        "part": lambda v: v == "head",
        "program": lambda v: _str(v) and os.path.isabs(v),
        "argv": lambda v: isinstance(v, list) and len(v) <= 256 and all(map(_str, v)),
        "env": lambda v: (
            isinstance(v, dict) and len(v) <= 512 and all(map(_str, v.values()))
        ),
        "cwd": lambda v: _str(v) and os.path.isabs(v),
        "log": lambda v: _str(v) and os.path.isabs(v),
    },
    "forward": {"part": lambda v: v == "head", "to": _to},
    "state": {"part": lambda v: v == "head"},
    "kill": {"part": lambda v: v == "head"},
    "lease": {},
    "teardown": {},
}
#: The verbs that come only after ``up``, and those only before it.
AFTER_UP = {"aim", "peers", "ping", "transfer", "forward"}
BEFORE_UP = {"stun", "keep", "up"}


def end_children() -> None:
    for proc in list(STATE["children"].values()):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def owner_of(local: tuple[str, int], peer: tuple[str, int]) -> set[int]:
    """The pids holding the socket whose local end is ``peer`` and remote end
    ``local``: the connecting side of an accepted connection (Linux /proc)."""

    def hexed(address: tuple[str, int]) -> str:
        quad = socket.inet_aton(address[0])[::-1].hex().upper()
        return f"{quad}:{address[1]:04X}"

    inode = None
    with open("/proc/net/tcp", encoding="ascii") as table:
        for line in table.readlines()[1:]:
            words = line.split()
            if words[1] == hexed(peer) and words[2] == hexed(local):
                inode = words[9]
    if inode is None:
        return set()
    found = set()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                if os.readlink(f"/proc/{pid}/fd/{fd}") == f"socket:[{inode}]":
                    found.add(int(pid))
        except OSError:
            continue
    return found


def pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while chunk := a.recv(65536):
            b.sendall(chunk)
    except OSError:
        pass
    finally:
        with contextlib.suppress(OSError):
            b.shutdown(socket.SHUT_WR)  # half-close: the answer may still come back


def serve_forward(listener: socket.socket, part: str, to: str) -> None:
    while True:
        try:
            conn, peer = listener.accept()
        except OSError:
            return
        child = STATE["children"].get(part)
        owners = owner_of(listener.getsockname(), peer)
        if child is None or child.poll() is not None or child.pid not in owners:
            record({"event": "refused", "to": to, "owners": sorted(owners)})
            sys.stderr.write(f"forward to {to}: refused a socket not the {part}'s\n")
            conn.close()
            continue
        route = CONFIG.get("routes", {}).get(to)
        if route is None:
            conn.close()
            continue
        host, _, port = route.rpartition(":")
        out = socket.create_connection((host, int(port)))
        record({"event": "accepted", "to": to, "pid": child.pid})
        threading.Thread(target=pipe, args=(conn, out), daemon=True).start()
        threading.Thread(target=pipe, args=(out, conn), daemon=True).start()


def answer(verb: str, req: dict[str, Any]) -> dict[str, Any]:
    if verb == "prepare":
        STATE["prepared"] = True
        STATE["lease_s"] = req["lease_s"]
        STATE["lease_at"] = time.monotonic()
        return {"public_key": KEY}
    if verb == "stun":
        return {"rtts": [[s[0], s[1], 1500] for s in req["servers"]]}
    if verb == "up":
        STATE["up"] = True
        for peer in req["peers"]:
            if peer["host"] is not None:
                STATE["aims"][peer["key"]] = f"{peer['host']}:{peer['port']}"
            else:
                STATE["aims"].setdefault(peer["key"], None)
        return {}
    if verb == "aim":
        for peer in req["peers"]:
            if peer["moved"] and peer["host"] is not None:
                STATE["aims"][peer["key"]] = f"{peer['host']}:{peer['port']}"
        return {}
    if verb == "peers":
        return {
            "now": int(time.time()),
            "peers": [
                {"key": k, "handshake": int(time.time()) if a else 0, "endpoint": a}
                for k, a in STATE["aims"].items()
            ],
        }
    if verb == "ping":
        return {"rtt_ms": 0.512, "full": True, "size": req["size"]}
    if verb == "transfer":
        STATE["rx"] += 148
        return {
            "peers": [
                {"key": k, "rx": STATE["rx"], "tx": int(CONFIG.get("tx", 4096))}
                for k in STATE["aims"]
            ]
        }
    if verb == "spawn":
        part = req["part"]
        old = STATE["children"].get(part)
        if old is not None and old.poll() is None:
            raise RefusedError("bad_state", "the part runs")
        with open(req["log"], "ab") as log:
            proc = subprocess.Popen(
                [req["program"], *req["argv"]],
                env=req["env"],
                cwd=req["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        STATE["children"][part] = proc
        with open(f"/proc/{proc.pid}/stat", encoding="ascii") as stat:
            start = stat.read().rsplit(")", 1)[1].split()[19]
        return {"pid": proc.pid, "start": CONFIG.get("start_token", start)}
    if verb == "forward":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        threading.Thread(
            target=serve_forward, args=(listener, req["part"], req["to"]), daemon=True
        ).start()
        return {"port": listener.getsockname()[1]}
    if verb == "state":
        proc = STATE["children"].get(req["part"])
        if proc is None:
            return {"state": "absent", "exit": None}
        code = proc.poll()
        return {"state": "running" if code is None else "exited", "exit": code}
    if verb == "kill":
        proc = STATE["children"].pop(req["part"], None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        return {}
    if verb == "lease":
        STATE["lease_at"] = time.monotonic()
        return {}
    return {}


class RefusedError(Exception):
    def __init__(self, code: str, why: str) -> None:
        super().__init__(why)
        self.code = code
        self.why = why


def watch_lease() -> None:
    while True:
        time.sleep(0.05)
        if (
            STATE["prepared"]
            and time.monotonic() - STATE["lease_at"] > STATE["lease_s"]
        ):
            sys.stderr.write("lease ran out\n")
            end_children()
            os._exit(0)


def main() -> int:
    CONFIG.update(load_config(sys.argv[1]))
    assert sys.argv[2] == "session"
    write(
        {
            "id": 0,
            "ok": True,
            "helper": "mcgyvr-wg",
            "version": CONFIG["version"],
            "proto": int(CONFIG.get("proto", 1)),
        }
    )
    threading.Thread(target=watch_lease, daemon=True).start()
    faults = CONFIG.get("faults", {})
    for line in sys.stdin:
        req = json.loads(line)
        record(req)
        rid, verb = req.get("id"), req.get("verb")
        fault = faults.get(verb)
        if fault == "die":
            end_children()
            return 9
        if fault == "silent":
            continue
        if fault == "garbage":
            with OUT:
                sys.stdout.write("not json\n")
                sys.stdout.flush()
            continue
        try:
            if verb not in FIELDS:
                raise RefusedError("bad_request", f"no verb {verb!r}")
            fields = FIELDS[verb]
            given = {k: v for k, v in req.items() if k not in ("id", "verb")}
            if set(given) != set(fields) or not all(
                check(given[k]) for k, check in fields.items()
            ):
                raise RefusedError("bad_request", f"{verb}: not its fields")
            if fault == "refuse":
                raise RefusedError("bad_state", f"{verb}: refused as told")
            if verb != "prepare" and not STATE["prepared"]:
                raise RefusedError("bad_state", f"{verb} before prepare")
            if verb in AFTER_UP and not STATE["up"]:
                raise RefusedError("bad_state", f"{verb} before up")
            if verb in BEFORE_UP and STATE["up"]:
                raise RefusedError("bad_state", f"{verb} after up")
            if verb == "prepare" and STATE["prepared"]:
                raise RefusedError("bad_state", "prepare twice")
            result = answer(verb, given)
            reply = {"id": rid, "ok": True, **result}
            if fault == "extra_key":
                reply["extra"] = 1
            if fault == "wrong_id":
                reply["id"] = rid + 1
            write(reply)
        except RefusedError as refused:
            record({"event": "refusal", "verb": verb, "code": refused.code})
            write({"id": rid, "ok": False, "error": refused.code, "why": refused.why})
        if verb == "teardown":
            end_children()
            return 0
    end_children()  # stdin closed: the agent is gone
    return 0


if __name__ == "__main__":
    sys.exit(main())
