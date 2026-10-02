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
  ``ip``) that owns the session's network namespace. It is the only container
  holding a capability, ``NET_ADMIN``, and that capability reaches only its
  own namespace, never the host's. On start it closes the namespace (an
  ``nft`` table dropping everything but loopback), makes the WireGuard
  interface, and generates the session's private key straight into it
  (``wg genkey | wg set … private-key /dev/stdin``): the key is never in a
  file, never in an argument, never in a log, and dies with the container.
  It prints the public key, its bridge address and gateway, and then lives
  only while the agent keeps renewing its lease (:data:`LEASE_FILE`); a lease
  that runs out takes the interface down and the container with it.
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
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

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
    "iproute2-minimal\n"
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

#: Process limits: the tunnel runs three tools; the worker and the head an
#: engine with its threads.
TUNNEL_PIDS = 64
WORKER_PIDS = 256
HEAD_PIDS = 512
#: The tunnel's memory, in MiB: WireGuard's buffers under a model's transfer.
TUNNEL_MEMORY_MB = 256
#: The writable scratch each container gets, as tmpfs options.
TUNNEL_TMPFS = "/run:rw,nosuid,nodev,noexec,size=1m"
ENGINE_TMPFS = "/tmp:rw,nosuid,nodev,noexec,size=64m"

#: The tunnel's entry: close the namespace, make the interface and its key,
#: say what the agent needs, then live as long as the lease. ``$1`` is the
#: listen port, ``$2`` the lease in seconds.
TUNNEL_ENTRY = r"""set -eu
umask 077
port="$1"
lease_s="$2"
mkdir -p /run/mcgyvr
touch /run/mcgyvr/lease
nft -f - <<'RULES'
table inet mcgyvr {
  chain input { type filter hook input priority 0; policy drop; iif "lo" accept; }
  chain output { type filter hook output priority 0; policy drop; oif "lo" accept; }
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
wg genkey | wg set wg0 private-key /dev/stdin listen-port "$port"
ip link set wg0 up
echo "public-key $(wg show wg0 public-key)"
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

#: Bring the tunnel up: ``$1`` this rig's address with the session's prefix,
#: ``$2`` the listen port, then five arguments per peer: its public key, the
#: endpoint address and port it is reached at, the keepalive in seconds, and
#: its allowed addresses, comma separated. Each peer's endpoint, and only
#: that, may send to and receive from the listen port; ICMP echo between the
#: rig and its peers' addresses is let through, for the round-trip probe.
TUNNEL_SCRIPT = r"""set -eu
self="$1"
port="$2"
shift 2
ip address add "$self" dev wg0
own="${self%/*}"
add="add rule inet mcgyvr"
icmp="icmp type { echo-request, echo-reply }"
rules=$(
  while [ "$#" -ge 5 ]; do
    wg set wg0 peer "$1" allowed-ips "$5" endpoint "$2:$3" \
      persistent-keepalive "$4"
    echo "$add input iifname eth0 ip saddr $2 udp dport $port accept"
    echo "$add output oifname eth0 ip daddr $2 udp sport $port accept"
    for net in $(echo "$5" | tr ',' ' '); do
      echo "$add input iifname wg0 ip saddr $net ip daddr $own $icmp accept"
      echo "$add output oifname wg0 ip saddr $own ip daddr $net $icmp accept"
    done
    shift 5
  done
)
printf '%s\n' "$rules" | nft -f -
echo "up"
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
_TUNNEL_LINE = re.compile(r"(public-key|address|gateway) (\S+)")


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
    ctx: int
    n_gpu_layers: int
    devices: tuple[str, ...]  # the engine's device names, in the hub's order
    tensor_split: tuple[int, ...]
    rpc: tuple[str, ...]  # ``address:port`` of each worker, RPC0 first
    bind: str  # the namespace's bridge address, where the published port lands
    memory_mb: int


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
    ``docker``."""
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
        "1",
        "-c",
        str(spec.ctx),
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
