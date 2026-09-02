"""A scan reports what it measured, not what the machine's nameplate claims.

Every number here is stubbed. The suite asserts on how the code treats a
measurement -- that it reads free memory as well as total, that it keeps cores
and threads apart, that it writes what it found and flags a disagreement with
what it found last time -- never on the hardware the suite happens to run on.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.scan import (
    Bandwidth,
    Cpu,
    Memory,
    Mismatch,
    Vram,
    compare,
    load_prior,
    machine_id,
    scan,
    write_scan,
)

MEMINFO = "MemTotal:       49293144 kB\nMemAvailable:   45010000 kB\n"
MEMINFO_SMALL = "MemTotal:       33554432 kB\nMemAvailable:   30000000 kB\n"
SMI = "0, NVIDIA GeForce RTX 3060, 12288, 11286\n"
SMI_IDLE = "0, NVIDIA GeForce RTX 3060, 12288, 12\n"
LSCPU = (
    "CPU(s):                20\nCore(s) per socket:    10\nThread(s) per core:    2\n"
)
LSCPU_NO_SMT = (
    "CPU(s):                8\nCore(s) per socket:    8\nThread(s) per core:    1\n"
)


#: What the `bench` fixture hands a case: a re-installer for the stubbed
#: hardware answers, called with any subset of `install`'s keyword arguments.
Bench = Callable[..., None]


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch) -> Bench:
    """Hardware answers, stubbed at the two seams a scan reaches through."""

    def install(
        *,
        meminfo: str | None = MEMINFO,
        smi: str | None = SMI,
        lscpu: str | None = LSCPU,
        bandwidth: float | None = 41.2,
        free_gb: float = 512.0,
    ) -> None:
        table = {"nvidia-smi": smi, "lscpu": lscpu}
        monkeypatch.setattr(
            scan_module, "_run", lambda binary, *a, **k: table.get(binary)
        )
        monkeypatch.setattr(scan_module, "_read_meminfo", lambda: meminfo)
        monkeypatch.setattr(
            scan_module,
            "measure_bandwidth",
            lambda: (
                None
                if bandwidth is None
                else Bandwidth(measured_gbps=bandwidth, how="copy loop")
            ),
        )
        monkeypatch.setattr(
            scan_module, "_free_bytes", lambda path: int(free_gb * 1024**3)
        )

    install()
    return install


def test_vram_reports_free_not_only_nameplate(bench: Bench) -> None:
    assert scan().gpus[0].vram == Vram(total_mib=12288, used_mib=11286, free_mib=1002)


def test_ram_reports_available_not_only_total(bench: Bench) -> None:
    memory = scan().memory
    assert memory == Memory(total_gb=47.0, available_gb=42.9)


def test_cores_and_threads_are_separate_numbers(bench: Bench) -> None:
    assert scan().cpu == Cpu(cores=10, threads=20)


def test_smt_is_derived_from_the_two_numbers(bench: Bench) -> None:
    cpu = scan().cpu
    assert cpu is not None
    assert cpu.smt is True
    bench(lscpu=LSCPU_NO_SMT)
    cpu = scan().cpu
    assert cpu is not None
    assert cpu.smt is False


def test_bandwidth_is_measured_not_read_from_a_nameplate(bench: Bench) -> None:
    got = scan().bandwidth
    assert got is not None
    assert got.measured_gbps == pytest.approx(41.2)
    assert got.how != "dmidecode"


def test_bandwidth_that_cannot_be_measured_is_absent_not_guessed(bench: Bench) -> None:
    bench(bandwidth=None)
    result = scan()
    assert result.bandwidth is None
    assert result.notes


def test_disk_free_is_measured_for_the_weights_path(
    bench: Bench, tmp_path: Path
) -> None:
    disk = scan(weights_dir=tmp_path).disk
    assert disk is not None
    assert disk.path == tmp_path
    assert disk.free_gb == pytest.approx(512.0)


def test_scan_is_persisted_keyed_by_machine_id(bench: Bench, tmp_path: Path) -> None:
    result = scan()
    path = write_scan(result, root=tmp_path)
    assert path == tmp_path / f"{machine_id(result)}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["machine"]["id"] == machine_id(
        result
    )


def test_machine_id_is_stable_across_two_scans(bench: Bench) -> None:
    assert machine_id(scan()) == machine_id(scan())


def test_a_scan_round_trips_through_disk(bench: Bench, tmp_path: Path) -> None:
    result = scan()
    write_scan(result, root=tmp_path)
    assert load_prior(machine_id(result), root=tmp_path) == result


def test_mismatch_flags_ram_that_disagrees_with_the_prior(
    bench: Bench, tmp_path: Path
) -> None:
    bench(meminfo=MEMINFO_SMALL)
    prior = scan()
    write_scan(prior, root=tmp_path)
    bench(meminfo=MEMINFO)
    now = scan()
    assert Mismatch(field="memory.total_gb", prior=32.0, measured=47.0) in compare(
        now, load_prior(machine_id(now), root=tmp_path)
    )


def test_no_prior_is_not_a_mismatch(bench: Bench, tmp_path: Path) -> None:
    assert compare(scan(), load_prior("nobody", root=tmp_path)) == ()


def test_a_volatile_number_alone_is_not_a_mismatch(
    bench: Bench, tmp_path: Path
) -> None:
    write_scan(scan(), root=tmp_path)
    bench(smi=SMI_IDLE)
    now = scan()
    assert compare(now, load_prior(machine_id(now), root=tmp_path)) == ()


def test_absence_of_a_gpu_is_an_outcome_not_an_error(bench: Bench) -> None:
    bench(smi=None)
    result = scan()
    assert result.gpus == ()
    assert result.notes


def test_a_bare_machine_still_scans(bench: Bench) -> None:
    bench(smi=None, lscpu=None, bandwidth=None)
    assert scan().machine.id


def test_every_measured_fact_carries_its_provenance(bench: Bench) -> None:
    facts = scan().facts
    assert facts
    assert all(fact.how for fact in facts)


#: Three rows nvidia-smi really prints. Only the first is four clean fields:
#: the second carries a comma inside the name a vendor chose, and the third is
#: a shape this parser does not know.
SMI_AWKWARD = (
    "0, NVIDIA RTX A4000, 16376, 1000\n"
    "1, Tesla T4, Custom, 15360, 400\n"
    "2, GRID A100, 40960\n"
)
SMI_MIG = "0, NVIDIA A100-SXM4-40GB MIG 1g.5gb, [N/A], [N/A]\n"


def test_a_comma_in_a_card_name_does_not_drop_the_card(bench: Bench) -> None:
    """`Tesla T4, Custom` is one card, not a malformed row.

    The name is the only field a vendor writes, and a comma in it splits the
    row into five. Requiring exactly four fields loses a card that is present
    -- and every card is a place a unit gets bound to by index.
    """
    bench(smi=SMI_AWKWARD)
    result = scan()
    assert [(gpu.index, gpu.name) for gpu in result.gpus] == [
        (0, "NVIDIA RTX A4000"),
        (1, "Tesla T4, Custom"),
    ]
    assert result.gpus[1].vram == Vram(total_mib=15360, used_mib=400, free_mib=14960)


def test_a_row_that_cannot_be_read_is_noted_rather_than_dropped(
    bench: Bench,
) -> None:
    """Rule 1: absence is an outcome, and a note matters as much as the absence.

    A row dropped in silence reads downstream as a machine with fewer cards --
    which places a unit on the wrong index and makes the next `compare` report
    a card that was never pulled.
    """
    bench(smi=SMI_AWKWARD)
    result = scan()
    assert any("GRID A100" in note for note in result.notes)


def test_a_mig_row_reporting_na_for_memory_is_not_silence(bench: Bench) -> None:
    """`[N/A]` memory is "not determined", never "no card here"."""
    bench(smi=SMI_MIG)
    result = scan()
    assert result.gpus == ()
    assert any("MIG 1g.5gb" in note for note in result.notes)
    assert not any("reported no device" in note for note in result.notes)


def test_a_clean_card_list_says_nothing_about_unreadable_rows(bench: Bench) -> None:
    """The note is evidence, so it must not fire on a scan with nothing to report."""
    result = scan()
    assert len(result.gpus) == 1
    assert not any("could not read" in note for note in result.notes)


def test_nvidia_smi_answering_with_nothing_still_says_so(bench: Bench) -> None:
    """No rows at all is a different fact from rows that could not be read."""
    bench(smi="\n")
    result = scan()
    assert result.gpus == ()
    assert any("reported no device" in note for note in result.notes)
