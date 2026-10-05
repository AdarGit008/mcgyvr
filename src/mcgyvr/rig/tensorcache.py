"""The rig's tensor cache: a worker mounts only files the agent has hashed.

A worker's RPC server (``-c``, ``LLAMA_CACHE``) keeps each tensor its head
sent, over the engine's hash threshold, in a file named by the tensor's hash,
and loads it back by that name alone. In the pinned engine (``llama.cpp``
b10644):

* the engine's RPC server program (``rpc-server.cpp``) puts the files in
  ``<LLAMA_CACHE>/rpc/`` (``fs_get_cache_directory() + "rpc"``);
* ``ggml/src/ggml-rpc/ggml-rpc.cpp``, ``rpc_server::set_tensor``, names one
  ``snprintf("%016" PRIx64, fnv_hash(data, size))`` — the FNV-1a 64 of the
  whole tensor (``fnv_hash``: offset basis ``0xcbf29ce484222325``, prime
  ``0x100000001b3``, xor then multiply), sixteen lower-case hex digits — and
  writes it in place with a truncating ``std::ofstream``: no temporary name,
  no rename;
* ``rpc_server::get_cached_file`` checks only that the name exists, and
  ``set_tensor_hash`` answers ``result = 1`` without hashing what it read.

So a worker killed mid-write leaves the first part of a tensor under the
whole tensor's name, and the next worker to mount the folder loads it as
complete weights. The agent cannot change how the engine writes; it hashes
the folder before a worker mounts it (:meth:`Ledger.check`): a file whose
content hashes to its name is kept, anything else under the folder — a torn
file, a file of any other name, a link — is removed, and the folder is
mounted only while every file in it is one the agent hashed and that has not
changed since (:meth:`Ledger.trusted`).

The ledger outlives the agent. After each check it is written beside the
cache folder (:func:`saved_beside`; never in it, since a worker mounts the
folder), and a new agent reads it back, so the first worker session after an
agent restart mounts the cache instead of being sent every tensor again while
the whole folder is hashed once more. What is read back is trusted no further
than the agent's own memory was: a file counts only while its device, inode,
size and times are what the last agent hashed, so a file written to, cut
short or replaced since is hashed again, a file the ledger does not name is
too, and one that is gone is forgotten. The cache is addressed by content — a
file's name is its tensor's hash, whatever model sent it — so a file that is
whole is right for any model that asks for that name, and the ledger never
says more of a file than that it is whole. The saved ledger names the boot it
was written in (:func:`boot_id`) and is read in that boot alone: a machine
that went down may have lost a file's content and kept its size and times, so
after a reboot, or where the boot cannot be told, the folder is hashed as
before. A saved ledger that does not read is no ledger.

The hashing runs in processes of their own at the lowest priority
(:func:`hash_files`), so the agent's threads never wait on it.
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

#: FNV-1a 64, as the engine's ``fnv_hash`` computes it.
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
_MASK = (1 << 64) - 1
#: A cached tensor's name: ``"%016" PRIx64`` of its hash.
NAME = re.compile(r"[0-9a-f]{16}")
#: How much of a file is read at a time while it is hashed, in bytes.
CHUNK = 1 << 22
#: How many files are hashed at once, each by a process of its own: half the
#: machine's cores, at most four (pure Python hashes about 9 MB/s a core).
HASHERS = max(1, min(4, (os.cpu_count() or 1) // 2))
#: How often a hashing process is looked at, in seconds.
HASHER_POLL_S = 0.01

#: Where the kernel names this boot of the machine.
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
#: The saved ledger's shape, and the most of one that is read, in bytes.
SAVED_VERSION = 1
MAX_SAVED_BYTES = 64 << 20

#: What says a file is the one the agent hashed: its device, inode, size,
#: and the times any write to it changes.
Identity = tuple[int, int, int, int, int]


def fnv1a_64(data: bytes, value: int = FNV_OFFSET) -> int:
    """``data``'s FNV-1a 64, continued from ``value``."""
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & _MASK
    return value


def file_name(path: Path) -> str:
    """The name the engine gives a file of ``path``'s content."""
    value = FNV_OFFSET
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            value = fnv1a_64(chunk, value)
    return f"{value:016x}"


def hash_files(paths: Sequence[Path], stop: threading.Event) -> dict[Path, str]:
    """Each file's name as the engine gives it, :data:`HASHERS` files at once,
    each in a process of its own at the lowest priority; a file that could
    not be read is left out, and so is every file once ``stop`` is set."""
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
    """Everything under ``folder`` but its folders, links not followed."""
    for root, dirs, files in os.walk(folder, followlinks=False):
        for name in [*files, *(d for d in dirs if (Path(root) / d).is_symlink())]:
            path = Path(root) / name
            with contextlib.suppress(OSError):
                yield path, path.lstat()


def _remove(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def boot_id() -> str | None:
    """This boot of the machine, as its kernel names it; ``None`` where it
    does not say."""
    try:
        found = BOOT_ID.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return found or None


def saved_beside(folder: Path) -> Path:
    """Where the ledger of cache ``folder`` is kept: beside it, not in it."""
    return folder.with_name(folder.name + ".ledger.json")


def _read_saved(saved: Path) -> dict[Path, Identity]:
    """What ``saved`` says was hashed, when it was written in this boot and
    reads whole; nothing otherwise."""
    boot = boot_id()
    if boot is None:
        return {}
    try:
        descriptor = os.open(saved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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
    """The files of a cache folder an agent hashed, as they were then: this
    agent's, and with ``saved`` the last agent's of this boot, read from it
    and written back after each check."""

    def __init__(self, saved: Path | None = None) -> None:
        self._saved = saved
        self._known: dict[Path, Identity] = {} if saved is None else _read_saved(saved)

    def _save(self) -> None:
        """Write what is known to the saved ledger, whole or not at all; a
        ledger that could not be written is one the next agent hashes for."""
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
            descriptor = os.open(
                partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                json.dump(document, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(partial, self._saved)
        except OSError:
            _remove(partial)

    def trusted(self, folder: Path) -> bool:
        """Whether every file under ``folder`` is one this agent hashed, and
        unchanged since: only such a folder may be mounted."""
        for path, found in _entries(folder):
            if self._known.get(path) != _identity(found):
                return False
        return True

    def check(self, folder: Path, stop: threading.Event) -> None:
        """Hash what under ``folder`` is not yet known; keep each file whose
        content hashes to its name, remove everything else. No worker may
        have the folder mounted meanwhile."""
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
                continue  # written to while it was hashed: hashed next time
            if named.get(path) == path.name:
                self._known[path] = identity
            else:
                _remove(path)
        self._save()


if __name__ == "__main__":
    # One file's name, for :func:`hash_files`.
    with contextlib.suppress(OSError):
        os.nice(19)
    sys.stdout.write(file_name(Path(sys.argv[1])) + "\n")
