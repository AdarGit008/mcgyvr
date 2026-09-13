"""The retired config digest and its journal copy (R2, retired 2026-09-13).

This is the mechanism ``src/mcgyvr/config.py`` carried until the config was
retired in favour of ``fleet.yaml`` + ``policy.yaml``:

* ``DIGEST_PREFIX = "cfg-"`` — the prefix ``Config.digest`` minted;
* ``Config.digest`` — ``cfg-`` plus the sha256 of :meth:`Config.canonical`;
* ``CONFIGS_DIR`` and :func:`keep` — ``<journal>/configs/<digest>.yaml``, the
  copy a result's ``config_digest`` resolved to and the file ``MCGYVR_CONFIG``
  re-selected.

The owner ruled (2026-09-13) that the prefix is retired with the mechanism,
not re-prefixed, because ``mcgyvr.fleet.ids`` refuses ``cfg-`` as a retired
identity kind. The live ``src`` tree no longer contains these definitions; the
functions below are kept verbatim-in-spirit so the old claim is on the record
(``okf/must-read/always.md``: superseded code is archived, never deleted).
Nothing here is imported by live code.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any, Protocol

#: What a config's identity started with, so it could never be read as a
#: product digest or a blob name: those are bare hex.
DIGEST_PREFIX = "cfg-"
#: Where the journal kept the config each run was made under, by its digest:
#: ``<journal.dir>/configs/<digest>.yaml``.
CONFIGS_DIR = "configs"


class _Canonical(Protocol):
    """The one method :func:`digest` and :func:`keep` needed from ``Config``."""

    def canonical(self) -> str: ...


def digest(config: _Canonical) -> str:
    """The retired identity: ``cfg-`` and the sha256 of :meth:`canonical`.

    Over the loaded and validated tree and never over the file's bytes, because
    an identity that moved when a comment was added would name the edit and not
    the setup (owner's ruling R2, 2026-09-06).
    """
    raw = config.canonical().encode("utf-8")
    return DIGEST_PREFIX + hashlib.sha256(raw).hexdigest()


def keep(config: _Canonical, journal_dir: Path) -> Path:
    """File ``config`` under ``journal_dir`` by its digest, and return the path.

    ``<journal_dir>/configs/<digest>.yaml``, holding :meth:`canonical`.
    Content-addressed; a new copy is staged under a name unique to this writer
    and moved into place whole, as the journal's blobs are.
    """
    text = config.canonical()
    where = journal_dir / CONFIGS_DIR
    path = where / f"{digest(config)}.yaml"
    try:
        if path.read_text(encoding="utf-8") == text:
            return path
    except (OSError, UnicodeDecodeError):
        pass
    where.mkdir(parents=True, exist_ok=True)
    staging = where / f".{path.name}.{os.getpid()}-{threading.get_ident()}.part"
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        try:
            data = text.encode("utf-8")
            while data:
                data = data[os.write(fd, data) :]
        finally:
            os.close(fd)
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return path
