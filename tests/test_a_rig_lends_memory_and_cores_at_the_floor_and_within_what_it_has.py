"""A rig lends memory and cores at the hub's floor and within what it has.

The lending settings name the host memory (``ram_mb``) and the cores
(``cpu_cores``) a rig lends, 0 for none, and keep them across a save and a
load. An amount under its kind's floor (:data:`mcgyvr.hubwire.LEND_FLOOR_MB`,
:data:`mcgyvr.hubwire.LEND_FLOOR_CORES`) is refused with a message naming the
floor, wherever it comes from. ``mcgyvr rig share`` also holds what it is told
to lend to the machine as read now: memory to what is available less a
headroom, cores to all but one, and a named card to its kind's floor; and
memory of a DDR generation the hub does not count (one Windows reads under
:data:`mcgyvr.hubwire.RAM_DDR_MIN`) is refused naming the one it counts, while
memory whose generation is unread (Linux, where SMBIOS needs root) lends by
its size alone. It says back what the rig lends.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from tests import rig_pool_fakes as fakes
from tests.machine_shapes import Card, HostShape, host_reading

RAM_FLOOR = hubwire.LEND_FLOOR_MB[hubwire.RESOURCE_RAM]
GPU_FLOOR = hubwire.LEND_FLOOR_MB[hubwire.RESOURCE_GPU]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("MCGYVR_HOME", str(home))
    return home


MACHINE = HostShape(
    label="linux-lender",
    system="linux",
    machine_id="0123456789abcdef0123456789abcdf3",
    memory_mib=RAM_FLOOR * 4,
    available_mib=RAM_FLOOR * 2 + RAM_FLOOR // 2,
    cpu_model="Example CPU L8",
    cores=4,
    threads=8,
    version="6.1-example",
    cards=(
        Card(index=0, name="Example Card S", vendor="vendor-a", total_mib=1024),
        Card(index=1, name="Example Card T", vendor="vendor-a", total_mib=16384),
    ),
)


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """``rig share`` reads this invented machine, never the one the suite runs on."""
    from mcgyvr.rig import hardware

    reading = host_reading(MACHINE)
    monkeypatch.setattr(hardware, "read_machine", lambda: reading)


def _share(*arguments: str) -> int:
    from mcgyvr import cli

    return cli.main(["rig", "share", *arguments])


def test_memory_and_cores_lent_are_kept_and_read_back(_home: Path) -> None:
    from mcgyvr.rig import sharing

    assert (sharing.Sharing().ram_mb, sharing.Sharing().cpu_cores) == (0, 0)
    kept = fakes.sharing(None, ram_mb=RAM_FLOOR * 2, cpu_cores=hubwire.LEND_FLOOR_CORES)
    sharing.save(kept)
    assert sharing.load() == kept
    written = json.loads((_home / sharing.SHARING_FILE).read_text())
    assert (written["ram_mb"], written["cpu_cores"]) == (
        RAM_FLOOR * 2,
        hubwire.LEND_FLOOR_CORES,
    )


@pytest.mark.parametrize(
    ("data", "field", "floor"),
    [
        ({"ram_mb": RAM_FLOOR - 1}, "ram_mb", f"{RAM_FLOOR} MiB"),
        ({"cpu_cores": hubwire.LEND_FLOOR_CORES - 1}, "cpu_cores", "cores"),
        ({"ram_mb": -1}, "ram_mb", None),
        ({"ram_mb": "8G"}, "ram_mb", None),
        ({"cpu_cores": hubwire.MAX_RESOURCE_CORES + 1}, "cpu_cores", None),
    ],
)
def test_an_amount_the_hub_would_not_count_is_refused_by_its_field(
    _home: Path, data: dict[str, Any], field: str, floor: str | None
) -> None:
    from mcgyvr.rig import sharing

    _home.mkdir(parents=True)
    (_home / sharing.SHARING_FILE).write_text(json.dumps(data))
    with pytest.raises(sharing.SharingError) as refused:
        sharing.load()
    assert f": {field}:" in str(refused.value)
    if floor is not None:
        assert floor in str(refused.value) and "floor" in str(refused.value)


@pytest.mark.usefixtures("machine")
def test_share_lends_memory_and_cores_and_says_them_back(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.rig import sharing

    assert _share("--ram-mb", str(RAM_FLOOR * 2), "--cpu-cores", "4") == 0
    kept = sharing.load()
    assert (kept.ram_mb, kept.cpu_cores) == (RAM_FLOOR * 2, 4)
    said = capsys.readouterr().out
    assert f"lent ram: {RAM_FLOOR * 2} MiB" in said and "lent cpu: 4 cores" in said
    assert _share("--ram-mb", "0", "--cpu-cores", "0") == 0
    assert (sharing.load().ram_mb, sharing.load().cpu_cores) == (0, 0)
    assert "lent ram: none" in capsys.readouterr().out


@pytest.mark.usefixtures("machine")
@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        (("--ram-mb", str(RAM_FLOOR - 1)), f"{RAM_FLOOR} MiB"),
        (("--cpu-cores", "1"), f"{hubwire.LEND_FLOOR_CORES} cores"),
        (("--ram-mb", str(RAM_FLOOR * 2 + RAM_FLOOR // 2)), "available"),
        (("--cpu-cores", "8"), "7"),
        (("--cards", "0"), f"{GPU_FLOOR} MiB"),
    ],
)
def test_share_refuses_a_lend_under_the_floor_or_past_what_the_machine_has(
    arguments: tuple[str, ...], said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import sharing

    assert _share(*arguments) != 0
    err = capsys.readouterr().err
    assert said in err, err
    assert sharing.load() == sharing.Sharing()


@pytest.mark.usefixtures("machine")
def test_share_lends_a_card_at_its_floor(capsys: pytest.CaptureFixture[str]) -> None:
    from mcgyvr.rig import sharing

    assert _share("--cards", "1") == 0
    assert sharing.load().cards == (1,)


def test_share_will_not_lend_memory_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import hardware, sharing

    def unread() -> Any:
        raise OSError("no reading here")

    monkeypatch.setattr(hardware, "read_machine", unread)
    assert _share("--ram-mb", str(RAM_FLOOR)) != 0
    assert "could not be read" in capsys.readouterr().err
    assert sharing.load() == sharing.Sharing()


# --- the RAM's generation ----------------------------------------------------------


def _windows(label: str, ddr: int | None, memory_mib: int) -> HostShape:
    return HostShape(
        label=label,
        system="windows",
        machine_id="aaaa0000-bbbb-cccc-dddd-eeeeffff00d0",
        memory_mib=memory_mib,
        available_mib=memory_mib - RAM_FLOOR // 4,
        cpu_model="Example CPU W8",
        cores=4,
        threads=8,
        version="0.0.9-example",
        card_tool="none",
        ddr=ddr,
    )


#: Windows reads each module's DDR generation; Linux does not (SMBIOS needs root).
CURRENT = _windows("windows-current-ram", hubwire.RAM_DDR_MIN, RAM_FLOOR * 2)
OLDER = _windows("windows-older-ram", hubwire.RAM_DDR_MIN - 1, RAM_FLOOR * 4)


def _reads(monkeypatch: pytest.MonkeyPatch, machine: HostShape) -> None:
    from mcgyvr.rig import hardware

    reading = host_reading(machine)
    monkeypatch.setattr(hardware, "read_machine", lambda: reading)


def test_the_reader_names_the_ram_generation_where_the_system_tells_it() -> None:
    def ram(machine: HostShape) -> dict[str, Any]:
        found = host_reading(machine)["resources"]
        resource: dict[str, Any] = next(r for r in found if r["kind"] == "ram")
        return resource

    assert ram(CURRENT)["ddr"] == hubwire.RAM_DDR_MIN
    assert ram(OLDER)["ddr"] == hubwire.RAM_DDR_MIN - 1
    assert ram(MACHINE)["ddr"] is None  # Linux: unread, so counted by size alone
    unknown = _windows("windows-unknown-ram", None, RAM_FLOOR * 2)
    assert ram(unknown)["ddr"] is None
    for resource in host_reading(CURRENT)["resources"]:
        assert (resource["ddr"] is None) is (resource["kind"] != "ram")


def test_ram_of_the_current_generation_lends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.rig import sharing

    _reads(monkeypatch, CURRENT)
    assert _share("--ram-mb", str(RAM_FLOOR)) == 0
    assert sharing.load().ram_mb == RAM_FLOOR


def test_ram_of_an_older_generation_is_refused_naming_the_one_counted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import sharing

    _reads(monkeypatch, OLDER)
    assert _share("--ram-mb", str(RAM_FLOOR)) != 0
    err = capsys.readouterr().err
    assert f"DDR{hubwire.RAM_DDR_MIN}" in err and f"DDR{hubwire.RAM_DDR_MIN - 1}" in err
    assert sharing.load() == sharing.Sharing()


@pytest.mark.usefixtures("machine")
def test_ram_of_an_unread_generation_lends_by_its_size_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.rig import sharing

    assert _share("--ram-mb", str(RAM_FLOOR)) == 0
    assert sharing.load().ram_mb == RAM_FLOOR
    assert _share("--ram-mb", str(RAM_FLOOR * 3 // 4)) != 0
    assert f"{RAM_FLOOR} MiB" in capsys.readouterr().err
    assert sharing.load().ram_mb == RAM_FLOOR


def test_ram_of_an_older_generation_is_never_advertised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import hardware, sharing

    monkeypatch.setattr(
        sharing, "SESSION_SYSTEMS", sharing.SESSION_SYSTEMS | {"windows"}
    )
    for machine, lent in ((CURRENT, True), (OLDER, False)):
        reading = host_reading(machine)

        def reader(reading: dict[str, Any] = reading) -> dict[str, Any]:
            return reading

        report = hardware.read(reader=reader)
        share = fakes.sharing(tmp_path, cards=(), ram_mb=RAM_FLOOR)
        kinds = [r.kind for r in share.lendable(report).lent]
        assert (hubwire.RESOURCE_RAM in kinds) is lent


@pytest.mark.parametrize(
    ("types", "ddr"),
    [
        (["24", "24"], 3),  # DDR3
        (["26"], 4),  # DDR4
        (["34", "34"], 5),  # DDR5
        (["29"], 3),  # LPDDR3, a laptop's
        (["30"], 4),  # LPDDR4
        (["35"], 5),  # LPDDR5
        (["34", "26"], 4),  # mixed: the lowest generation
        (["0", "26"], 4),  # an unknown module beside a read one
        (["0"], None),  # unknown is unread, never 0
        (["1"], None),  # "Other"
        ([], None),
    ],
)
def test_a_modules_smbios_type_names_its_generation_or_none(
    types: list[str], ddr: int | None
) -> None:
    from mcgyvr.serving import rigscan

    class Windows:
        system = "windows"

        def cim(self) -> tuple[dict[str, Any], str]:
            return {"memory": [{"capacity": "1", "type": t} for t in types]}, ""

    assert rigscan._ddr(Windows()) == ddr  # type: ignore[arg-type]
