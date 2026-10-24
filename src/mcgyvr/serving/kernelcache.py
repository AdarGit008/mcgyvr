"""The rig's store for the kernels a card's driver compiles, kept across starts.

Promise: a llama.cpp unit's container finds the kernels an earlier start of
any unit on its rig compiled, because the CUDA driver's compute cache is a
folder on the rig, ``$MCGYVR_HOME/cuda-cache`` (default
``~/.mcgyvr/cuda-cache``), mounted into the container, rather than a folder
inside the container that is gone when the container is.

An engine image may ship its kernels as PTX only for a card, and the driver
then compiles that PTX at every start and caches the result under
``$CUDA_CACHE_PATH``, else ``$HOME/.nv/ComputeCache``. Which images do so,
and what a start costs without the store, depends on the image and the card;
nothing here states a figure for it.

`folder` names the store under a mcgyvr home the rig resolved. `mount` is how
a container is handed it: one bind mount and the two variables the driver
reads, as a compose volume and environment (`Mount.volume`, `Mount.env`) or
as ``docker run`` flags (`Mount.docker_args`), so every launch path spells
the store the same way.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.fleet.roots import HOME_DIR, HOME_ENV

#: The store's folder under the mcgyvr home, and the store as help text names it.
DIR = "cuda-cache"
SHOWN = f"${HOME_ENV}/{DIR} (default {HOME_DIR}/{DIR})"
#: Where the store is mounted inside a container. `PATH_ENV` names it
#: explicitly, so the store is used whatever user and HOME the image runs as.
MOUNT = "/cuda-cache"
#: The variables the CUDA driver reads for its compute cache: the folder, and
#: the most bytes it keeps there.
PATH_ENV = "CUDA_CACHE_PATH"
SIZE_ENV = "CUDA_CACHE_MAXSIZE"
#: A fact, not a reading: the maximum NVIDIA documents for CUDA_CACHE_MAXSIZE,
#: 4 GiB, against a default of 1 GiB on desktop and server platforms
#: (https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/environment-variables.html).
#: One store serves every unit on a rig, so it gets the most it may hold.
MAX_BYTES = 4294967296


def folder(home: Path) -> Path:
    """The store under `home`, a mcgyvr home as the rig itself resolved it."""
    return home / DIR


@dataclass(frozen=True)
class Mount:
    """The store as one container is handed it: a bind mount and its variables."""

    #: The bind mount, ``<store on the rig>:MOUNT:rw``.
    volume: str
    #: CUDA_CACHE_PATH at the mount and CUDA_CACHE_MAXSIZE at `MAX_BYTES`.
    env: Mapping[str, str] = field(default_factory=dict)

    def docker_args(self) -> list[str]:
        """The same mount as ``docker run`` flags: ``--volume``, then one
        ``--env`` per variable, in name order."""
        args = ["--volume", self.volume]
        for name in sorted(self.env):
            args += ["--env", f"{name}={self.env[name]}"]
        return args


def mount(store: Path) -> Mount:
    """The mount that puts `store`, a folder on the rig, where the driver writes.

    The bind is writable whatever else the container is (a read-only root
    included), and a missing folder is made by the daemon that starts it.
    """
    return Mount(
        volume=f"{store}:{MOUNT}:rw",
        env={PATH_ENV: MOUNT, SIZE_ENV: str(MAX_BYTES)},
    )
