"""Where the hub may be known in the product, as data.

The product is offline and for one user. The hub — other people's cards,
brokered — is reached through the hub client, ``src/mcgyvr/rig/``, and the
``mcgyvr rig`` command in ``src/mcgyvr/cli.py``. Everything else under
``src/mcgyvr/`` is the *offline core* (:func:`in_core`).
``tests/test_only_the_command_line_imports_the_hub_client.py`` holds the core
to importing nothing of the hub client (nor the command line, which imports
it); :data:`IMPORTS_NOT_YET_MOVED` lists the imports it still has.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests._paths import REPO, SRC

#: The hub client's package.
HUB_CLIENT = "mcgyvr.rig"

#: What is not the offline core, relative to ``src/mcgyvr/``: the command line
#: (a ``cli/`` package after the cli.py split) and the hub client.
NOT_CORE_FILES: frozenset[str] = frozenset()
NOT_CORE_DIRS = frozenset({"rig", "cli"})

#: The imports into the hub client, or into the command line, from the offline
#: core that the tree still has, as ``(importer, imported)``: a module by its
#: dotted name, a script that no import reaches by its path under
#: ``src/mcgyvr/``. It is empty: the last one, the pooled session's sandbox
#: reading the WireGuard key's shape from ``rig.sessionwire``, left when that
#: sandbox moved into ``rig/`` as ``rig/pooled.py``.
IMPORTS_NOT_YET_MOVED: frozenset[tuple[str, str]] = frozenset()


def in_core(rel: str) -> bool:
    """Whether a path under ``src/mcgyvr/`` is in the offline core."""
    return rel not in NOT_CORE_FILES and rel.split("/", 1)[0] not in NOT_CORE_DIRS


def core_files(repo: Path = REPO) -> list[str]:
    """Every file git tracks in the offline core, relative to ``src/mcgyvr/``.
    Tracked only, so a stray file in a checkout neither fails nor passes it."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", "src/mcgyvr"],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", "surrogateescape")
    rels = (p.removeprefix("src/mcgyvr/") for p in out.split("\0") if p)
    return sorted(rel for rel in rels if in_core(rel) and (SRC / rel).is_file())
