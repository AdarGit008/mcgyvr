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
  (https://github.com/ggml-org/llama.cpp/releases/tag/b11960). Release
  v0.8.0's ``nightly-tag.txt`` names b11960 as the build it is.
- The container tag ``server-cuda-b11960`` answers on ghcr.io (manifest HEAD,
  HTTP 200), ``ghcr.io/ggml-org/llama.cpp``.
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
"""

from __future__ import annotations

from dataclasses import dataclass

from mcgyvr.serving.release import Asset, Release

#: The pinned llama.cpp build.
TAG = "b11960"
#: Where it is published.
REPO = "ggml-org/llama.cpp"
#: The Linux container image of the same build, CUDA flavour.
IMAGE = f"ghcr.io/ggml-org/llama.cpp:server-cuda-{TAG}"
#: The programs the native launch runs out of an archive: the server, and the
#: worker a model split across machines starts on each of them.
SERVER = "llama-server"
RPC_SERVER = "ggml-rpc-server"
EXECUTABLES = (SERVER, RPC_SERVER)

#: The backends a native build runs on, spelled as the resource contract
#: spells a backend (``rocm`` aside: no build here is picked for it).
METAL = "metal"
CUDA = "cuda"
VULKAN = "vulkan"
CPU = "cpu"
BACKENDS = (METAL, CUDA, VULKAN, CPU)
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
    _build("darwin", "arm64", METAL, "llama-b11960-bin-macos-arm64.tar.gz"),
    _build("darwin", "x86_64", CPU, "llama-b11960-bin-macos-x64.tar.gz"),
    _build("linux", "x86_64", CPU, "llama-b11960-bin-ubuntu-x64.tar.gz"),
    _build("linux", "arm64", CPU, "llama-b11960-bin-ubuntu-arm64.tar.gz"),
    _build("linux", "x86_64", VULKAN, "llama-b11960-bin-ubuntu-vulkan-x64.tar.gz"),
    _build("linux", "arm64", VULKAN, "llama-b11960-bin-ubuntu-vulkan-arm64.tar.gz"),
    _build(
        "linux",
        "x86_64",
        CUDA,
        "llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
        "cudart-llama-b11960-bin-ubuntu-cuda-13.4-x64.tar.gz",
    ),
    _build(
        "linux",
        "x86_64",
        CUDA,
        "llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "cudart-llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz",
    ),
    _build(
        "linux",
        "arm64",
        CUDA,
        "llama-b11960-bin-ubuntu-cuda-13.4-arm64.tar.gz",
        "cudart-llama-b11960-bin-ubuntu-cuda-13.4-arm64.tar.gz",
    ),
    _build("windows", "x86_64", CPU, "llama-b11960-bin-win-cpu-x64.zip"),
    _build("windows", "arm64", CPU, "llama-b11960-bin-win-cpu-arm64.zip"),
    _build("windows", "x86_64", VULKAN, "llama-b11960-bin-win-vulkan-x64.zip"),
    _build("windows", "arm64", VULKAN, "llama-b11960-bin-win-vulkan-arm64.zip"),
    _build(
        "windows",
        "x86_64",
        CUDA,
        "llama-b11960-bin-win-cuda-13.4-x64.zip",
        "cudart-llama-bin-win-cuda-13.4-x64.zip",
    ),
    _build(
        "windows",
        "x86_64",
        CUDA,
        "llama-b11960-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
    ),
    _build(
        "windows",
        "arm64",
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


def backend_for(os_name: str, arch: str, *, nvidia_driver: str | None) -> str:
    """The backend a native unit runs on here (pin K5).

    macOS on Apple silicon: Metal; an Intel Mac: the CPU. Windows and Linux:
    CUDA when `nvidia_driver` (``nvidia-smi``'s ``driver_version``) runs a
    pinned CUDA build for this architecture, else Vulkan, else the CPU.
    """
    if os_name == "darwin":
        return METAL if arch == "arm64" else CPU
    if nvidia_driver and any(
        b.backend == CUDA and driver_runs(b, nvidia_driver)
        for b in BUILDS
        if (b.os, b.arch) == (os_name, arch)
    ):
        return CUDA
    if any(b.backend == VULKAN for b in BUILDS if (b.os, b.arch) == (os_name, arch)):
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
