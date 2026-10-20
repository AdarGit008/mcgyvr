"""A scan reports what it measured, not what the machine's nameplate claims.

Every number here is stubbed. The one reader of a machine
(:mod:`mcgyvr.serving.rigscan`) is run in-process with its tool seam
(``_run``), its timed copy and the free-space call answered by the suite, over
an empty file root holding only the ``/proc/meminfo`` a case gives, and its
document is read back as :meth:`mcgyvr.scan.Scan.from_json` reads it. The
suite asserts on how the code treats a measurement -- that it reads free
memory as well as total, that it keeps cores and threads apart, that it
records what it found as the machine's rig file and flags a disagreement with
what it found last time -- never on the hardware the suite happens to run on.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.scan import Cpu, Memory, Scan, Vram
from mcgyvr.serving import rigfile, rigscan

MEMINFO = "MemTotal:       49293144 kB\nMemAvailable:   45010000 kB\n"
MEMINFO_SMALL = "MemTotal:       33554432 kB\nMemAvailable:   30000000 kB\n"
#: Rows as the reader asks for them: index, total, used, free, then the name,
#: asked last so a comma in it stays in the name.
SMI = "0, 12288, 11286, 1002, NVIDIA GeForce RTX 3060\n"
SMI_IDLE = "0, 12288, 12, 12276, NVIDIA GeForce RTX 3060\n"
LSCPU = (
    "CPU(s):                20\nCore(s) per socket:    10\nThread(s) per core:    2\n"
)
LSCPU_NO_SMT = (
    "CPU(s):                8\nCore(s) per socket:    8\nThread(s) per core:    1\n"
)
FIRST_QUERY = f"--query-gpu={rigscan.FIRST_QUERY}"


class _Usage:
    """What ``shutil.disk_usage`` answers, at the free size a case gives."""

    def __init__(self, free_gb: float) -> None:
        self.free = int(free_gb * 1024**3)
        self.total = 2 * self.free
        self.used = self.total - self.free


#: What the `bench` fixture hands a case: a re-installer for the stubbed
#: hardware answers, called with any subset of `install`'s keyword arguments.
Bench = Callable[..., None]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The reader's file root: nothing of the machine the suite runs on is read."""
    folder = tmp_path / "root"
    (folder / "proc").mkdir(parents=True)
    return folder


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch, root: Path) -> Bench:
    """Hardware answers, stubbed at the seams the one reader reaches through."""

    def install(
        *,
        meminfo: str | None = MEMINFO,
        smi: str | None = SMI,
        lscpu: str | None = LSCPU,
        bandwidth: float | None = 41.2,
        free_gb: float = 512.0,
    ) -> None:
        def run(
            argv: Sequence[str], *, bound: float = 0.0
        ) -> tuple[str | None, str | None]:
            if argv[0] == "nvidia-smi" and argv[1] == FIRST_QUERY:
                return smi, None
            if argv[0] == "lscpu":
                return lscpu, None
            return None, None

        monkeypatch.setattr(rigscan, "_run", run)
        meminfo_path = root / "proc" / "meminfo"
        if meminfo is None:
            meminfo_path.unlink(missing_ok=True)
        else:
            meminfo_path.write_text(meminfo, encoding="utf-8")
        monkeypatch.setattr(
            rigscan,
            "measure_bandwidth",
            lambda root="": (
                None
                if bandwidth is None
                else {"measured_gbps": bandwidth, "how": "copy loop"}
            ),
        )
        monkeypatch.setattr(shutil, "disk_usage", lambda path: _Usage(free_gb))

    install()
    return install


@pytest.fixture
def scan(root: Path, tmp_path: Path) -> Callable[..., Scan]:
    """One reading of the stubbed machine, as a scan."""

    def read(weights_dir: Path | None = None) -> Scan:
        return Scan.from_json(json.dumps(reading(root, weights_dir or tmp_path)))

    return read


def reading(root: Path, weights_dir: Path) -> dict[str, Any]:
    return rigscan.scan(weights_dir=str(weights_dir), root=str(root))


@pytest.fixture
def rigs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The folder of rig files, where the one record of a machine is kept."""
    folder = tmp_path / "rigs"
    monkeypatch.setenv("MCGYVR_RIGS", str(folder))
    return folder


def test_vram_reports_free_not_only_nameplate(bench: Bench, scan: Any) -> None:
    assert scan().gpus[0].vram == Vram(total_mib=12288, used_mib=11286, free_mib=1002)


def test_ram_reports_available_not_only_total(bench: Bench, scan: Any) -> None:
    memory = scan().memory
    assert memory == Memory(total_gb=47.0, available_gb=42.9)


def test_cores_and_threads_are_separate_numbers(bench: Bench, scan: Any) -> None:
    assert scan().cpu == Cpu(cores=10, threads=20)


def test_a_cpu_without_smt_reports_one_thread_per_core(bench: Bench, scan: Any) -> None:
    bench(lscpu=LSCPU_NO_SMT)
    assert scan().cpu == Cpu(cores=8, threads=8)


def test_bandwidth_is_measured_not_read_from_a_nameplate(
    bench: Bench, scan: Any
) -> None:
    got = scan().bandwidth
    assert got is not None
    assert got.measured_gbps == pytest.approx(41.2)
    assert got.how != "dmidecode"


def test_bandwidth_that_cannot_be_measured_is_absent_not_guessed(
    bench: Bench, scan: Any
) -> None:
    bench(bandwidth=None)
    result = scan()
    assert result.bandwidth is None
    assert any(note.startswith("Memory bandwidth") for note in result.notes)


def test_disk_free_is_measured_for_the_weights_path(
    bench: Bench, scan: Any, tmp_path: Path
) -> None:
    disk = scan(weights_dir=tmp_path / "weights").disk
    assert disk is not None
    assert disk.path == tmp_path / "weights"
    assert disk.free_gb == pytest.approx(512.0)


def test_a_reading_is_recorded_once_as_the_machines_rig_file(
    bench: Bench, root: Path, tmp_path: Path, rigs: Path
) -> None:
    taken = reading(root, tmp_path)
    saved = rigfile.save(rigfile.LOCAL, taken)
    assert saved.path == rigs / f"{rigfile.LOCAL}.json"
    assert sorted(path.name for path in rigs.iterdir()) == [saved.path.name]
    recorded = json.loads(saved.path.read_text(encoding="utf-8"))
    assert recorded["reading"]["machine"]["id"] == taken["machine"]["id"]


def test_machine_id_is_stable_across_two_scans(bench: Bench, scan: Any) -> None:
    assert scan().machine.id == scan().machine.id


def test_a_reading_round_trips_through_its_rig_file(
    bench: Bench, root: Path, tmp_path: Path, rigs: Path
) -> None:
    taken = reading(root, tmp_path)
    rigfile.save(rigfile.LOCAL, taken)
    recorded = rigfile.read(rigfile.LOCAL)
    assert recorded is not None
    assert recorded.scan == Scan.from_json(json.dumps(taken))


def test_a_move_flags_ram_that_disagrees_with_the_record(
    bench: Bench, root: Path, tmp_path: Path, rigs: Path
) -> None:
    bench(meminfo=MEMINFO_SMALL)
    rigfile.save(rigfile.LOCAL, reading(root, tmp_path))
    bench(meminfo=MEMINFO)
    saved = rigfile.save(rigfile.LOCAL, reading(root, tmp_path))
    assert saved.before is not None
    found = rigfile.moved(saved.before, saved.now)
    assert rigfile.Moved("ram_total_gb", 32.0, 47.0) in found
    assert all(rigfile.is_hardware(change) for change in found), found


def test_no_record_is_nothing_moved(
    bench: Bench, root: Path, tmp_path: Path, rigs: Path
) -> None:
    assert rigfile.save(rigfile.LOCAL, reading(root, tmp_path)).before is None


def test_a_volatile_number_alone_is_nothing_moved(
    bench: Bench, root: Path, tmp_path: Path, rigs: Path
) -> None:
    rigfile.save(rigfile.LOCAL, reading(root, tmp_path))
    bench(smi=SMI_IDLE, free_gb=100.0)
    saved = rigfile.save(rigfile.LOCAL, reading(root, tmp_path))
    assert saved.before is not None
    assert rigfile.moved(saved.before, saved.now) == ()


def test_absence_of_a_gpu_is_an_outcome_not_an_error(bench: Bench, scan: Any) -> None:
    bench(smi=None)
    result = scan()
    assert result.gpus == ()
    assert result.notes
    assert not result.gpus_determined


def test_a_bare_machine_still_scans(bench: Bench, scan: Any, root: Path) -> None:
    (root / "proc" / "sys" / "kernel").mkdir(parents=True)
    (root / "proc" / "sys" / "kernel" / "hostname").write_text("box-1\n")
    bench(smi=None, lscpu=None, bandwidth=None, meminfo=None)
    assert scan().machine.id


def test_every_measured_fact_carries_its_provenance(bench: Bench, scan: Any) -> None:
    facts = scan().facts
    assert facts
    assert all(fact.how for fact in facts)


#: Three rows nvidia-smi really prints, as the reader asks for them. The
#: second carries a comma inside the name a vendor chose, and the third is a
#: vGPU parent whose memory the tool does not give.
SMI_AWKWARD = (
    "0, 16376, 1000, 15376, NVIDIA RTX A4000\n"
    "1, 15360, 400, 14960, Tesla T4, Custom\n"
    "2, 40960, [N/A], [N/A], GRID A100\n"
)
SMI_MIG = "0, [N/A], [N/A], [N/A], NVIDIA A100-SXM4-40GB MIG 1g.5gb\n"


def test_a_comma_in_a_card_name_does_not_drop_the_card(bench: Bench, scan: Any) -> None:
    """`Tesla T4, Custom` is one card, not a malformed row.

    The name is the only field a vendor writes, and a comma in it splits the
    row. It is asked last, so the comma stays in the name; requiring a fixed
    field count would lose a card that is present -- and every card is a place
    a unit gets bound to by index.
    """
    bench(smi=SMI_AWKWARD)
    result = scan()
    assert [(gpu.index, gpu.name) for gpu in result.gpus] == [
        (0, "NVIDIA RTX A4000"),
        (1, "Tesla T4, Custom"),
    ]
    assert result.gpus[1].vram == Vram(total_mib=15360, used_mib=400, free_mib=14960)


def test_a_row_that_cannot_be_read_is_noted_rather_than_dropped(
    bench: Bench, scan: Any
) -> None:
    """Rule 1: absence is an outcome, and a note matters as much as the absence.

    A row dropped in silence reads downstream as a machine with fewer cards --
    which places a unit on the wrong index and makes the next comparison
    report a card that was never pulled.
    """
    bench(smi=SMI_AWKWARD)
    result = scan()
    said = [note for note in result.notes if note.startswith(rigscan.GPU_ROW_UNREAD)]
    assert len(said) == 1 and "card 2" in said[0], result.notes
    assert not result.gpus_determined


def test_a_mig_row_reporting_na_for_memory_is_not_silence(
    bench: Bench, scan: Any
) -> None:
    """`[N/A]` memory is "not determined", never "no card here"."""
    bench(smi=SMI_MIG)
    result = scan()
    assert result.gpus == ()
    assert any(
        note.startswith(rigscan.GPU_ROW_UNREAD) and "[N/A]" in note
        for note in result.notes
    ), result.notes
    assert not any("reported no device" in note for note in result.notes)


def test_a_clean_card_list_says_nothing_about_unreadable_rows(
    bench: Bench, scan: Any
) -> None:
    """The note is evidence, so it must not fire on a scan with nothing to report."""
    result = scan()
    assert len(result.gpus) == 1
    assert not any("could not read" in note for note in result.notes)
    assert result.gpus_determined


def test_nvidia_smi_answering_with_nothing_still_says_so(
    bench: Bench, scan: Any
) -> None:
    """No rows at all is a different fact from rows that could not be read."""
    bench(smi="\n")
    result = scan()
    assert result.gpus == ()
    assert any("reported no device" in note for note in result.notes)


#: box1 as nvidia-smi printed it on 2026-09-05 with the 35B unit up: the card
#: says 6144 total, 5306 used and 438 free, which do not sum -- 400 MiB is the
#: driver's own reserve and is never handed to a process.
SMI_RESERVED = "0, 6144, 5306, 438, NVIDIA GeForce RTX 3050\n"


def test_free_vram_is_the_cards_own_number_not_total_minus_used(
    bench: Bench, scan: Any
) -> None:
    """``total - used`` is not what the card will hand out, and the gap decides fits.

    Measured on box1 (2026-09-05): total 6144, used 5306, free 438. Deriving
    free from the first two reports 838 -- 400 MiB that no process can have,
    because the driver is holding it. A placement sized against the derived
    number clears every gate and then OOMs at load by exactly that reserve.

    The reserve is reported rather than folded away, so the sum still closes:
    a scan whose three numbers did not add up would be a scan nobody could
    act on, which is the objection the derivation was answering.
    """
    bench(smi=SMI_RESERVED)
    vram = scan().gpus[0].vram
    assert vram.free_mib == 438
    assert vram.reserved_mib == 400
    assert vram.total_mib == vram.used_mib + vram.free_mib + vram.reserved_mib


def test_a_card_holding_nothing_back_reports_no_reserve(
    bench: Bench, scan: Any
) -> None:
    """The reserve is a reading, not a constant: a card that hands out all of
    its free memory reports zero and the sum closes just the same."""
    bench(smi="0, 12288, 11286, 1002, NVIDIA GeForce RTX 3060\n")
    vram = scan().gpus[0].vram
    assert (vram.free_mib, vram.reserved_mib) == (1002, 0)
