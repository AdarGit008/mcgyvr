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

:data:`RELEASE` holds no archive until the helper's first release: its
digests are taken from the helper's own reproducible build and checked
against the published archives before they are committed here. Until then
:func:`pinned_for` is false on every system, so no rig offers a native
session, and :func:`helper` refuses before anything is fetched.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from mcgyvr import hostos
from mcgyvr.hubwire import HOST_ARCH, HOST_OS
from mcgyvr.serving.release import Release, ReleaseError, install

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

#: The pinned archives: none until the helper's first release (module docstring).
RELEASE = Release(repo=REPO, tag=TAG, assets=())


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
    from mcgyvr.serving.native import machine_arch

    return machine_arch()


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
