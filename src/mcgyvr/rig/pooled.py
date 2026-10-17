""

from __future__ import annotations

import hashlib
import ipaddress
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.rig.sessionwire import WIREGUARD_KEY
from mcgyvr.sandbox.image import DockerResult, DockerRunner, subprocess_runner

#
LABEL = "mcgyvr.pool"
LABEL_SESSION = "mcgyvr.pool.session"
LABEL_AGENT = "mcgyvr.pool.agent"
LABEL_PART = "mcgyvr.pool.part"

#
SECCOMP_PROFILE = Path(__file__).with_name("pooled-seccomp.json")

#
#
TUNNEL_DOCKERFILE = (
    "FROM alpine:3.22@sha256:"
    "5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8\n"
    "RUN apk add --no-cache wireguard-go wireguard-tools-wg nftables "
    "iproute2-minimal python3\n"
)
#
TUNNEL_REPOSITORY = "mcgyvr-tunnel"

#
HEAD_API_PORT = 8080
#
CACHE_MOUNT = "/rpc-cache"
MODELS_MOUNT = "/models"
#
KV_CACHE_TYPE = "q8_0"
#
LEASE_FILE = "/run/mcgyvr/lease"
#
#
KEEPER_PID_FILE = "/run/mcgyvr/stun.pid"
#
TUNNEL_PYTHON = "python3"

#
#
TUNNEL_PIDS = 64
WORKER_PIDS = 256
HEAD_PIDS = 512
#
#
#
TUNNEL_MEMORY_MB = 1024
#
#
TUNNEL_GO_MEMORY_MB = TUNNEL_MEMORY_MB * 3 // 4
#
#
#
#
#
TUNNEL_MTU = 1200
#
#
#
PING_HEADERS = 28
#
#
FULL_PINGS = 3
#
TUNNEL_TMPFS = "/run:rw,nosuid,nodev,noexec,size=1m"
ENGINE_TMPFS = "/tmp:rw,nosuid,nodev,noexec,size=64m"

#
#
#
#
TUNNEL_ENTRY = (
    r"""set -eu
umask 077
port="$1"
lease_s="$2"
mkdir -p /run/mcgyvr
touch /run/mcgyvr/lease
nft -f - <<'RULES'
table inet mcgyvr {
  chain stun_in { }
  chain stun_out { }
  chain wg_in { }
  chain wg_out { }
  chain input {
    type filter hook input priority 0; policy drop;
    iif "lo" accept
    jump stun_in
    jump wg_in
  }
  chain output {
    type filter hook output priority 0; policy drop;
    oif "lo" accept
    jump stun_out
    jump wg_out
  }
  chain forward { type filter hook forward priority 0; policy drop; }
}
RULES
wireguard-go -f wg0 >/dev/null 2>&1 &
wg_pid=$!
tries=0
while [ ! -S /run/wireguard/wg0.sock ]; do
  tries=$((tries + 1))
  if [ "$tries" -gt 100 ]; then echo "failed: no wireguard interface"; exit 3; fi
  sleep 0.1
done
wg genkey | wg set wg0 private-key /dev/stdin
"""
    + f"ip link set wg0 mtu {TUNNEL_MTU} up\n"
    + r"""echo "public-key $(wg show wg0 public-key)"
echo "address $(ip -4 -o addr show dev eth0 | awk '{print $4; exit}')"
echo "gateway $(ip -4 route show default | awk '{print $3; exit}')"
echo "ready"
while kill -0 "$wg_pid" 2>/dev/null; do
  now=$(date +%s)
  seen=$(stat -c %Y /run/mcgyvr/lease)
  if [ $((now - seen)) -gt "$lease_s" ]; then
    echo "lease ran out"
    kill "$wg_pid"
    exit 0
  fi
  sleep 2
done
echo "wireguard ended"
exit 4
"""
)

#
#
#
STUN_SCRIPT = r"""set -eu
port="$1"
shift
{
  echo "flush chain inet mcgyvr stun_in"
  echo "flush chain inet mcgyvr stun_out"
  while [ "$#" -ge 2 ]; do
    echo "add rule inet mcgyvr stun_out oifname eth0 ip daddr $1 \
udp sport $port udp dport $2 accept"
    echo "add rule inet mcgyvr stun_in iifname eth0 ip saddr $1 \
udp sport $2 udp dport $port accept"
    shift 2
  done
} | nft -f -
echo "open"
"""

#
#
#
#
#
#
#
#
#
#
#
TUNNEL_SCRIPT = r"""set -eu
self="$1"
port="$2"
shift 2
if [ -f /run/mcgyvr/stun.pid ]; then
  keeper=$(cat /run/mcgyvr/stun.pid)
  kill "$keeper" 2>/dev/null || true
  tries=0
  while kill -0 "$keeper" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -gt 50 ]; then echo "failed: the binding keeper lives on"; exit 3; fi
    sleep 0.1
  done
  rm -f /run/mcgyvr/stun.pid
fi
own="${self%/*}"
add="add rule inet mcgyvr"
icmp="icmp type { echo-request, echo-reply }"
table() {
  echo "flush chain inet mcgyvr stun_in"
  echo "flush chain inet mcgyvr stun_out"
  echo "flush chain inet mcgyvr wg_in"
  echo "flush chain inet mcgyvr wg_out"
  while [ "$#" -ge 5 ]; do
    if [ "$2" != "-" ]; then
      echo "$add wg_in iifname eth0 ip saddr $2 udp dport $port accept"
      echo "$add wg_out oifname eth0 ip daddr $2 udp sport $port accept"
    fi
    for net in $(echo "$5" | tr ',' ' '); do
      echo "$add input iifname wg0 ip saddr $net ip daddr $own $icmp accept"
      echo "$add output oifname wg0 ip saddr $own ip daddr $net $icmp accept"
    done
    shift 5
  done
}
table "$@" | nft -f -
wg set wg0 listen-port "$port"
ip address add "$self" dev wg0
while [ "$#" -ge 5 ]; do
  if [ "$2" = "-" ]; then
    wg set wg0 peer "$1" allowed-ips "$5" persistent-keepalive "$4"
  else
    wg set wg0 peer "$1" allowed-ips "$5" endpoint "$2:$3" \
      persistent-keepalive "$4"
  fi
  shift 5
done
echo "up"
"""

#
#or
#
#
#
#
#
#
PATH_SCRIPT = r"""set -eu
port="$1"
shift
table() {
  echo "flush chain inet mcgyvr wg_in"
  echo "flush chain inet mcgyvr wg_out"
  while [ "$#" -ge 5 ]; do
    if [ "$2" != "-" ]; then
      if [ "$4" = "exact" ]; then
        echo "add rule inet mcgyvr wg_in iifname eth0 ip saddr $2 \
udp sport $3 udp dport $port accept"
        echo "add rule inet mcgyvr wg_out oifname eth0 ip daddr $2 \
udp dport $3 udp sport $port accept"
      else
        echo "add rule inet mcgyvr wg_in iifname eth0 ip saddr $2 \
udp dport $port accept"
        echo "add rule inet mcgyvr wg_out oifname eth0 ip daddr $2 \
udp sport $port accept"
      fi
    fi
    shift 5
  done
}
table "$@" | nft -f -
while [ "$#" -ge 5 ]; do
  if [ "$2" != "-" ] && [ "$5" = "1" ]; then
    wg set wg0 peer "$1" endpoint "$2:$3"
  fi
  shift 5
done
echo "aimed"
"""

#
#
#
#
PEERS_SCRIPT = r"""for host in "$@"; do
  ping -c 1 -W 1 -q "$host" >/dev/null 2>&1 &
done
wait
echo "now $(date +%s)"
wg show wg0 latest-handshakes | sed 's/^/handshake /'
wg show wg0 endpoints | sed 's/^/endpoint /'
"""

#
#
OPEN_WORKER_SCRIPT = r"""set -eu
self="$1"
port="$2"
shift 2
for net in "$@"; do
  echo "add rule inet mcgyvr input iifname wg0 ip saddr $net ip daddr $self \
tcp dport $port accept"
  echo "add rule inet mcgyvr output oifname wg0 ip saddr $self ip daddr $net \
tcp sport $port accept"
done | nft -f -
echo "open"
"""

#
#
#
#
#
#
#
OPEN_HEAD_SCRIPT = r"""set -eu
self="$1"
gateway="$2"
shift 2
range=$(cat /proc/sys/net/ipv4/ip_local_port_range)
low=$(echo $range | cut -d' ' -f1)
high=$(echo $range | cut -d' ' -f2)
{
  echo "add rule inet mcgyvr input iifname eth0 ip saddr $gateway \
tcp dport 8080 accept"
  echo "add rule inet mcgyvr output oifname eth0 ip daddr $gateway \
tcp sport 8080 accept"
  while [ "$#" -ge 2 ]; do
    echo "add rule inet mcgyvr output oifname wg0 ip saddr $self ip daddr $1 \
tcp dport $2 accept"
    echo "add rule inet mcgyvr input iifname wg0 ip saddr $1 ip daddr $self \
tcp sport $2 tcp dport $low-$high accept"
    shift 2
  done
} | nft -f -
echo "open"
"""

#
#
LISTENING_SCRIPT = r"""set -eu
hex=$(echo "$1" | awk -F. '{printf "%02X%02X%02X%02X", $4, $3, $2, $1}')
port=$(printf '%04X' "$2")
grep -q " $hex:$port 00000000:0000 0A " /proc/net/tcp
"""

#
#
#
#
#
#
#
#
#
#
PING_SCRIPT = (
    r"""set -eu
ping -c 1 -W 2 -q "$1" >/dev/null
ping -c 5 -i 0.2 -W 1 -q "$1" | awk -F/ '/min\/avg/ {print $4}'
"""
    + f"size=$(( $(cat /sys/class/net/wg0/mtu) - {PING_HEADERS} ))\n"
    + f'if ping -c {FULL_PINGS} -i 0.2 -W 1 -q -s "$size" "$1" >/dev/null 2>&1; then\n'
    + r"""  echo "full ok $size"
else
  echo "full lost $size"
fi
"""
)

#
#
#
#
#
TRANSFER_SCRIPT = r"""for host in "$@"; do
  ping -c 1 -W 1 -q "$host" >/dev/null 2>&1 &
done
wait
wg show wg0 transfer
"""

#
GUARD_SCRIPT = r""""$@" &
child=$!
trap 'kill "$child" 2>/dev/null' TERM INT
while kill -0 "$child" 2>/dev/null; do
  if [ ! -e /sys/class/net/wg0 ]; then
    kill "$child" 2>/dev/null
    wait "$child"
    exit 70
  fi
  sleep 2
done
wait "$child"
"""

_NAME_DIGEST = 12
#
_COUNT_DIGITS = 20
_TUNNEL_LINE = re.compile(r"(public-key|address|gateway) (\S+)")
#t.
_TRANSFER_LINE = re.compile(
    rf"({WIREGUARD_KEY.pattern})\t(\d{{1,{_COUNT_DIGITS}}})\t(\d{{1,{_COUNT_DIGITS}}})"
)


class PoolError(Exception):
    ""


@dataclass(frozen=True, kw_only=True)
class Owner:
    ""

    uid: int
    gid: int
    agent_pid: int


@dataclass(frozen=True, kw_only=True)
class TunnelSpec:
    ""

    session_id: str
    image: str
    listen_port: int
    publish: tuple[str, ...]  #
    api_port: int | None  #
    lease_s: int


@dataclass(frozen=True, kw_only=True)
class WorkerSpec:
    ""

    session_id: str
    image: str
    binary: str
    gpu: int  #
    bind: str
    port: int
    cache_dir: Path | None
    memory_mb: int


@dataclass(frozen=True, kw_only=True)
class HeadSpec:
    ""

    session_id: str
    image: str
    binary: str
    gpus: tuple[int, ...]  #
    models_dir: Path
    model: str  #
    name: str  #
    ctx: int  #
    n_gpu_layers: int
    devices: tuple[str, ...]  #
    tensor_split: tuple[int, ...]
    rpc: tuple[str, ...]  #
    bind: str  #
    memory_mb: int
    slots: int = 1  #


@dataclass(frozen=True, kw_only=True)
class TunnelHello:
    ""

    public_key: str
    address: str  #
    gateway: str


def container_name(session_id: str, part: str) -> str:
    ""
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:_NAME_DIGEST]
    return f"mcgyvr-pool-{digest}-{part}"


def tunnel_image() -> str:
    ""
    digest = hashlib.sha256(TUNNEL_DOCKERFILE.encode()).hexdigest()[:_NAME_DIGEST]
    return f"{TUNNEL_REPOSITORY}:{digest}"


def _labels(session_id: str, part: str, owner: Owner) -> list[str]:
    return [
        "--label",
        f"{LABEL}=1",
        "--label",
        f"{LABEL_SESSION}={session_id}",
        "--label",
        f"{LABEL_PART}={part}",
        "--label",
        f"{LABEL_AGENT}={owner.agent_pid}",
    ]


def _engine_lockdown(owner: Owner, memory_mb: int, pids: int) -> list[str]:
    return [
        "--user",
        f"{owner.uid}:{owner.gid}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--security-opt",
        f"seccomp={SECCOMP_PROFILE}",
        "--read-only",
        "--tmpfs",
        ENGINE_TMPFS,
        "--ipc",
        "private",
        "--pids-limit",
        str(pids),
        "--memory",
        f"{memory_mb}m",
        "--memory-swap",
        f"{memory_mb}m",
        "--env",
        "HOME=/tmp",
        "--env",
        "CUDA_DEVICE_ORDER=PCI_BUS_ID",
    ]


def tunnel_argv(spec: TunnelSpec, owner: Owner) -> list[str]:
    ""
    argv = [
        "run",
        "--detach",
        "--name",
        container_name(spec.session_id, "tunnel"),
        *_labels(spec.session_id, "tunnel", owner),
        "--cap-drop",
        "ALL",
        "--cap-add",
        "NET_ADMIN",
        "--security-opt",
        "no-new-privileges=true",
        "--read-only",
        "--tmpfs",
        TUNNEL_TMPFS,
        "--device",
        "/dev/net/tun",
        "--pids-limit",
        str(TUNNEL_PIDS),
        "--memory",
        f"{TUNNEL_MEMORY_MB}m",
        "--memory-swap",
        f"{TUNNEL_MEMORY_MB}m",
        "--env",
        f"GOMEMLIMIT={TUNNEL_GO_MEMORY_MB}MiB",
    ]
    for host in spec.publish:
        argv += ["--publish", f"{host}:{spec.listen_port}:{spec.listen_port}/udp"]
    if spec.api_port is not None:
        argv += ["--publish", f"127.0.0.1:{spec.api_port}:{HEAD_API_PORT}/tcp"]
    argv += [
        "--entrypoint",
        "/bin/sh",
        spec.image,
        "-c",
        TUNNEL_ENTRY,
        "mcgyvr-tunnel",
        str(spec.listen_port),
        str(spec.lease_s),
    ]
    return argv


def worker_argv(spec: WorkerSpec, owner: Owner) -> list[str]:
    ""
    part = f"worker-{spec.gpu}"
    argv = [
        "run",
        "--detach",
        "--name",
        container_name(spec.session_id, part),
        *_labels(spec.session_id, part, owner),
        "--network",
        f"container:{container_name(spec.session_id, 'tunnel')}",
        "--gpus",
        f"device={spec.gpu}",
        *_engine_lockdown(owner, spec.memory_mb, WORKER_PIDS),
    ]
    cache: list[str] = []
    if spec.cache_dir is not None:
        argv += [
            "--volume",
            f"{spec.cache_dir}:{CACHE_MOUNT}:rw",
            "--env",
            f"LLAMA_CACHE={CACHE_MOUNT}",
        ]
        cache = ["-c"]
    argv += [
        "--entrypoint",
        "/bin/sh",
        spec.image,
        "-c",
        GUARD_SCRIPT,
        "mcgyvr-guard",
        spec.binary,
        "-H",
        spec.bind,
        "-p",
        str(spec.port),
        "-d",
        "CUDA0",
        *cache,
    ]
    return argv


def head_argv(spec: HeadSpec, owner: Owner) -> list[str]:
    ""
    argv = [
        "run",
        "--detach",
        "--name",
        container_name(spec.session_id, "head"),
        *_labels(spec.session_id, "head", owner),
        "--network",
        f"container:{container_name(spec.session_id, 'tunnel')}",
    ]
    if spec.gpus:
        listed = ",".join(str(gpu) for gpu in spec.gpus)
        argv += ["--gpus", f'"device={listed}"']
    argv += [
        *_engine_lockdown(owner, spec.memory_mb, HEAD_PIDS),
        "--volume",
        f"{spec.models_dir}:{MODELS_MOUNT}:ro",
        "--entrypoint",
        "/bin/sh",
        spec.image,
        "-c",
        GUARD_SCRIPT,
        "mcgyvr-guard",
        spec.binary,
        "-m",
        f"{MODELS_MOUNT}/{spec.model}",
        "--alias",
        spec.name,
        "-ngl",
        str(spec.n_gpu_layers),
        "-sm",
        "layer",
        "-np",
        str(spec.slots),
        "-c",
        str(spec.slots * spec.ctx),
        "-fa",
        "on",
        "-ctk",
        KV_CACHE_TYPE,
        "-ctv",
        KV_CACHE_TYPE,
        "--host",
        spec.bind,
        "--port",
        str(HEAD_API_PORT),
    ]
    if spec.rpc:
        argv += ["--rpc", ",".join(spec.rpc)]
    argv += [
        "-dev",
        ",".join(spec.devices),
        "-ts",
        ",".join(str(share) for share in spec.tensor_split),
    ]
    return argv


def read_tunnel_hello(logs: str) -> TunnelHello | None:
    ""
    said: dict[str, str] = {}
    ready = False
    for line in logs.splitlines():
        if line.strip() == "ready":
            ready = True
        found = _TUNNEL_LINE.fullmatch(line.strip())
        if found:
            said[found.group(1)] = found.group(2)
    if not ready or set(said) != {"public-key", "address", "gateway"}:
        return None
    return TunnelHello(
        public_key=said["public-key"],
        address=said["address"],
        gateway=said["gateway"],
    )


def _read_counts(said: str, column: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in said.splitlines():
        found = _TRANSFER_LINE.fullmatch(line.strip())
        if found:
            counts[found.group(1)] = int(found.group(column))
    return counts


def read_transfer(said: str) -> dict[str, int]:
    ""
    return _read_counts(said, 2)


def read_sent(said: str) -> dict[str, int]:
    ""
    return _read_counts(said, 3)


_FULL_LINE = re.compile(r"full (ok|lost) (\d{1,5})")


@dataclass(frozen=True, kw_only=True)
class PingSeen:
    ""

    rtt_ms: float | None = None
    full: bool | None = None
    size: int | None = None

    @property
    def narrow(self) -> bool:
        ""
        return self.rtt_ms is not None and self.full is False


def read_ping(said: str) -> PingSeen:
    ""
    rtt: float | None = None
    full: bool | None = None
    size: int | None = None
    for line in said.splitlines():
        line = line.strip()
        found = _FULL_LINE.fullmatch(line)
        if found:
            full, size = found.group(1) == "ok", int(found.group(2))
            continue
        if rtt is None and len(line) < _COUNT_DIGITS:
            try:
                read = float(line)
            except ValueError:
                continue
            if math.isfinite(read) and read >= 0:
                rtt = read
    return PingSeen(rtt_ms=rtt, full=full, size=size)


@dataclass(frozen=True, kw_only=True)
class PeersSeen:
    ""

    now: int
    handshakes: dict[str, int]
    endpoints: dict[str, tuple[str, int]]


_PEER_LINE = re.compile(
    rf"(handshake|endpoint) ({WIREGUARD_KEY.pattern})\t"
    rf"(\d{{1,{_COUNT_DIGITS}}}|\d{{1,3}}(?:\.\d{{1,3}}){{3}}:\d{{1,5}}|\(none\))"
)


def read_peers(said: str) -> PeersSeen | None:
    ""
    now = None
    handshakes: dict[str, int] = {}
    endpoints: dict[str, tuple[str, int]] = {}
    for line in said.splitlines():
        line = line.strip()
        if line.startswith("now ") and line[4:].isdigit() and len(line) < 32:
            now = int(line[4:])
            continue
        found = _PEER_LINE.fullmatch(line)
        if found is None:
            continue
        what, key, value = found.groups()
        if what == "handshake" and value.isdigit():
            handshakes[key] = int(value)
        elif what == "endpoint" and ":" in value:
            host, _, port = value.partition(":")
            try:
                ipaddress.IPv4Address(host)
            except ValueError:
                continue
            if 1 <= int(port) <= 65535:
                endpoints[key] = (host, int(port))
    if now is None:
        return None
    return PeersSeen(now=now, handshakes=handshakes, endpoints=endpoints)


@dataclass(frozen=True, kw_only=True)
class Owned:
    ""

    name: str
    session_id: str
    agent_pid: int | None
    running: bool


class Pool:
    ""

    def __init__(self, runner: DockerRunner = subprocess_runner) -> None:
        self._runner = runner

    def _call(self, args: Sequence[str], what: str) -> DockerResult:
        result = self._runner(list(args), None)
        if not result.ok:
            said = " ".join((result.stderr or result.stdout).split())[:300]
            raise PoolError(f"docker {what} failed ({result.returncode}): {said}")
        return result

    def ensure_tunnel_image(self) -> str:
        ""
        tag = tunnel_image()
        found = self._runner(["image", "inspect", "--format", "{{.Id}}", tag], None)
        if found.ok:
            return tag
        built = self._runner(
            ["build", "--quiet", "--tag", tag, "-"], TUNNEL_DOCKERFILE.encode()
        )
        if not built.ok:
            said = " ".join(built.stderr.split())[:300]
            raise PoolError(f"docker build of {tag} failed: {said}")
        return tag

    def start(self, argv: Sequence[str]) -> None:
        ""
        self._call(argv, "run")

    def run_script(self, name: str, script: str, *args: str) -> str:
        ""
        result = self._call(
            ["exec", name, "/bin/sh", "-c", script, "mcgyvr", *args], "exec"
        )
        return result.stdout

    def run_python(self, name: str, source: str, *args: str) -> str:
        ""
        result = self._call(
            ["exec", name, TUNNEL_PYTHON, "-I", "-c", source, *args], "exec"
        )
        return result.stdout

    def start_python(self, name: str, source: str, *args: str) -> None:
        ""
        self._call(
            ["exec", "--detach", name, TUNNEL_PYTHON, "-I", "-c", source, *args],
            "exec",
        )

    def try_script(self, name: str, script: str, *args: str) -> bool:
        ""
        result = self._runner(
            ["exec", name, "/bin/sh", "-c", script, "mcgyvr", *args], None
        )
        return result.ok

    def renew_lease(self, name: str) -> bool:
        ""
        return self._runner(["exec", name, "touch", LEASE_FILE], None).ok

    def logs(self, name: str, tail: int) -> str:
        ""
        result = self._runner(["logs", "--tail", str(tail), name], None)
        return result.stdout + result.stderr

    def state(self, name: str) -> str | None:
        ""
        result = self._runner(
            ["container", "inspect", "--format", "{{.State.Status}}", name], None
        )
        return result.stdout.strip() if result.ok else None

    def remove(self, names: Sequence[str]) -> None:
        ""
        if names:
            self._runner(["rm", "--force", "--volumes", *names], None)

    def owned(self) -> list[Owned]:
        ""
        result = self._call(
            [
                "ps",
                "--all",
                "--filter",
                f"label={LABEL}=1",
                "--format",
                f'{{{{.Names}}}}\t{{{{.Label "{LABEL_SESSION}"}}}}\t'
                f'{{{{.Label "{LABEL_AGENT}"}}}}\t{{{{.State}}}}',
            ],
            "ps",
        )
        found: list[Owned] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 4 or not parts[0]:
                continue
            name, session, agent, state = parts
            found.append(
                Owned(
                    name=name,
                    session_id=session,
                    agent_pid=int(agent) if agent.isdigit() else None,
                    running=state == "running",
                )
            )
        return found
