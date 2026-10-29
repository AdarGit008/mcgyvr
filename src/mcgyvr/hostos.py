"""What differs between Linux, macOS and Windows, answered in one place.

Linux and macOS are POSIX: a file lock is ``flock``, a user is a uid, a file is
opened without following a link by ``O_NOFOLLOW``, a mode says who may read a
file, and a child started in a session of its own is killed with its whole
group. Windows has none of these. It has ``msvcrt.locking``, a per-user profile
whose ACLs say who may read, console process groups, and ``.exe`` programs.
Every module that needs one of these asks here, so each difference is written
once, and on Linux every call below is the very call the caller made before.

Everything is decided when called, from ``sys.platform``, never at import:
the module imports on all three systems (nothing POSIX-only is imported at
the top), and a test can fake any of them. Standard library only.
"""

from __future__ import annotations

import contextlib
import errno
import getpass
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The name mcgyvr's own data and cache folders take under the system's.
APP = "mcgyvr"
#: Where a Windows lock is taken: one byte far past any end a lock file or a
#: journal reaches. Windows byte-range locks are mandatory, so a lock over
#: the content would refuse every other reader of it; a byte past the end
#: guards nothing but itself, which is all a lock file needs.
WINDOWS_LOCK_AT = 0x7FFF_FFFE
#: How often a blocking Windows lock is tried again while another holds it;
#: ``msvcrt`` has no lock call that waits for as long as it takes.
WINDOWS_LOCK_RETRY_S = 0.05
#: The errors ``msvcrt.locking`` raises for a byte another handle holds.
_HELD = frozenset({errno.EACCES, errno.EDEADLK})
#: How long a Windows tree kill is given before the leader alone is killed.
TASKKILL_S = 10.0
#: The kernel's id for the current boot, on Linux.
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
#: macOS's command that prints the id it gives the current boot.
DARWIN_BOOT_ID = ("/usr/sbin/sysctl", "-n", "kern.bootsessionuuid")
#: How long that command is given to answer.
BOOT_ID_S = 5.0
#: What a Windows user name keeps when it names a folder; the rest becomes ``_``.
_UNSAFE_NAME = re.compile(r"[^a-z0-9._-]")
#: The architectures ``platform.machine()`` spells several ways, by one name.
_ARCHES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
    "armv8": "arm64",
    "armv8l": "arm64",
}


def os_name() -> str:
    """``linux``, ``darwin`` or ``windows``; any other POSIX answers ``linux``."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def arch() -> str:
    """``x86_64`` or ``arm64``, as this interpreter runs; else the raw name, lower.

    It is the interpreter's architecture: an x86_64 Python under Rosetta or
    under Windows' ARM emulation answers ``x86_64`` on an ARM machine.
    """
    machine = platform.machine().lower()
    return _ARCHES.get(machine, machine)


def exe(name: str) -> str:
    """``name`` as a program file is named here: ``.exe`` added on Windows."""
    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


# --- locks -----------------------------------------------------------------


def lock(fd: int, *, shared: bool = False, blocking: bool = True) -> None:
    """Lock the open file `fd`, waiting for it unless `blocking` is False.

    POSIX: ``flock``, exclusive unless `shared`; a lock another holder has
    raises :class:`BlockingIOError` when not blocking. Closing the descriptor
    releases it. Windows: ``msvcrt.locking`` of one byte at
    :data:`WINDOWS_LOCK_AT`, always exclusive (there is no shared lock), with
    the file position put back as it was; a held lock raises
    :class:`BlockingIOError` the same way, and a blocking lock is retried
    until it is had. Windows releases it on close too, though not at once, so
    a holder that can should :func:`unlock` first.
    """
    if sys.platform == "win32":
        _windows_lock(fd, blocking=blocking)
        return
    import fcntl

    how = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    fcntl.flock(fd, how if blocking else how | fcntl.LOCK_NB)


def unlock(fd: int) -> None:
    """Release the lock :func:`lock` took on `fd`."""
    if sys.platform == "win32":
        import msvcrt

        with _at_lock_byte(fd):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _windows_lock(fd: int, *, blocking: bool) -> None:
    if sys.platform == "win32":
        import msvcrt

        while True:
            try:
                with _at_lock_byte(fd):
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno not in _HELD:
                    raise
                if not blocking:
                    raise BlockingIOError(
                        errno.EAGAIN, "the lock is held by another holder"
                    ) from exc
                time.sleep(WINDOWS_LOCK_RETRY_S)
                continue
            return


@contextlib.contextmanager
def _at_lock_byte(fd: int) -> Iterator[None]:
    """Stand `fd` at :data:`WINDOWS_LOCK_AT` for the block, then put it back."""
    where = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, WINDOWS_LOCK_AT, os.SEEK_SET)
    try:
        yield
    finally:
        os.lseek(fd, where, os.SEEK_SET)


# --- users, modes and links ------------------------------------------------


def current_user_id() -> str:
    """This user, as a folder name or a message may carry it.

    POSIX: the uid, in decimal. Windows: the login name, lower case, with any
    character a file name should not hold turned into ``_`` (``user`` when
    no name can be read). Windows' temporary folder is already the user's
    own, so the name only keeps two users' folders apart where they share one.
    """
    if sys.platform == "win32":
        try:
            name = getpass.getuser()
        except (ImportError, KeyError, OSError):
            name = ""
        return _UNSAFE_NAME.sub("_", name.lower()) or "user"
    return str(os.getuid())


def posix_ids() -> tuple[int, int] | None:
    """``(uid, gid)`` of this process, or None where there are none (Windows)."""
    if sys.platform == "win32":
        return None
    return os.getuid(), os.getgid()


def owned_by_current_user(found: os.stat_result) -> bool:
    """Whether the file `found` describes belongs to this user.

    POSIX: its uid is ours. Windows: always, since ``st_uid`` is always 0
    there; the files mcgyvr keeps sit in the user's profile or temporary
    folder, which the profile's ACL keeps to that user.
    """
    if sys.platform == "win32":
        return True
    return found.st_uid == os.getuid()


def others_mode_bits(found: os.stat_result, mask: int = 0o077) -> int:
    """The bits of `mask` that `found`'s mode grants group or other.

    POSIX: ``S_IMODE(st_mode) & mask``. Windows: 0, since a mode there says
    only read-only or not; who else may read is the profile ACL's to say.
    """
    if sys.platform == "win32":
        return 0
    return stat.S_IMODE(found.st_mode) & mask


def chmod_private(
    target: int | str | os.PathLike[str], *, directory: bool = False
) -> None:
    """Narrow `target` (a path, or an open descriptor) to its owner alone.

    POSIX: mode 0o700 for a directory, else 0o600; a descriptor is changed
    through ``fchmod``. Windows: nothing; a mode cannot narrow who may read,
    and the user's profile ACL already keeps its files to that user.
    """
    if sys.platform == "win32":
        return
    os.chmod(target, 0o700 if directory else 0o600)


def open_flags_nofollow() -> int:
    """``O_NOFOLLOW`` where the system has it, else 0 (Windows)."""
    return getattr(os, "O_NOFOLLOW", 0)


def open_flags_nonblock() -> int:
    """``O_NONBLOCK`` where the system has it, else 0 (Windows has no FIFOs)."""
    return getattr(os, "O_NONBLOCK", 0)


def open_nofollow(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
    """``os.open(path, flags, mode)`` that refuses to go through a link.

    Where ``O_NOFOLLOW`` exists it is added and the kernel refuses a link.
    Where it does not (Windows), the file is opened and then checked: if the
    path is a link now, or no longer names the file that was opened, the
    descriptor is closed and ``OSError(ELOOP)`` raised, as ``O_NOFOLLOW``
    would have.
    """
    nofollow = open_flags_nofollow()
    fd = os.open(path, flags | nofollow, mode)
    if nofollow:
        return fd
    try:
        seen = os.lstat(path)
        opened = os.fstat(fd)
        if stat.S_ISLNK(seen.st_mode) or (seen.st_dev, seen.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise OSError(
                errno.ELOOP,
                "refused: the path is a link, or changed while it was opened",
                os.fspath(path),
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


# --- processes ---------------------------------------------------------------


def popen_group_kwargs() -> dict[str, Any]:
    """What ``subprocess.Popen`` takes to start a child heading a group of its own.

    POSIX: a new session (``start_new_session``), so the child's children
    share its process group and :func:`kill_group` reaches them all. Windows:
    a new console process group, so :func:`signal_group` reaches it alone.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_group(proc: subprocess.Popen[Any]) -> None:
    """Kill `proc` and everything it started, without asking.

    POSIX: ``SIGKILL`` to its process group; a group already gone raises
    ``ProcessLookupError`` as ``killpg`` does. Windows: ``taskkill /F /T``
    (by its full path under ``%SYSTEMROOT%``) ends the tree, then the leader
    is killed itself in case that could not run.
    """
    if sys.platform == "win32":
        system = os.environ.get("SYSTEMROOT") or r"C:\Windows"
        taskkill = os.path.join(system, "System32", "taskkill.exe")
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [taskkill, "/F", "/T", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=TASKKILL_S,
                check=False,
            )
        proc.kill()
        return
    os.killpg(proc.pid, signal.SIGKILL)


def signal_group(proc: subprocess.Popen[Any], signum: int) -> None:
    """Pass `signum` to the group `proc` heads, so its children hear it too.

    POSIX: ``killpg``. Windows: a console ``CTRL_BREAK_EVENT`` to the group
    :func:`popen_group_kwargs` started, the one interrupt Windows can send to
    a group; the child's Python sees it as ``SIGBREAK``.
    """
    if sys.platform == "win32":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        return
    os.killpg(proc.pid, signum)


def stop_signals() -> tuple[signal.Signals, ...]:
    """The signals that ask a foreground agent to stop: TERM, and HUP or BREAK.

    POSIX: ``SIGTERM`` and ``SIGHUP`` (the terminal went away). Windows has no
    ``SIGHUP``; ``SIGBREAK`` (Ctrl-Break, or :func:`signal_group`) stands in.
    """
    if sys.platform == "win32":
        return signal.SIGTERM, signal.SIGBREAK
    return signal.SIGTERM, signal.SIGHUP


def lower_priority() -> None:
    """Run this process at the lowest priority, or as it is if that is refused.

    POSIX: ``nice(19)``. Windows: the idle priority class.
    """
    if sys.platform == "win32":
        import ctypes

        idle = 0x40  # IDLE_PRIORITY_CLASS
        with contextlib.suppress(OSError, AttributeError):
            kernel = ctypes.windll.kernel32
            kernel.SetPriorityClass(kernel.GetCurrentProcess(), idle)
        return
    with contextlib.suppress(OSError):
        os.nice(19)


def boot_id() -> str | None:
    """The system's id for the current boot, or None when it cannot be read.

    Linux: :data:`BOOT_ID`. macOS: ``kern.bootsessionuuid``. Windows: None,
    so whatever is held to one boot is not trusted past the call that wrote it.
    """
    if sys.platform == "win32":
        return None
    if sys.platform == "darwin":
        try:
            done = subprocess.run(
                DARWIN_BOOT_ID,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=BOOT_ID_S,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        found = done.stdout.strip() if done.returncode == 0 else ""
        return found or None
    try:
        found = BOOT_ID.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return found or None


# --- folders -----------------------------------------------------------------


@dataclass(frozen=True)
class UserDirs:
    """The user's home, and the folders mcgyvr keeps its data and its caches in.

    The config folder is not here: it is ``~/.mcgyvr`` on every system
    (:func:`mcgyvr.fleet.roots.home`).
    """

    home: Path
    data: Path
    cache: Path


def user_dirs() -> UserDirs:
    """Where this user's mcgyvr data and caches go when nothing else says.

    ``$XDG_STATE_HOME`` (when absolute) places the data folder, and
    ``$XDG_CACHE_HOME`` (when set, ``~`` expanded) the cache folder, on every
    system: a variable the user set wins. Unset, each system's own place:

    - Linux: ``~/.local/state/mcgyvr`` and ``~/.cache/mcgyvr``, as before;
    - macOS: ``~/Library/Application Support/mcgyvr`` and
      ``~/Library/Caches/mcgyvr``;
    - Windows: ``%LOCALAPPDATA%\\mcgyvr`` and ``%LOCALAPPDATA%\\mcgyvr\\cache``,
      where an unset or relative ``%LOCALAPPDATA%`` is ``~\\AppData\\Local``.
    """
    home = Path.home()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = (
            Path(local)
            if local and Path(local).is_absolute()
            else home / "AppData" / "Local"
        )
        data, cache = base / APP, base / APP / "cache"
    elif sys.platform == "darwin":
        library = home / "Library"
        data, cache = library / "Application Support" / APP, library / "Caches" / APP
    else:
        data, cache = home / ".local" / "state" / APP, home / ".cache" / APP
    state = os.environ.get("XDG_STATE_HOME")
    if state and Path(state).is_absolute():
        data = Path(state) / APP
    cached = os.environ.get("XDG_CACHE_HOME")
    if cached:
        cache = Path(cached).expanduser() / APP
    return UserDirs(home=home, data=data, cache=cache)


def shell_rc_file(shell: str | None, home: Path | None = None) -> Path | None:
    """The startup file `shell` reads (a path or a name, as ``$SHELL`` gives it).

    bash, zsh, sh/dash and fish under `home` (default: the user's home);
    PowerShell's profile for ``pwsh`` and ``powershell`` (Windows'
    ``.exe`` suffix dropped first). No shell named is zsh on macOS, its
    login shell, and nothing elsewhere; an unknown shell is None.
    """
    if not shell and sys.platform == "darwin":
        shell = "zsh"
    if not shell:
        return None
    base = os.path.basename(shell)
    if sys.platform == "win32" and base.lower().endswith(".exe"):
        base = base[: -len(".exe")]
    home = home if home is not None else Path.home()
    if base == "bash":
        return home / ".bashrc"
    if base == "zsh":
        return home / ".zshrc"
    if base in ("sh", "dash"):
        return home / ".profile"
    if base == "fish":
        return home / ".config" / "fish" / "config.fish"
    if base == "pwsh":
        return home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    if base == "powershell":
        return (
            home
            / "Documents"
            / "WindowsPowerShell"
            / "Microsoft.PowerShell_profile.ps1"
        )
    return None
