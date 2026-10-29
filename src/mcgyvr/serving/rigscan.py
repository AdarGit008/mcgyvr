#!/usr/bin/env python3
# Rig scan: reads what this machine is into one JSON document.
"""Read what this machine is into one JSON document.

The card (GPU) facts come from nvidia-smi, rocm-smi and the DRM entries of
sysfs; the CPU, memory, boot time and swappiness come from /proc, /sys and
lscpu; disk, model files, docker, ssh and interface addresses come from the
local host. A value that cannot be read is never filled in: it is named in
`unread` with the field it belongs to and a reason, and prose about a whole
missing section goes in `notes`.

`read_machine` returns the short document (machine identity, cards, memory),
`scan` adds GPU sizing, CPU, measured memory bandwidth, disk, models on disk,
docker, network and the token-only `snapshot` that a later visit is compared
against, and `main` prints either; every tool call and file read is bounded.
"""

import contextlib
import hashlib
import json
import os
import platform
import queue
import re
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import IO, Any

KB_PER_GB = 1024.0 * 1024.0
MIB_PER_GB = 1024.0
BYTES_PER_GB = 1024.0**3
MIB_BYTES = 1024 * 1024

# The bandwidth probe copies a block of memory COPY_PASSES times and keeps the
# fastest pass; the block drops to COPY_MIB_TIGHT when the memory spare is under
# TIGHT_RAM_GB past the two blocks the probe holds at once.
COPY_MIB = 256
COPY_PASSES = 5
COPY_MIB_TIGHT = 64
TIGHT_RAM_GB = 2.0

WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"
#: The variable that moves mcgyvr's home on this machine, and the folder it names
#: when nothing does: the same pair as `mcgyvr.fleet.roots.HOME_ENV` and
#: `HOME_DIR`, spelled again because this file runs on a rig without the package.
HOME_ENV = "MCGYVR_HOME"
HOME_DIR = "~/.mcgyvr"
#: Machine identity sources, in order: the first machine-id file holding a value,
#: then the host name.
MACHINE_ID_FILES = ("/etc/machine-id", "/var/lib/dbus/machine-id")
HOSTNAME_FILE = "/proc/sys/kernel/hostname"
DRM = "/sys/class/drm"

#: What one tool call may take: seconds before it is killed, and bytes of output kept.
BOUND_S = 20.0
BYTES_MAX = 262144
#: What text read from a file or a tool may take: one line's length, and how many
#: lines a whole card list may run to.
LINE_MAX = 4096
LINES_MAX = 4096
#: Longest printed name taken as a name.
NAME_MAX = 256
#: Longest run of digits taken as a size: is_size caps a size at 10**18.
DIGITS_MAX = 18

ROOT_VARIABLE = "MCGYVR_TEST_MACHINE_ROOT"
SECONDS_VARIABLE = "MCGYVR_TEST_TOOL_SECONDS"

#: Quantisation tag closing a GGUF file name, as in Q4_K_M.gguf or BF16.gguf.
GGUF_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)

#: The NVIDIA tool is asked for one line per card with a fixed field list, in that
#: order, comma separated, with no header and no units, so each line is split back
#: out by position. Its answer also settles whether this machine has an NVIDIA card
#: at all: a tool that runs and prints no row is reported as left over from a
#: machine whose card is gone, while a tool that is absent or fails leaves the card
#: list unread, with the tool's own reason kept.
FIRST_TOOL = "nvidia-smi"
FIRST_QUERY = "index,memory.total,memory.used,memory.free,name"
#: The snapshot asks again for the fields the short reading does not carry: the
#: slot, the compute capability, the driver and the reserved memory. Tools that do
#: not know memory.reserved are asked the shorter query instead.
SNAPSHOT_QUERY = "index,pci.bus_id,compute_cap,driver_version,memory.reserved"
SNAPSHOT_QUERY_OLD = "index,pci.bus_id,compute_cap,driver_version"
#: The AMD tool prints one JSON object keyed by card name, with the VRAM total and
#: used memory in bytes, which are divided down to MiB to match the NVIDIA rows.
#: The keys, not the arguments to the tool, decide which cards are reported, so a
#: machine with no AMD card simply yields no member.
SECOND_TOOL = "rocm-smi"
SECOND_ARGS = ("--showproductname", "--showmeminfo", "vram", "--json")
#: sysfs names a card's vendor by PCI id; the first map turns that id into the
#: vendor label used everywhere else, and the second says which tool reads it.
PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
VENDOR_TOOLS = {"nvidia": FIRST_TOOL, "amd": SECOND_TOOL}

#: A template that makes `docker version` print the daemon's version and nothing else.
DOCKER_VERSION_FORMAT = "{{.Server.Version}}"
#: ssh sets SSH_CONNECTION to "client_ip client_port server_ip server_port" in the
#: session's environment, so its third field is the address this machine was reached at.
SSH_CONNECTION_ENV = "SSH_CONNECTION"
#: Arguments that make `ip` list the IPv4 addresses, one interface per line.
IP_ADDR_ARGS = ("-4", "-o", "addr", "show")
#: The fallback where `ip` is absent or fails: `hostname -I` prints every address
#: on the host's interfaces, loopback and link-local left out, without their
#: interface names.
HOSTNAME_ADDR_ARGS = ("hostname", "-I")

#: Note text for a card list that could not be read: the first is used when the
#: NVIDIA tool never answered, so nothing at all is known about the cards; the
#: second when it answered but one row was unreadable and that card is left out.
GPU_NOT_DETERMINED = "GPU: not determined"
GPU_ROW_UNREAD = "GPU: nvidia-smi printed a row this could not read"

#: The snapshot is the part of the reading that a later visit is compared against:
#: flat text tokens, one per key, in the order below. Every value is folded to a
#: single token so a difference is a string difference and not a difference of
#: spacing; a value that could not be read is left out of the map and named in the
#: reading's unread list instead, so a key that is absent means "not read" and
#: never "zero".
#: The card keys describe the first NVIDIA card alone; the further cards are folded
#: into one token each, so a card arriving or leaving still shows as a change.
SNAPSHOT_KEYS = (
    "uptime_since",
    "cpu_max_mhz",
    "cpu_model",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "gpu_name",
    "gpu_vram_mib",
    "gpu_cc",
    "gpu_slot",
    "driver",
    "gpu_reserve_mib",
    "gpu_used_mib",
    "gpu_free_mib",
    "gpu_others",
    "docker",
    "kernel",
    "os_machine_id",
    "mem_available_kib",
    "mem_total_kib",
    "swap_total_kib",
    "swappiness",
    "nproc",
    "hostname",
)
#: The part of the snapshot that comes from the GPU state: when the card reading
#: fails, every one of these keys is reported unread with the same reason.
SNAPSHOT_CARD_KEYS = (
    "gpu_name",
    "gpu_vram_mib",
    "gpu_cc",
    "gpu_slot",
    "driver",
    "gpu_reserve_mib",
    "gpu_used_mib",
    "gpu_free_mib",
    "gpu_others",
)

_HEX16 = re.compile(r"[0-9a-f]{16}", re.ASCII)
_HOST = re.compile(r"[A-Za-z0-9._-]{1,253}", re.ASCII)
_DIGITS = re.compile(r"[0-9]+", re.ASCII)
_PCI_ID = re.compile(r"0x[0-9a-fA-F]{4}", re.ASCII)


def _fingerprint(seed: str) -> str:
    # Sixteen hex digits of sha256 over the seed: the same seed gives the same id
    # on every run of this code, and sixteen digits fit the id in one token while
    # leaving little room for two seeds to collide.
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def tok(value: str) -> str:
    """Fold every run of whitespace and of underscores to one underscore, and take
    underscores off both ends, so the value is a single token."""
    return re.sub(r"_+", "_", re.sub(r"\s+", "_", value)).strip("_")


def is_text(value: str) -> bool:
    """True when every character is printable: no control, format or private
    character, and no line or paragraph separator. A space is allowed."""
    return all(
        unicodedata.category(c)[0] != "C"
        and unicodedata.category(c) not in ("Zl", "Zp")
        for c in value
    )


def name_problem(value: object) -> str | None:
    """Say what keeps a printed value from being used as a name, or None when it is
    usable: it must be text, non-empty, no longer than NAME_MAX, not the tool's
    [N/A] placeholder, free of replacement characters, printable, and without
    space around it."""
    if not isinstance(value, str):
        return "the name is not text"
    if value == "":
        return "the name is empty"
    if len(value) > NAME_MAX:
        return f"the name printed is longer than {NAME_MAX} characters"
    if value in ("[N/A]", "N/A"):
        return "the name printed is [N/A]: its source gave no name"
    if "�" in value:
        return "the name printed holds a byte that is not text"
    if not is_text(value) or value != value.strip():
        return "the name printed holds characters a name does not"
    return None


def is_size(value: object) -> bool:
    """True for an int that is not negative and is below 10**DIGITS_MAX; a bool is
    not a size, and neither is a float."""
    return type(value) is int and 0 <= value < 10**DIGITS_MAX


def is_machine_id(value: object) -> bool:
    """True for the machine id this module makes: sixteen lowercase hex digits."""
    return isinstance(value, str) and _HEX16.fullmatch(value) is not None


# Calling a tool is the one place a scan can hang or flood, so it goes through
# _run: stdout is read under a time bound and a byte bound, the process group is
# killed rather than waited on, and every way the answer can be unusable comes
# back as a reason a note can carry to the reader.


def _group_kwargs() -> dict[str, Any]:
    """What Popen takes to start a tool heading a group of its own.

    A clone of ``mcgyvr.hostos.popen_group_kwargs`` (this file is shipped to a
    rig alone, so it cannot import it): a new session on POSIX, a new console
    process group on Windows.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_group(process: subprocess.Popen[Any]) -> None:
    """Kill a tool and all it started: a clone of ``mcgyvr.hostos.kill_group``.

    POSIX: SIGKILL to its process group. Windows: ``taskkill /F /T`` by its
    full path, then the tool itself.
    """
    if sys.platform == "win32":
        system = os.environ.get("SYSTEMROOT") or r"C:\Windows"
        taskkill = os.path.join(system, "System32", "taskkill.exe")
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [taskkill, "/F", "/T", "/PID", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10.0,
                check=False,
            )
        process.kill()
        return
    os.killpg(process.pid, signal.SIGKILL)


@contextlib.contextmanager
def _reader(stream: IO[bytes]) -> Iterator[Callable[[float], bytes | None]]:
    """A read of at most 65536 bytes from `stream` that waits `left` seconds.

    It answers None when nothing came in time and ``b""`` at the end. POSIX
    waits on a selector over the pipe; Windows, whose selectors take sockets
    only, has a thread read the pipe into a queue instead.
    """
    if sys.platform == "win32":
        got: queue.Queue[bytes] = queue.Queue()

        def pump() -> None:
            try:
                while True:
                    data = os.read(stream.fileno(), 65536)
                    got.put(data)
                    if not data:
                        return
            except (OSError, ValueError):
                got.put(b"")

        threading.Thread(target=pump, daemon=True).start()

        def taken(left: float) -> bytes | None:
            try:
                return got.get(timeout=left)
            except queue.Empty:
                return None

        yield taken
        return
    with selectors.DefaultSelector() as watch:
        watch.register(stream, selectors.EVENT_READ)

        def selected(left: float) -> bytes | None:
            if not watch.select(left):
                return None
            return os.read(stream.fileno(), 65536)

        yield selected


def _run(
    argv: Sequence[str], *, bound: float = BOUND_S
) -> tuple[str | None, str | None]:
    """Run argv and return (text, None), or (None, why) when it gave no usable text.

    The tool is looked up on PATH first, so a tool that is not installed gives
    (None, None): nothing was tried, and nothing failed. Stdout is read through a
    selector until the tool closes it, the bound runs out, or the output passes
    BYTES_MAX; stderr is discarded and the process is started heading a group of
    its own (a session on POSIX), so a kill takes any children with it. The text
    is decoded as utf-8 with replacement, since a tool may print bytes that are
    not text.
    """
    found = shutil.which(argv[0])
    if found is None:
        return None, None
    label = " ".join(argv[:2])
    try:
        process = subprocess.Popen(
            [found, *argv[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **_group_kwargs(),
        )
    except OSError as exc:
        return None, f"{label} could not start ({exc.strerror or exc})"
    assert process.stdout is not None
    deadline = time.monotonic() + bound
    chunks: list[bytes] = []
    size = 0
    why: str | None = None
    with _reader(process.stdout) as read:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                why = (
                    f"{label} did not answer within {bound:g} s"
                    if process.poll() is None
                    else f"{label} left its output open past {bound:g} s"
                )
                break
            data = read(left)
            if data is None:
                continue
            if not data:
                break
            chunks.append(data)
            size += len(data)
            if size > BYTES_MAX:
                why = f"{label} printed more than {BYTES_MAX} bytes"
                break
    if why is None:
        try:
            process.wait(timeout=max(deadline - time.monotonic(), 0.0))
        except subprocess.TimeoutExpired:
            why = f"{label} did not answer within {bound:g} s"
    if why is not None or process.poll() is None:
        with contextlib.suppress(OSError):
            _kill_group(process)
    process.stdout.close()
    process.wait()
    if why is not None:
        return None, why
    if process.returncode != 0:
        return None, f"{label} exited {process.returncode}"
    return b"".join(chunks).decode("utf-8", errors="replace"), None


def _at(root: str, path: str) -> str:
    """The path as it is read: root is prefixed to it, so a test tree can stand in
    for the real one, and with no root the absolute path is used as it is."""
    return root + path if root else path


def _read(root: str, path: str) -> tuple[str | None, str]:
    """Read a whole file and return (text, ""), or (None, why) when it is not there,
    cannot be opened, or holds more than BYTES_MAX bytes. The reason is a fragment
    made to follow the path in a note, as in "device/vendor is not there"."""
    where = _at(root, path)
    if not os.path.lexists(where):
        return None, "is not there"
    try:
        with open(where, "rb") as handle:
            raw = handle.read(BYTES_MAX + 1)
    except OSError:
        return None, "is not readable"
    if len(raw) > BYTES_MAX:
        return None, f"holds more than {BYTES_MAX} bytes"
    return raw.decode("utf-8", errors="replace"), ""


def _first_line(root: str, path: str) -> tuple[str | None, str]:
    """Read the first line of a file, stripped, and return (line, ""), or
    (None, why) when the file is unreadable or the line is longer than LINE_MAX.
    Only the first line is looked at, so a second line is not an error here."""
    text, why = _read(root, path)
    if text is None:
        return None, why
    line = text.split("\n", 1)[0]
    if len(line) > LINE_MAX:
        return None, f"holds a line longer than {LINE_MAX} characters"
    return line.strip(), ""


# One reading of the machine's cards, mutable so that the three sources can add to
# it: which cards were found, which were printed twice, which fields could not be
# read and why, and which sources and vendors answered.


class _Reading:
    """The cards found so far, keyed by vendor and index, and everything that could
    not be read about them.

    `unread` holds {field, why} pairs with the field path a caller can match on
    ("card.nvidia.0.total"). `cards` holds one entry per card, and a vendor and
    index printed twice is dropped from it into `twice`, since the source then
    contradicts itself. `sources` names the tools and files that answered,
    `covered` the vendors whose own tool answered, `printed` counts the rows each
    tool printed, and `unsized` lists cards whose total memory nothing could read.
    """

    def __init__(self) -> None:
        self.cards: dict[tuple[str, int], dict[str, Any]] = {}
        self.twice: set[tuple[str, int]] = set()
        self.unread: list[dict[str, str]] = []
        self.unsized: list[str] = []
        self.sources: list[str] = []
        self.covered: set[str] = set()
        self.printed: dict[str, int] = {}
        #: Set once the NVIDIA tool runs and answers at all, whatever it printed;
        #: _gpus uses it to tell "no NVIDIA card here" from "no answer to read".
        self.first_answered = False

    def note(self, field: str, why: str) -> None:
        self.unread.append({"field": field, "why": why})

    def named(self, field: str) -> bool:
        return any(item["field"] == field for item in self.unread)

    def add(self, vendor: str, index: int, card: dict[str, Any]) -> None:
        self.printed[vendor] = self.printed.get(vendor, 0) + 1
        where = (vendor, index)
        if where in self.cards or where in self.twice:
            if where not in self.twice:
                self.note(
                    f"card.{vendor}.{index}",
                    f"the card source printed index {index} twice; neither line "
                    "is taken",
                )
            self.cards.pop(where, None)
            self.twice.add(where)
            return
        self.cards[where] = {"vendor": vendor, "index": index, **card}

    def number(
        self, value: str, field: str, source: str, *, bytes_: bool = False
    ) -> int | None:
        """Read a printed size, in MiB when bytes_ is set, noting field and source and
        returning None for each way it can fail: no value, [N/A], something that is
        not all digits, or more digits than a size can have."""
        value = value.strip()
        if value == "":
            self.note(field, f"{source} printed no value for it")
        elif value in ("[N/A]", "N/A"):
            self.note(field, f"{source} printed [N/A] for it")
        elif not _DIGITS.fullmatch(value):
            self.note(
                field, f"{source} printed a value for it that is not a whole number"
            )
        elif len(value) > DIGITS_MAX:
            self.note(field, f"{source} printed a number for it too large to be a size")
        else:
            return int(value) // MIB_BYTES if bytes_ else int(value)
        return None

    def name(self, value: str, field: str, source: str) -> str | None:
        """The printed name, trimmed and folded to NFC, or None when it is empty or
        fails name_problem; either way the field is noted with the reason."""
        value = unicodedata.normalize("NFC", value.strip())
        if value == "":
            self.note(field, f"{source} printed no name for it")
            return None
        problem = name_problem(value)
        if problem is not None:
            self.note(field, f"{source}: {problem}")
            return None
        return value

    def free(
        self, total: int | None, used: int | None, field: str, source: str
    ) -> int | None:
        if total is None or used is None:
            self.note(
                field,
                "free memory is the total less the used, and one of them is unread",
            )
            return None
        if used > total:
            self.note(field, f"{source} printed more memory used than the card's total")
            return None
        return total - used

    def no_card(self, field: str, tool: str) -> None:
        if not self.named(field):
            self.note(
                field,
                f"{tool} is installed and printed no card. If this machine has no "
                "card of its vendor, the tool is left over and can be removed",
            )


def _lines(text: str, reading: _Reading, field: str, what: str) -> list[str] | None:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > LINES_MAX:
        reading.note(
            field, f"{what} printed more than {LINES_MAX} lines; its cards are unread"
        )
        return None
    return lines


def _first_tool(reading: _Reading, bound: float) -> list[dict[str, Any]]:
    """Read the NVIDIA rows into the reading and return its NVIDIA cards.

    A line is index,total,used,free,name in that order. A line that is not a card
    line is noted and skipped; when it comes right after a card, that card's name
    is dropped, as the name has probably run over a line break. A tool that answers
    with nothing is noted as probably left over from a machine whose card is gone,
    and a tool that could not be run leaves the cards unread.
    """
    text, why = _run(
        (FIRST_TOOL, f"--query-gpu={FIRST_QUERY}", "--format=csv,noheader,nounits"),
        bound=bound,
    )
    if text is None:
        if why is not None:
            reading.note(
                f"cards.{FIRST_TOOL}",
                f"{why}; its cards are unread. Run {FIRST_TOOL} by hand to see why, "
                "or remove it if this machine has no card of its vendor",
            )
        return []
    reading.first_answered = True
    lines = _lines(text, reading, f"cards.{FIRST_TOOL}", FIRST_TOOL)
    if lines is None:
        return []
    start = len(reading.cards)
    last: tuple[str, int] | None = None
    for line in lines:
        if len(line) > LINE_MAX:
            reading.note(
                f"cards.{FIRST_TOOL}",
                f"{FIRST_TOOL} printed a line longer than {LINE_MAX} characters",
            )
            continue
        if not line.strip():
            continue
        fields = line.split(",", 4)
        fields += [""] * (5 - len(fields))
        index = fields[0].strip()
        if not _DIGITS.fullmatch(index):
            if last is not None and last in reading.cards:
                # The name is the last field on a row, so a line break inside it
                # shows up here: this card keeps its numbers and loses its name,
                # rather than being read as a card whose index is not a number.
                reading.cards[last]["name"] = None
                reading.note(
                    f"card.nvidia.{last[1]}.name",
                    f"{FIRST_TOOL} printed a line after this card that is not a card "
                    "line; its name may run over a line break",
                )
            else:
                reading.note(
                    f"cards.{FIRST_TOOL}",
                    f"{FIRST_TOOL} printed a line that is not a card line",
                )
            continue
        if len(index) > 9:
            reading.note(
                f"cards.{FIRST_TOOL}",
                f"{FIRST_TOOL} printed a card index too large to be one",
            )
            continue
        number = int(index)
        key = f"card.nvidia.{number}"
        reading.add(
            "nvidia",
            number,
            {
                "total_mib": reading.number(fields[1], f"{key}.total", FIRST_TOOL),
                "used_mib": reading.number(fields[2], f"{key}.used", FIRST_TOOL),
                "free_mib": reading.number(fields[3], f"{key}.free", FIRST_TOOL),
                "name": reading.name(fields[4], f"{key}.name", FIRST_TOOL),
            },
        )
        last = ("nvidia", number)
    rows = [card for (vendor, _), card in reading.cards.items() if vendor == "nvidia"]
    if len(reading.cards) > start or rows:
        reading.sources.append(FIRST_TOOL)
        reading.covered.add("nvidia")
    else:
        reading.no_card(f"cards.{FIRST_TOOL}", FIRST_TOOL)
    return rows


def _text_of(value: object) -> str:
    """A JSON member as the text a number field can be read from: a float through
    repr, so its decimal part survives, other numbers and strings as they are, and
    anything else as the empty string, which reads as no value."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return ""
    return repr(value) if isinstance(value, float) else str(value)


def _second_tool(reading: _Reading, bound: float) -> None:
    """Read the AMD cards from the JSON the tool prints into the reading.

    Members named card<N> are the cards; inside one, keys are matched without
    regard to case, the VRAM total and used memory arrive in bytes and are divided
    to MiB, and the name is card series with card model as the fallback. Output that
    is not a JSON object, or a card count past LINES_MAX, leaves the cards unread
    with the reason.
    """
    text, why = _run((SECOND_TOOL, *SECOND_ARGS), bound=bound)
    if text is None:
        if why is not None:
            reading.note(
                f"cards.{SECOND_TOOL}",
                f"{why}; its cards are unread. Run {SECOND_TOOL} by hand to see why, "
                "or remove it if this machine has no card of its vendor",
            )
        return
    try:
        data = json.loads(text)
    except ValueError:
        reading.note(f"cards.{SECOND_TOOL}", f"{SECOND_TOOL}: its output is not JSON")
        return
    if not isinstance(data, dict):
        reading.note(
            f"cards.{SECOND_TOOL}", f"{SECOND_TOOL}: its output is not a JSON object"
        )
        return
    rows: list[tuple[int, str, str, str]] = []
    for member, entry in data.items():
        match = re.fullmatch(r"card([0-9]{1,9})", str(member))
        if match is None:
            continue
        if not isinstance(entry, dict):
            reading.note(
                f"cards.{SECOND_TOOL}",
                f"{SECOND_TOOL}: its entry for a card is not a JSON object",
            )
            continue
        low = {str(k).lower(): v for k, v in entry.items()}
        rows.append(
            (
                int(match.group(1)),
                _text_of(low.get("vram total memory (b)", "")),
                _text_of(low.get("vram total used memory (b)", "")),
                _text_of(low.get("card series", low.get("card model", ""))),
            )
        )
    if len(rows) > LINES_MAX:
        reading.note(
            f"cards.{SECOND_TOOL}", f"{SECOND_TOOL} printed more than {LINES_MAX} cards"
        )
        return
    start = len(reading.cards)
    for index, total_text, used_text, name_text in sorted(rows):
        key = f"card.amd.{index}"
        total = reading.number(total_text, f"{key}.total", SECOND_TOOL, bytes_=True)
        used = reading.number(used_text, f"{key}.used", SECOND_TOOL, bytes_=True)
        reading.add(
            "amd",
            index,
            {
                "total_mib": total,
                "used_mib": used,
                "free_mib": reading.free(total, used, f"{key}.free", SECOND_TOOL),
                "name": reading.name(name_text, f"{key}.name", SECOND_TOOL),
            },
        )
    if len(reading.cards) > start:
        reading.sources.append(SECOND_TOOL)
        reading.covered.add("amd")
    else:
        reading.no_card(f"cards.{SECOND_TOOL}", SECOND_TOOL)


def _sysfs(reading: _Reading, root: str) -> None:
    """Add the cards the tools did not report, from the DRM entries in sysfs.

    Each cardN with a device directory is a card, its vendor is the PCI vendor id
    (a card with no product_name is named PCI vid:did), and its memory comes from
    mem_info_vram_total and mem_info_vram_used, in bytes. A card of a vendor whose
    own tool already answered is counted but not added, so the count per vendor can
    still say that a tool's list is short.
    """
    drm = _at(root, DRM)
    try:
        entries = os.listdir(drm)
    except OSError:
        entries = []
    numbered = sorted(
        int(name[4:])
        for name in entries
        if re.fullmatch(r"card[0-9]{1,9}", name)
        and os.path.isdir(os.path.join(drm, name))
    )
    seen: dict[str, int] = {}
    start = len(reading.cards)
    for number in numbered:
        device = f"{DRM}/card{number}/device"
        vid, why = _first_line(root, f"{device}/vendor")
        if vid is not None and _PCI_ID.fullmatch(vid):
            vid = vid.lower()
            vendor = PCI_VENDORS.get(vid, f"pci-{vid}")
        else:
            why = why or "holds no PCI vendor id"
            vendor = "unknown"
            vid = None
            reading.note(
                f"card.unknown.{number}.vendor",
                f"sysfs gives no PCI vendor id for card{number} (device/vendor {why}); "
                "it may be a display that is not a PCI card",
            )
        seen[vendor] = seen.get(vendor, 0) + 1
        # A vendor whose tool already answered keeps the tool's rows: sysfs would
        # otherwise add a second entry for the same card under another index.
        if vendor in reading.covered:
            continue
        key = f"card.{vendor}.{number}"
        did, _ = _first_line(root, f"{device}/device")
        did = did.lower() if did is not None and _PCI_ID.fullmatch(did) else None
        product, why = _first_line(root, f"{device}/product_name")
        named_unread = False
        if product is None and why not in ("is not there", "is not readable"):
            reading.note(f"{key}.name", f"sysfs: device/product_name {why}")
            named_unread = True
        if product is None and vid is not None and did is not None:
            product = f"PCI {vid}:{did}"
        name = None
        if not named_unread:
            name = reading.name(product or "", f"{key}.name", "sysfs")
        tool = VENDOR_TOOLS.get(vendor)
        total_text, why = _first_line(root, f"{device}/mem_info_vram_total")
        total: int | None = None
        if total_text is not None:
            total = reading.number(total_text, f"{key}.total", "sysfs", bytes_=True)
        elif why != "is not there":
            reading.note(f"{key}.total", f"sysfs: device/mem_info_vram_total {why}")
        elif tool is not None and shutil.which(tool) is not None:
            reading.note(
                f"{key}.total",
                "sysfs publishes no memory size for this card "
                "(device/mem_info_vram_total is not there), and "
                f"{tool}, installed here, did not read it",
            )
        else:
            reading.note(
                f"{key}.total",
                "sysfs publishes no memory size for this card "
                "(device/mem_info_vram_total is not there), and no card tool "
                "installed here reads its vendor",
            )
            reading.unsized.append(key)
        used_text, why = _first_line(root, f"{device}/mem_info_vram_used")
        used: int | None = None
        if used_text is not None:
            used = reading.number(used_text, f"{key}.used", "sysfs", bytes_=True)
        else:
            reading.note(
                f"{key}.used",
                "sysfs gives no used memory for this card: "
                f"device/mem_info_vram_used {why}",
            )
        reading.add(
            vendor,
            number,
            {
                "total_mib": total,
                "used_mib": used,
                "free_mib": reading.free(total, used, f"{key}.free", "sysfs"),
                "name": name,
            },
        )
    if len(reading.cards) > start:
        reading.sources.append("sysfs")
    # sysfs counts every card of a vendor, including the ones the tool printed, so
    # a tool that printed fewer rows than sysfs shows can be said to be short.
    for vendor, count in sorted(seen.items()):
        if vendor in reading.covered and count > reading.printed.get(vendor, 0):
            tool = VENDOR_TOOLS[vendor]
            reading.note(
                f"cards.{tool}",
                f"sysfs shows {count} cards of vendor {vendor} and {tool} printed "
                f"{reading.printed.get(vendor, 0)}; its list of cards may be short",
            )


def _host(root: str, reading: _Reading) -> str:
    """The host name from sysfs, or the node name when there is no test root and the
    file gave nothing; a name that is missing or ill-formed is noted and read as the
    empty string."""
    got, _ = _first_line(root, HOSTNAME_FILE)
    if not got and not root:
        got = platform.node()
    if not got:
        reading.note(
            "host", f"the host name is unread ({HOSTNAME_FILE}, the node name)"
        )
        return ""
    if len(got) > 253:
        reading.note("host", "the host name is longer than a host name may be")
        return ""
    if not _HOST.fullmatch(got):
        reading.note("host", "the host name holds characters a host name does not")
        return ""
    return got


def _machine(root: str, reading: _Reading) -> tuple[dict[str, Any], list[str]]:
    """The machine's identity: host name, kernel release, and an id hashed from the
    first machine-id file that holds a value, or from the host name when none does.

    `id_from` names the seed that was used. A file holding what a machine id cannot
    be (a control character, a second line, more than a line) is not hashed, and the
    host name is not used in its place, since the machine evidently has an id that
    could not be read; that case and the host-name case are both noted.
    """
    host = _host(root, reading)
    notes: list[str] = []
    machine: dict[str, Any] = {
        "id": "",
        "id_from": None,
        "host": host,
        "kernel": platform.release(),
    }
    for path in MACHINE_ID_FILES:
        text, why = _read(root, path)
        if text is None:
            if why in ("is not there", "is not readable"):
                continue
            reading.note(
                "machine_id",
                f"{path} {why}; the id is taken neither from it nor from the host name",
            )
            return machine, notes
        seed = text.strip()
        if len(seed) > LINE_MAX or not is_text(seed):
            reading.note(
                "machine_id",
                f"{path} holds what a machine id does not (a control character, a "
                "second line, or more than a line); the id is taken neither from it "
                "nor from the host name",
            )
            return machine, notes
        if seed:
            machine["id"], machine["id_from"] = _fingerprint(seed), path
            return machine, notes
    if not host:
        reading.note(
            "machine_id",
            f"no machine-id file ({', '.join(MACHINE_ID_FILES)}) and no host name to "
            "derive it from",
        )
        return machine, notes
    # No machine-id file held a value, so the host name is the seed; the note
    # appended below says that the id then holds only until the machine is renamed.
    machine["id"], machine["id_from"] = _fingerprint(f"host:{host}"), "hostname"
    notes.append(
        "Machine id: derived from the hostname — no /etc/machine-id. It is "
        "stable until the host is renamed, and a rename will read as a new "
        "machine rather than as a changed one."
    )
    return machine, notes


def machine_id(*, root: str = "") -> str:
    """The machine id alone, for callers that need nothing else; the empty string
    when it could not be read."""
    machine, _ = _machine(root, _Reading())
    return str(machine["id"])


def _meminfo_field(text: str, key: str) -> int | None:
    for line in text.splitlines():
        name, sep, rest = line.partition(":")
        if sep and name.strip() == key:
            head = rest.split()
            if head and _DIGITS.fullmatch(head[0]):
                return int(head[0])
    return None


def _memory(
    root: str, bound: float
) -> tuple[dict[str, Any] | None, list[dict[str, str]], list[str]]:
    """Total and available memory in GB, with the facts behind them and the notes
    about anything missing.

    A figure that was not read is never passed off as whole: without MemTotal the
    memory is None with a note, and available memory is None when nothing reported
    it. On macOS, where there is no meminfo and no test root, sysctl gives the total
    and the note says available memory was not read. The middle value is the
    {field, how} facts and the last one the note prose.
    """
    text, _ = _read(root, "/proc/meminfo")
    if text is None:
        if platform.system() == "Darwin" and not root:
            out, _ = _run(("sysctl", "-n", "hw.memsize"), bound=bound)
            if out is not None and out.strip().isdigit():
                gb = round(int(out.strip()) / BYTES_PER_GB, 1)
                return (
                    {"total_gb": gb, "available_gb": None},
                    [{"field": "memory.total_gb", "how": "sysctl -n hw.memsize"}],
                    [
                        "Memory: available memory not read — sysctl gives the "
                        "total only."
                    ],
                )
        return None, [], ["Memory: not determined — /proc/meminfo is unreadable."]
    total = _meminfo_field(text, "MemTotal")
    available = _meminfo_field(text, "MemAvailable")
    how = "/proc/meminfo MemAvailable"
    if total is None:
        return None, [], ["Memory: /proc/meminfo carried no MemTotal."]
    if available is None:
        # Kernels that print no MemAvailable have only MemFree, which is what is
        # left before caches give anything back; the fact's "how" records the swap.
        available = _meminfo_field(text, "MemFree")
        how = "/proc/meminfo MemFree (no MemAvailable)"
    if available is None:
        return (
            None,
            [],
            ["Memory: MemTotal was readable but nothing reported free memory."],
        )
    return (
        {
            "total_gb": round(total / KB_PER_GB, 1),
            "available_gb": round(available / KB_PER_GB, 1),
        },
        [
            {"field": "memory.total_gb", "how": "/proc/meminfo MemTotal"},
            {"field": "memory.available_gb", "how": how},
        ],
        [],
    )


class _Short:
    """One short reading of the machine, kept as the document it is handed out as.

    The card list is merged from all three sources, and then any card field that
    came back empty without a reason of its own is given one, so the list never
    shows a blank it cannot explain. `unsized` holds the cards still missing a
    memory size after the merge, and `notes` the prose from identity and memory.
    """

    def __init__(self, root: str, bound: float) -> None:
        reading = _Reading()
        machine, self.notes = _machine(root, reading)
        self.rows = _first_tool(reading, bound)
        self.first_answered = reading.first_answered
        _second_tool(reading, bound)
        _sysfs(reading, root)
        memory, self.memory_facts, memory_notes = _memory(root, bound)
        self.notes += memory_notes
        cards = [reading.cards[where] for where in sorted(reading.cards)]
        # A field that no source filled and no source explained is still named, so
        # a card list reads as incomplete field by field and not only as a list
        # that happens to be shorter.
        for card in cards:
            key = f"card.{card['vendor']}.{card['index']}"
            for field, name in (
                ("name", "name"),
                ("total_mib", "total"),
                ("used_mib", "used"),
                ("free_mib", "free"),
            ):
                if card[field] is None and not reading.named(f"{key}.{name}"):
                    reading.note(
                        f"{key}.{name}", "the source printed no value and no reason"
                    )
        held = {f"card.{c['vendor']}.{c['index']}": c for c in cards}
        unsized = [
            key
            for key in reading.unsized
            if key in held and held[key]["total_mib"] is None
        ]
        self.document: dict[str, Any] = {
            "machine": machine,
            "cards": cards,
            "card_sources": reading.sources,
            "unsized": unsized,
            "memory": memory,
            "unread": reading.unread,
        }


def read_machine(*, root: str = "", bound: float = BOUND_S) -> dict[str, Any]:
    """The short reading of this machine: its identity, its cards with the sources
    that answered and the fields that could not be read, and its memory. No CPU,
    disk, docker or snapshot work is done here."""
    return _Short(root, bound).document


# The gpus section of a scan is built from the NVIDIA rows alone; the cards of
# other vendors stay in the card list, unsized for a fit. A row that could not be
# read is named in a note with its reasons instead of vanishing, and a machine whose
# NVIDIA tool never answered is reported as not determined, never as zero.


def _gpus(
    rows: list[dict[str, Any]], answered: bool, unread: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    """The gpus section, the facts behind it, and the notes about the rows left out.

    Reserved memory is the total less the used and the free, floored at zero. A card
    with any of its fields unread is left out of the section, with the reasons from
    the reading's unread list, since MIG and vGPU rows print memory as [N/A] and
    land there. The section comes back empty, with a note, when the NVIDIA tool never
    answered or answered with no device.
    """
    how = f"{FIRST_TOOL} --query-gpu={FIRST_QUERY}"
    if not answered:
        return (
            [],
            [],
            [
                f"{GPU_NOT_DETERMINED} — {FIRST_TOOL} is absent or failed. This is a "
                "machine without an NVIDIA card as far as its tool can tell; the "
                "cards of other vendors are in the reading's card list, and are not "
                "sized for a fit here, so bind VRAM by hand on those rather than "
                "reading this as zero."
            ],
        )
    gpus: list[dict[str, Any]] = []
    facts: list[dict[str, str]] = []
    notes: list[str] = []
    for card in sorted(rows, key=lambda c: c["index"]):
        values = [card[k] for k in ("name", "total_mib", "used_mib", "free_mib")]
        if any(v is None for v in values):
            key = f"card.nvidia.{card['index']}"
            why = "; ".join(
                f"{u['field']}: {u['why']}"
                for u in unread
                if u["field"].startswith(key)
            )
            named = f" ({card['name']})" if card["name"] else ""
            notes.append(
                f"{GPU_ROW_UNREAD}, so card {card['index']}{named} is missing from "
                "the scan "
                f"({why}). MIG and vGPU rows report memory as [N/A] and land here. "
                "Read the card list as incomplete rather than short: the indexes "
                "below place a unit, and a change in their number reads as "
                "hardware that was pulled."
            )
            continue
        name, total, used, free = values
        index = card["index"]
        gpus.append(
            {
                "index": index,
                "name": name,
                "vram": {
                    "total_mib": total,
                    "used_mib": used,
                    "free_mib": free,
                    "reserved_mib": max(total - used - free, 0),
                },
            }
        )
        facts.append({"field": f"gpu[{index}].vram.total_mib", "how": how})
        facts.append({"field": f"gpu[{index}].vram.free_mib", "how": how})
        facts.append(
            {
                "field": f"gpu[{index}].vram.reserved_mib",
                "how": f"{how} (total-used-free)",
            }
        )
    if not gpus and not notes:
        notes.append(f"GPU: {FIRST_TOOL} answered but reported no device.")
    return gpus, facts, notes


def _cpu(bound: float) -> tuple[dict[str, int] | None, list[dict[str, str]], list[str]]:
    """Core and thread counts from lscpu, the cores as Core(s) per socket times the
    socket count, and os.cpu_count() for both counts when lscpu gives no core count,
    with a note saying that this count is of threads and not of cores."""
    text, _ = _run(("lscpu",), bound=bound)
    if text is not None:
        threads = _lscpu_int(text, "CPU(s)")
        per_socket = _lscpu_int(text, "Core(s) per socket")
        sockets = _lscpu_int(text, "Socket(s)") or 1
        if threads is not None and per_socket is not None:
            return (
                {"cores": per_socket * sockets, "threads": threads},
                [
                    {"field": "cpu.threads", "how": "lscpu CPU(s)"},
                    {
                        "field": "cpu.cores",
                        "how": "lscpu Core(s) per socket x Socket(s)",
                    },
                ],
                [],
            )
    count = os.cpu_count()
    if count is None:
        return (
            None,
            [],
            ["CPU: not determined — lscpu and os.cpu_count() gave nothing."],
        )
    return (
        {"cores": count, "threads": count},
        [{"field": "cpu.threads", "how": "os.cpu_count()"}],
        [
            "CPU: lscpu gave no core count, and os.cpu_count() reports the thread "
            "count; cores are taken as the same number (no SMT claim either way)."
        ],
    )


def _lscpu_field(text: str, key: str) -> str | None:
    """The value lscpu printed for a key, without the colon or the space around it;
    None when the output carries no such key."""
    for line in text.splitlines():
        name, sep, rest = line.partition(":")
        if sep and name.strip() == key:
            return rest.strip()
    return None


def _lscpu_int(text: str, key: str) -> int | None:
    value = (_lscpu_field(text, key) or "").split()
    return int(value[0]) if value and _DIGITS.fullmatch(value[0]) else None


def _spare_gb(root: str) -> float:
    """The memory a new allocation could take, in GB, from MemAvailable or MemFree;
    0.0 when meminfo cannot be read, so a machine whose memory cannot be seen is
    measured by the bandwidth probe as a small one."""
    text, _ = _read(root, "/proc/meminfo")
    if text is None:
        return 0.0
    available = _meminfo_field(text, "MemAvailable")
    if available is None:
        available = _meminfo_field(text, "MemFree")
    return 0.0 if available is None else available / KB_PER_GB


def measure_bandwidth(root: str = "") -> dict[str, Any] | None:
    """Copy one block of memory onto another and keep the fastest pass.

    Two buffers are allocated and one is copied onto the other COPY_PASSES times;
    the result is the highest bytes-copied-per-second of those passes, so one slow
    pass does not drag it down. The block is COPY_MIB, or COPY_MIB_TIGHT when the
    machine has less than TIGHT_RAM_GB spare beyond the two buffers. None when the
    buffers cannot be allocated or no pass could be timed, which the caller reports
    as not measured rather than filling in.
    """
    mib = COPY_MIB
    if _spare_gb(root) < TIGHT_RAM_GB + 2 * mib / MIB_PER_GB:
        mib = COPY_MIB_TIGHT
    try:
        source = bytearray(mib * MIB_BYTES)
        target = bytearray(mib * MIB_BYTES)
    except (MemoryError, ValueError):
        return None
    target[:] = source  # every page of the target is touched before any is timed
    moved = float(len(source))
    fastest = 0.0
    for _ in range(COPY_PASSES):
        start = time.perf_counter()
        target[:] = source
        elapsed = time.perf_counter() - start
        if elapsed > 0.0:
            fastest = max(fastest, moved / elapsed)
    if fastest <= 0.0:
        return None
    return {
        "measured_gbps": round(fastest / 1e9, 1),
        "how": (
            f"in-process copy of {mib} MiB x{COPY_PASSES}, best pass, bytes copied/s"
        ),
    }


def default_weights_dir() -> str:
    """Where weights live when the caller names no directory: MCGYVR_WEIGHTS with ~
    expanded, or ``weights`` in the system's cache folder: ~/.cache/mcgyvr/weights
    on Linux (whatever XDG_CACHE_HOME says, as always), ~/Library/Caches/mcgyvr/weights
    on macOS, %LOCALAPPDATA%\\mcgyvr\\cache\\weights on Windows. A clone of
    ``mcgyvr.hostos.user_dirs`` with no XDG variable, since this file is shipped
    alone."""
    override = os.environ.get(WEIGHTS_DIR_ENV)
    if override:
        return os.path.expanduser(override)
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/mcgyvr/weights")
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if not (local and os.path.isabs(local)):
            local = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(local, "mcgyvr", "cache", "weights")
    return os.path.expanduser("~/.cache/mcgyvr/weights")


def mcgyvr_home() -> str | None:
    """mcgyvr's home on this machine: MCGYVR_HOME with ~ expanded, else ~/.mcgyvr.

    None when MCGYVR_HOME names a relative folder, which would be a different
    folder from each working directory; the scan then reports no home rather
    than guess one.
    """
    named = os.environ.get(HOME_ENV)
    if named:
        expanded = os.path.expanduser(named)
        return expanded if os.path.isabs(expanded) else None
    return os.path.expanduser(HOME_DIR)


def _disk_device(path: str) -> str | None:
    """The device the path is on, from /proc/self/mounts: the source of the longest
    mount point the resolved path falls under, with escaped spaces in the mount point
    decoded. None when mounts cannot be read or no mount point contains the path."""
    try:
        with open("/proc/self/mounts", encoding="utf-8") as handle:
            mounts = handle.read()
    except OSError:
        return None
    resolved = os.path.realpath(path)
    best, best_len = None, -1
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        source, mount = parts[0], parts[1].replace("\\040", " ")
        inside = resolved == mount or resolved.startswith(mount.rstrip("/") + "/")
        if inside and len(mount) > best_len:
            best, best_len = source, len(mount)
    return best


def _disk(path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Free and total space in GB on the weights path, and the device behind it.

    The counts are asked of the path and then of its parents, since the weights
    directory may not exist yet; when nothing on the way up can be read both stay
    zero, so a free_gb of 0.0 is as much a failed reading as a full disk.
    """
    free, total = 0, 0
    probe = path
    while True:
        try:
            usage = shutil.disk_usage(probe)
            free, total = usage.free, usage.total
            break
        except OSError:
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
    disk: dict[str, Any] = {"path": path, "free_gb": round(free / BYTES_PER_GB, 1)}
    facts = [{"field": "disk.free_gb", "how": f"free space on {path}"}]
    if total:
        disk["total_gb"] = round(total / BYTES_PER_GB, 1)
        facts.append({"field": "disk.total_gb", "how": f"total space on {path}"})
    device = _disk_device(path)
    if device is not None:
        disk["device"] = device
        facts.append(
            {"field": "disk.device", "how": f"/proc/self/mounts source for {path}"}
        )
    return disk, facts


def _model_name_and_quant(name: str) -> tuple[str, str | None]:
    match = GGUF_QUANT.search(name)
    if match is None:
        return name[: -len(".gguf")], None
    return name[: match.start()], match.group(1).upper()


def _models_on_disk(
    roots: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """The model files under each root, once each, with the size the filesystem
    reports.

    A .gguf file is split into a model name and a quantisation tag, a .safetensors
    file keeps its base name and no tag. Hidden files and hidden directories are
    skipped, symlinked directories are not followed, and a file whose size cannot be
    read is left out.
    """
    found: list[dict[str, Any]] = []
    facts: list[dict[str, str]] = []
    seen: set[str] = set()
    for top in dict.fromkeys(os.path.expanduser(r) for r in roots):
        if not os.path.isdir(top):
            continue
        for folder, dirs, files in os.walk(top, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                lower = name.lower()
                path = os.path.join(folder, name)
                if name.startswith(".") or path in seen:
                    continue
                if lower.endswith(".gguf"):
                    model, quant = _model_name_and_quant(name)
                elif lower.endswith(".safetensors"):
                    model, quant = os.path.splitext(name)[0], None
                else:
                    continue
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                seen.add(path)
                found.append(
                    {"name": model, "quant": quant, "size_bytes": size, "path": path}
                )
                facts.append({"field": f"models_on_disk[{path}]", "how": "filesystem"})
    return found, facts


def _docker(bound: float) -> tuple[str | None, str | None]:
    """The version the docker daemon answered with, or None and the reason there is
    no version: no CLI here, the call failed, or the daemon gave nothing."""
    text, why = _run(
        ("docker", "version", "--format", DOCKER_VERSION_FORMAT), bound=bound
    )
    version = (text or "").strip()
    if version:
        return version, None
    if text is None and why is None:
        return None, "no docker CLI here"
    return None, why or "its daemon answered no version"


def _parse_ip_addr(output: str) -> list[dict[str, str]]:
    """The interface names and IPv4 addresses in `ip -o -4 addr show` output, with
    the prefix length and any @peer suffix taken off. A line without an inet word, or
    with nothing after it, is skipped."""
    found: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split()
        if "inet" not in parts[:3] or len(parts) < 4:
            continue
        at = parts.index("inet")
        if at + 1 >= len(parts):
            continue
        found.append(
            {
                "interface": parts[at - 1].split("@")[0],
                "address": parts[at + 1].split("/")[0],
            }
        )
    return found


def _parse_hostname_addresses(output: str) -> list[dict[str, str]]:
    """The IPv4 addresses in `hostname -I` output, each with no interface name, since
    `hostname` prints none. A word that is not an IPv4 address (an IPv6 one) is
    skipped."""
    found: list[dict[str, str]] = []
    for word in output.split():
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", word):
            found.append({"interface": "", "address": word})
    return found


def _network(bound: float) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    """The address this machine was reached at and the IPv4 addresses on its
    interfaces.

    Only an ssh session carries the address it was reached at, in SSH_CONNECTION,
    and only a four-field setting is believed. The addresses come from `ip`, or,
    where `ip` is absent or fails, from `hostname -I` without interface names. Each
    of the two is noted when it could not be read, and the note says which.
    """
    said = os.environ.get(SSH_CONNECTION_ENV, "").split()
    reached = said[2] if len(said) == 4 else None
    text, _ = _run(("ip", *IP_ADDR_ARGS), bound=bound)
    facts: list[dict[str, str]] = []
    notes: list[str] = []
    if reached is None:
        notes.append(
            "Network: not reached over ssh (no SSH_CONNECTION), so the address "
            "it was reached at is not known."
        )
    else:
        facts.append(
            {"field": "network.reached_at", "how": "local address in SSH_CONNECTION"}
        )
    if text is not None:
        facts.append({"field": "network.ipv4", "how": "ip " + " ".join(IP_ADDR_ARGS)})
        return {"reached_at": reached, "ipv4": _parse_ip_addr(text)}, facts, notes
    fallback, _ = _run(HOSTNAME_ADDR_ARGS, bound=bound)
    if fallback is None:
        notes.append(
            "Network: `ip "
            + " ".join(IP_ADDR_ARGS)
            + "` and `"
            + " ".join(HOSTNAME_ADDR_ARGS)
            + "` are absent or failed, so the "
            "addresses on its interfaces are not read."
        )
        return {"reached_at": reached, "ipv4": []}, facts, notes
    facts.append({"field": "network.ipv4", "how": " ".join(HOSTNAME_ADDR_ARGS)})
    return (
        {"reached_at": reached, "ipv4": _parse_hostname_addresses(fallback)},
        facts,
        notes,
    )


# The snapshot is a map of key to one token per fact. Every key goes through put(),
# so one rule holds for all of them: a token that folded away to nothing is not a
# value, and the key is reported unread with the reason it was read as empty.


class _Snapshot:
    """The snapshot map under construction, and the keys that could not be filled.

    `values` holds one token per key. An empty token is kept only for gpu_others,
    where it means that there is no further card, not that one went unread.
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.unread: list[dict[str, str]] = []

    def put(self, key: str, value: str | None, why: str) -> None:
        value = tok(value) if value is not None else ""
        if value or (value == "" and key == "gpu_others" and why == ""):
            self.values[key] = value
        else:
            self.unread.append(
                {"field": f"snapshot.{key}", "why": why or "read as empty"}
            )


def _uptime_since(root: str, bound: float) -> tuple[str | None, str]:
    text, _ = _read(root, "/proc/stat")
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "btime" and _DIGITS.fullmatch(parts[1]):
            when = datetime.fromtimestamp(int(parts[1]), UTC)
            return when.strftime("%Y-%m-%dT%H:%M:%SZ"), ""
    out, _ = _run(("uptime", "-s"), bound=bound)
    if out and out.strip():
        return out.strip().replace(" ", "T"), ""
    return None, "cannot read the boot time (/proc/stat btime, uptime -s)"


def _cpu_max_mhz(root: str, bound: float) -> tuple[str | None, str]:
    # cpufreq publishes kHz and the snapshot wants whole MHz, so the value is divided
    # down; lscpu's CPU max MHz is the fallback, cut before the decimal point.
    khz, _ = _first_line(root, "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    if khz and _DIGITS.fullmatch(khz):
        return str(int(khz) // 1000), ""
    out, _ = _run(("lscpu",), bound=bound)
    mhz = (_lscpu_field(out or "", "CPU max MHz") or "").split(".")[0]
    if mhz and _DIGITS.fullmatch(mhz):
        return mhz, ""
    return None, "cannot read cpu_max_mhz (cpufreq/cpuinfo_max_freq, lscpu)"


def _cpu_model(root: str, bound: float) -> tuple[str | None, str]:
    text, _ = _read(root, "/proc/cpuinfo")
    for line in (text or "").splitlines():
        name, sep, rest = line.partition(":")
        if sep and name.strip() == "model name" and rest.strip():
            return rest.strip(), ""
    out, _ = _run(("lscpu",), bound=bound)
    model = _lscpu_field(out or "", "Model name")
    if model:
        return model, ""
    return None, "cannot read the CPU model (/proc/cpuinfo, lscpu)"


def _ram_mt_s(bound: float) -> tuple[str | None, str]:
    # The DDR speed is only in the firmware tables, which dmidecode needs root to
    # read, so `sudo -n` is tried second: it fails at once instead of asking for a
    # password. Different modules at different speeds make one token dishonest, so
    # more than one speed is reported as unread.
    out, _ = _run(("dmidecode", "-t", "memory"), bound=bound)
    if not out:
        out, _ = _run(("sudo", "-n", "dmidecode", "-t", "memory"), bound=bound)
    if not out:
        return None, (
            "cannot read the DDR speed: dmidecode -t memory produced nothing "
            "(needs root, or sudo -n)"
        )
    speeds = sorted(
        set(
            re.findall(
                r"^\s*Configured Memory Speed:\s*([0-9]+)\s*MT/s",
                out,
                flags=re.MULTILINE,
            )
        )
    )
    if not speeds:
        return None, (
            "dmidecode reported no 'Configured Memory Speed' line; the DDR "
            "speed is unread"
        )
    if len(speeds) != 1:
        return None, (
            f"dmidecode reports {len(speeds)} different configured memory speeds "
            f"({' '.join(speeds)}); one token cannot name them honestly"
        )
    return speeds[0], ""


def _power_limit(root: str, which: str) -> tuple[str | None, str]:
    folder = next(
        (
            d
            for d in (
                "/sys/class/powercap/intel-rapl:0",
                "/sys/class/powercap/intel-rapl/intel-rapl:0",
            )
            if os.path.isdir(_at(root, d))
        ),
        None,
    )
    if folder is None:
        return None, (
            "no intel-rapl package directory under /sys/class/powercap; the power "
            "limits are unread"
        )
    index, want = (0, "long_term") if which == "pl1" else (1, "short_term")
    # The constraint is checked by name and not by its number, so that an index
    # meaning something else on this machine is caught here: a name that does not
    # match leaves the limit unread instead of reporting another limit's value.
    value, why = _first_line(root, f"{folder}/constraint_{index}_power_limit_uw")
    if value is None:
        return (
            None,
            f"{folder}/constraint_{index}_power_limit_uw {why}; {which} is unread",
        )
    got, _ = _first_line(root, f"{folder}/constraint_{index}_name")
    if got and got != want:
        return None, (
            f"{folder}/constraint_{index}_name reads {got!r}, not {want!r}; the "
            f"constraint indices are not what {which} assumes"
        )
    if not _DIGITS.fullmatch(value):
        return None, f"{which} read {value!r}, which is not a number of microwatts"
    return value, ""


def _snapshot_cards(
    snapshot: _Snapshot, cards: list[dict[str, Any]], bound: float
) -> None:
    """Fill the GPU keys of the snapshot from the first NVIDIA card.

    The snapshot query adds the slot, the compute capability, the driver and, where
    the tool knows the field, the reserved memory; a tool that does not know
    memory.reserved is asked the shorter query. The further NVIDIA cards are folded
    into gpu_others, one token each. When the tool is absent or names no card, every
    card key is reported unread with that one reason.
    """
    nvidia = sorted(
        (c for c in cards if c["vendor"] == "nvidia"), key=lambda c: c["index"]
    )
    text, why = _run(
        (FIRST_TOOL, f"--query-gpu={SNAPSHOT_QUERY}", "--format=csv,noheader,nounits"),
        bound=bound,
    )
    reserved_read = True
    if text is None:
        text, why = _run(
            (
                FIRST_TOOL,
                f"--query-gpu={SNAPSHOT_QUERY_OLD}",
                "--format=csv,noheader,nounits",
            ),
            bound=bound,
        )
        reserved_read = False
    if text is None or not nvidia:
        reason = why or (
            f"{FIRST_TOOL} is not on PATH"
            if text is None
            else f"{FIRST_TOOL} read no card"
        )
        for key in SNAPSHOT_CARD_KEYS:
            snapshot.put(key, None, f"the GPU state is unread: {reason}")
        return
    extra: dict[int, list[str]] = {}
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if parts and _DIGITS.fullmatch(parts[0]):
            extra[int(parts[0])] = parts[1:]
    first = nvidia[0]
    facts = extra.get(first["index"], [])
    slot, cc, driver = [*facts, "", "", ""][:3]
    snapshot.put("gpu_name", first["name"], "the first card's name is unread")
    snapshot.put(
        "gpu_vram_mib",
        None if first["total_mib"] is None else str(first["total_mib"]),
        "the first card's memory is unread",
    )
    snapshot.put("gpu_cc", cc, f"{FIRST_TOOL} gave no compute_cap for the first card")
    snapshot.put(
        "gpu_slot", slot, f"{FIRST_TOOL} gave no pci.bus_id for the first card"
    )
    snapshot.put("driver", driver, f"{FIRST_TOOL} gave no driver_version")
    # The reserved memory is what the card holds back for itself: the tool's own
    # figure where it reports one, and the total less the used and the free where it
    # does not, or where the figure is not a number.
    reserve = facts[3] if reserved_read and len(facts) > 3 else ""
    if not _DIGITS.fullmatch(reserve):
        total, used, free = first["total_mib"], first["used_mib"], first["free_mib"]
        reserve = (
            "" if None in (total, used, free) else str(max(total - used - free, 0))
        )
    for key, field in (("gpu_used_mib", "used_mib"), ("gpu_free_mib", "free_mib")):
        value = first[field]
        snapshot.put(
            key,
            None if value is None else str(value),
            f"the first card's {field} is unread",
        )
    snapshot.put(
        "gpu_reserve_mib",
        reserve,
        f"{FIRST_TOOL} reports no memory.reserved and no usable total/used/free",
    )
    # Each further card becomes one token, slot:name:total:cc, and the tokens are
    # sorted so that the order the tool prints its cards in cannot read as a change.
    others = []
    for card in nvidia[1:]:
        slot_of, cc_of = [*extra.get(card["index"], []), "", ""][:2]
        others.append(
            ":".join(
                tok(str(v))
                for v in (slot_of, card["name"] or "", card["total_mib"] or "", cc_of)
            )
        )
    snapshot.put("gpu_others", ";".join(sorted(others)), "")


def _snapshot(
    root: str,
    bound: float,
    machine: Mapping[str, Any],
    cards: list[dict[str, Any]],
    docker: str | None,
    docker_why: str | None,
) -> _Snapshot:
    snapshot = _Snapshot()
    snapshot.put(*_pair("uptime_since", _uptime_since(root, bound)))
    snapshot.put(*_pair("cpu_max_mhz", _cpu_max_mhz(root, bound)))
    snapshot.put(*_pair("cpu_model", _cpu_model(root, bound)))
    snapshot.put(*_pair("ram_mt_s", _ram_mt_s(bound)))
    snapshot.put(*_pair("pl1_uw", _power_limit(root, "pl1")))
    snapshot.put(*_pair("pl2_uw", _power_limit(root, "pl2")))
    _snapshot_cards(snapshot, cards, bound)
    # Docker is recorded by the version its daemon answered with, so that a daemon
    # upgrade is the change and an installed CLI on its own is not.
    snapshot.put(
        "docker", docker, f"cannot read the docker daemon's version: {docker_why}"
    )
    snapshot.put("kernel", platform.release(), "cannot read the kernel version")
    # The machine id and the host name are the values the machine section carries,
    # copied here so that the snapshot alone tells one machine from another.
    snapshot.put("hostname", machine.get("host") or None, "cannot read the hostname")
    snapshot.put(
        "os_machine_id",
        machine.get("id") or None,
        "the machine id is unread (see machine_id)",
    )
    meminfo, why = _read(root, "/proc/meminfo")
    for key, field in (
        ("mem_available_kib", "MemAvailable"),
        ("mem_total_kib", "MemTotal"),
        ("swap_total_kib", "SwapTotal"),
    ):
        value = _meminfo_field(meminfo or "", field)
        snapshot.put(
            key,
            None if value is None else str(value),
            f"cannot read {field} from /proc/meminfo" + (f" (it {why})" if why else ""),
        )
    swappiness, why = _first_line(root, "/proc/sys/vm/swappiness")
    snapshot.put(
        "swappiness",
        swappiness if swappiness and _DIGITS.fullmatch(swappiness) else None,
        "cannot read swappiness (/proc/sys/vm/swappiness)",
    )
    count = os.cpu_count()
    snapshot.put(
        "nproc", None if count is None else str(count), "os.cpu_count() gave nothing"
    )
    ordered = {
        key: snapshot.values[key] for key in SNAPSHOT_KEYS if key in snapshot.values
    }
    snapshot.values = ordered
    return snapshot


def _pair(key: str, read: tuple[str | None, str]) -> tuple[str, str | None, str]:
    return key, read[0], read[1]


# The whole scan: the short reading first, then each section the short reading does
# not carry, each kept with the {field, how} facts it rests on and the prose about
# what could not be read, so a consumer can tell a measured value from a missing one.


def scan(
    weights_dir: str | None = None,
    model_stores: Sequence[str] = (),
    *,
    root: str = "",
    bound: float = BOUND_S,
) -> dict[str, Any]:
    """The whole reading of this machine, in one document.

    The short reading is the base, and gpus, cpu, bandwidth, disk, models_on_disk,
    docker, network, home and snapshot are added to it, with every fact, note and
    unread field gathered from those sections. The weights directory is the one
    given, or the default, and model_stores are searched alongside it.
    """
    read = _Short(root, bound)
    short = read.document
    machine = short["machine"]
    gpus, gpu_facts, gpu_notes = _gpus(read.rows, read.first_answered, short["unread"])
    cpu, cpu_facts, cpu_notes = _cpu(bound)
    bandwidth = measure_bandwidth(root)
    path = weights_dir if weights_dir is not None else default_weights_dir()
    disk, disk_facts = _disk(path)
    models, model_facts = _models_on_disk((*model_stores, path))
    docker, docker_why = _docker(bound)
    network, network_facts, network_notes = _network(bound)
    snapshot = _snapshot(root, bound, machine, short["cards"], docker, docker_why)
    notes = list(read.notes)
    facts = [
        {
            "field": "machine.id",
            "how": f"sha256 of {machine['id_from']}"
            if machine["id_from"]
            else "unread",
        },
        *gpu_facts,
        *read.memory_facts,
        *cpu_facts,
    ]
    if bandwidth is None:
        notes.append(
            "Memory bandwidth: not measured — the copy loop produced no usable "
            "timing. Left absent rather than filled in from a module nameplate, "
            "which describes the parts and not this machine."
        )
    else:
        facts.append({"field": "bandwidth.measured_gbps", "how": bandwidth["how"]})
    if docker is None:
        notes.append(f"Docker: not read — {docker_why}.")
    home = mcgyvr_home()
    if home is None:
        notes.append(
            f"mcgyvr home: not read — ${HOME_ENV} names a relative folder, so no "
            "store for compiled kernels is mounted into this rig's units."
        )
    return {
        **short,
        "gpus": gpus,
        "cpu": cpu,
        "bandwidth": bandwidth,
        "disk": disk,
        "models_on_disk": models,
        "docker": docker,
        "network": network,
        "home": home,
        "snapshot": snapshot.values,
        "unread": [*short["unread"], *snapshot.unread],
        "notes": [*notes, *gpu_notes, *cpu_notes, *network_notes],
        "facts": [*facts, *disk_facts, *model_facts, *network_facts],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Print the scan, or the short reading with --cards, as JSON on stdout.

    MCGYVR_TEST_MACHINE_ROOT is prefixed to every path that is read, and
    MCGYVR_TEST_TOOL_SECONDS replaces the time bound when it holds 1 to 6 digits
    giving a whole number of seconds above zero; anything else in it is noted rather
    than used. Any argument other than --cards is a usage error, which returns 2.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    root = os.environ.get(ROOT_VARIABLE, "")
    bound = BOUND_S
    named: list[dict[str, str]] = []
    asked = os.environ.get(SECONDS_VARIABLE)
    if asked is not None:
        if re.fullmatch(r"[0-9]{1,6}", asked) and int(asked) > 0:
            bound = float(int(asked))
        else:
            named.append(
                {
                    "field": "tool_bound",
                    "why": f"{SECONDS_VARIABLE} is not 1 to 6 digits giving a whole "
                    f"number of seconds above 0; the bound is {BOUND_S:g} s",
                }
            )
    if args not in ([], ["--cards"]):
        print(f"rigscan: takes no argument but --cards, not {args!r}", file=sys.stderr)
        return 2
    document = (
        read_machine(root=root, bound=bound) if args else scan(root=root, bound=bound)
    )
    document["unread"] = [*named, *document["unread"]]
    print(json.dumps(document, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
