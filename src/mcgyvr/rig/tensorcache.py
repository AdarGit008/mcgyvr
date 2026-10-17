""

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

#
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
_MASK = (1 << 64) - 1
#
NAME = re.compile(r"[0-9a-f]{16}")
#
CHUNK = 1 << 22
#
#
HASHERS = max(1, min(4, (os.cpu_count() or 1) // 2))
#
HASHER_POLL_S = 0.01

#
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
#
SAVED_VERSION = 1
MAX_SAVED_BYTES = 64 << 20

#
#
Identity = tuple[int, int, int, int, int]


def fnv1a_64(data: bytes, value: int = FNV_OFFSET) -> int:
    ""
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & _MASK
    return value


def file_name(path: Path) -> str:
    ""
    value = FNV_OFFSET
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            value = fnv1a_64(chunk, value)
    return f"{value:016x}"


def hash_files(paths: Sequence[Path], stop: threading.Event) -> dict[Path, str]:
    ""
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
    ""
    for root, dirs, files in os.walk(folder, followlinks=False):
        for name in [*files, *(d for d in dirs if (Path(root) / d).is_symlink())]:
            path = Path(root) / name
            with contextlib.suppress(OSError):
                yield path, path.lstat()


def _remove(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def boot_id() -> str | None:
    ""
    try:
        found = BOOT_ID.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return found or None


def saved_beside(folder: Path) -> Path:
    ""
    return folder.with_name(folder.name + ".ledger.json")


def _read_saved(saved: Path) -> dict[Path, Identity]:
    ""
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
    ""

    def __init__(self, saved: Path | None = None) -> None:
        self._saved = saved
        self._known: dict[Path, Identity] = {} if saved is None else _read_saved(saved)

    def _save(self) -> None:
        ""
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
        ""
        for path, found in _entries(folder):
            if self._known.get(path) != _identity(found):
                return False
        return True

    def check(self, folder: Path, stop: threading.Event) -> None:
        ""
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
                continue  #
            if named.get(path) == path.name:
                self._known[path] = identity
            else:
                _remove(path)
        self._save()


if __name__ == "__main__":
    #
    with contextlib.suppress(OSError):
        os.nice(19)
    sys.stdout.write(file_name(Path(sys.argv[1])) + "\n")
