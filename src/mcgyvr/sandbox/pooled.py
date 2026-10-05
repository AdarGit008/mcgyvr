"""The containers of a pooled-inference session on this machine, and nothing more.

A rig that lends its cards to a hub's session runs other people's work: the
model server (the *head*) answers requests the hub relays, and the RPC server
(the *worker*) runs whatever compute graph its head sends, with no
authentication and no encryption of its own. So neither ever runs as an
ordinary process, and neither ever touches a network but the session's.

Each session is up to three kinds of container, all on this machine's own
daemon (:func:`mcgyvr.sandbox.image.subprocess_runner`, which refuses
``DOCKER_HOST`` and ``DOCKER_CONTEXT``), all labelled so a later agent can
find what an earlier one left (:func:`Pool.owned`):

* **the tunnel** (:func:`tunnel_argv`) — a small image of this product's own
  (:data:`TUNNEL_DOCKERFILE`: WireGuard in user space, ``wg``, ``nft``,
  ``ip``, and a Python to run :mod:`mcgyvr.rig.udpwire` with) that owns the
  session's network namespace. It is the only container holding a
  capability, ``NET_ADMIN``, and that capability reaches only its own
  namespace, never the host's. On start it closes the namespace (an ``nft``
  table dropping everything but loopback), makes the WireGuard interface,
  and generates the session's private key straight into it (``wg genkey |
  wg set … private-key /dev/stdin``): the key is never in a file, never in
  an argument, never in a log, and dies with the container. It prints the
  public key, its bridge address and gateway, and then lives only while the
  agent keeps renewing its lease (:data:`LEASE_FILE`); a lease that runs out
  takes the interface down and the container with it.

  The table has four chains of its own that the scripts below fill and
  empty whole, each in one ``nft`` transaction: ``stun_in``/``stun_out``
  hold the hub's binding responders while the tunnel's port asks them where
  it is seen from (:data:`STUN_SCRIPT`), and are emptied when the tunnel
  comes up; ``wg_in``/``wg_out`` hold, per peer, the one address its
  WireGuard packets may come from and go to — the candidate being tried
  while the tunnel walks a peer's candidates, then the confirmed endpoint
  (or the relay) alone, port and all (:data:`PATH_SCRIPT`). WireGuard takes
  its listen port only when the tunnel comes up (:data:`TUNNEL_SCRIPT`), so
  until then the port is the binding requests' own, and the address the hub
  saw is the one WireGuard's packets leave by.
* **a worker per lent card** (:func:`worker_argv`) and **the head**
  (:func:`head_argv`) join the tunnel's namespace (``--network
  container:…``) and so have no network of their own: what the tunnel's
  table lets through (:data:`TUNNEL_SCRIPT`, :data:`OPEN_WORKER_SCRIPT`,
  :data:`OPEN_HEAD_SCRIPT`) is all they reach. Each runs as the agent's own
  unprivileged user, with every capability dropped, ``no-new-privileges``,
  a read-only root, a seccomp profile of its own (:data:`SECCOMP_PROFILE`:
  docker's default without tracing another process or handing out file
  handles), memory and process limits, and one mount: the worker's own
  cache folder, or the head's models folder read-only. Its process runs
  under :data:`GUARD_SCRIPT`, which ends it when the tunnel's interface is
  gone — so a tunnel that dies takes its worker or head with it.

The head's API is published on ``127.0.0.1`` only, to the agent that relays
to it; the tunnel's UDP port on the LAN addresses the owner lends on, and
nowhere else.

Every value that reaches a script is passed as a positional argument, never
written into the script, and has been read as an address, a port or a key
before it gets here (:mod:`mcgyvr.rig.tunnel`).
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.rig.sessionwire import WIREGUARD_KEY
from mcgyvr.sandbox.image import DockerResult, DockerRunner, subprocess_runner

#: The label every pooled container carries, and the labels that say whose.
LABEL = "mcgyvr.pool"
LABEL_SESSION = "mcgyvr.pool.session"
LABEL_AGENT = "mcgyvr.pool.agent"
LABEL_PART = "mcgyvr.pool.part"

#: The seccomp profile the worker and the head run under.
SECCOMP_PROFILE = Path(__file__).with_name("pooled-seccomp.json")

#: The tunnel image: user-space WireGuard and the tools to configure it, on a
#: base pinned by digest. Its tag is this text's digest (:func:`tunnel_image`).
TUNNEL_DOCKERFILE = (
    "FROM alpine:3.22@sha256:"
    "5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8\n"
    "RUN apk add --no-cache wireguard-go wireguard-tools-wg nftables "
    "iproute2-minimal python3\n"
)
#: The tunnel image's repository; its tag is a digest of the Dockerfile.
TUNNEL_REPOSITORY = "mcgyvr-tunnel"

#: The port the head's API listens on inside its namespace.
HEAD_API_PORT = 8080
#: Where the worker's cache folder and the head's models folder are mounted.
CACHE_MOUNT = "/rpc-cache"
MODELS_MOUNT = "/models"
#: The KV cache type the head runs with, which planning sizes the cache by.
KV_CACHE_TYPE = "q8_0"
#: The file whose age is the tunnel's lease, inside the tunnel container.
LEASE_FILE = "/run/mcgyvr/lease"
#: Where the tunnel's binding keeper (:mod:`mcgyvr.rig.udpwire` ``keep``)
#: writes its pid, so the tunnel can end it before WireGuard takes the port.
KEEPER_PID_FILE = "/run/mcgyvr/stun.pid"
#: The tunnel's Python, which runs :mod:`mcgyvr.rig.udpwire` as it is.
TUNNEL_PYTHON = "python3"

#: Process limits: the tunnel runs three tools; the worker and the head an
#: engine with its threads.
TUNNEL_PIDS = 64
WORKER_PIDS = 256
HEAD_PIDS = 512
#: The tunnel's memory, in MiB: WireGuard's buffer pools grow with
#: throughput, and a model's weights cross the tunnel at LAN speed while the
#: head loads; a tunnel killed for memory takes wg0, and the head, with it.
TUNNEL_MEMORY_MB = 1024
#: Go's soft memory limit for wireguard-go, in MiB, well under the cap: it
#: collects its garbage harder as it nears this instead of being OOM-killed.
TUNNEL_GO_MEMORY_MB = TUNNEL_MEMORY_MB * 3 // 4
#: The MTU of the tunnel's interface. WireGuard adds its header and tag (32
#: bytes), UDP (8) and, at most, an IPv6 header (40) to each packet: 80 bytes,
#: which must fit the smallest MTU an IPv6 path may have, 1280 -- a relay's
#: path can be that small, and the tunnel's table drops the ICMP that would
#: say a packet was too big, so a larger packet is lost without a word.
TUNNEL_MTU = 1200
#: The writable scratch each container gets, as tmpfs options.
TUNNEL_TMPFS = "/run:rw,nosuid,nodev,noexec,size=1m"
ENGINE_TMPFS = "/tmp:rw,nosuid,nodev,noexec,size=64m"

#: The tunnel's entry: close the namespace, make the interface and its key,
#: say what the agent needs, then live as long as the lease. ``$1`` is the
#: listen port (WireGuard takes it only when the tunnel comes up:
#: :data:`TUNNEL_SCRIPT`), ``$2`` the lease in seconds.
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

#: Let the hub's binding responders be asked from the tunnel's port: ``$1``
#: the port, then each responder's address and port. Only those, from and to
#: that port, until the tunnel comes up and empties the chains.
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

#: Bring the tunnel up: ``$1`` this rig's address with the session's prefix,
#: ``$2`` the listen port, then five arguments per peer: its public key, the
#: address and port it is first tried at (``-`` and ``0`` for none yet), the
#: keepalive in seconds, and its allowed addresses, comma separated. The
#: binding keeper is ended and the responders' rules emptied first, then
#: WireGuard takes the port. The table is written before any peer is set, so
#: WireGuard's first packet is never the one the table drops; each peer's
#: address, and only that, may send to and receive from the listen port (any
#: of its ports while candidates are walked: :data:`PATH_SCRIPT` narrows it);
#: ICMP echo between the rig and its peers' addresses is let through, for the
#: round-trip probe and the head's watch of its workers.
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

#: Aim the tunnel's peers: ``$1`` the listen port, then five arguments per
#: peer — its key, the address and port it is tried at (``-`` and ``0`` for
#: none), ``host`` (any port of that address may answer, while a candidate is
#: tried) or ``exact`` (that endpoint alone, once confirmed), and ``1`` to
#: point WireGuard there or ``0`` to leave WireGuard's own endpoint be (it
#: may have followed a peer whose NAT moved the port). Every peer is named
#: each time: the chains are written whole, in one transaction, before any
#: peer is pointed anywhere.
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

#: What the tunnel knows of its peers now: its clock, each peer's latest
#: handshake (seconds since the epoch, 0 for none) and endpoint, read after
#: one ping over the tunnel to each address given (``"$@"``), so a peer not
#: yet shaken hands with has a packet to shake hands for.
PEERS_SCRIPT = r"""for host in "$@"; do
  ping -c 1 -W 1 -q "$host" >/dev/null 2>&1 &
done
wait
echo "now $(date +%s)"
wg show wg0 latest-handshakes | sed 's/^/handshake /'
wg show wg0 endpoints | sed 's/^/endpoint /'
"""

#: Let a worker's port be reached: ``$1`` this rig's tunnel address, ``$2``
#: the port, then the peers' allowed addresses that may reach it.
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

#: Let the head reach its workers and the agent reach the head: ``$1`` this
#: rig's tunnel address, ``$2`` the bridge gateway (where the published API
#: port's traffic comes from), then a worker's address and port per pair. A
#: worker's answers are taken only on this namespace's ephemeral ports, where
#: the head's own connections are, never on the API's. (The range is read whole
#: with ``cat``: busybox's ``read`` reads a ``/proc/sys`` file a byte at a time
#: and gets nothing.)
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

#: Whether ``$1``:``$2`` is listening in this namespace, read from the kernel's
#: own table, so asking never takes the server's one client slot.
LISTENING_SCRIPT = r"""set -eu
hex=$(echo "$1" | awk -F. '{printf "%02X%02X%02X%02X", $4, $3, $2, $1}')
port=$(printf '%04X' "$2")
grep -q " $hex:$port 00000000:0000 0A " /proc/net/tcp
"""

#: The mean round trip to ``$1`` over the tunnel, in milliseconds, once the
#: tunnel's handshake is done: the first packet to a peer waits for it.
PING_SCRIPT = r"""set -eu
ping -c 1 -W 2 -q "$1" >/dev/null
ping -c 5 -i 0.2 -W 1 -q "$1" | awk -F/ '/min\/avg/ {print $4}'
"""

#: What the tunnel has heard from each peer and sent it: WireGuard's byte
#: counts per peer key (received, sent), read after one ping over the tunnel
#: to each address given (``"$@"``), so a quiet peer is asked for a word
#: first. An unanswered ping is no error here: the counts say whether
#: anything came back, and whether a load's weights go out.
TRANSFER_SCRIPT = r"""for host in "$@"; do
  ping -c 1 -W 1 -q "$host" >/dev/null 2>&1 &
done
wait
wg show wg0 transfer
"""

#: Run the engine (``"$@"``) only while the tunnel's interface lives.
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
#: The most digits a byte count of ``wg`` is read with: past 2**64.
_COUNT_DIGITS = 20
_TUNNEL_LINE = re.compile(r"(public-key|address|gateway) (\S+)")
#: A line of ``wg show … transfer``: a peer's key, bytes received, bytes sent.
_TRANSFER_LINE = re.compile(
    rf"({WIREGUARD_KEY.pattern})\t(\d{{1,{_COUNT_DIGITS}}})\t(\d{{1,{_COUNT_DIGITS}}})"
)


class PoolError(Exception):
    """A docker call for a session failed; the message names the call."""


@dataclass(frozen=True, kw_only=True)
class Owner:
    """Who a session's containers run as and belong to: the agent's user and
    process."""

    uid: int
    gid: int
    agent_pid: int


@dataclass(frozen=True, kw_only=True)
class TunnelSpec:
    """The tunnel container of one session."""

    session_id: str
    image: str
    listen_port: int
    publish: tuple[str, ...]  # the LAN addresses the UDP port is published on
    api_port: int | None  # the loopback port the head's API is published on
    lease_s: int


@dataclass(frozen=True, kw_only=True)
class WorkerSpec:
    """One RPC server on one card, bound to the session's tunnel address."""

    session_id: str
    image: str
    binary: str
    gpu: int  # the vendor's own index of the card
    bind: str
    port: int
    cache_dir: Path | None
    memory_mb: int


@dataclass(frozen=True, kw_only=True)
class HeadSpec:
    """The model server of one session."""

    session_id: str
    image: str
    binary: str
    gpus: tuple[int, ...]  # the vendor's own indexes, in bus order
    models_dir: Path
    model: str  # the file, relative to ``models_dir``
    ctx: int  # the context of one slot
    n_gpu_layers: int
    devices: tuple[str, ...]  # the engine's device names, in the hub's order
    tensor_split: tuple[int, ...]
    rpc: tuple[str, ...]  # ``address:port`` of each worker, RPC0 first
    bind: str  # the namespace's bridge address, where the published port lands
    memory_mb: int
    slots: int = 1  # how many requests it serves at once, each with ``ctx``


@dataclass(frozen=True, kw_only=True)
class TunnelHello:
    """What the tunnel printed on start: its public key and where it sits."""

    public_key: str
    address: str  # with the bridge's prefix
    gateway: str


def container_name(session_id: str, part: str) -> str:
    """The name of ``part`` of ``session_id``'s containers: a digest of the
    session id, so any id the hub picks makes a name docker takes."""
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:_NAME_DIGEST]
    return f"mcgyvr-pool-{digest}-{part}"


def tunnel_image() -> str:
    """The tunnel image's tag: its repository and the Dockerfile's digest."""
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
    """``docker run`` of the session's tunnel, without the leading ``docker``."""
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
    """``docker run`` of one RPC server, without the leading ``docker``."""
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
    """``docker run`` of the session's model server, without the leading
    ``docker``.

    It serves ``spec.slots`` requests at once, each slot with ``spec.ctx`` of
    context of its own: ``-np`` slots and ``-c`` slots times ``ctx``, which the
    engine divides between them. ``-np`` is always given, since the engine
    shares one cache among every slot when it picks the count itself, and a
    shared cache that fills fails every request it holds. ``-dev`` and
    ``-ts`` are in the hub's order, unchanged: the last device holds the
    output layer."""
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
    """The tunnel's start lines in ``logs``, or ``None`` before it is ready."""
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
    """The bytes the tunnel received from each peer, by the peer's key, from
    what :data:`TRANSFER_SCRIPT` printed; a line that does not read is left
    out, so a peer it names counts as not heard from."""
    return _read_counts(said, 2)


def read_sent(said: str) -> dict[str, int]:
    """The bytes the tunnel sent each peer, by the peer's key, from what
    :data:`TRANSFER_SCRIPT` printed; a line that does not read is left out."""
    return _read_counts(said, 3)


@dataclass(frozen=True, kw_only=True)
class PeersSeen:
    """What :data:`PEERS_SCRIPT` printed: the tunnel's clock, and by peer
    key the latest handshake (0 for none) and the endpoint WireGuard uses."""

    now: int
    handshakes: dict[str, int]
    endpoints: dict[str, tuple[str, int]]


_PEER_LINE = re.compile(
    rf"(handshake|endpoint) ({WIREGUARD_KEY.pattern})\t"
    rf"(\d{{1,{_COUNT_DIGITS}}}|\d{{1,3}}(?:\.\d{{1,3}}){{3}}:\d{{1,5}}|\(none\))"
)


def read_peers(said: str) -> PeersSeen | None:
    """What the tunnel said of its peers, or ``None`` when it said no time; a
    line that does not read is left out."""
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
    """A pooled container on this machine's daemon, and whose it is."""

    name: str
    session_id: str
    agent_pid: int | None
    running: bool


class Pool:
    """A session's docker calls, through one :data:`DockerRunner`."""

    def __init__(self, runner: DockerRunner = subprocess_runner) -> None:
        self._runner = runner

    def _call(self, args: Sequence[str], what: str) -> DockerResult:
        result = self._runner(list(args), None)
        if not result.ok:
            said = " ".join((result.stderr or result.stdout).split())[:300]
            raise PoolError(f"docker {what} failed ({result.returncode}): {said}")
        return result

    def ensure_tunnel_image(self) -> str:
        """The tunnel image's tag, built from :data:`TUNNEL_DOCKERFILE` first
        when this daemon does not have it."""
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
        """Run one container: ``argv`` as the ``*_argv`` builders make it."""
        self._call(argv, "run")

    def run_script(self, name: str, script: str, *args: str) -> str:
        """Run ``script`` with ``args`` in container ``name``; what it printed."""
        result = self._call(
            ["exec", name, "/bin/sh", "-c", script, "mcgyvr", *args], "exec"
        )
        return result.stdout

    def run_python(self, name: str, source: str, *args: str) -> str:
        """Run Python ``source`` with ``args`` in container ``name``; what it
        printed."""
        result = self._call(
            ["exec", name, TUNNEL_PYTHON, "-I", "-c", source, *args], "exec"
        )
        return result.stdout

    def start_python(self, name: str, source: str, *args: str) -> None:
        """Start Python ``source`` with ``args`` in container ``name``, and
        leave it running."""
        self._call(
            ["exec", "--detach", name, TUNNEL_PYTHON, "-I", "-c", source, *args],
            "exec",
        )

    def try_script(self, name: str, script: str, *args: str) -> bool:
        """Whether ``script`` with ``args`` succeeds in container ``name``."""
        result = self._runner(
            ["exec", name, "/bin/sh", "-c", script, "mcgyvr", *args], None
        )
        return result.ok

    def renew_lease(self, name: str) -> bool:
        """Renew the tunnel's lease; ``False`` when it could not be."""
        return self._runner(["exec", name, "touch", LEASE_FILE], None).ok

    def logs(self, name: str, tail: int) -> str:
        """The last ``tail`` lines container ``name`` printed, both streams."""
        result = self._runner(["logs", "--tail", str(tail), name], None)
        return result.stdout + result.stderr

    def state(self, name: str) -> str | None:
        """Container ``name``'s state (``running``, ``exited``, …), or ``None``
        when there is no such container."""
        result = self._runner(
            ["container", "inspect", "--format", "{{.State.Status}}", name], None
        )
        return result.stdout.strip() if result.ok else None

    def remove(self, names: Sequence[str]) -> None:
        """Remove the containers ``names``, running or not; a name with no
        container is no error."""
        if names:
            self._runner(["rm", "--force", "--volumes", *names], None)

    def owned(self) -> list[Owned]:
        """Every pooled container this daemon has, running or not."""
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
