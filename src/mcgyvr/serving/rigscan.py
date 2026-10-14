#!/usr/bin/env python3
"""The one reader of a machine's hardware, run here or shipped as ``python3 -``.

Nothing else in mcgyvr runs a hardware tool. Every reading of a machine —
``mcgyvr scan`` of this machine or of a rig, the door's gate 2 and gate 7,
``read``, the card figures a serve step files, ``mcgyvr detect``'s cards and
RAM, the hardware a rig reports to its hub — is this module's one document,
read where the machine is. Two readers would be two opinions about one
machine, and the first thing two opinions do is disagree about the one fact
somebody needed.

It must stay importable (the product imports it, and the door reads it by file
to base64-encode it) and stdlib-only (a rig has no venv, no mcgyvr, no
PYTHONPATH). Under ``__main__`` it prints one JSON document to stdout and
nothing else; ``--cards`` prints the short reading alone (:func:`read_machine`).

**What the document holds.** Three parts, read in one pass so one card tool
call answers all three:

* the **short reading** (:func:`read_machine`): the machine's id and host
  name, every card each source shows, on any vendor, and RAM. The rig id
  (:func:`mcgyvr.fleet.ids.rig_id`) is the digest of the machine id and the
  cards' names and sizes, so this is what names the machine;
* the **capacity scan** :meth:`mcgyvr.scan.Scan.from_json` parses: free VRAM,
  available RAM, cores, timed memory bandwidth, free disk where weights land,
  the weights already on disk, the docker daemon's version, and where the
  machine is reached;
* the **snapshot** (:data:`SNAPSHOT_KEYS`): the whitespace-free tokens the
  door's gates hold a run to and stamp into its record — the boot time, the
  CPU's clock and power limits, the DDR speed, the first card's slot and
  compute capability, the driver, the kernel, RAM and swap. What holds the
  rig at run time (its containers, the processes on its card) is the door's
  runtime reader's, ``gate-scripts/rig-units.sh``, and not here.

**A field that is not read is named, with why, and never filled in.** Every
``None`` in the short reading, and every snapshot key that has no value, is in
``unread`` as ``{"field": ..., "why": ...}``. A snapshot key is never printed
as a placeholder: a placeholder in a rig stamp is a fabricated row, and the
whole point of the snapshot is that it can be compared with a declaration and
disagree. The capacity scan keeps its own older rule — absence makes the scan
smaller and adds a note — because a bare machine is a valid answer to "what
can this hold".

**Cards, on any vendor.** The first vendor's tool (``nvidia-smi``) and the
second vendor's (``rocm-smi``), each that is installed, then sysfs's DRM class
for the cards of every vendor no answering tool covered. A card is listed
once: sysfs gives no card of a vendor a tool answered for, and when sysfs
shows more cards of that vendor than the tool printed, the tool's list is
named unread (``cards.<tool>``). A tool that is installed and prints no card,
or fails, is named unread too. A card is known by its vendor and its index as
its source numbers it, so two vendors may both have a card 0. A card no
installed tool reads and whose sysfs entry publishes no size is named in
``unsized``: the rig id leaves such a card out. Nothing here sums the cards
or picks one of them, so a machine of several cards is never read as its
first.

**What a tool prints is untrusted.** Each call is bounded in time
(:data:`BOUND_S`) and in bytes (:data:`BYTES_MAX`); a value that is not what
its field takes is named unread rather than passed on: a size that is not a
whole number, a name that is empty, ``[N/A]``, longer than :data:`NAME_MAX`,
or holds a character a name does not (:func:`name_problem`). A name is taken
in Unicode normal form C.

**It asks for raised rights once, and only for the snapshot.** The DDR speed
is read by ``dmidecode``, which needs root; it is asked plainly, then through
``sudo -n`` (never a prompt). The short reading, which a rig's hub agent takes
on every heartbeat, asks for no raised rights at all.

Two environment variables are for the product's tests only, and are read by
:func:`main` alone: ``MCGYVR_TEST_MACHINE_ROOT`` (every file this reads is
read under that folder) and ``MCGYVR_TEST_TOOL_SECONDS`` (the bound on each
tool call, 1 to 6 digits of whole seconds above 0).
"""

import contextlib
import hashlib
import json
import os
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

KB_PER_GB = 1024.0 * 1024.0
MIB_PER_GB = 1024.0
BYTES_PER_GB = 1024.0**3
MIB_BYTES = 1024 * 1024

# Bandwidth: a timed copy, sized to make the reading repeat. At 64 MiB a
# shared machine varied by 44% run to run; at 256 MiB by 9%. A machine with
# little free RAM is measured with the smaller buffer, and ``how`` says so.
COPY_MIB = 256
COPY_PASSES = 5
COPY_MIB_TIGHT = 64
TIGHT_RAM_GB = 2.0

WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"
#: The files a machine id is taken from, the first that is there and not blank.
MACHINE_ID_FILES = ("/etc/machine-id", "/var/lib/dbus/machine-id")
HOSTNAME_FILE = "/proc/sys/kernel/hostname"
DRM = "/sys/class/drm"

#: The bound on each tool call, in seconds, and on what is read of its output.
BOUND_S = 20.0
BYTES_MAX = 262144
#: The longest line taken from a file, and the most lines from one call.
LINE_MAX = 4096
LINES_MAX = 4096
#: The longest name passed on, in characters; a longer one is named unread.
NAME_MAX = 256
#: The longest run of digits taken as a size: more is no size of a card.
DIGITS_MAX = 18

ROOT_VARIABLE = "MCGYVR_TEST_MACHINE_ROOT"
SECONDS_VARIABLE = "MCGYVR_TEST_TOOL_SECONDS"

#: A GGUF quantisation as file names spell it, at the end of the name.
GGUF_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)

#: What the first vendor's tool is asked: one line per card, sizes in MiB,
#: ``[N/A]`` for a value it cannot give. The name is asked last, so a comma in
#: it stays in the name. A name holding a line break is caught when what
#: follows the break is not a card row, or a row for an index already
#: printed; when it is a row for another index it forges a card nothing here
#: can tell from a real one.
FIRST_TOOL = "nvidia-smi"
FIRST_QUERY = "index,memory.total,memory.used,memory.free,name"
#: What the snapshot asks it besides, per card. ``memory.reserved`` is not
#: known to every driver, so a query without it is asked when it fails.
SNAPSHOT_QUERY = "index,pci.bus_id,compute_cap,driver_version,memory.reserved"
SNAPSHOT_QUERY_OLD = "index,pci.bus_id,compute_cap,driver_version"
#: The second vendor's tool, asked for JSON: a member per card named
#: ``cardN``, its name under ``Card series`` (else ``Card model``), its memory
#: in bytes under ``VRAM Total Memory (B)`` and ``VRAM Total Used Memory (B)``.
#: Keys are matched without case.
SECOND_TOOL = "rocm-smi"
SECOND_ARGS = ("--showproductname", "--showmeminfo", "vram", "--json")
#: PCI vendor ids sysfs gives, by the vendor name a card is listed under, and
#: the tool that reads each vendor's cards (none reads the third's).
PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
VENDOR_TOOLS = {"nvidia": FIRST_TOOL, "amd": SECOND_TOOL}

#: What the docker CLI is asked: the daemon's version, one line.
DOCKER_VERSION_FORMAT = "{{.Server.Version}}"
#: What sshd tells the session it starts: the client's address and port,
#: then the address and port this machine was reached at.
SSH_CONNECTION_ENV = "SSH_CONNECTION"
#: What ``ip`` is asked: every IPv4 address, one line each.
IP_ADDR_ARGS = ("-4", "-o", "addr", "show")

#: How a capacity scan's notes begin when its card list is not the whole
#: answer: the first vendor's tool gave none, or printed a card this could
#: not read whole. Such a list is "not determined", never "fewer cards".
GPU_NOT_DETERMINED = "GPU: not determined"
GPU_ROW_UNREAD = "GPU: nvidia-smi printed a row this could not read"

#: The snapshot's keys, in the order a reading prints them. Each is a
#: whitespace-free token, legal in a stamp exactly as it is. ``gpu_others``
#: names the cards beyond the first as ``slot:name:vram_mib:cc``, sorted by
#: slot and ``;``-joined, and is empty for a machine of one card.
#: ``os_machine_id`` is the machine's id (``machine.id``), the one derivation.
#: What holds the rig at run time — its containers and the processes on its
#: card — is not here: ``gate-scripts/rig-units.sh`` reads that, and the door
#: ships it beside this reader.
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
#: The snapshot keys the first card's tool gives; a rig whose card these do
#: not read is a rig the door does not compare.
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
    # systemd's own advice is not to hand /etc/machine-id out as-is; hashing
    # keeps the property this needs (same machine, same answer) without
    # publishing an id other software treats as a secret.
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def tok(value: str) -> str:
    """``value`` as one whitespace-free token: a snapshot value is legal inside
    a stamp exactly as it is printed, so blanks become ``_`` rather than being
    quoted somewhere downstream."""
    return re.sub(r"_+", "_", re.sub(r"\s+", "_", value)).strip("_")


def is_text(value: str) -> bool:
    """No control, format, private, unassigned or line-breaking character."""
    return all(
        unicodedata.category(c)[0] != "C"
        and unicodedata.category(c) not in ("Zl", "Zp")
        for c in value
    )


def name_problem(value: object) -> str | None:
    """Why ``value`` is not a card name a reading takes, or ``None`` when it is.

    The one rule for a name, held by this reader where the name is printed and
    by :func:`mcgyvr.fleet.ids.rig_id` where a reading from another machine is
    taken: a document that did not come from this reader gets no easier rule.
    """
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
    """A whole number of MiB as a reading holds one."""
    return type(value) is int and 0 <= value < 10**DIGITS_MAX


def is_machine_id(value: object) -> bool:
    """A machine id as this reader derives one: 16 lower-case hex digits."""
    return isinstance(value, str) and _HEX16.fullmatch(value) is not None


# --------------------------------------------------------------------------
# the seams: a tool call and a file read
# --------------------------------------------------------------------------


def _run(
    argv: Sequence[str], *, bound: float = BOUND_S
) -> tuple[str | None, str | None]:
    """What a tool printed, bounded: ``(text, None)``; ``(None, why)`` when it
    failed; ``(None, None)`` when it is not installed.

    Standard input is closed (a tool that read it would wait for nothing), and
    standard error dropped. The tool and anything it started run in a session
    of their own, killed whole once ``bound`` seconds pass: a tool that does not
    answer, or exits leaving a child holding its output open, is named and
    never waited on. At most :data:`BYTES_MAX` bytes are taken.
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
            start_new_session=True,
        )
    except OSError as exc:
        return None, f"{label} could not start ({exc.strerror or exc})"
    assert process.stdout is not None
    deadline = time.monotonic() + bound
    chunks: list[bytes] = []
    size = 0
    why: str | None = None
    with selectors.DefaultSelector() as watch:
        watch.register(process.stdout, selectors.EVENT_READ)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                why = (
                    f"{label} did not answer within {bound:g} s"
                    if process.poll() is None
                    else f"{label} left its output open past {bound:g} s"
                )
                break
            if not watch.select(left):
                continue
            data = os.read(process.stdout.fileno(), 65536)
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
            os.killpg(process.pid, signal.SIGKILL)
    process.stdout.close()
    process.wait()
    if why is not None:
        return None, why
    if process.returncode != 0:
        return None, f"{label} exited {process.returncode}"
    return b"".join(chunks).decode("utf-8", errors="replace"), None


def _at(root: str, path: str) -> str:
    """``path`` under ``root``: nothing is read outside it."""
    return root + path if root else path


def _read(root: str, path: str) -> tuple[str | None, str]:
    """The text of a file, and ``""``; or ``None`` and why it was not read."""
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
    """The first line of a file, trimmed; or ``None`` and why it was not read."""
    text, why = _read(root, path)
    if text is None:
        return None, why
    line = text.split("\n", 1)[0]
    if len(line) > LINE_MAX:
        return None, f"holds a line longer than {LINE_MAX} characters"
    return line.strip(), ""


# --------------------------------------------------------------------------
# the short reading: machine, cards, memory
# --------------------------------------------------------------------------


class _Reading:
    """What one reading of the cards gathers before it is printed."""

    def __init__(self) -> None:
        self.cards: dict[tuple[str, int], dict[str, Any]] = {}
        self.twice: set[tuple[str, int]] = set()
        self.unread: list[dict[str, str]] = []
        self.unsized: list[str] = []
        self.sources: list[str] = []
        self.covered: set[str] = set()
        self.printed: dict[str, int] = {}
        #: Whether the first vendor's tool answered at all, cards or none.
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
        """``value`` as a whole number of MiB, or ``None`` after naming ``field``."""
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
        """``value`` as a card name, or ``None`` after naming ``field``."""
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
    """The first vendor's cards, as its tool prints them; the rows are returned
    for the capacity scan, which reads the same call."""
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
                # A line that is not a card after a card: its name may have run
                # over a line break, so the name before it is not trusted.
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
    """A JSON value as the text a field is read from; a bool or a container is no
    value, and a fraction keeps its point so it is named as no whole number."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return ""
    return repr(value) if isinstance(value, float) else str(value)


def _second_tool(reading: _Reading, bound: float) -> None:
    """The second vendor's cards, as its tool's JSON gives them."""
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
    """The cards of every vendor no answering tool covered, from sysfs.

    Each card is ``/sys/class/drm/cardN`` (a connector is ``cardN-NAME``), its PCI
    ids in ``device/vendor`` and ``device/device``; the amdgpu driver publishes
    its memory in bytes as ``device/mem_info_vram_total`` and ``_used``. A card
    with no name file is named by its PCI ids; an entry with no PCI vendor id
    (a display that is not a PCI card) is listed under the vendor ``unknown``.
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
        # A vendor a tool answered for is that tool's; sysfs adds no card of it.
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
    # A tool that printed fewer cards than sysfs shows of its vendor.
    for vendor, count in sorted(seen.items()):
        if vendor in reading.covered and count > reading.printed.get(vendor, 0):
            tool = VENDOR_TOOLS[vendor]
            reading.note(
                f"cards.{tool}",
                f"sysfs shows {count} cards of vendor {vendor} and {tool} printed "
                f"{reading.printed.get(vendor, 0)}; its list of cards may be short",
            )


def _host(root: str, reading: _Reading) -> str:
    """The machine's host name as it names itself, or ``""`` named unread."""
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
    """Identify the machine by something durable, never by what was measured.

    A machine that gains a card is the same machine to its scans; its rig id
    (:func:`mcgyvr.fleet.ids.rig_id`) adds the cards. The id is the first 16
    hex of the sha256 of the first machine-id file that is there and not
    blank, trimmed; else of ``host:NAME``. A file that is there and cannot be
    taken whole is named, not passed over: the host name would give another
    id for the same machine.
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
    # A host name is weaker — it can be changed, and two machines can share one
    # — but it is durable enough to name a machine by, and saying so is better
    # than refusing to read a machine without systemd.
    machine["id"], machine["id_from"] = _fingerprint(f"host:{host}"), "hostname"
    notes.append(
        "Machine id: derived from the hostname — no /etc/machine-id. It is "
        "stable until the host is renamed, and a rename will read as a new "
        "machine rather than as a changed one."
    )
    return machine, notes


def machine_id(*, root: str = "") -> str:
    """This machine's id alone, as every reading names it, without reading a
    card: ``""`` when it cannot be read. What a lease and a recorded reading
    of this very machine are matched by, and no measurement is paid for it."""
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
    """System memory: the total, and the kernel's estimate of what a new
    workload could get without swapping (free memory alone understates it)."""
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
        # MemFree is the older kernels' answer and a worse one — it excludes
        # reclaimable cache — so it is used only as a fallback, and said so.
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
    """The short reading, and what the capacity scan takes from the same calls:
    the first tool's rows, whether it answered, and the notes and facts of the
    machine id and memory."""

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
        # Every None of a card is named, once.
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
    """The short reading of this machine: its id, its cards on any vendor, and RAM.

    What a rig's hub agent reads on every heartbeat and what a serve step
    files of the card: no timed copy, no disk walk, and no raised rights.
    """
    return _Short(root, bound).document


# --------------------------------------------------------------------------
# the capacity scan
# --------------------------------------------------------------------------


def _gpus(
    rows: list[dict[str, Any]], answered: bool, unread: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    """The first vendor's cards a fit is sized against, each read whole.

    Free is the card's own answer, not total less used: the two differ by the
    driver's reserve, which no process is ever given, and a placement sized
    against the over-statement clears the fit and then fails to allocate. The
    reserve is derived as the remainder so the four numbers sum exactly.
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
    """Cores and threads kept apart, because they are different constraints."""
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
    """A ``key: value`` line, matched on the whole key, so lscpu's ``NUMA node0
    CPU(s)`` is never taken for its ``CPU(s)``."""
    for line in text.splitlines():
        name, sep, rest = line.partition(":")
        if sep and name.strip() == key:
            return rest.strip()
    return None


def _lscpu_int(text: str, key: str) -> int | None:
    value = (_lscpu_field(text, key) or "").split()
    return int(value[0]) if value and _DIGITS.fullmatch(value[0]) else None


def _spare_gb(root: str) -> float:
    """Available RAM, or 0.0 when unread, so the smaller copy buffer is chosen:
    a scan that cannot tell how much room it has should not take half a GB."""
    text, _ = _read(root, "/proc/meminfo")
    if text is None:
        return 0.0
    available = _meminfo_field(text, "MemAvailable")
    if available is None:
        available = _meminfo_field(text, "MemFree")
    return 0.0 if available is None else available / KB_PER_GB


def measure_bandwidth(root: str = "") -> dict[str, Any] | None:
    """Time a large memory copy and report GB/s, or None when it cannot be read.

    Deliberately not dmidecode: a nameplate figure is what the modules are
    rated at, not how many channels they populate. Both buffers are touched
    before the clock starts, and the best pass is taken: everything that
    perturbs a copy loop can only make it slower.
    """
    mib = COPY_MIB
    if _spare_gb(root) < TIGHT_RAM_GB + 2 * mib / MIB_PER_GB:
        mib = COPY_MIB_TIGHT
    try:
        source = bytearray(mib * MIB_BYTES)
        target = bytearray(mib * MIB_BYTES)
    except (MemoryError, ValueError):
        return None
    target[:] = source  # fault both mappings in, off the clock
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
    """Where weights land when nothing names a folder: ``$MCGYVR_WEIGHTS``, else
    ``~/.cache/mcgyvr/weights``."""
    override = os.environ.get(WEIGHTS_DIR_ENV)
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser("~/.cache/mcgyvr/weights")


def _disk_device(path: str) -> str | None:
    """The device of the filesystem holding ``path``, when /proc names one."""
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
    """Free space where weights would land. A folder named before it is made is
    measured by its nearest ancestor: the answer for the parent is the answer
    for the child once it exists."""
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
    """Every ``*.gguf`` and ``*.safetensors`` under ``roots``, named enough to be
    reused instead of fetched. A missing root is absence; a file that cannot be
    stat'ed is skipped rather than guessed at; hidden folders are not walked."""
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
    """The version this user's docker daemon reports, or ``None`` and why not."""
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
    """``ip -4 -o addr show``: ``<n>: <interface> inet <address>/<prefix> ...``."""
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


def _network(bound: float) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    """Where this machine is reached, as it says itself. Nothing is resolved.

    The address the ssh session arrived at is the one the controller reached it
    by; the interface addresses are what else it holds. Which one a worker
    listens on is picked by the controller from these, never looked up.
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
    if text is None:
        notes.append(
            "Network: `ip " + " ".join(IP_ADDR_ARGS) + "` is absent or failed, "
            "so the addresses on its interfaces are not read."
        )
    else:
        facts.append({"field": "network.ipv4", "how": "ip " + " ".join(IP_ADDR_ARGS)})
    ipv4 = _parse_ip_addr(text) if text is not None else []
    return {"reached_at": reached, "ipv4": ipv4}, facts, notes


# --------------------------------------------------------------------------
# the snapshot
# --------------------------------------------------------------------------


class _Snapshot:
    """The snapshot's values as they are read, and why each unread one is not."""

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
    # One rig's max clock moved 4800 -> 4600 unattended; a row that cannot name
    # it is not comparable with one taken before the move.
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
    # RAM has moved between rigs twice in six days. Never guessed.
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
    # constraint_N_power_limit_uw, never constraint_N_max_power_uw: the latter
    # is the CPU's rated TDP and reads the same whatever the live limit is,
    # which looks exactly like the cap being in force when it is not.
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
    """The first card's facts, and the cards beyond it, from the card tool."""
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
    # The reserve is GSP firmware and differs per boot, so it is derived from
    # the other three rather than assumed when the driver omits it.
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
    # The cards beyond the first, by slot: the same extra card in another slot
    # is a different machine to a stamp.
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
    # A Vulkan ICD manifest is mounted by one docker version and not by another,
    # so the daemon's version is a fact of the rig and not of the tooling.
    snapshot.put(
        "docker", docker, f"cannot read the docker daemon's version: {docker_why}"
    )
    snapshot.put("kernel", platform.release(), "cannot read the kernel version")
    # The daemon gate 3 reaches answers to this name, so a container started
    # through the door is started on the machine gate 2 read.
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


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------


def scan(
    weights_dir: str | None = None,
    model_stores: Sequence[str] = (),
    *,
    root: str = "",
    bound: float = BOUND_S,
) -> dict[str, Any]:
    """Read this machine whole: the short reading, the capacity scan and the
    snapshot, as one document. Never raises: a bare machine is a valid answer."""
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
    return {
        **short,
        "gpus": gpus,
        "cpu": cpu,
        "bandwidth": bandwidth,
        "disk": disk,
        "models_on_disk": models,
        "docker": docker,
        "network": network,
        "snapshot": snapshot.values,
        "unread": [*short["unread"], *snapshot.unread],
        "notes": [*notes, *gpu_notes, *cpu_notes, *network_notes],
        "facts": [*facts, *disk_facts, *model_facts, *network_facts],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Print one JSON document: the whole reading, or ``--cards`` the short one."""
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
