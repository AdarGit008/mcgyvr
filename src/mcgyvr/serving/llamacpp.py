"""The one llama.cpp build mcgyvr runs: in the Linux image, and as native binaries.

One release tag is pinned (:data:`TAG`), and both ways of running llama.cpp
take it: the Linux container image (:data:`IMAGE`, whose tag is the build) and
the archives the native launch fetches (:data:`RELEASE`, each with the size and
sha256 GitHub states for it). A head and a worker split across a Linux
container and a native Mac or Windows binary are then the same build.

:func:`build_for` picks the archive for a system, an architecture and a
backend, and :func:`backend_for` picks the backend for a system (pin K5):
Metal on macOS on Apple silicon; on Windows and Linux CUDA when ``nvidia-smi``
reads a driver the build supports, else Vulkan, else the CPU. A CUDA build
comes with the CUDA runtime archive llama.cpp publishes beside it.

Sources (read 2026-10-29):

- Release b11960, its asset names, sizes and sha256 digests: the GitHub API,
  https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11960
  (https://github.com/ggml-org/llama.cpp/releases/tag/b11960). The stable
  release v0.8.0's ``nightly-tag.txt`` names b11960 as the build it is
  (https://github.com/ggml-org/llama.cpp/releases/download/v0.8.0/nightly-tag.txt).
- The container tag ``server-cuda-b11960`` answers a manifest request
  (HTTP 200,
  https://ghcr.io/v2/ggml-org/llama.cpp/manifests/server-cuda-b11960; listed at
  https://github.com/ggml-org/llama.cpp/pkgs/container/llama.cpp). Its server
  image holds ``llama-server`` alone (``COPY ... /app/full/llama-server /app/``,
  https://github.com/ggml-org/llama.cpp/blob/b11960/.devops/cuda.Dockerfile):
  a containerised rpc worker runs the operator's own image, whose program
  ``emit.RPC_COMMAND`` names; the native archives name it ``ggml-rpc-server``.
- The archives hold ``llama-server`` and ``ggml-rpc-server`` (read from the
  macOS arm64, Ubuntu x64 and Windows Vulkan x64 archives of b11960): the tar
  archives under one ``llama-b11960/`` folder, the Windows zips flat.
- CUDA runtime DLLs "ship separately as
  cudart-llama-bin-win-cuda-<ver>-<arch>.zip (needed next to the cuda build
  when the CUDA toolkit is not installed)":
  https://github.com/ggml-org/llama.cpp/releases (asset names, GitHub API).
- Driver ranges: "13.x >= 580 N/A; 12.x >= 525 < 580" (Minor Version
  Compatibility), https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html
- "On MacOS, Metal is enabled by default."
  https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- The RPC protocol the build speaks: ``#define RPC_PROTO_MAJOR_VERSION 8``,
  ``#define RPC_PROTO_MINOR_VERSION 0`` (patch 1, never compared),
  https://github.com/ggml-org/llama.cpp/blob/b11960/ggml/include/ggml-rpc.h
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from mcgyvr.hostos import DARWIN, LINUX, WINDOWS
from mcgyvr.hubwire import (
    ARCH_ARM64,
    ARCH_X86_64,
    BACKEND_CPU,
    BACKEND_CUDA,
    BACKEND_METAL,
    BACKEND_VULKAN,
    HOST_ARCH,
)
from mcgyvr.serving.release import Asset, Release

#: The pinned llama.cpp build.
TAG = "b11960"
#: Where it is published.
REPO = "ggml-org/llama.cpp"
#: The Linux container image of the same build, CUDA flavour.
IMAGE = f"ghcr.io/ggml-org/llama.cpp:server-cuda-{TAG}"
#: The runtime a rig names in its offer when it runs this build natively.
RUNTIME = f"{REPO}@{TAG}"
#: The llama.cpp RPC protocol this build speaks (major, minor), which a rig
#: running it names in its hello as a :class:`mcgyvr.hubwire.RpcProto`
#: (:data:`mcgyvr.rig.session.PINNED_RPC_PROTO`) so the hub pairs heads and
#: workers by :func:`mcgyvr.hubwire.rpc_compatible`. Plain numbers here: this
#: module is shipped to rigs, which carry no hubwire.
RPC_PROTO_MAJOR = 8
RPC_PROTO_MINOR = 0
#: The programs the native launch runs out of an archive: the server, and the
#: worker a model split across machines starts on each of them.
SERVER = "llama-server"
RPC_SERVER = "ggml-rpc-server"
EXECUTABLES = (SERVER, RPC_SERVER)

#: The backends a native build runs on, the resource contract's own
#: (``rocm`` aside: no build here is picked for it), and the systems and
#: architectures it is built for, the wire's (:mod:`mcgyvr.hubwire`).
CUDA, METAL, VULKAN, CPU = BACKEND_CUDA, BACKEND_METAL, BACKEND_VULKAN, BACKEND_CPU
BACKENDS = (METAL, CUDA, VULKAN, CPU)
X86_64, ARM64 = ARCH_X86_64, ARCH_ARM64
ARCHES = HOST_ARCH
#: The lowest driver branch each CUDA major version runs on (NVIDIA's minor
#: version compatibility table); below the lowest, a CUDA build is not picked.
CUDA_DRIVER_FLOOR = {13: 580, 12: 525}

RELEASE = Release(
    repo=REPO,
    tag=TAG,
    assets=(
        Asset(
            "llama-b11960-bin-macos-arm64.tar.gz",
            16465074,
            "58e5a5e1d7c2bf66cedd9c29e0323f3e570660a70a1e2156d32eed08f4cc1e3c",
        ),
        Asset(
            "llama-b11960-bin-macos-x64.tar.gz",
            12205764,
            "d1e6c9ddcaed9a3b1bb8f3d946bdb3481c7b919357a4029dcb747762397f1da5",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-x64.tar.gz",
            22686210,
            "31cc3a6bc638ac6c48dc4b1b74888f1eaadf3d14227c1e5f67daf9a49541d97a",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-arm64.tar.gz",
            18411465,
            "0065ecfbffe8a790bb0d28059a3320cdc8f723b7f3f248cdc8bfc04790927715",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-vulkan-x64.tar.gz",
            35474467,
            "164199e978304bb32a8a6c24b8efa015528ddf286821596eab676c90b375feac",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-vulkan-arm64.tar.gz",
            28828107,
            "22d1f852055a95a5c969b90326a2b68b4618eca6c54638bae27b4ee603031d53",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
            182524002,
            "64d57beb9abb637c177c6afb313760a0c0782224cac71e74869eed5b8f9a1ea4",
        ),
        Asset(
            "cudart-llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
            594371478,
            "7c4d5974bd39649df649649e5d71950688a70e37aaae00bf11afbb656ea2cc56",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
            163957335,
            "0cf758b28483593a5a15e0d2c9b686c40840d1f8be9b5bb2417f04a053113907",
        ),
        Asset(
            "cudart-llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
            440232534,
            "756e14988abb5daa60d25f27a9766a9a78f04c88647c4b92a88fb749488d72f7",
        ),
        Asset(
            "llama-b11960-bin-ubuntu-cuda-13.4-arm64.tar.gz",
            159059972,
            "a66743e250e2975d7181b9f51048bfbea7903106035b711bea5c552360323452",
        ),
        Asset(
            "cudart-llama-b11960-bin-ubuntu-cuda-13.4-arm64.tar.gz",
            552521522,
            "4b20f8c8dab2eb49c9f46ab93e11858877f1c031696f665ed5584b045187d0a0",
        ),
        Asset(
            "llama-b11960-bin-win-cpu-x64.zip",
            24407745,
            "73f962f82850d244db47eaacb9d913637027b82399124324298576d58c5f4287",
        ),
        Asset(
            "llama-b11960-bin-win-cpu-arm64.zip",
            13018162,
            "77349357c38da235bb0eed37bcc5ecf3efef21bb5dc42c2269589c0e71cfa00f",
        ),
        Asset(
            "llama-b11960-bin-win-vulkan-x64.zip",
            37345851,
            "bac6914b5e83523eb008c6789eaa12669f93fbc196c3b9e8237b6672323b33e9",
        ),
        Asset(
            "llama-b11960-bin-win-vulkan-arm64.zip",
            25547008,
            "cd375e330452496aadf8a872cde6d48c92e51d598088e5575a32a0d43bc0c9f0",
        ),
        Asset(
            "llama-b11960-bin-win-cuda-12.4-x64.zip",
            279763224,
            "8d9d819261de10cc2f03921b8b79c779c5c458e21edb60c170ee30a7d462d684",
        ),
        Asset(
            "cudart-llama-bin-win-cuda-12.4-x64.zip",
            391443627,
            "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
        ),
        Asset(
            "llama-b11960-bin-win-cuda-13.4-x64.zip",
            164986387,
            "31c75ea62b80f0816c855ea783ef68757bc2d48028edaa57d904e4982bddea4a",
        ),
        Asset(
            "cudart-llama-bin-win-cuda-13.4-x64.zip",
            423535356,
            "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668",
        ),
        Asset(
            "llama-b11960-bin-win-cuda-13.4-arm64.zip",
            152745165,
            "3bde5e443757db131bf6b6e26079bd22ce01e2e6170439997634d7ac7c000119",
        ),
        Asset(
            "cudart-llama-bin-win-cuda-13.4-arm64.zip",
            153262407,
            "642dcde8805b3e3165ca710a5443b3b4044b27d96bd3ee3132473988c9bcb774",
        ),
    ),
)


class NoBuildError(LookupError):
    """No pinned archive runs on this system, architecture and backend."""


@dataclass(frozen=True)
class Build:
    """One native build: what it runs on, and the archives it is made of.

    `name` is the folder it is unpacked into under the tag's; `assets` the
    archive and, for CUDA, the runtime archive unpacked beside it.
    """

    os: str
    arch: str
    backend: str
    name: str
    assets: tuple[str, ...]


def _build(os_name: str, arch: str, backend: str, *assets: str) -> Build:
    stem = assets[0].removeprefix(f"llama-{TAG}-bin-")
    for suffix in (".tar.gz", ".zip"):
        stem = stem.removesuffix(suffix)
    return Build(os_name, arch, backend, stem, assets)


#: Every build mcgyvr picks, by (system, architecture, backend). A CUDA backend
#: has one row per CUDA major version; :func:`build_for` takes the newest the
#: driver runs.
BUILDS: tuple[Build, ...] = (
    _build(DARWIN, ARM64, METAL, "llama-b11960-bin-macos-arm64.tar.gz"),
    _build(DARWIN, X86_64, CPU, "llama-b11960-bin-macos-x64.tar.gz"),
    _build(LINUX, X86_64, CPU, "llama-b11960-bin-ubuntu-x64.tar.gz"),
    _build(LINUX, ARM64, CPU, "llama-b11960-bin-ubuntu-arm64.tar.gz"),
    _build(LINUX, X86_64, VULKAN, "llama-b11960-bin-ubuntu-vulkan-x64.tar.gz"),
    _build(LINUX, ARM64, VULKAN, "llama-b11960-bin-ubuntu-vulkan-arm64.tar.gz"),
    _build(
        LINUX,
        X86_64,
        CUDA,
        "llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
        "cudart-llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
    ),
    _build(
        LINUX,
        X86_64,
        CUDA,
        "llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "cudart-llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
    ),
    _build(
        LINUX,
        ARM64,
        CUDA,
        "llama-b11960-bin-ubuntu-cuda-13.4-arm64.tar.gz",
        "cudart-llama-b11960-bin-ubuntu-cuda-13.4-arm64.tar.gz",
    ),
    _build(WINDOWS, X86_64, CPU, "llama-b11960-bin-win-cpu-x64.zip"),
    _build(WINDOWS, ARM64, CPU, "llama-b11960-bin-win-cpu-arm64.zip"),
    _build(WINDOWS, X86_64, VULKAN, "llama-b11960-bin-win-vulkan-x64.zip"),
    _build(WINDOWS, ARM64, VULKAN, "llama-b11960-bin-win-vulkan-arm64.zip"),
    _build(
        WINDOWS,
        X86_64,
        CUDA,
        "llama-b11960-bin-win-cuda-13.4-x64.zip",
        "cudart-llama-bin-win-cuda-13.4-x64.zip",
    ),
    _build(
        WINDOWS,
        X86_64,
        CUDA,
        "llama-b11960-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
    ),
    _build(
        WINDOWS,
        ARM64,
        CUDA,
        "llama-b11960-bin-win-cuda-13.4-arm64.zip",
        "cudart-llama-bin-win-cuda-13.4-arm64.zip",
    ),
)


def cuda_major(build: Build) -> int | None:
    """The CUDA major version a CUDA build was made with, from its archive name."""
    if build.backend != CUDA:
        return None
    version = build.name.split("cuda-", 1)[1].split("-", 1)[0]
    return int(version.split(".", 1)[0])


def driver_runs(build: Build, driver: str | None) -> bool:
    """Whether an NVIDIA driver of version `driver` runs `build`'s CUDA.

    Only the branch (the number before the first dot) is compared with
    :data:`CUDA_DRIVER_FLOOR`. A non-CUDA build runs on any driver; an unread
    driver runs no CUDA build.
    """
    major = cuda_major(build)
    if major is None:
        return True
    try:
        branch = int((driver or "").strip().split(".", 1)[0])
    except ValueError:
        return False
    return branch >= CUDA_DRIVER_FLOOR.get(major, 10**9)


def backend_for(
    os_name: str, arch: str, *, nvidia_driver: str | None, vulkan: bool = True
) -> str:
    """The backend a native unit runs on here (pin K5).

    macOS on Apple silicon: Metal; an Intel Mac: the CPU. Windows and Linux:
    CUDA when `nvidia_driver` (``nvidia-smi``'s ``driver_version``) runs a
    pinned CUDA build for this architecture, else Vulkan when the machine has
    a Vulkan loader (`vulkan`), else the CPU.
    """
    if os_name == DARWIN:
        return METAL if arch == ARM64 else CPU
    if nvidia_driver and any(
        b.backend == CUDA and driver_runs(b, nvidia_driver)
        for b in BUILDS
        if (b.os, b.arch) == (os_name, arch)
    ):
        return CUDA
    if vulkan and any(
        b.backend == VULKAN for b in BUILDS if (b.os, b.arch) == (os_name, arch)
    ):
        return VULKAN
    return CPU


def build_for(
    os_name: str, arch: str, backend: str, *, nvidia_driver: str | None = None
) -> Build:
    """The pinned build for this system, architecture and backend.

    For CUDA, the newest CUDA major version `nvidia_driver` runs. Raises
    :class:`NoBuildError` naming what there is when none fits.
    """
    rows = [b for b in BUILDS if (b.os, b.arch, b.backend) == (os_name, arch, backend)]
    if backend == CUDA:
        rows = [b for b in rows if driver_runs(b, nvidia_driver)]
    if not rows:
        offered = sorted(
            {b.backend for b in BUILDS if (b.os, b.arch) == (os_name, arch)}
        )
        raise NoBuildError(
            f"no pinned llama.cpp {TAG} build runs {backend} on {os_name} {arch}"
            + (
                f" (driver {nvidia_driver})"
                if backend == CUDA and nvidia_driver
                else ""
            )
            + f"; this system has builds for: {', '.join(offered) or 'none'}"
        )
    return max(rows, key=lambda b: cuda_major(b) or 0)


#: Where a native llama.cpp unit listens (K13), checked where it is written
#: (emit) and where it is started (the native launcher, on this machine or on
#: a rig the door ships it to): a server on the loopback alone, so no firewall
#: asks and only its own machine reaches it (the hub never reaches a unit
#: directly: the rig agent relays its requests to the unit's local address),
#: and a server stating another `--host` or `LLAMA_ARG_HOST` is refused; a
#: pooled rpc worker on the address the head reaches it at, its tunnel
#: address, stated with `-H` and nothing wider (:func:`worker_may_listen`).
LOOPBACK = "127.0.0.1"
#: The flag and the variable llama-server reads its listening address from.
HOST_FLAG = "--host"
HOST_ENV = "LLAMA_ARG_HOST"
#: The rpc worker's short spelling of `--host`: `if (arg == "-H" || arg ==
#: "--host")`, default "127.0.0.1"
#: (https://github.com/ggml-org/llama.cpp/blob/b11960/tools/rpc/rpc-server.cpp).
RPC_HOST_FLAG = "-H"


def stated_hosts(argv: list[str] | tuple[str, ...], *, rpc: bool = False) -> list[str]:
    """Every listening address `argv` states (`--host H` or `--host=H`; for
    the rpc worker, `-H H` too)."""
    flags = (HOST_FLAG, RPC_HOST_FLAG) if rpc else (HOST_FLAG,)
    hosts: list[str] = []
    for n, part in enumerate(argv):
        for flag in flags:
            if part == flag:
                hosts.append(argv[n + 1] if n + 1 < len(argv) else "")
            elif part.startswith(f"{flag}="):
                hosts.append(part[len(flag) + 1 :])
    return hosts


#: The shared address space overlay networks hand out (RFC 6598: the /10
#: that starts at 100.64, a tailnet's), written as a number. A worker recorded
#: at one of these is reached only by a head on the same overlay.
OVERLAY = ipaddress.IPv4Network((100 << 24 | 64 << 16, 10))
#: The networks an rpc worker may bind an address in, and no other: the
#: private ranges (RFC 1918: 10/8, 172.16/12, 192.168/16) and :data:`OVERLAY`.
#: Python's `is_private` is not the rule: it also counts the documentation
#: ranges, link-local and 240/4, and leaves the overlay range out.
WORKER_NETWORKS = (
    *(
        ipaddress.IPv4Network(net)
        for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ),
    OVERLAY,
)


def worker_may_listen(address: ipaddress.IPv4Address) -> bool:
    """Whether a worker on another machine may bind this address.

    rpc-server has no authentication, so the address must be one the head
    reaches that worker at and nothing wider: an address of a private or an
    overlay network (:data:`WORKER_NETWORKS`), never every interface,
    loopback, link-local, a documentation range or an address the internet
    can reach.
    """
    return any(address in net for net in WORKER_NETWORKS)


def _worker_address(host: str) -> bool:
    try:
        return worker_may_listen(ipaddress.IPv4Address(host))
    except ValueError:
        return False  # rpc-server binds an IPv4 literal alone


def beyond_loopback(
    argv: list[str] | tuple[str, ...], env: dict[str, str], *, rpc: bool = False
) -> str | None:
    """Why a native unit's `argv` and `env` would listen where K13 does not let
    it, or None when they keep to it: a server on the loopback alone; with
    `rpc`, a worker on the tunnel address it states, each `-H`/`--host` an
    IPv4 literal :func:`worker_may_listen` allows."""
    stated = stated_hosts(argv, rpc=rpc)
    if rpc:
        if stated and all(_worker_address(h) for h in stated):
            return None
        return (
            "a native rpc worker listens on the address the head reaches it at "
            f"and nothing wider: state it with {RPC_HOST_FLAG}, an IPv4 address "
            "of a private or overlay network (never every interface, loopback, "
            "link-local, a documentation range or a global address; a Mac's "
            "Thunderbolt Bridge assigns itself a 169.254 address: give the "
            "bridge a private address)"
        )
    # Windows reads a variable's name without case: `llama_arg_host` is it too.
    named = any(key.upper() == HOST_ENV for key in env)
    if named or any(h != LOOPBACK for h in stated):
        return (
            f"a native unit listens on {LOOPBACK} alone (the rig agent relays to "
            "it, and pooled workers bind the tunnel address); drop the "
            f"{HOST_FLAG} or {HOST_ENV} its launch states"
        )
    return None
