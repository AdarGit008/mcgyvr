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

import calendar
import contextlib
import errno
import functools
import getpass
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
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
#: macOS's ``ps``, which reads a process's start time without privilege.
DARWIN_PS = "/bin/ps"
#: ``%c`` in the C locale, which is how that ``ps`` prints a start time.
DARWIN_LSTART = "%a %b %d %H:%M:%S %Y"
#: How long that command is given to answer.
BOOT_ID_S = 5.0
#: The bit of a Windows reparse tag that marks a name surrogate: a symbolic
#: link or a junction, which sends a path somewhere else (a cloud-file
#: placeholder carries a tag without it, and is a plain file).
_NAME_SURROGATE = 0x2000_0000
#: Windows' answers for a process that is still running, and for a pid that
#: names no process; and the access asked to read a process's exit code.
_STILL_ACTIVE = 259
_ERROR_INVALID_PARAMETER = 87
_QUERY_LIMITED_INFORMATION = 0x1000
#: The access asked to end a process; Windows' creation flags subprocess does
#: not name: no console, and out of the starter's job; and the job limit that
#: ends a job's processes when its last handle closes, set as the extended
#: limit information class.
_PROCESS_TERMINATE = 0x0001
_DETACHED_PROCESS = 0x0000_0008
_CREATE_BREAKAWAY_FROM_JOB = 0x0100_0000
_CREATE_NO_WINDOW = 0x0800_0000
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x0000_2000
_JOB_EXTENDED_LIMIT_INFORMATION = 9
#: What a Windows user name keeps when it names a folder; the rest becomes ``_``.
_UNSAFE_NAME = re.compile(r"[^a-z0-9._-]")


def os_name() -> str:
    """``linux``, ``darwin`` or ``windows``; any other POSIX answers ``linux``."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def exe(name: str) -> str:
    """``name`` as a program file is named here: ``.exe`` added on Windows."""
    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


# --- locks -----------------------------------------------------------------


def lock(fd: int, *, blocking: bool = True) -> None:
    """Lock the open file `fd`, waiting for it unless `blocking` is False.

    POSIX: an exclusive ``flock``; a lock another holder has raises
    :class:`BlockingIOError` when not blocking. Closing the descriptor
    releases it. Windows: ``msvcrt.locking`` of one byte at
    :data:`WINDOWS_LOCK_AT`, with the file position put back as it was; a held
    lock raises :class:`BlockingIOError` the same way, and a blocking lock is retried
    until it is had. Windows releases it on close too, though not at once, so
    a holder that can should :func:`unlock` first.
    """
    if sys.platform == "win32":
        _windows_lock(fd, blocking=blocking)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)


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

    POSIX: the uid, in decimal. Windows: the login name from the environment,
    lower case, with any character a file name should not hold turned into
    ``_`` (``user`` when no name can be read). It is a label, not a proof: on
    Windows the per-user folders sit under the user's own profile
    (:func:`user_temp_root`), which is what keeps them apart.
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

    POSIX: its uid is ours. Windows: not checked, and always True, since
    ``st_uid`` is always 0 there; who may use the file is its folder's ACL's
    to say. The folders mcgyvr makes by default are in the user's profile,
    whose ACL keeps them to that user; a folder named by ``$MCGYVR_HOME``,
    ``$MCGYVR_DATA`` or an XDG variable keeps whatever ACL it has.
    """
    if sys.platform == "win32":
        return True
    return found.st_uid == os.getuid()


def others_mode_bits(found: os.stat_result, mask: int = 0o077) -> int:
    """The bits of `mask` that `found`'s mode grants group or other.

    POSIX: ``S_IMODE(st_mode) & mask``. Windows: not checked, and always 0,
    since a mode there says only read-only or not; who else may read is the
    folder's ACL's to say (:func:`owned_by_current_user`).
    """
    if sys.platform == "win32":
        return 0
    return stat.S_IMODE(found.st_mode) & mask


def is_link(found: os.stat_result) -> bool:
    """Whether `found` (from ``lstat``) is a link a path is sent through.

    POSIX: a symbolic link. Windows: a symbolic link or a junction (a reparse
    point whose tag is a name surrogate), which ``S_ISLNK`` does not report and
    any user can make without privilege.
    """
    if stat.S_ISLNK(found.st_mode):
        return True
    if sys.platform == "win32":
        return bool(getattr(found, "st_reparse_tag", 0) & _NAME_SURROGATE)
    return False


def chmod_private(
    target: int | str | os.PathLike[str], *, directory: bool = False
) -> None:
    """Narrow `target` (a path, or an open descriptor) to its owner alone.

    POSIX: mode 0o700 for a directory, else 0o600; a descriptor is changed
    through ``fchmod``. Windows: nothing is changed, since a mode cannot
    narrow who may read. A file there is as private as its folder's ACL makes
    it: the user's alone in the profile folders mcgyvr makes by default, and
    as inherited anywhere else.
    """
    if sys.platform == "win32":
        return
    os.chmod(target, 0o700 if directory else 0o600)


def _nofollow() -> int:
    """``O_NOFOLLOW`` where the system has it, else 0 (Windows)."""
    return getattr(os, "O_NOFOLLOW", 0)


def open_flags_nonblock() -> int:
    """``O_NONBLOCK`` where the system has it, else 0 (Windows has no FIFOs)."""
    return getattr(os, "O_NONBLOCK", 0)


def open_flags_binary() -> int:
    """``O_BINARY`` where the system has it (Windows), else 0.

    Windows' ``os.open`` opens in text mode otherwise: a written ``\\n``
    becomes ``\\r\\n`` and a read stops at Ctrl-Z.
    """
    return getattr(os, "O_BINARY", 0)


def open_nofollow(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
    """``os.open(path, flags, mode)`` that refuses to go through a link.

    The file is opened in binary mode (:func:`open_flags_binary`). Where
    ``O_NOFOLLOW`` exists it is added and the kernel refuses a link. Where it
    does not (Windows), the link is detected after the open rather than
    prevented: if the path is a link or junction (:func:`is_link`), or no
    longer names the file that was opened, the descriptor is closed and
    ``OSError(ELOOP)`` raised, as ``O_NOFOLLOW`` would have. What the open
    did through the link (``O_CREAT`` making its target) is not undone, so on
    Windows this relies on the folder being the user's own.
    """
    nofollow = _nofollow()
    fd = os.open(path, flags | nofollow | open_flags_binary(), mode)
    if nofollow:
        return fd
    try:
        seen = os.lstat(path)
        opened = os.fstat(fd)
        if is_link(seen) or (seen.st_dev, seen.st_ino) != (
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
    is killed itself in case that could not run. Windows follows the tree by
    live parents only, so once the leader has exited, what it left running is
    not reached; a Job Object would reach it, and is not used here.
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


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid exists, asked without touching it.

    POSIX: signal 0; a pid that cannot be signalled but is there (another
    user's) counts as running, and only one the kernel reports gone is dead.
    Windows, where ``os.kill(pid, 0)`` would send a Ctrl-C event: the process
    is opened to read its exit code; a pid naming no process is dead, one that
    cannot be opened (another user's) counts as running, and so does one that
    exited with code 259, which Windows cannot tell from still running.
    """
    if sys.platform == "win32":
        import _winapi

        try:
            handle = _winapi.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
        except OSError as exc:
            return getattr(exc, "winerror", None) != _ERROR_INVALID_PARAMETER
        try:
            return _winapi.GetExitCodeProcess(handle) == _STILL_ACTIVE
        except OSError:
            return True
        finally:
            _winapi.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def process_start_time(pid: int) -> str | None:
    """When `pid` started, as a token compared only with a later reading of it.

    A pid can be reused by a new process once the first is gone; the pid with
    the start time it had names one process. Linux: field 22 of
    ``/proc/<pid>/stat`` (clock ticks since boot). macOS: ``ps -o lstart=``,
    "the exact time the command started, using the '%c' format described in
    strftime(3)" (https://keith.github.io/xcode-man-pages/ps.1.html), read in
    the C locale and UTC so every reader spells it alike, as whole seconds
    since the epoch (one plain token, as a lease line needs). Windows: the creation
    time ``GetProcessTimes`` gives, in 100 ns units
    (https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes).
    None when it cannot be read: the process is gone, or not this user's to ask.
    """
    if sys.platform == "win32":
        return _windows_start_time(pid)
    if sys.platform == "darwin":
        try:
            done = subprocess.run(
                [DARWIN_PS, "-o", "lstart=", "-p", str(pid)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=BOOT_ID_S,
                check=False,
                env={"LC_ALL": "C", "TZ": "UTC", "PATH": "/usr/bin:/bin"},
            )
        except (OSError, subprocess.SubprocessError):
            return None
        found = " ".join(done.stdout.split()) if done.returncode == 0 else ""
        try:
            return str(calendar.timegm(time.strptime(found, DARWIN_LSTART)))
        except ValueError:
            return None
    try:
        record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        start = record.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None
    return start if start.isdigit() else None


@functools.cache
def _kernel32() -> Any:
    """kernel32, with the calls that answer a HANDLE declared so once.

    ctypes takes an undeclared result for a C ``int``, which would cut a
    64-bit HANDLE short.
    """
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel


def _windows_start_time(pid: int) -> str | None:
    """``GetProcessTimes``' creation time of `pid`, or None."""
    import ctypes
    from ctypes import wintypes

    kernel = _kernel32()
    handle = kernel.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        created = times[0]
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


def popen_detached_kwargs(*, breakaway: bool = True) -> dict[str, Any]:
    """What ``subprocess.Popen`` takes to start a child that outlives its starter.

    POSIX: a new session, so no signal sent to the starter's group or
    terminal reaches it. Windows: a new process group with no console
    (``DETACHED_PROCESS``), and, when `breakaway`, out of any job the starter
    runs in (``CREATE_BREAKAWAY_FROM_JOB``): a job that kills its processes
    when it closes would otherwise end the child with its starter. A job that
    forbids breaking away makes the start fail; the caller then starts it
    again without `breakaway`.
    (https://docs.python.org/3/library/subprocess.html#windows-constants)
    """
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | _DETACHED_PROCESS
        if breakaway:
            flags |= _CREATE_BREAKAWAY_FROM_JOB
        return {"creationflags": flags}
    return {"start_new_session": True}


def popen_no_window_kwargs() -> dict[str, Any]:
    """What ``subprocess.Popen`` takes so a console program opens no window.

    Windows gives a console program started by a process with no console of
    its own (a detached supervisor) a new visible console, whose closing ends
    it; ``CREATE_NO_WINDOW`` starts it with none
    (https://docs.python.org/3/library/subprocess.html#subprocess.CREATE_NO_WINDOW).
    Nothing elsewhere.
    """
    if sys.platform == "win32":
        return {"creationflags": _CREATE_NO_WINDOW}
    return {}


def kill_on_close_job(proc: subprocess.Popen[Any]) -> int | None:
    """Tie `proc` to this process's life where the system can, and say how.

    Windows: a Job Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``, which
    "causes all processes associated with the job to terminate when the last
    handle to the job is closed"
    (https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information),
    set through ``SetInformationJobObject`` with
    ``JobObjectExtendedLimitInformation`` (9)
    (https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-setinformationjobobject),
    and `proc` assigned to it. The handle returned is this process's only one:
    it closes when this process ends, however it ends, and `proc` and what it
    started end with it. None when no job could be made, and on POSIX, which
    has no such object: there the caller ends the group itself
    (:func:`end_pid`).
    """
    if sys.platform == "win32":
        return _windows_job(proc)
    return None


def _windows_job(proc: subprocess.Popen[Any]) -> int | None:
    """The Job Object :func:`kill_on_close_job` makes on Windows, or None."""
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _Io(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _Basic),
            ("IoInfo", _Io),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = _kernel32()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    handle = int(getattr(proc, "_handle", 0))
    if not (
        kernel.SetInformationJobObject(
            job,
            _JOB_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        and handle
        and kernel.AssignProcessToJobObject(job, handle)
    ):
        kernel.CloseHandle(job)
        return None
    return int(job)


def end_pid(pid: int, *, force: bool = False, group: bool = False) -> bool:
    """Ask the process `pid` (and its group, when `group`) to end; True if asked.

    For a process this one did not start and holds no handle to, such as a
    supervisor found by its record. POSIX: ``SIGTERM``, or ``SIGKILL`` when
    `force`, to the pid or, when `group`, to the group it heads. Windows:
    ``TerminateProcess``, which is the only end Windows gives a process with
    no console of its own; `group` is not reached there, which is what a Job
    Object (:func:`kill_on_close_job`) is for. False when the process is gone
    or not this user's to end.
    """
    if sys.platform == "win32":
        kernel = _kernel32()
        handle = kernel.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if not handle:
            return False
        try:
            return bool(kernel.TerminateProcess(handle, 1))
        finally:
            kernel.CloseHandle(handle)
    signum = signal.SIGKILL if force else signal.SIGTERM
    try:
        if group:
            os.killpg(pid, signum)
        else:
            os.kill(pid, signum)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def inherited_fd_kwargs(fd: int) -> tuple[str, dict[str, Any]]:
    """How a child is handed a pipe's write end `fd`: its name, and Popen's kwargs.

    POSIX: the descriptor number, kept open across exec by ``pass_fds``.
    Windows, where ``pass_fds`` is not supported: the OS handle behind `fd`,
    made inheritable and passed alone in the ``handle_list``
    (https://docs.python.org/3/library/subprocess.html#subprocess.STARTUPINFO);
    the child opens it again with :func:`inherited_fd`.
    """
    if sys.platform == "win32":
        import msvcrt

        handle = msvcrt.get_osfhandle(fd)
        os.set_handle_inheritable(handle, True)
        info = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [handle]})  # type: ignore[attr-defined]
        return str(handle), {"startupinfo": info, "close_fds": True}
    return str(fd), {"pass_fds": (fd,)}


def inherited_fd(name: str) -> int:
    """The descriptor the name :func:`inherited_fd_kwargs` gave stands for here."""
    if sys.platform == "win32":
        import msvcrt

        return msvcrt.open_osfhandle(int(name), os.O_WRONLY)
    return int(name)


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


def user_data_dir() -> Path:
    """Where this user's mcgyvr data goes when ``$MCGYVR_DATA`` does not say.

    ``mcgyvr`` under ``$XDG_STATE_HOME`` when that is absolute, on every
    system: a variable the user set wins. Unset, each system's own place:
    Linux ``~/.local/state/mcgyvr``, as before; macOS
    ``~/Library/Application Support/mcgyvr``; Windows
    ``%LOCALAPPDATA%\\mcgyvr``. The home is looked up only when needed.
    """
    state = os.environ.get("XDG_STATE_HOME")
    if state and Path(state).is_absolute():
        return Path(state) / APP
    if sys.platform == "win32":
        return _local_app_data() / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    return Path.home() / ".local" / "state" / APP


def user_cache_dir() -> Path:
    """Where this user's mcgyvr caches go.

    ``mcgyvr`` under ``$XDG_CACHE_HOME`` when that is set (``~`` expanded), on
    every system. Unset: Linux ``~/.cache/mcgyvr``, as before; macOS
    ``~/Library/Caches/mcgyvr``; Windows ``%LOCALAPPDATA%\\mcgyvr\\cache``.
    The weights do not follow ``$XDG_CACHE_HOME`` (``rigscan``'s clone).
    """
    cached = os.environ.get("XDG_CACHE_HOME")
    if cached:
        return Path(cached).expanduser() / APP
    if sys.platform == "win32":
        return _local_app_data() / APP / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP
    return Path.home() / ".cache" / APP


def _local_app_data() -> Path:
    """``%LOCALAPPDATA%`` when absolute, else ``~\\AppData\\Local``."""
    local = os.environ.get("LOCALAPPDATA")
    if local and os.path.isabs(local):
        return Path(local)
    return Path.home() / "AppData" / "Local"


def user_temp_root() -> Path:
    """The folder per-user temporary folders are made in.

    POSIX: the system's temporary folder, looked up on every call (shared by
    every user, so a folder made there is checked before it is used). Windows:
    ``%LOCALAPPDATA%\\mcgyvr\\tmp`` in the user's own profile, never ``%TEMP%``,
    which the environment can point at a folder other users may write
    (``C:\\Temp``), nor a cache folder an XDG variable may move.
    """
    if sys.platform == "win32":
        return _local_app_data() / APP / "tmp"
    return Path(tempfile.gettempdir())


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
