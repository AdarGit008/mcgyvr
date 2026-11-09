"""The one ``mcgyvr-wg`` build a native pooled session runs: pinned by tag and sha256.

``mcgyvr-wg`` is the userspace WireGuard helper of a Mac or Windows rig's
pooled sessions: wireguard-go with its netstack IP stack, no TUN device and
no admin rights. It is built in a repository of its own and published as one
archive per system and architecture; this module pins which
(:data:`TAG`), where (:data:`REPO`), what each archive is called
(:func:`asset_name`) and, for each, the length and sha256 it must have
(:data:`RELEASE`), as :mod:`mcgyvr.serving.llamacpp` pins llama.cpp. The
archives are fetched, verified and unpacked by :mod:`mcgyvr.serving.release`,
nothing else, and nothing that is not pinned here is fetched.

:data:`RELEASE` holds one archive per system and architecture of the
helper's ``v0.1.0``: each digest is taken from the helper's own reproducible
build and was checked against the archive both the GitHub release and the
Forgejo release publish before it was committed here. A Linux rig never runs
the helper (its sessions run in docker); its archives are pinned because the
helper ships them. A system or architecture with no row offers no native
session, and :func:`helper` refuses for it before anything is fetched.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from mcgyvr import hostos
from mcgyvr.hubwire import HOST_ARCH, HOST_OS
from mcgyvr.serving.release import Asset, Release, ReleaseError, install

#: The pinned helper release.
TAG = "v0.1.0"
#: Where it is published (the helper's own repository, mirrored where
#: :data:`mcgyvr.serving.release.DOWNLOAD_URL` reaches it).
REPO = "AdarGit008/mcgyvr-wg"
#: The program each archive holds (``.exe`` added on Windows).
PROGRAM = "mcgyvr-wg"
#: The version of the stdin/stdout grammar the agent speaks to the helper; the
#: helper's banner names the one it speaks, and any other is refused.
PROTO = 1
#: The archive kind each system's asset is published as.
ARCHIVE = {"darwin": "tar.gz", "linux": "tar.gz", "windows": "zip"}

#: The pinned archives: the helper's v0.1.0, built reproducibly from the tag
#: (Go 1.27.3, CGO off, ``-trimpath``) and checked against the archives the
#: GitHub release and the Forgejo release publish (module docstring).
RELEASE = Release(
    repo=REPO,
    tag=TAG,
    assets=(
        Asset(
            "mcgyvr-wg-v0.1.0-darwin-arm64.tar.gz",
            5294497,
            "7f446f355976ae9d1bdb45c01dfcee716f0374466ea3968851a33365b5200b28",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-darwin-x86_64.tar.gz",
            5573119,
            "068f811df409a61e54d2696dd992d25706c613725bc4d49eb3dff7ffe37aa980",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-windows-x86_64.zip",
            5679609,
            "1f024978b2c1af9c45253971ee2cc26a1a4771ae37dcc639e5d259c67e103e78",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-windows-arm64.zip",
            5249751,
            "3fbcb938e012899ccc21474dd92dbcbbbc392cf36bca788c7ec18c01b61f5c73",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-linux-x86_64.tar.gz",
            5604288,
            "4447d4561a430d16c055aa3269b17528ebe6d56e639cbefe0de5a14cb51370a1",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-linux-arm64.tar.gz",
            5215185,
            "b097eb0a446d7db0ca4529d7f50c63395fc9ad0fe89c5fecd8c25ec13818acc2",
        ),
    ),
)


def asset_name(os_name: str, arch: str) -> str:
    """The archive of the pinned helper for one system and architecture.

    ``mcgyvr-wg-<tag>-<os>-<arch>.<tar.gz|zip>``, the system and architecture
    spelled as the wire spells them (:data:`mcgyvr.hubwire.HOST_OS`,
    :data:`mcgyvr.hubwire.HOST_ARCH`).
    """
    if os_name not in HOST_OS or arch not in HOST_ARCH:
        raise ReleaseError(f"no mcgyvr-wg archive is named for {os_name} {arch}")
    return f"{PROGRAM}-{TAG}-{os_name}-{arch}.{ARCHIVE[os_name]}"


def pinned_for(os_name: str, arch: str) -> bool:
    """Whether a helper archive is pinned for this system and architecture,
    read from the table alone: nothing is fetched."""
    try:
        name = asset_name(os_name, arch)
    except ReleaseError:
        return False
    return any(asset.name == name for asset in RELEASE.assets)


@cache
def _arch() -> str:
    from mcgyvr.serving import rigscan

    return str(rigscan.host()["arch"])


def pinned_here() -> bool:
    """Whether a helper archive is pinned for this machine; a rig offers a
    native session only then (the architecture is read once)."""
    return pinned_for(hostos.os_name(), _arch())


def install_dir() -> Path:
    """Where the helper is unpacked: one folder per system and architecture,
    the same across pin bumps, so a firewall's rule for the program keeps
    naming it."""
    from mcgyvr.fleet.roots import home

    return home() / "bin" / PROGRAM


def helper(os_name: str, arch: str) -> Path:
    """The pinned helper program for this system and architecture, fetched and
    verified on first use; :class:`ReleaseError` when none is pinned for it or
    it cannot be fetched as pinned."""
    name = asset_name(os_name, arch)
    if not pinned_for(os_name, arch):
        raise ReleaseError(
            f"no pinned {PROGRAM} {TAG} archive for {os_name} {arch}; a native "
            "pooled session needs it, and nothing unpinned is fetched"
        )
    folder = install(
        RELEASE, [name], install_dir() / f"{os_name}-{arch}", executables=[PROGRAM]
    )
    return folder / hostos.exe(PROGRAM)
