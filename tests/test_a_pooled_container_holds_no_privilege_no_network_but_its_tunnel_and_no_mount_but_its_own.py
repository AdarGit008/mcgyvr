"""A pooled container holds no privilege, no network but its tunnel, one mount.

A rig lending its cards runs other people's work: a model server answering
relayed requests, and an RPC server that runs any compute graph its head
sends, with no authentication. So the argv each is started with is the whole
promise, and it is asserted here exactly, flag for flag:

* the worker and the head run as the agent's own user, with every
  capability dropped, ``no-new-privileges``, a read-only root, the product's
  seccomp profile, a private IPC namespace, memory without swap, a process
  limit, and one mount (the worker's cache, the head's models read-only);
* neither has a network of its own: each joins its session's tunnel
  container, and the tunnel is the only one holding ``NET_ADMIN`` (in its own
  namespace), with every other capability dropped;
* nothing is published but the tunnel's UDP port on the addresses the owner
  lends on, and the head's API on loopback; no argument binds ``0.0.0.0``
  and none asks for the host's network;
* the private key is made inside the tunnel and fed to WireGuard on a pipe:
  no argument, no file, no log line carries it.

The seccomp profile is docker's default without the calls that trace or
read another process or hand out a file handle — and nothing wider.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

OWNER_UID, OWNER_GID, AGENT_PID = 1000, 1000, 4242
#: The worker's seccomp profile: docker's default (moby/profiles at commit
#: 3c28324314729dbade8287e868eef6338c42807a) without four calls, byte for byte.
SECCOMP_SHA256 = "a5c1305f39ead96e020eed882b030001d097657780af86ca33543f2d1f274195"
LAN = "192.0.2.10"
TUNNEL_ADDRESS = "198.51.100.2"
BRIDGE = "203.0.113.2"


def _owner() -> Any:
    from mcgyvr.sandbox import pooled

    return pooled.Owner(uid=OWNER_UID, gid=OWNER_GID, agent_pid=AGENT_PID)


def _flags(argv: Sequence[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, word in enumerate(argv[:-1]) if word == flag]


def _lockdown(memory: str, pids: str) -> list[str]:
    from mcgyvr.sandbox import pooled

    return [
        "--user",
        f"{OWNER_UID}:{OWNER_GID}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--security-opt",
        f"seccomp={pooled.SECCOMP_PROFILE}",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--ipc",
        "private",
        "--pids-limit",
        pids,
        "--memory",
        memory,
        "--memory-swap",
        memory,
        "--env",
        "HOME=/tmp",
        "--env",
        "CUDA_DEVICE_ORDER=PCI_BUS_ID",
    ]


def test_the_worker_runs_with_nothing_but_its_card_its_cache_and_its_tunnel() -> None:
    from mcgyvr.sandbox import pooled

    spec = pooled.WorkerSpec(
        session_id="session-1",
        image="engine:rpc",
        binary="/app/ggml-rpc-server",
        gpu=1,
        bind=TUNNEL_ADDRESS,
        port=50052,
        cache_dir=Path("/var/cache/pool"),
        memory_mb=4096,
    )
    tunnel = pooled.container_name("session-1", "tunnel")
    name = pooled.container_name("session-1", "worker-1")
    assert pooled.worker_argv(spec, _owner()) == [
        "run",
        "--detach",
        "--name",
        name,
        "--label",
        "mcgyvr.pool=1",
        "--label",
        "mcgyvr.pool.session=session-1",
        "--label",
        "mcgyvr.pool.part=worker-1",
        "--label",
        f"mcgyvr.pool.agent={AGENT_PID}",
        "--network",
        f"container:{tunnel}",
        "--gpus",
        "device=1",
        *_lockdown("4096m", "256"),
        "--volume",
        "/var/cache/pool:/rpc-cache:rw",
        "--env",
        "LLAMA_CACHE=/rpc-cache",
        "--entrypoint",
        "/bin/sh",
        "engine:rpc",
        "-c",
        pooled.GUARD_SCRIPT,
        "mcgyvr-guard",
        "/app/ggml-rpc-server",
        "-H",
        TUNNEL_ADDRESS,
        "-p",
        "50052",
        "-d",
        "CUDA0",
        "-c",
    ]


def test_a_worker_without_a_cache_mounts_nothing() -> None:
    from mcgyvr.sandbox import pooled

    spec = pooled.WorkerSpec(
        session_id="s",
        image="engine:rpc",
        binary="/app/ggml-rpc-server",
        gpu=0,
        bind=TUNNEL_ADDRESS,
        port=50052,
        cache_dir=None,
        memory_mb=1024,
    )
    argv = pooled.worker_argv(spec, _owner())
    assert "--volume" not in argv and "-v" not in argv and argv[-1] == "CUDA0"
    assert not any(word.startswith("LLAMA_CACHE") for word in argv)


def test_the_head_runs_with_its_cards_its_models_read_only_and_its_tunnel() -> None:
    from mcgyvr.sandbox import pooled

    spec = pooled.HeadSpec(
        session_id="session-1",
        image="engine:rpc",
        binary="/app/llama-server",
        gpus=(0, 1),
        models_dir=Path("/srv/models"),
        model="dense/model-q5.gguf",
        ctx=12288,
        n_gpu_layers=99,
        devices=("CUDA0", "CUDA1", "RPC0"),
        tensor_split=(10, 10, 5),
        rpc=(f"{TUNNEL_ADDRESS}:50052",),
        bind=BRIDGE,
        memory_mb=16384,
    )
    tunnel = pooled.container_name("session-1", "tunnel")
    assert pooled.head_argv(spec, _owner()) == [
        "run",
        "--detach",
        "--name",
        pooled.container_name("session-1", "head"),
        "--label",
        "mcgyvr.pool=1",
        "--label",
        "mcgyvr.pool.session=session-1",
        "--label",
        "mcgyvr.pool.part=head",
        "--label",
        f"mcgyvr.pool.agent={AGENT_PID}",
        "--network",
        f"container:{tunnel}",
        "--gpus",
        '"device=0,1"',
        *_lockdown("16384m", "512"),
        "--volume",
        "/srv/models:/models:ro",
        "--entrypoint",
        "/bin/sh",
        "engine:rpc",
        "-c",
        pooled.GUARD_SCRIPT,
        "mcgyvr-guard",
        "/app/llama-server",
        "-m",
        "/models/dense/model-q5.gguf",
        "-ngl",
        "99",
        "-sm",
        "layer",
        "-np",
        "1",
        "-c",
        "12288",
        "-fa",
        "on",
        "-ctk",
        "q8_0",
        "-ctv",
        "q8_0",
        "--host",
        BRIDGE,
        "--port",
        "8080",
        "--rpc",
        f"{TUNNEL_ADDRESS}:50052",
        "-dev",
        "CUDA0,CUDA1,RPC0",
        "-ts",
        "10,10,5",
    ]


def test_the_tunnel_alone_holds_net_admin_and_publishes_its_port_and_loopback() -> None:
    from mcgyvr.sandbox import pooled

    spec = pooled.TunnelSpec(
        session_id="session-1",
        image="mcgyvr-tunnel:abc",
        listen_port=51820,
        publish=(LAN,),
        api_port=18080,
        lease_s=60,
    )
    assert pooled.tunnel_argv(spec, _owner()) == [
        "run",
        "--detach",
        "--name",
        pooled.container_name("session-1", "tunnel"),
        "--label",
        "mcgyvr.pool=1",
        "--label",
        "mcgyvr.pool.session=session-1",
        "--label",
        "mcgyvr.pool.part=tunnel",
        "--label",
        f"mcgyvr.pool.agent={AGENT_PID}",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "NET_ADMIN",
        "--security-opt",
        "no-new-privileges=true",
        "--read-only",
        "--tmpfs",
        "/run:rw,nosuid,nodev,noexec,size=1m",
        "--device",
        "/dev/net/tun",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--publish",
        f"{LAN}:51820:51820/udp",
        "--publish",
        "127.0.0.1:18080:8080/tcp",
        "--entrypoint",
        "/bin/sh",
        "mcgyvr-tunnel:abc",
        "-c",
        pooled.TUNNEL_ENTRY,
        "mcgyvr-tunnel",
        "51820",
        "60",
    ]


@pytest.mark.parametrize("which", ["worker", "head", "tunnel"])
def test_no_container_asks_for_the_hosts_network_a_wildcard_or_privilege(
    which: str,
) -> None:
    from mcgyvr.sandbox import pooled

    owner = _owner()
    argv: list[str]
    if which == "worker":
        argv = pooled.worker_argv(
            pooled.WorkerSpec(
                session_id="s",
                image="i",
                binary="b",
                gpu=0,
                bind=TUNNEL_ADDRESS,
                port=50052,
                cache_dir=None,
                memory_mb=1,
            ),
            owner,
        )
    elif which == "head":
        argv = pooled.head_argv(
            pooled.HeadSpec(
                session_id="s",
                image="i",
                binary="b",
                gpus=(),
                models_dir=Path("/m"),
                model="x.gguf",
                ctx=256,
                n_gpu_layers=1,
                devices=("RPC0",),
                tensor_split=(1,),
                rpc=(f"{TUNNEL_ADDRESS}:50052",),
                bind=BRIDGE,
                memory_mb=1,
            ),
            owner,
        )
    else:
        argv = pooled.tunnel_argv(
            pooled.TunnelSpec(
                session_id="s",
                image="i",
                listen_port=51820,
                publish=(LAN,),
                api_port=None,
                lease_s=60,
            ),
            owner,
        )
    text = " ".join(argv)
    assert "0.0.0.0" not in text
    assert "--privileged" not in argv
    assert "--network" not in argv or _flags(argv, "--network")[0].startswith(
        "container:"
    )
    assert "host" not in _flags(argv, "--network") + _flags(argv, "--pid")
    assert "/var/run/docker.sock" not in text and "docker.sock" not in text
    assert _flags(argv, "--cap-drop") == ["ALL"]
    assert _flags(argv, "--cap-add") == ([] if which != "tunnel" else ["NET_ADMIN"])
    assert "no-new-privileges=true" in _flags(argv, "--security-opt")
    assert "--read-only" in argv
    for published in _flags(argv, "--publish"):
        host = published.split(":", 1)[0]
        assert host in (LAN, "127.0.0.1")
        assert published.endswith("/udp") or host == "127.0.0.1"


def test_the_private_key_is_made_in_the_tunnel_and_never_written_or_said() -> None:
    from mcgyvr.sandbox import pooled

    entry = pooled.TUNNEL_ENTRY
    assert "wg genkey | wg set wg0 private-key /dev/stdin" in entry
    assert "private-key /run" not in entry and "> /" not in entry.split("RULES")[-1]
    said = [line for line in entry.splitlines() if line.strip().startswith("echo")]
    assert said and not any("private" in line or "genkey" in line for line in said)
    assert "wg show wg0 public-key" in entry
    # The table closes the namespace before the interface exists.
    assert entry.index("policy drop") < entry.index("wireguard-go")


def test_the_tunnels_start_lines_are_read_only_when_it_says_it_is_ready() -> None:
    from mcgyvr.sandbox import pooled

    key = "A" * 43 + "="
    early = f"public-key {key}\naddress {BRIDGE}/24\n"
    assert pooled.read_tunnel_hello(early) is None
    hello = pooled.read_tunnel_hello(early + "gateway 203.0.113.1\nready\n")
    assert hello == pooled.TunnelHello(
        public_key=key, address=f"{BRIDGE}/24", gateway="203.0.113.1"
    )


def test_the_seccomp_profile_is_dockers_default_without_tracing_or_handles() -> None:
    import hashlib

    from mcgyvr.sandbox import pooled

    raw = pooled.SECCOMP_PROFILE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SECCOMP_SHA256
    profile = json.loads(raw)
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    allowed = {
        name
        for block in profile["syscalls"]
        if block["action"] == "SCMP_ACT_ALLOW"
        for name in block["names"]
    }
    removed = {"ptrace", "process_vm_readv", "process_vm_writev", "name_to_handle_at"}
    assert not allowed & removed
    assert not {"io_uring_setup", "io_uring_enter", "io_uring_register"} & allowed
    assert {"mmap", "ioctl", "futex", "socket", "connect", "clone"} <= allowed


def test_a_container_name_is_one_docker_takes_whatever_id_the_hub_picked() -> None:
    import re

    from mcgyvr.sandbox import pooled

    for session in ("-leading-dash", "_under", "a" * 64, "x"):
        name = pooled.container_name(session, "tunnel")
        assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", name)
        assert session not in name or len(session) < 3


def test_the_tunnel_image_is_named_by_what_it_is_built_from() -> None:
    from mcgyvr.sandbox import pooled

    tag = pooled.tunnel_image()
    assert tag.startswith("mcgyvr-tunnel:") and len(tag.split(":")[1]) == 12
    assert "@sha256:" in pooled.TUNNEL_DOCKERFILE.splitlines()[0]


def test_the_head_script_reads_the_port_range_whole() -> None:
    from mcgyvr.sandbox import pooled

    # busybox's `read` takes a /proc/sys file a byte at a time and gets nothing,
    # which failed the head's firewall on a live rig; the range is read whole.
    script = pooled.OPEN_HEAD_SCRIPT
    assert "read " not in script
    assert "$(cat /proc/sys/net/ipv4/ip_local_port_range)" in script


def test_the_round_trip_is_measured_after_the_handshake_not_with_it() -> None:
    from mcgyvr.sandbox import pooled

    # The first packet to a peer waits for WireGuard's handshake; a live run
    # reported a third of a second for a tunnel whose warm round trip was 1 ms.
    lines = pooled.PING_SCRIPT.splitlines()
    warm = next(i for i, line in enumerate(lines) if "-c 1" in line)
    measured = next(i for i, line in enumerate(lines) if "min\\/avg" in line)
    assert warm < measured
