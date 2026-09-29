"""Runs the product's machine reader over an invented machine.

The reader, ``machine-read.sh``, is run as the door ships it: ``bash -s`` with
the script on stdin. Here its PATH holds only stub card tools, a stub container
tool, traps for every command that asks for elevated rights, and the few
programs the script needs (:data:`PROGRAMS`); every file it reads (sysfs, the
machine-id file, the host name) lies under a fake root it takes from
``MCGYVR_TEST_MACHINE_ROOT``. Nothing of the machine the tests run on is read.

A machine is set out as a :class:`Staged`: what each tool prints and how it
exits, what sysfs holds, what the container tool lists. :func:`stage` sets out
an invented machine of :mod:`tests.machine_shapes` the way this helper models
it:

- a card of the vendor ``vendor-a`` is read by the first vendor's tool
  (:data:`FIRST_TOOL`), whose card text is the generator's own
  :func:`~tests.machine_shapes.card_reader_text`; its process listing is
  answered here from the card's holders, since the generator does not answer it;
- a card of ``vendor-b`` is read by the second vendor's tool
  (:data:`SECOND_TOOL`), whose text is built here; that tool counts what the
  card keeps for itself as used;
- a machine without the card tool (``card_reader_missing``) has neither tool,
  and its cards are found in sysfs only, numbered by their place in the shape;
  there a ``vendor-b`` card publishes its name and memory and a ``vendor-a``
  card neither.

:func:`expected_cards` and :func:`expected_unread` say what the reader must
report for a shape under that model, computed from the shape, never from a run.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from tests.machine_shapes import Card, Shape, card_reader_text

REPO = Path(__file__).resolve().parent.parent
READER = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "machine-read.sh"

#: The environment variable the reader takes its fake file root from.
ROOT_VARIABLE = "MCGYVR_TEST_MACHINE_ROOT"

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

#: Commands that ask for elevated rights or read what only they may; each is a
#: trap on the reader's PATH that records being called.
ELEVATION = ("sudo", "su", "pkexec", "doas", "runuser", "dmidecode")

#: The programs the reader may use besides the stubs.
PROGRAMS = ("bash", "cat", "sha256sum")

MIB = 1024 * 1024


@dataclass(frozen=True, kw_only=True)
class SysfsCard:
    """One ``/sys/class/drm/cardN`` entry. ``None`` leaves a file out."""

    number: int
    vendor: str
    device: str
    product_name: str | None = None
    vram_total_bytes: int | None = None
    vram_used_bytes: int | None = None


@dataclass(frozen=True, kw_only=True)
class Staged:
    """A machine as the reader finds it. Bytes are what a tool prints.

    ``None`` for a tool's text means the tool is not installed.
    ``first_tool_processes`` maps a card index to (text, exit status); an index
    not in it is answered with an error. ``containers`` is the container
    tool's listing, ``ID|NAME|PROJECT`` per line.
    """

    first_tool: bytes | None = None
    first_tool_exit: int = 0
    first_tool_processes: Mapping[int, tuple[bytes, int]] = field(default_factory=dict)
    second_tool: bytes | None = None
    second_tool_exit: int = 0
    sysfs: tuple[SysfsCard, ...] = ()
    containers: bytes | None = b""
    containers_exit: int = 0
    restarts: Mapping[str, bytes] = field(default_factory=dict)
    machine_id_file: str | None = "0123456789abcdef0123456789abcdef"
    hostname: str | None = "box-1.example"
    python: bool = True


@dataclass(frozen=True, kw_only=True)
class Ran:
    """One run of the reader."""

    stdout: str
    stderr: str
    returncode: int
    unexpected: tuple[str, ...]
    elevated: tuple[str, ...]


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
        publishes = card.vendor == "vendor-b" and card.total_mib is not None
        found.append(
            SysfsCard(
                number=number,
                vendor=PCI_VENDOR[card.vendor],
                device=_device_id(card.name),
                product_name=card.name if card.vendor == "vendor-b" else None,
                vram_total_bytes=card.total_mib * MIB if publishes else None,
                vram_used_bytes=(
                    _second_tool_used_mib(card) * MIB if publishes else None
                ),
            )
        )
    return tuple(found)


def _tool_cards(shape: Shape, vendor: str) -> tuple[Card, ...]:
    if shape.card_reader_missing:
        return ()
    return tuple(sorted((c for c in shape.cards if c.vendor == vendor), key=_index))


def _index(card: Card) -> int:
    return card.index


def stage(shape: Shape, /) -> Staged:
    """The invented machine set out as the reader will find it."""
    first = _tool_cards(shape, "vendor-a")
    second = _tool_cards(shape, "vendor-b")
    return Staged(
        first_tool=(
            None
            if shape.card_reader_missing
            else card_reader_text(
                first, query=FIRST_TOOL_CARDS[0].removeprefix("--query-gpu=")
            ).encode("utf-8")
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


_STUB_HEAD = """#!{bash}
here={here}
say() {{ cat "$here/$1.out"; exit "$(cat "$here/$1.exit")"; }}
odd() {{ printf '%s %s\\n' "${{0##*/}}" "$*" >> "$here/unexpected.log"; exit 97; }}
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
    cat "$here/restarts.$id.out"; exit 0
fi
odd "$@"
"""

_TRAP = """#!{bash}
printf '%s %s\\n' "{name}" "$*" >> {log}
exit 1
"""


def _stub(folder: Path, name: str, body: str, answers: Mapping[str, bytes]) -> None:
    here = folder / f".{name}"
    here.mkdir(parents=True)
    for key, text in answers.items():
        _write(here / f"{key}.out", text)
    bash = shutil.which("bash")
    assert bash, "no bash on the test's PATH"
    script = folder / name
    script.write_text(_STUB_HEAD.format(bash=bash, here=here) + body, "utf-8")
    script.chmod(0o755)


def _exit(folder: Path, name: str, key: str, status: int) -> None:
    _write(folder / f".{name}" / f"{key}.exit", str(status))


def run(staged: Staged, where: Path, /) -> Ran:
    """Run the reader over ``staged``, in fresh folders under ``where``."""
    stubs = where / "stubs"
    programs = where / "programs"
    root = where / "root"
    for folder in (stubs, programs, root):
        folder.mkdir(parents=True)
    log = where / "elevated.log"
    bash = shutil.which("bash")
    assert bash, "no bash on the test's PATH"

    for name in PROGRAMS:
        found = shutil.which(name)
        assert found, f"no {name} on the test's PATH"
        (programs / name).symlink_to(found)
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
        _stub(
            stubs,
            FIRST_TOOL,
            _FIRST_TOOL_STUB.format(
                cards=" ".join(FIRST_TOOL_CARDS),
                processes=" ".join(FIRST_TOOL_PROCESSES),
            ),
            answers,
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
        _write(device / "vendor", card.vendor + "\n")
        _write(device / "device", card.device + "\n")
        if card.product_name is not None:
            _write(device / "product_name", card.product_name + "\n")
        if card.vram_total_bytes is not None:
            _write(device / "mem_info_vram_total", f"{card.vram_total_bytes}\n")
        if card.vram_used_bytes is not None:
            _write(device / "mem_info_vram_used", f"{card.vram_used_bytes}\n")
        # A connector entry beside the card, which is not a card.
        (device.parent.parent / f"card{card.number}-HDMI-A-1").mkdir(exist_ok=True)
    if staged.machine_id_file is not None:
        _write(root / "etc" / "machine-id", staged.machine_id_file + "\n")
    if staged.hostname is not None:
        _write(root / "proc" / "sys" / "kernel" / "hostname", staged.hostname + "\n")

    done = subprocess.run(
        [bash, "-s"],
        input=READER.read_bytes(),
        capture_output=True,
        env={
            "PATH": f"{stubs}{os.pathsep}{programs}",
            ROOT_VARIABLE: str(root),
            "LC_ALL": "C",
        },
        cwd=where,
        timeout=60,
        check=False,
    )
    unexpected = [
        line
        for path in sorted(stubs.glob(".*/unexpected.log"))
        for line in path.read_text("utf-8").splitlines()
    ]
    elevated = log.read_text("utf-8").splitlines() if log.exists() else []
    return Ran(
        stdout=done.stdout.decode("utf-8", errors="replace"),
        stderr=done.stderr.decode("utf-8", errors="replace"),
        returncode=done.returncode,
        unexpected=tuple(unexpected),
        elevated=tuple(elevated),
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


def _read_by_sysfs(shape: Shape) -> bool:
    return not _tool_cards(shape, "vendor-a") and not _tool_cards(shape, "vendor-b")


def expected_cards(shape: Shape, /) -> list[Expected]:
    """The cards the reading holds for this shape, sorted by vendor and index."""
    found: list[Expected] = []
    if not _read_by_sysfs(shape):
        for card in _tool_cards(shape, "vendor-a"):
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
        for card in _tool_cards(shape, "vendor-b"):
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
    else:
        for number, card in enumerate(shape.cards):
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
    return unread


def replace(staged: Staged, /, **changes: object) -> Staged:
    """A copy of ``staged`` with ``changes``."""
    return dataclasses.replace(staged, **changes)
