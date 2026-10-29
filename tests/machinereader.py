"""Runs the product's one machine reader over an invented machine.

The reader, ``src/mcgyvr/serving/rigscan.py``, is run as the door ships it:
``python3 -I -B -`` with the source on stdin, asked for its short reading
(``--cards``). Here its PATH holds only stub card tools and traps for six
commands that raise rights or read what only raised rights may
(:data:`ELEVATION`). Every file it reads (sysfs, the machine-id files, the
host name, memory) lies under a fake root it takes from
``MCGYVR_TEST_MACHINE_ROOT``. Nothing of the machine the tests run on is read.
The stubs call ``cat`` and ``sleep`` by their full paths, so neither is on the
reader's PATH.

A machine is set out as a :class:`Staged`: what each tool prints and how it
exits, what sysfs holds, what the container tool lists. :func:`stage` sets out
an invented machine of :mod:`tests.machine_shapes` the way this helper models
it:

- a card of the vendor ``vendor-a`` is read by the first vendor's tool
  (:data:`FIRST_TOOL`), whose card text is the generator's own
  :func:`~tests.machine_shapes.card_reader_text`;
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

from tests._paths import REPO as REPO
from tests.machine_shapes import (
    PCI_VENDOR_IDS,
    Card,
    HostShape,
    Shape,
    card_reader_text,
    device_id,
    host_files,
    host_tools,
)

READER = REPO / "src" / "mcgyvr" / "serving" / "rigscan.py"

#: The environment variables the reader takes, for tests only.
ROOT_VARIABLE = "MCGYVR_TEST_MACHINE_ROOT"
SECONDS_VARIABLE = "MCGYVR_TEST_TOOL_SECONDS"
SYSTEM_VARIABLE = "MCGYVR_TEST_MACHINE_OS"

FIRST_TOOL = "nvidia-smi"
SECOND_TOOL = "rocm-smi"

#: The questions the reader asks each tool, exactly; a stub answers only these.
FIRST_TOOL_CARDS = (
    "--query-gpu=index,memory.total,memory.used,memory.free,name",
    "--format=csv,noheader,nounits",
)
SECOND_TOOL_CARDS = ("--showproductname", "--showmeminfo", "vram", "--json")

#: The vendor label the reading gives a card read by its vendor's tool, and
#: the vendor id sysfs gives it.
TOOL_VENDOR: Mapping[str, str] = {"vendor-a": "nvidia", "vendor-b": "amd"}
PCI_VENDOR: Mapping[str, str] = {
    vendor: f"0x{pci.lower()}" for vendor, pci in PCI_VENDOR_IDS.items()
}

#: Commands that raise rights or read what only raised rights may; each is a
#: trap on the reader's PATH that records being called.
ELEVATION = ("sudo", "su", "pkexec", "doas", "runuser", "dmidecode")

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
    ``first_tool_waits`` makes the first tool wait instead of answering;
    ``first_tool_reads_stdin`` makes it read its standard input to the end
    before it answers; ``first_tool_leaves_child`` makes it start a child that
    holds its output open for half a minute, and answer. ``tool_seconds`` is
    the bound the reader is told to put on each tool call. The machine-id file
    and the host name are written with a line break after them when given as
    text, and as they are when given as bytes. ``environment`` is added to the
    reader's.
    """

    first_tool: bytes | None = None
    first_tool_exit: int = 0
    first_tool_waits: bool = False
    first_tool_reads_stdin: bool = False
    first_tool_leaves_child: bool = False
    second_tool: bytes | None = None
    second_tool_exit: int = 0
    sysfs: tuple[SysfsCard, ...] = ()
    machine_id_file: str | bytes | None = "0123456789abcdef0123456789abcdef"
    dbus_machine_id_file: str | None = None
    hostname: str | bytes | None = "box-1.example"
    tool_seconds: int | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    #: The system the reader is told to read the machine as (None: its own).
    system: str | None = None
    #: Further stub tools: name, then each exact argument list (as one string)
    #: with what the tool prints and its exit status; any other question is
    #: recorded as unexpected.
    tools: Mapping[str, Mapping[str, tuple[bytes, int]]] = field(default_factory=dict)
    #: Stub tools kept outside PATH: a path under the run's folder, and the name of
    #: the tool in ``tools`` it answers as. ``{where}`` in an ``environment``
    #: value is the run's folder, so a variable can point the reader there.
    placed: Mapping[str, str] = field(default_factory=dict)
    #: Further files under the fake root, by their absolute path on the machine.
    files: Mapping[str, str] = field(default_factory=dict)


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
    return "0x" + device_id(name)


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
here='{here}'
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
odd "$@"
"""

_SECOND_TOOL_STUB = """
if [ "$*" = "{cards}" ]; then say cards; fi
odd "$@"
"""

_TABLE_STUB_CASE = """
if [ "$*" = "{arguments}" ]; then say {key}; fi
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


def _table_stub(
    folder: Path, name: str, table: Mapping[str, tuple[bytes, int]]
) -> None:
    """A stub tool that answers each argument list of ``table`` and records any
    other question as unexpected."""
    body = "".join(
        _TABLE_STUB_CASE.format(arguments=arguments, key=f"a{number}")
        for number, arguments in enumerate(table)
    )
    answers = {f"a{n}": text for n, (text, _) in enumerate(table.values())}
    _stub(folder, name, body + 'odd "$@"\n', answers)
    for number, (_, status) in enumerate(table.values()):
        _exit(folder, name, f"a{number}", status)


def _exit(folder: Path, name: str, key: str, status: int) -> None:
    _write(folder / f".{name}" / f"{key}.exit", str(status))


def _set_out(
    staged: Staged, stubs: Path, programs: Path, root: Path, log: Path
) -> None:
    bash = _program("bash")
    for name in ELEVATION:
        trap = stubs / name
        trap.write_text(_TRAP.format(bash=bash, name=name, log=log), "utf-8")
        trap.chmod(0o755)

    if staged.first_tool is not None:
        answers = {"cards": staged.first_tool}
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
            _FIRST_TOOL_STUB.format(cards=" ".join(FIRST_TOOL_CARDS)),
            answers,
            prelude,
        )
        _exit(stubs, FIRST_TOOL, "cards", staged.first_tool_exit)
    if staged.second_tool is not None:
        _stub(
            stubs,
            SECOND_TOOL,
            _SECOND_TOOL_STUB.format(cards=" ".join(SECOND_TOOL_CARDS)),
            {"cards": staged.second_tool},
        )
        _exit(stubs, SECOND_TOOL, "cards", staged.second_tool_exit)
    for name, table in staged.tools.items():
        if name not in staged.placed.values():
            _table_stub(stubs, name, table)
    for place, name in staged.placed.items():
        folder = stubs.parent / Path(place).parent
        folder.mkdir(parents=True, exist_ok=True)
        _table_stub(folder, Path(place).name, staged.tools[name])
    for path, text in staged.files.items():
        _write(root / path.lstrip("/"), text)
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
    if staged.system is not None:
        env[SYSTEM_VARIABLE] = staged.system
    env.update(
        {
            name: value.replace("{where}", str(where))
            for name, value in staged.environment.items()
        }
    )
    return env


def run(
    staged: Staged,
    where: Path,
    /,
    *,
    give_up_after: float = 60,
    command: tuple[str, ...] | None = None,
    source: bytes | None = None,
) -> Ran:
    """Run the reader over ``staged``, in fresh folders under ``where``.

    After ``give_up_after`` seconds the reader and everything it started are
    killed, and what it printed so far is returned. ``command`` runs another
    command than ``python3 -I -B - --cards`` (for example one that traces it),
    with the source still on its standard input; ``source`` hands it other
    bytes than the reader's file (the packed program the door ships).
    """
    stubs = where / "stubs"
    programs = where / "programs"
    root = where / "root"
    for folder in (stubs, programs, root):
        folder.mkdir(parents=True)
    log = where / "elevated.log"
    _set_out(staged, stubs, programs, root, log)

    process = subprocess.Popen(
        list(command or (sys.executable, "-I", "-B", "-", "--cards")),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=reader_env(where, staged),
        cwd=where,
        start_new_session=True,
    )
    gave_up = False
    try:
        out, err = process.communicate(
            READER.read_bytes() if source is None else source, timeout=give_up_after
        )
    except subprocess.TimeoutExpired:
        gave_up = True
        os.killpg(process.pid, signal.SIGKILL)
        out, err = process.communicate()
    unexpected = [
        line
        for path in sorted(where.glob("**/.*/unexpected.log"))
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


def reading(text: str, /) -> dict[str, Any]:
    """The reader's document, as the product takes it."""
    document = json.loads(text)
    assert isinstance(document, dict)
    return document


def machine_reading(shape: Shape, where: Path, /) -> dict[str, Any]:
    """The reader's document for this invented machine."""
    return reading(machine_read_text(shape, where))


def unread(document: Mapping[str, Any], /) -> dict[str, str]:
    """The fields a reading names unread, each with why."""
    return {u["field"]: u["why"] for u in document["unread"]}


def cards(document: Mapping[str, Any], /) -> list[tuple[Any, ...]]:
    """``(vendor, index, name, total, used, free)`` per card of a reading."""
    return [
        (
            c["vendor"],
            c["index"],
            c["name"],
            c["total_mib"],
            c["used_mib"],
            c["free_mib"],
        )
        for c in document["cards"]
    ]


def fingerprint(seed: str) -> str:
    """A machine id as the reader derives it from its machine-id file."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


#: A card as the reading should hold it: (vendor, index, name, total, used,
#: free).
Expected = tuple[str, int, str | None, int | None, int | None, int | None]


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
            used = None if card.total_mib is None else card.used_mib
            found.append(
                ("nvidia", card.index, card.name, card.total_mib, used, card.free_mib)
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
                )
            )
        elif card.vendor == "vendor-b":
            found.append(("amd", number, card.name, None, None, None))
        else:
            name = f"PCI {PCI_VENDOR[card.vendor]}:{_device_id(card.name)}"
            found.append(("nvidia", number, name, None, None, None))
    return sorted(found, key=lambda c: (c[0], c[1]))


def expected_unread(shape: Shape, /) -> set[str]:
    """The fields the reading names as unread for this shape."""
    unread: set[str] = set()
    for vendor, index, _, total, used, free in expected_cards(shape):
        key = f"card.{vendor}.{index}"
        for name, value in (("total", total), ("used", used), ("free", free)):
            if value is None:
                unread.add(f"{key}.{name}")
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


#: Where an invented Windows machine keeps nvidia-smi.exe outside PATH, under the
#: run's folder, and the variable that names that folder's root.
_CARD_TOOL_FOLDERS: Mapping[str, tuple[str, str]] = {
    "system32": ("windows/System32", "SYSTEMROOT"),
    "nvsmi": ("program-files/NVIDIA Corporation/NVSMI", "PROGRAMFILES"),
}
#: Where Windows keeps its own tools, which the reader calls by full path.
_SYSTEM_TOOLS: Mapping[str, str] = {
    "reg": "windows/System32/reg.exe",
    "powershell": "windows/System32/WindowsPowerShell/v1.0/powershell.exe",
}


def stage_host(machine: HostShape, /) -> Staged:
    """An invented machine with its system, set out as the reader will find it:
    every tool of :func:`tests.machine_shapes.host_tools` a stub (on PATH, or on
    Windows where Windows keeps it, under ``SYSTEMROOT`` and the vendor's
    folder), and every file of :func:`tests.machine_shapes.host_files` under the
    root."""
    tables: dict[str, dict[str, tuple[bytes, int]]] = {}
    for argv, (text, status) in host_tools(machine).items():
        tables.setdefault(argv[0], {})[" ".join(argv[1:])] = (
            text.encode("utf-8"),
            status,
        )
    placed: dict[str, str] = {}
    environment: dict[str, str] = {}
    if machine.system == "windows":
        environment["SYSTEMROOT"] = "{where}/windows"
        for name, place in _SYSTEM_TOOLS.items():
            if name in tables:
                placed[place] = name
        folder = _CARD_TOOL_FOLDERS.get(machine.card_tool)
        if FIRST_TOOL in tables:
            relative, variable = folder or ("stubs", "")
            placed[f"{relative}/nvidia-smi.exe"] = FIRST_TOOL
            if variable and variable != "SYSTEMROOT":
                environment[variable] = "{where}/" + relative.split("/")[0]
    return Staged(
        machine_id_file=None,
        hostname=None,
        system=machine.system,
        tools=tables,
        placed=placed,
        environment=environment,
        files=host_files(machine),
    )


def replace(staged: Staged, /, **changes: Any) -> Staged:
    """A copy of ``staged`` with ``changes``."""
    return dataclasses.replace(staged, **changes)
