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
            5294307,
            "19fd591e156a945d932596fa3154858ae71fdac54e618e1dcf7d4532e27d1783",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-darwin-x86_64.tar.gz",
            5573158,
            "39c4912f0934a2893476718d2353edc82b6358fa165186ccd2946574d819b89e",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-windows-x86_64.zip",
            5679611,
            "9ce4a1ff02c557b857010bf9e1c7d306626a345830085a7ade24de0ef2d3c029",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-windows-arm64.zip",
            5249776,
            "292299177bee7e17be71490216b76f912068c8752b712e541fee07dbc10a08d9",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-linux-x86_64.tar.gz",
            5604200,
            "c65c35c0dd20a0f47caf350343bf9c7d25300fe9bbbe80f25e48b75941eaf9bb",
        ),
        Asset(
            "mcgyvr-wg-v0.1.0-linux-arm64.tar.gz",
            5215255,
            "7f14f9b45a315e535524aec72d07313545728cebe4ef58be4c8f137bdef492aa",
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
