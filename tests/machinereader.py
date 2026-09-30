"""Runs the product's machine reader over an invented machine.

The reader, ``machine-read.sh``, is run as the door ships it: ``bash -s`` with
the script on stdin. Here its PATH holds only stub card tools, a stub container
tool, traps for six commands that raise rights or read what only raised rights
may (:data:`ELEVATION`), and the programs the script uses (:data:`PROGRAMS`,
plus ``timeout`` and ``python3`` unless a test leaves them out). Every file it
reads (sysfs, the machine-id files, the host name) lies under a fake root it
takes from ``MCGYVR_TEST_MACHINE_ROOT``. Nothing of the machine the tests run on
is read. The stubs call ``cat`` and ``sleep`` by their full paths, so neither is
on the reader's PATH.

A machine is set out as a :class:`Staged`: what each tool prints and how it
exits, what sysfs holds, what the container tool lists. :func:`stage` sets out
an invented machine of :mod:`tests.machine_shapes` the way this helper models
it:

- a card of the vendor ``vendor-a`` is read by the first vendor's tool
  (:data:`FIRST_TOOL`), whose card text is the generator's own
  :func:`~tests.machine_shapes.card_reader_text`; its process listing is
  answered here from the card's holders, since the generator does not answer it;
- a card of ``vendor-b`` is read by the second vendor's tool
  (:data:`SECOND_TOOL`), whose text is built here, and which is installed only
  on a machine that has such a card; that tool counts what the card keeps for
  itself as used;
- a machine without the card tool (``card_reader_missing``) has neither tool;
- every card is also in sysfs, numbered by its place in the shape; there a
  ``vendor-b`` card publishes its name and memory and a ``vendor-a`` card
  neither. The reader takes from sysfs the cards of a vendor no tool answered
  for; under this model the tool of that vendor is then not installed, so a
  card of it whose size sysfs does not publish is one the reading names
  unsized (:func:`expected_unsized`).

:func:`expected_cards` and :func:`expected_unread` say what the reader must
report for a shape under that model, computed from the shape, never from a run.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.machine_shapes import Card, Shape, card_reader_text

REPO = Path(__file__).resolve().parent.parent
READER = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "machine-read.sh"

#: The environment variables the reader takes, for tests only.
ROOT_VARIABLE = "MCGYVR_TEST_MACHINE_ROOT"
SECONDS_VARIABLE = "MCGYVR_TEST_TOOL_SECONDS"

FIRST_TOOL = "nvidia-smi"
SECOND_TOOL = "rocm-smi"

#: The questions the reader asks each tool, exactly; a stub answers only these.
FIRST_TOOL_CARDS = (
    "--query-gpu=index,memory.total,memory.used,memory.free,name",
    "--format=csv,noheader,nounits",
)
FIRST_TOOL_PROCESSES = (
    "--query-compute-apps=pid,used_memory,process_name",
    "--format=csv,noheader,nounits",
)
SECOND_TOOL_CARDS = ("--showproductname", "--showmeminfo", "vram", "--json")

#: The vendor label the reading gives a card read by its vendor's tool, and
#: the vendor id sysfs gives it.
TOOL_VENDOR: Mapping[str, str] = {"vendor-a": "nvidia", "vendor-b": "amd"}
PCI_VENDOR: Mapping[str, str] = {"vendor-a": "0x10de", "vendor-b": "0x1002"}

#: Commands that raise rights or read what only raised rights may; each is a
#: trap on the reader's PATH that records being called.
ELEVATION = ("sudo", "su", "pkexec", "doas", "runuser", "dmidecode")

#: The programs the reader always has on its PATH besides the stubs.
PROGRAMS = ("bash", "sha256sum", "tr", "head")

MIB = 1024 * 1024


@dataclass(frozen=True, kw_only=True)
class SysfsCard:
    """One ``/sys/class/drm/cardN`` entry. ``None`` leaves a file out.

    ``raw`` maps a file name under ``device/`` to bytes written as they are,
    over what the other fields would write. ``product_name_dir`` writes
    ``product_name`` as a folder instead of a file, to model a name file that
    is there but cannot be read.
    """

    number: int
    vendor: str | None
    device: str
    product_name: str | None = None
    product_name_dir: bool = False
    vram_total_bytes: int | None = None
    vram_used_bytes: int | None = None
    raw: Mapping[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Staged:
    """A machine as the reader finds it. Bytes are what a tool prints.

    ``None`` for a tool's text means the tool is not installed.
    ``first_tool_processes`` maps a card index to (text, exit status); an index
    not in it is answered with an error. ``containers`` is the container
    tool's listing, ``ID|NAME|PROJECT`` per line. ``first_tool_waits`` makes
    the first tool wait instead of answering; ``first_tool_reads_stdin`` makes
    it read its standard input to the end before it answers;
    ``first_tool_leaves_child`` makes it start a child that holds its output
    open for half a minute, and answer. ``tool_seconds`` is the bound the
    reader is told to put on each tool call. The machine-id file and the host
    name are written with a line break after them when given as text, and as
    they are when given as bytes. ``environment`` is added to the reader's.
    """

    first_tool: bytes | None = None
    first_tool_exit: int = 0
    first_tool_processes: Mapping[int, tuple[bytes, int]] = field(default_factory=dict)
    first_tool_waits: bool = False
    first_tool_reads_stdin: bool = False
    first_tool_leaves_child: bool = False
    second_tool: bytes | None = None
    second_tool_exit: int = 0
    sysfs: tuple[SysfsCard, ...] = ()
    containers: bytes | None = b""
    containers_exit: int = 0
    restarts: Mapping[str, bytes] = field(default_factory=dict)
    machine_id_file: str | bytes | None = "0123456789abcdef0123456789abcdef"
    dbus_machine_id_file: str | None = None
    hostname: str | bytes | None = "box-1.example"
    python: bool = True
    timeout_program: bool = True
    tool_seconds: int | None = None
    environment: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Ran:
    """One run of the reader. ``gave_up`` when it was stopped from outside."""

    stdout: str
    stderr: str
    returncode: int
    unexpected: tuple[str, ...]
    elevated: tuple[str, ...]
    gave_up: bool = False


def _device_id(name: str) -> str:
    return "0x" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:4]


def _first_tool_processes(card: Card) -> bytes:
    lines = [f"{h.pid}, {h.mib}, {h.name}\n" for h in card.holders]
    return "".join(lines).encode("utf-8")


def _second_tool_used_mib(card: Card) -> int:
    assert card.total_mib is not None
    return card.reserved_mib + card.used_mib


def _second_tool_text(cards: tuple[Card, ...]) -> bytes:
    body: dict[str, dict[str, str]] = {}
    for card in cards:
        entry = {
            "Card series": card.name,
            "Card model": _device_id(card.name),
            "Card vendor": "Example Vendor, Inc.",
        }
        if card.total_mib is not None:
            entry["VRAM Total Memory (B)"] = str(card.total_mib * MIB)
            entry["VRAM Total Used Memory (B)"] = str(_second_tool_used_mib(card) * MIB)
        body[f"card{card.index}"] = entry
    return json.dumps(body).encode("utf-8")


def _sysfs(shape: Shape) -> tuple[SysfsCard, ...]:
    found = []
    for number, card in enumerate(shape.cards):
        total = card.total_mib if card.vendor == "vendor-b" else None
        found.append(
            SysfsCard(
                number=number,
                vendor=PCI_VENDOR[card.vendor],
                device=_device_id(card.name),
                product_name=card.name if card.vendor == "vendor-b" else None,
                vram_total_bytes=None if total is None else total * MIB,
                vram_used_bytes=(
                    None if total is None else _second_tool_used_mib(card) * MIB
                ),
            )
        )
    return tuple(found)


def _index(card: Card) -> int:
    return card.index


def _of(shape: Shape, vendor: str) -> tuple[Card, ...]:
    return tuple(sorted((c for c in shape.cards if c.vendor == vendor), key=_index))


def _first_installed(shape: Shape) -> bool:
    return not shape.card_reader_missing


def _second_installed(shape: Shape) -> bool:
    return not shape.card_reader_missing and bool(_of(shape, "vendor-b"))


def _covered(shape: Shape) -> set[str]:
    """The vendors a tool answered for with at least one card."""
    covered = set()
    if _first_installed(shape) and _of(shape, "vendor-a"):
        covered.add("vendor-a")
    if _second_installed(shape):
        covered.add("vendor-b")
    return covered


def stage(shape: Shape, /) -> Staged:
    """The invented machine set out as the reader will find it."""
    first = _of(shape, "vendor-a") if _first_installed(shape) else ()
    second = _of(shape, "vendor-b") if _second_installed(shape) else ()
    return Staged(
        first_tool=(
            card_reader_text(
                first, query=FIRST_TOOL_CARDS[0].removeprefix("--query-gpu=")
            ).encode("utf-8")
            if _first_installed(shape)
            else None
        ),
        first_tool_processes={
            card.index: (_first_tool_processes(card), 0) for card in first
        },
        second_tool=_second_tool_text(second) if second else None,
        sysfs=_sysfs(shape),
        machine_id_file=shape.machine_id,
        hostname=shape.host,
    )


def _write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)


def _line(content: str | bytes) -> str | bytes:
    return content if isinstance(content, bytes) else content + "\n"


def _program(name: str) -> str:
    found = shutil.which(name)
    assert found, f"no {name} on the test's PATH"
    return found


_STUB_HEAD = """#!{bash}
here={here}
say() {{ {cat} "$here/$1.out"; read -r s < "$here/$1.exit"; exit "$s"; }}
odd() {{ printf '%s %s\\n' "${{0##*/}}" "$*" >> "$here/unexpected.log"; exit 97; }}
"""

_WAITS = """exec {sleep} 600
"""

_READS_STDIN = """{cat} > "$here/stdin.seen"
"""

_LEAVES_CHILD = """( exec {sleep} 30 ) &
"""

_FIRST_TOOL_STUB = """
if [ "$*" = "{cards}" ]; then say cards; fi
if [ "$1" = -i ] && [ "${{*:3}}" = "{processes}" ]; then
    case $2 in ''|*[!0-9]*) odd "$@" ;; esac
    [ -f "$here/processes.$2.out" ] || {{ echo "no card $2" >&2; exit 6; }}
    say "processes.$2"
fi
odd "$@"
"""

_SECOND_TOOL_STUB = """
if [ "$*" = "{cards}" ]; then say cards; fi
odd "$@"
"""

_CONTAINER_STUB = """
if [ "$1" = ps ] && [ "$2" = --no-trunc ]; then say ps; fi
if [ "$1" = inspect ]; then
    for id in "$@"; do :; done
    [ -f "$here/restarts.$id.out" ] || exit 1
    {cat} "$here/restarts.$id.out"; exit 0
fi
odd "$@"
"""

_TRAP = """#!{bash}
printf '%s %s\\n' "{name}" "$*" >> {log}
exit 1
"""


def _stub(
    folder: Path, name: str, body: str, answers: Mapping[str, bytes], prelude: str = ""
) -> None:
    here = folder / f".{name}"
    here.mkdir(parents=True)
    for key, text in answers.items():
        _write(here / f"{key}.out", text)
    head = _STUB_HEAD.format(bash=_program("bash"), here=here, cat=_program("cat"))
    script = folder / name
    script.write_text(head + prelude + body.replace("{cat}", _program("cat")), "utf-8")
    script.chmod(0o755)


def _exit(folder: Path, name: str, key: str, status: int) -> None:
    _write(folder / f".{name}" / f"{key}.exit", str(status))


def _set_out(
    staged: Staged, stubs: Path, programs: Path, root: Path, log: Path
) -> None:
    bash = _program("bash")
    for name in PROGRAMS:
        (programs / name).symlink_to(_program(name))
    if staged.timeout_program:
        (programs / "timeout").symlink_to(_program("timeout"))
    if staged.python:
        (programs / "python3").symlink_to(sys.executable)
    for name in ELEVATION:
        trap = stubs / name
        trap.write_text(_TRAP.format(bash=bash, name=name, log=log), "utf-8")
        trap.chmod(0o755)

    if staged.first_tool is not None:
        answers = {"cards": staged.first_tool}
        answers |= {
            f"processes.{i}": t for i, (t, _) in staged.first_tool_processes.items()
        }
        prelude = ""
        if staged.first_tool_waits:
            prelude += _WAITS.format(sleep=_program("sleep"))
        if staged.first_tool_reads_stdin:
            prelude += _READS_STDIN.format(cat=_program("cat"))
        if staged.first_tool_leaves_child:
            prelude += _LEAVES_CHILD.format(sleep=_program("sleep"))
        _stub(
            stubs,
            FIRST_TOOL,
            _FIRST_TOOL_STUB.format(
                cards=" ".join(FIRST_TOOL_CARDS),
                processes=" ".join(FIRST_TOOL_PROCESSES),
            ),
            answers,
            prelude,
        )
        _exit(stubs, FIRST_TOOL, "cards", staged.first_tool_exit)
        for index, (_, status) in staged.first_tool_processes.items():
            _exit(stubs, FIRST_TOOL, f"processes.{index}", status)
    if staged.second_tool is not None:
        _stub(
            stubs,
            SECOND_TOOL,
            _SECOND_TOOL_STUB.format(cards=" ".join(SECOND_TOOL_CARDS)),
            {"cards": staged.second_tool},
        )
        _exit(stubs, SECOND_TOOL, "cards", staged.second_tool_exit)
    if staged.containers is not None:
        answers = {"ps": staged.containers}
        answers |= {f"restarts.{k}": v for k, v in staged.restarts.items()}
        _stub(stubs, "docker", _CONTAINER_STUB, answers)
        _exit(stubs, "docker", "ps", staged.containers_exit)

    for card in staged.sysfs:
        device = root / "sys" / "class" / "drm" / f"card{card.number}" / "device"
        if card.vendor is not None:
            _write(device / "vendor", card.vendor + "\n")
        _write(device / "device", card.device + "\n")
        if card.product_name_dir:
            (device / "product_name").mkdir(parents=True, exist_ok=True)
        elif card.product_name is not None:
            _write(device / "product_name", card.product_name + "\n")
        if card.vram_total_bytes is not None:
            _write(device / "mem_info_vram_total", f"{card.vram_total_bytes}\n")
        if card.vram_used_bytes is not None:
            _write(device / "mem_info_vram_used", f"{card.vram_used_bytes}\n")
        for name, content in card.raw.items():
            _write(device / name, content)
        # A connector entry beside the card, which is not a card.
        (device.parent.parent / f"card{card.number}-HDMI-A-1").mkdir(exist_ok=True)
    if staged.machine_id_file is not None:
        _write(root / "etc" / "machine-id", _line(staged.machine_id_file))
    if staged.dbus_machine_id_file is not None:
        _write(
            root / "var" / "lib" / "dbus" / "machine-id",
            staged.dbus_machine_id_file + "\n",
        )
    if staged.hostname is not None:
        _write(root / "proc" / "sys" / "kernel" / "hostname", _line(staged.hostname))


def reader_env(where: Path, staged: Staged) -> dict[str, str]:
    """The environment the reader runs in, for :func:`run` and its callers."""
    env = {
        "PATH": f"{where / 'stubs'}{os.pathsep}{where / 'programs'}",
        ROOT_VARIABLE: str(where / "root"),
        "LC_ALL": "C",
    }
    if staged.tool_seconds is not None:
        env[SECONDS_VARIABLE] = str(staged.tool_seconds)
    env.update(staged.environment)
    return env


def run(
    staged: Staged,
    where: Path,
    /,
    *,
    give_up_after: float = 60,
    command: tuple[str, ...] | None = None,
) -> Ran:
    """Run the reader over ``staged``, in fresh folders under ``where``.

    After ``give_up_after`` seconds the reader and everything it started are
    killed, and what it printed so far is returned. ``command`` runs another
    command than ``bash -s`` (for example one that traces it), with the script
    still on its standard input.
    """
    stubs = where / "stubs"
    programs = where / "programs"
    root = where / "root"
    for folder in (stubs, programs, root):
        folder.mkdir(parents=True)
    log = where / "elevated.log"
    _set_out(staged, stubs, programs, root, log)

    process = subprocess.Popen(
        list(command or (_program("bash"), "-s")),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=reader_env(where, staged),
        cwd=where,
        start_new_session=True,
    )
    gave_up = False
    try:
        out, err = process.communicate(READER.read_bytes(), timeout=give_up_after)
    except subprocess.TimeoutExpired:
        gave_up = True
        os.killpg(process.pid, signal.SIGKILL)
        out, err = process.communicate()
    unexpected = [
        line
        for path in sorted(stubs.glob(".*/unexpected.log"))
        for line in path.read_text("utf-8").splitlines()
    ]
    elevated = log.read_text("utf-8").splitlines() if log.exists() else []
    return Ran(
        stdout=out.decode("utf-8", errors="replace"),
        stderr=err.decode("utf-8", errors="replace"),
        returncode=process.returncode,
        unexpected=tuple(unexpected),
        elevated=tuple(elevated),
        gave_up=gave_up,
    )


def machine_read_text(shape: Shape, where: Path, /) -> str:
    """What the reader prints for this invented machine."""
    ran = run(stage(shape), where)
    assert ran.returncode == 0, ran.stderr
    assert not ran.unexpected, ran.unexpected
    return ran.stdout


def fingerprint(seed: str) -> str:
    """A machine id as the reader derives it from its machine-id file."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


#: A card as the reading should hold it: (vendor, index, name, total, used,
#: free, holders), holders being ``(pid, name, mib)`` each, or ``None`` when
#: they cannot be read.
Expected = tuple[
    str,
    int,
    str | None,
    int | None,
    int | None,
    int | None,
    tuple[tuple[int, str, int], ...] | None,
]


def expected_sources(shape: Shape, /) -> tuple[str, ...]:
    """The card sources the reading names for this shape, in order."""
    covered = _covered(shape)
    sources = []
    if "vendor-a" in covered:
        sources.append(FIRST_TOOL)
    if "vendor-b" in covered:
        sources.append(SECOND_TOOL)
    if any(card.vendor not in covered for card in shape.cards):
        sources.append("sysfs")
    return tuple(sources)


def expected_cards(shape: Shape, /) -> list[Expected]:
    """The cards the reading holds for this shape, sorted by vendor and index."""
    covered = _covered(shape)
    found: list[Expected] = []
    if "vendor-a" in covered:
        for card in _of(shape, "vendor-a"):
            holders = tuple((h.pid, h.name, h.mib) for h in card.holders)
            used = None if card.total_mib is None else card.used_mib
            found.append(
                (
                    "nvidia",
                    card.index,
                    card.name,
                    card.total_mib,
                    used,
                    card.free_mib,
                    holders,
                )
            )
    if "vendor-b" in covered:
        for card in _of(shape, "vendor-b"):
            assert card.total_mib is not None
            used = _second_tool_used_mib(card)
            found.append(
                (
                    "amd",
                    card.index,
                    card.name,
                    card.total_mib,
                    used,
                    card.total_mib - used,
                    None,
                )
            )
    for number, card in enumerate(shape.cards):
        if card.vendor in covered:
            continue
        if card.vendor == "vendor-b" and card.total_mib is not None:
            used = _second_tool_used_mib(card)
            found.append(
                (
                    "amd",
                    number,
                    card.name,
                    card.total_mib,
                    used,
                    card.total_mib - used,
                    None,
                )
            )
        elif card.vendor == "vendor-b":
            found.append(("amd", number, card.name, None, None, None, None))
        else:
            name = f"PCI {PCI_VENDOR[card.vendor]}:{_device_id(card.name)}"
            found.append(("nvidia", number, name, None, None, None, None))
    return sorted(found, key=lambda c: (c[0], c[1]))


def expected_unread(shape: Shape, /) -> set[str]:
    """The fields the reading names as unread for this shape."""
    unread: set[str] = set()
    for vendor, index, _, total, used, free, holders in expected_cards(shape):
        key = f"card.{vendor}.{index}"
        for name, value in (("total", total), ("used", used), ("free", free)):
            if value is None:
                unread.add(f"{key}.{name}")
        if holders is None:
            unread.add(f"{key}.holders")
    if _first_installed(shape) and "vendor-a" not in _covered(shape):
        unread.add(f"cards.{FIRST_TOOL}")
    return unread


def expected_unsized(shape: Shape, /) -> tuple[str, ...]:
    """The cards the reading names unsized for this shape, in reading order.

    A card is unsized when no answering tool covers its vendor, no installed
    tool reads it, and sysfs publishes no size for it.
    """
    covered = _covered(shape)
    found = []
    for number, card in enumerate(shape.cards):
        if card.vendor in covered:
            continue
        if card.vendor == "vendor-b" and card.total_mib is not None:
            continue
        found.append((TOOL_VENDOR[card.vendor], number))
    return tuple(f"card.{vendor}.{index}" for vendor, index in sorted(found))


def replace(staged: Staged, /, **changes: Any) -> Staged:
    """A copy of ``staged`` with ``changes``."""
    return dataclasses.replace(staged, **changes)
