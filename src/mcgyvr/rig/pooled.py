"""Docker containers for one pooled-inference session.

A session is a tunnel container plus the containers that join its network
namespace: `tunnel_argv`, `worker_argv` and `head_argv` build the `docker run`
argv for those parts, and every container is labelled so a later sweep can find
it again. The tunnel container runs `TUNNEL_ENTRY` as its entrypoint, which
starts wireguard-go, installs an nft table that drops everything by default, and
prints the facts read by `read_tunnel_hello`. The other scripts here are run
inside that container with `docker exec`: they open and close firewall holes for
the wireguard ports and the RPC ports, aim peers at candidate endpoints, and
report handshakes, byte counters and ping results, which `read_peers`,
`read_transfer`, `read_sent` and `read_ping` parse back. `Pool` wraps a
`DockerRunner` for all of it and raises `PoolError` with docker's own message
when a step fails.
"""

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

# Docker labels on every container this module starts; `owned` reads them back.
LABEL = "mcgyvr.pool"
LABEL_SESSION = "mcgyvr.pool.session"
LABEL_AGENT = "mcgyvr.pool.agent"
LABEL_PART = "mcgyvr.pool.part"

# Seccomp profile for the worker and head containers, beside this module.
SECCOMP_PROFILE = Path(__file__).with_name("pooled-seccomp.json")

# The tunnel image: a pinned alpine digest with wireguard-go, wg, nft and
# iproute2, plus python3 for the probe loops. Pool builds it when it is missing.
TUNNEL_DOCKERFILE = (
    "FROM alpine:3.22@sha256:"
    "5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8\n"
    "RUN apk add --no-cache wireguard-go wireguard-tools-wg nftables "
    "iproute2-minimal python3\n"
)
# Repository name the tunnel image is tagged with; the tag is a digest of the file.
TUNNEL_REPOSITORY = "mcgyvr-tunnel"

# Port llama-server listens on inside the head; api_port is published onto it.
HEAD_API_PORT = 8080
# Where a worker's cache volume and the rig's model folder are mounted.
CACHE_MOUNT = "/rpc-cache"
MODELS_MOUNT = "/models"
# KV cache type for llama-server: -ctk and -ctv both get this value.
KV_CACHE_TYPE = "q8_0"
# Touched by Pool.renew_lease; the entrypoint exits once its mtime lags by lease_s.
LEASE_FILE = "/run/mcgyvr/lease"
# Where the detached STUN keep-alive writes its pid, so the next TUNNEL_SCRIPT can
# kill it before it rebinds the listen port.
KEEPER_PID_FILE = "/run/mcgyvr/stun.pid"
# Interpreter in the tunnel container; run_python and start_python exec it with -I.
TUNNEL_PYTHON = "python3"

# --pids-limit per container: the tunnel runs wireguard-go and the probe loops,
# a worker one rpc server under the guard script, and a head one llama-server.
TUNNEL_PIDS = 64
WORKER_PIDS = 256
HEAD_PIDS = 512
# Memory limit for the tunnel container, in MiB; --memory-swap is the same number,
# so the container cannot swap above it. That budget has to hold wireguard-go, nft,
# wg and the probe loops, which is why the Go runtime below is capped at a fraction.
TUNNEL_MEMORY_MB = 1024
# GOMEMLIMIT for wireguard-go in MiB: three quarters of the container's memory, which
# leaves a quarter for the Go runtime's non-heap overhead, nft, wg and the probes.
TUNNEL_GO_MEMORY_MB = TUNNEL_MEMORY_MB * 3 // 4
# MTU of the wg0 interface, set by TUNNEL_ENTRY with `ip link`. It is the largest
# inner packet the tunnel carries; wireguard adds its own headers on top of it. The
# probes read it back from /sys/class/net/wg0/mtu and ping TUNNEL_MTU minus
# PING_HEADERS bytes, so a path that carries small packets can be told from one that
# carries a full-size payload; a peer that fails that ping makes the session too narrow.
TUNNEL_MTU = 1200
# Bytes ICMP adds to a ping payload: the 20-byte IP header and the 8-byte ICMP header.
# PING_SCRIPT subtracts it from the wg0 MTU to get the payload that fills a tunnel
# packet; the MTU is read inside the container, so the probe follows the live value.
PING_HEADERS = 28
# Full-size pings PING_SCRIPT sends; one reply makes ping succeed, so "full ok" means
# at least one of them came back and "full lost" means none did.
FULL_PINGS = 3
# Writable tmpfs over each read-only root: /run in the tunnel, /tmp (HOME) in engines.
TUNNEL_TMPFS = "/run:rw,nosuid,nodev,noexec,size=1m"
ENGINE_TMPFS = "/tmp:rw,nosuid,nodev,noexec,size=64m"

# Entrypoint of the tunnel container (`sh -c` with TUNNEL_ENTRY, the listen port and
# the lease seconds): install an nft table inet mcgyvr whose input, output and forward
# policies drop everything but loopback and the rules the later scripts add, start
# wireguard-go on wg0, print public-key, address, gateway and ready, watch the lease.
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

# Open the tunnel's UDP listen port to the given STUN servers: flush the stun chains,
# then allow, in both directions on eth0, that port against each server address and
# port pair (host, port, host, port, ...). The STUN probe binds the port after this.
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

# Bring the tunnel up. The arguments are what TunnelPlan.script_args() returns: the
# interface address in CIDR form, the listen port, and five words per peer: its public
# key, endpoint host or "-", endpoint port, keepalive seconds and allowed-ips.
# It first stops any keep-alive loop left by an earlier run, whose pid it finds in
# KEEPER_PID_FILE and which holds the listen port, then rewrites the whole table:
# flush the stun and wg chains, allow the wireguard port to each peer's endpoint on
# eth0, allow ICMP inside the tunnel between this address and each allowed network,
# set the listen port, add the address to wg0, and point each peer at its endpoint
# (leaving it unaimed when the host is "-") with its allowed-ips and keepalive.
# It prints "up" once all of that is in place; PATH_SCRIPT re-aims peers later.
# These rules match the peer's address and the listen port, not its source port.
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

# Move peers to the candidate addresses the walkers are testing. The arguments are the
# listen port, then five words per peer: public key, host or "-", port, a mode word
# and a moved flag, the same shape TUNNEL_SCRIPT takes. Only the wg chains are
# rewritten: flush them, then for each peer allow the listen port to and from its aim
# on eth0, matching the aim's own port too when the mode is "exact" and any port from
# that host when it is not (a peer aimed at "-" gets no rule at all). The wireguard
# endpoint is set to the aim only when the moved flag is "1", so a peer that is merely
# being tested keeps the endpoint it had. It prints "aimed" once nft has them.
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

# Poke each given host with one ping so wireguard handshakes happen, then print the
# epoch time and one line per peer for `wg show wg0 latest-handshakes` and `wg show
# wg0 endpoints`, prefixed "handshake " and "endpoint " so read_peers can tell them
# apart. A peer that answers nothing still appears, with a zero handshake and "(none)".
PEERS_SCRIPT = r"""for host in "$@"; do
  ping -c 1 -W 1 -q "$host" >/dev/null 2>&1 &
done
wait
echo "now $(date +%s)"
wg show wg0 latest-handshakes | sed 's/^/handshake /'
wg show wg0 endpoints | sed 's/^/endpoint /'
"""

# Open a worker's RPC port to the tunnel: for each peer network, allow TCP from wg0 to
# this address and port, and the replies back out, so the head can reach the server.
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

# Open the head's side of the tunnel. The arguments are this rig's tunnel address, the
# container gateway and one host/port pair per remote rpc device. On eth0 it allows the
# gateway to reach the head's API port, which is how the published port gets in. On wg0
# it allows the head to open TCP to each rpc device's address and port, and allows the
# replies to come back to the head's address on any port of the local ephemeral range
# the kernel picks for those outgoing connections
# (/proc/sys/net/ipv4/ip_local_port_range). It prints "open" once nft takes them.
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

# Does the given address and port already have a listening TCP socket? Both are turned
# into the hex form /proc/net/tcp uses and matched on an entry in state 0A (LISTEN).
LISTENING_SCRIPT = r"""set -eu
hex=$(echo "$1" | awk -F. '{printf "%02X%02X%02X%02X", $4, $3, $2, $1}')
port=$(printf '%04X' "$2")
grep -q " $hex:$port 00000000:0000 0A " /proc/net/tcp
"""

# Probe one peer host from inside the tunnel; the host is the only argument. A single
# ping must be answered or the script gives up (set -e), which tells a dead path from a
# slow one; then five pings at 0.2 s print the average round-trip time in milliseconds,
# the fourth field of ping's round-trip min/avg/max line once it is split on "/".
# The rest of the script asks whether the path carries a full-size tunnel packet: the
# payload is the wg0 MTU less PING_HEADERS, it is pinged FULL_PINGS times, and the
# script prints "full ok <size>" if at least one reply comes back and "full lost
# <size>" if none does. read_ping reports both parts, and PingSeen.narrow is the case
# that matters: small pings get through and a full-size one does not. A host that
# answers no small ping at all makes the script exit non-zero.
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

# Poke each given host with one ping so the peers on the other side have something to
# answer, then print `wg show wg0 transfer`: one line per peer with its public key and
# the bytes it received and sent.
# The pings go out in parallel and are waited for, and no ping's status matters;
# read_transfer and read_sent read the two counters out of the lines that parse.
TRANSFER_SCRIPT = r"""for host in "$@"; do
  ping -c 1 -W 1 -q "$host" >/dev/null 2>&1 &
done
wait
wg show wg0 transfer
"""

# Run the server; kill it on TERM/INT or when wg0 is gone (exit 70); return its status.
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
# Longest run of digits accepted for a counter, a handshake time or a bare rtt line.
_COUNT_DIGITS = 20
_TUNNEL_LINE = re.compile(r"(public-key|address|gateway) (\S+)")
# A `wg show wg0 transfer` line: the peer key, then its received and sent byte counts.
_TRANSFER_LINE = re.compile(
    rf"({WIREGUARD_KEY.pattern})\t(\d{{1,{_COUNT_DIGITS}}})\t(\d{{1,{_COUNT_DIGITS}}})"
)


class PoolError(Exception):
    """A docker step failed; the message names the step and quotes docker's output."""


@dataclass(frozen=True, kw_only=True)
class Owner:
    """The local user the containers run as, and the agent that started them.

    The engine containers run with --user uid:gid, so they write to this rig's
    cache and model folder as an unprivileged user rather than as root. The pid
    goes into the LABEL_AGENT label, which is how a sweep tells the containers of
    an agent that has died from those of a live one.
    """

    uid: int
    gid: int
    agent_pid: int


@dataclass(frozen=True, kw_only=True)
class TunnelSpec:
    """What one session's tunnel container needs: the session it belongs to, the
    image to run, the UDP port wireguard listens on, the addresses to publish that
    port on, the loopback port the head's API is published on (None when the
    session has no head) and how long the lease lasts, in seconds.
    """

    session_id: str
    image: str
    listen_port: int
    publish: tuple[str, ...]  # this rig's addresses to publish the listen port on
    api_port: int | None  # loopback port publishing the head's API; None with no head
    lease_s: int


@dataclass(frozen=True, kw_only=True)
class WorkerSpec:
    """What one worker container needs: the session, the image, the rpc server
    binary, the card it serves, the address and port to listen on inside the tunnel,
    an optional host cache folder to mount, and its memory limit in MiB.
    """

    session_id: str
    image: str
    binary: str
    gpu: int  # the card this worker serves; the only device its container sees
    bind: str
    port: int
    cache_dir: Path | None
    memory_mb: int


@dataclass(frozen=True, kw_only=True)
class HeadSpec:
    """What the head container needs: the session and image, the llama-server
    binary, the local cards to expose, the host folder holding the models and the
    model file inside it, the settings llama-server is started with, and the rpc
    devices on other rigs it should spread the model over.
    """

    session_id: str
    image: str
    binary: str
    gpus: tuple[int, ...]  # local cards to expose; empty when running on rpc only
    models_dir: Path
    model: str  # model file relative to models_dir, passed to -m
    name: str  # the alias llama-server serves it under (--alias)
    ctx: int  # context per slot; the -c argument is slots * ctx
    n_gpu_layers: int
    devices: tuple[str, ...]  # -dev list: CUDA<n> local cards, RPC<n> remote ones
    tensor_split: tuple[int, ...]
    rpc: tuple[str, ...]  # host:port of each remote rpc device, joined for --rpc
    bind: str  # address llama-server listens on (--host): this rig's tunnel address
    memory_mb: int
    slots: int = 1  # parallel slots (-np); the context and KV cache scale with it


@dataclass(frozen=True, kw_only=True)
class TunnelHello:
    """What TUNNEL_ENTRY printed before it was ready: the wireguard public key, the
    container's address on eth0 with its prefix, and its default gateway.
    """

    public_key: str
    address: str  # the container's eth0 address in CIDR form, from `ip -4 -o addr`
    gateway: str


def container_name(session_id: str, part: str) -> str:
    """The container name for one part of a session: "mcgyvr-pool-", the first
    twelve hex digits of the session id's sha256, then the part. Hashing keeps the
    name short and legal for docker while still differing per session, and the part
    keeps the tunnel, each worker and the head apart.
    """
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:_NAME_DIGEST]
    return f"mcgyvr-pool-{digest}-{part}"


def tunnel_image() -> str:
    """The tunnel image's tag: TUNNEL_REPOSITORY, with a digest of TUNNEL_DOCKERFILE
    as the tag, so a change to the Dockerfile asks for a different image.
    """
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
    """The `docker run` argv for a session's tunnel container.

    `spec.image` is the tunnel image. The container gets NET_ADMIN and no other
    capability, /dev/net/tun, a read-only root with a writable /run, the publish
    rules for the wireguard port and for the head's API, and TUNNEL_ENTRY as its
    entrypoint with the listen port and the lease seconds as its arguments.
    """
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
    """The `docker run` argv for the worker that serves one card.

    It joins the session's tunnel network namespace, gets that one card, is locked
    down like the head, mounts the cache folder when there is one (pointing
    LLAMA_CACHE at it and passing -c to the server), and runs the rpc server under
    GUARD_SCRIPT.
    """
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
    """The `docker run` argv for the head that serves the model.

    It joins the session's tunnel network namespace, gets the local cards (no
    --gpus at all when the model runs on rpc devices only), mounts the models
    folder read-only, and starts llama-server under GUARD_SCRIPT with the alias,
    slots, context, KV cache type and device split the spec asks for.
    """
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
    """Read TUNNEL_ENTRY's output out of the tunnel's logs.

    Returns None until a "ready" line has been seen and all three facts have been
    printed, because an early poll can catch a partial log. The values are not
    checked here; the caller does that. The last line of each kind wins.
    """
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
    """Bytes each peer has received, keyed by public key, from TRANSFER_SCRIPT."""
    return _read_counts(said, 2)


def read_sent(said: str) -> dict[str, int]:
    """Bytes each peer has sent, keyed by public key, from the same output."""
    return _read_counts(said, 3)


_FULL_LINE = re.compile(r"full (ok|lost) (\d{1,5})")


@dataclass(frozen=True, kw_only=True)
class PingSeen:
    """What PING_SCRIPT said about one peer: the average round-trip time in ms,
    whether a full-size payload got through, and the size that was tried.
    """

    rtt_ms: float | None = None
    full: bool | None = None
    size: int | None = None

    @property
    def narrow(self) -> bool:
        """True when the peer answered small pings but not a full-size one."""
        return self.rtt_ms is not None and self.full is False


def read_ping(said: str) -> PingSeen:
    """Read PING_SCRIPT's output: the first bare number is the average rtt in ms,
    and "full ok <size>" or "full lost <size>" is the full-size result. Lines that
    do not parse are skipped, so a missing rtt or verdict comes back as None.
    """
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
    """What PEERS_SCRIPT said about the session's peers: the epoch time the counts
    were taken, and per peer key its latest handshake and its endpoint.
    """

    now: int
    handshakes: dict[str, int]
    endpoints: dict[str, tuple[str, int]]


_PEER_LINE = re.compile(
    rf"(handshake|endpoint) ({WIREGUARD_KEY.pattern})\t"
    rf"(\d{{1,{_COUNT_DIGITS}}}|\d{{1,3}}(?:\.\d{{1,3}}){{3}}:\d{{1,5}}|\(none\))"
)


def read_peers(said: str) -> PeersSeen | None:
    """Read PEERS_SCRIPT's output.

    Returns None when no "now" line was found, which is what a partial or failed
    run looks like. A peer whose endpoint is "(none)" or is not a usable IPv4
    address and port still gets its handshake time, but no endpoint.
    """
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
    """A container carrying this module's label, as `docker ps` reports it: its
    name, the session it belongs to, the agent pid label, and whether it runs.
    """

    name: str
    session_id: str
    agent_pid: int | None
    running: bool


class Pool:
    """The docker commands a pooled session needs, over a DockerRunner.

    Steps a session cannot continue without (`start`, `run_script`, `run_python`,
    `start_python`, `ensure_tunnel_image`, `owned`) raise PoolError carrying
    docker's own message. The ones that only answer a question (`state`,
    `try_script`, `renew_lease`, `remove`, `logs`) report docker's failure as a
    value instead, because there the failure is an answer.
    """

    def __init__(self, runner: DockerRunner = subprocess_runner) -> None:
        self._runner = runner

    def _call(self, args: Sequence[str], what: str) -> DockerResult:
        result = self._runner(list(args), None)
        if not result.ok:
            said = " ".join((result.stderr or result.stdout).split())[:300]
            raise PoolError(f"docker {what} failed ({result.returncode}): {said}")
        return result

    def ensure_tunnel_image(self) -> str:
        """The tag of a tunnel image, building one from TUNNEL_DOCKERFILE (piped to
        `docker build -`) when no image with that tag is present.
        """
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
        """Run a container with the given `docker run` argv, raising on failure."""
        self._call(argv, "run")

    def run_script(self, name: str, script: str, *args: str) -> str:
        """Run a shell script inside a container and return its stdout.

        The extra arguments become the script's positional parameters and $0 is
        "mcgyvr". A non-zero exit, from docker or from the script, raises
        PoolError with the end of docker's output.
        """
        result = self._call(
            ["exec", name, "/bin/sh", "-c", script, "mcgyvr", *args], "exec"
        )
        return result.stdout

    def run_python(self, name: str, source: str, *args: str) -> str:
        """Run python source inside a container with `python3 -I -c` and return its
        stdout; the extra arguments become sys.argv[1:].
        """
        result = self._call(
            ["exec", name, TUNNEL_PYTHON, "-I", "-c", source, *args], "exec"
        )
        return result.stdout

    def start_python(self, name: str, source: str, *args: str) -> None:
        """Start python source in a container detached, so it outlives the exec
        call; the STUN keep-alive loop is started this way.
        """
        self._call(
            ["exec", "--detach", name, TUNNEL_PYTHON, "-I", "-c", source, *args],
            "exec",
        )

    def try_script(self, name: str, script: str, *args: str) -> bool:
        """Like run_script, but a non-zero exit is reported as False, not raised."""
        result = self._runner(
            ["exec", name, "/bin/sh", "-c", script, "mcgyvr", *args], None
        )
        return result.ok

    def renew_lease(self, name: str) -> bool:
        """Touch the tunnel's lease file; False when the exec failed, which means
        the tunnel container is gone.
        """
        return self._runner(["exec", name, "touch", LEASE_FILE], None).ok

    def logs(self, name: str, tail: int) -> str:
        """The container's output, its last `tail` lines, with stderr appended."""
        result = self._runner(["logs", "--tail", str(tail), name], None)
        return result.stdout + result.stderr

    def state(self, name: str) -> str | None:
        """Docker's state word for the container ("running", "exited", ...), or None
        when docker could not inspect it.
        """
        result = self._runner(
            ["container", "inspect", "--format", "{{.State.Status}}", name], None
        )
        return result.stdout.strip() if result.ok else None

    def remove(self, names: Sequence[str]) -> None:
        """Force-remove the named containers and their anonymous volumes, ignoring
        failures: what matters is that they are gone, not that docker said so.
        """
        if names:
            self._runner(["rm", "--force", "--volumes", *names], None)

    def owned(self) -> list[Owned]:
        """Every container carrying LABEL, parsed from `docker ps --all`.

        Lines without the four tab-separated fields are skipped. An agent label
        that is not a number becomes None, which a sweep reads as a container
        whose owner is unknown.
        """
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
