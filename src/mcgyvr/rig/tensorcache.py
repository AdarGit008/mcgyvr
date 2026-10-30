"""Content-addressed tensor cache.

Files are stored under the 16 lowercase hex digits of the FNV-1a 64-bit hash of
their contents, so a file whose name matches its hash is known to be intact.
This module names files by hashing them in low-priority child processes that
re-enter it as ``__main__``, and keeps a ledger of the stat identity (device,
inode, size, mtime, ctime) of every file it has verified, saved as JSON beside
the cache directory. A later check only re-reads files whose stat identity
changed, and removes anything that is not a regular file named like a digest or
that does not hash to its own name.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

from mcgyvr import hostos

#: FNV-1a 64-bit: the offset basis, prime multiplier and the mask that keeps
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
_MASK = (1 << 64) - 1
#: Exactly what a cache file may be called: 16 lowercase hex digits.
NAME = re.compile(r"[0-9a-f]{16}")
#: Bytes read per iteration when streaming a file through the hash.
CHUNK = 1 << 22
#: Hashing runs in child processes, so a large tensor never competes with the
#: agent's interpreter; this bounds how many of them run at once.
HASHERS = max(1, min(4, (os.cpu_count() or 1) // 2))
#: Seconds between polls for a finished hasher child.
HASHER_POLL_S = 0.01

#: Identifies the current boot: a ledger written in another boot is discarded.
#: Ledger format version, and the largest ledger file this code will read.
SAVED_VERSION = 1
MAX_SAVED_BYTES = 64 << 20

#: Device, inode, size, mtime and ctime in nanoseconds: what a cached hash is
#: trusted against, rechecked before the file is used.
Identity = tuple[int, int, int, int, int]


def fnv1a_64(data: bytes, value: int = FNV_OFFSET) -> int:
    """Return the 64-bit FNV-1a hash of ``data``, starting from ``value``.

    ``value`` defaults to FNV_OFFSET, so passing a previous result continues the
    hash over the chunk that follows it.
    """
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & _MASK
    return value


def file_name(path: Path) -> str:
    """Return the cache name of ``path``: its FNV-1a 64-bit hash, as 16 hex digits.

    The file is read in CHUNK-sized pieces and folded into a running hash, so a
    multi-gigabyte tensor is never held in memory.
    """
    value = FNV_OFFSET
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            value = fnv1a_64(chunk, value)
    return f"{value:016x}"


def hash_files(paths: Sequence[Path], stop: threading.Event) -> dict[Path, str]:
    """Hash ``paths`` in parallel child processes and return ``{path: digest}``.

    Each child re-runs this module on a single path and prints its name. A path is
    reported only when its child exits with status 0 and prints something that
    NAME matches in full; a child that fails, is killed or prints anything else
    simply leaves its path out of the result. At most HASHERS children run at once
    and the running ones are polled every HASHER_POLL_S seconds. If ``stop`` is
    set, the mapping collected so far is dropped and {} is returned. Any child
    still running on the way out is killed and its pipe closed.
    """
    waiting = list(reversed(paths))
    running: dict[Path, subprocess.Popen[bytes]] = {}
    found: dict[Path, str] = {}
    try:
        while waiting or running:
            if stop.is_set():
                return {}
            while waiting and len(running) < HASHERS:
                path = waiting.pop()
                running[path] = subprocess.Popen(
                    [sys.executable, "-m", __name__, str(path)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            for path, process in list(running.items()):
                if process.poll() is None:
                    continue
                del running[path]
                out = process.stdout.read() if process.stdout else b""
                name = out.decode("ascii", "replace").strip()
                if process.returncode == 0 and NAME.fullmatch(name):
                    found[path] = name
            time.sleep(HASHER_POLL_S)
        return found
    finally:
        for process in running.values():
            with contextlib.suppress(OSError):
                process.kill()
            process.wait()
        for process in running.values():
            if process.stdout:
                process.stdout.close()


def _identity(found: os.stat_result) -> Identity:
    return (
        found.st_dev,
        found.st_ino,
        found.st_size,
        found.st_mtime_ns,
        found.st_ctime_ns,
    )


def _entries(folder: Path) -> Iterator[tuple[Path, os.stat_result]]:
    """Yield ``(path, lstat)`` for every entry under ``folder``.

    Every file entry of the walk is yielded, together with symlinks that appear in
    the directory list (``os.walk`` lists but does not descend into them). Symlinks
    are never followed, and an entry whose ``lstat`` raises OSError is skipped.
    """
    for root, dirs, files in os.walk(folder, followlinks=False):
        for name in [*files, *(d for d in dirs if (Path(root) / d).is_symlink())]:
            path = Path(root) / name
            with contextlib.suppress(OSError):
                yield path, path.lstat()


def _remove(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def boot_id() -> str | None:
    """Return the system's identifier for the current boot, or None if unreadable.

    Read by :func:`mcgyvr.hostos.boot_id`; Windows has none, so there no ledger is
    trusted and every file is hashed again.
    """
    return hostos.boot_id()


def saved_beside(folder: Path) -> Path:
    """Return the ledger path kept beside ``folder``: ``<folder name>.ledger.json``."""
    return folder.with_name(folder.name + ".ledger.json")


def _read_saved(saved: Path) -> dict[Path, Identity]:
    """Return the ``{path: identity}`` pairs recorded in the ledger file ``saved``.

    {} is returned whenever the ledger cannot be trusted as a whole: when the boot
    id is unknown, when the file cannot be opened without following a symlink, when
    it is not a regular file of at most MAX_SAVED_BYTES, when its JSON has the
    wrong SAVED_VERSION, boot id or shape, or when any key is not an absolute path
    named like a cache entry with a five-integer identity.
    """
    boot = boot_id()
    if boot is None:
        return {}
    try:
        descriptor = hostos.open_nofollow(
            saved, os.O_RDONLY | hostos.open_flags_nonblock()
        )
    except OSError:
        return {}
    try:
        with os.fdopen(descriptor, "rb") as handle:
            found = os.fstat(handle.fileno())
            if not stat.S_ISREG(found.st_mode) or found.st_size > MAX_SAVED_BYTES:
                return {}
            document = json.loads(handle.read(MAX_SAVED_BYTES + 1))
    except (OSError, ValueError, RecursionError):
        return {}
    if (
        not isinstance(document, dict)
        or document.get("v") != SAVED_VERSION
        or document.get("boot") != boot
        or not isinstance(document.get("files"), dict)
    ):
        return {}
    known: dict[Path, Identity] = {}
    for name, identity in document["files"].items():
        path = Path(name)
        if (
            not path.is_absolute()
            or not NAME.fullmatch(path.name)
            or not isinstance(identity, list)
            or len(identity) != 5
            or not all(type(part) is int for part in identity)
        ):
            return {}
        known[path] = (
            identity[0],
            identity[1],
            identity[2],
            identity[3],
            identity[4],
        )
    return known


class Ledger:
    """The cache files verified so far, as ``{path: identity}``.

    The set is kept in memory between calls and, when a ledger path is given, is
    loaded from that file on construction and written back after every check, so
    an unchanged cache directory need not be rehashed in the same boot.
    """

    def __init__(self, saved: Path | None = None) -> None:
        self._saved = saved
        self._known: dict[Path, Identity] = {} if saved is None else _read_saved(saved)

    def _save(self) -> None:
        """Persist the known identities, if there is a ledger path and a boot id.

        The JSON is written to a per-pid temporary file opened with mode 0600, flushed
        and fsynced, then renamed over the ledger, so a reader sees either the old or
        the new document. Any OSError leaves the previous ledger untouched.
        """
        boot = boot_id()
        if self._saved is None or boot is None:
            return
        document = {
            "v": SAVED_VERSION,
            "boot": boot,
            "files": {str(path): list(i) for path, i in sorted(self._known.items())},
        }
        partial = self._saved.with_name(f"{self._saved.name}.{os.getpid()}.tmp")
        try:
            _remove(partial)
            descriptor = hostos.open_nofollow(
                partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                json.dump(document, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(partial, self._saved)
        except OSError:
            _remove(partial)

    def trusted(self, folder: Path) -> bool:
        """Return True when ``folder`` holds only files whose identity is already known.

        False as soon as an entry is missing from the known set or has different stat
        data, which includes every file the ledger never listed.
        """
        for path, found in _entries(folder):
            if self._known.get(path) != _identity(found):
                return False
        return True

    def check(self, folder: Path, stop: threading.Event) -> None:
        """Re-verify ``folder`` and update the ledger to match what is there.

        Entries that are not regular files named like a digest are removed. Files whose
        identity changed are forgotten and passed to :func:`hash_files`; each survives
        only if it still has the same identity after hashing and its digest equals its
        file name, and is removed otherwise. Identities of files that are gone are
        dropped. If ``stop`` is set while hashing, the unhashed files are left alone and
        nothing is saved; otherwise the ledger is saved at the end.
        """
        present: set[Path] = set()
        asked: dict[Path, Identity] = {}
        for path, found in _entries(folder):
            if not stat.S_ISREG(found.st_mode) or not NAME.fullmatch(path.name):
                _remove(path)
                continue
            present.add(path)
            identity = _identity(found)
            if self._known.get(path) != identity:
                self._known.pop(path, None)
                asked[path] = identity
        self._known = {p: i for p, i in self._known.items() if p in present}
        named = hash_files(sorted(asked), stop)
        if stop.is_set():
            return
        for path, identity in asked.items():
            try:
                now = _identity(path.lstat())
            except OSError:
                continue
            if now != identity:
                continue  # changed while being hashed, so redo it on a later check
            if named.get(path) == path.name:
                self._known[path] = identity
            else:
                _remove(path)
        self._save()


if __name__ == "__main__":
    # Hasher child: name the one path given, at the lowest priority.
    hostos.lower_priority()
    sys.stdout.write(file_name(Path(sys.argv[1])) + "\n")
