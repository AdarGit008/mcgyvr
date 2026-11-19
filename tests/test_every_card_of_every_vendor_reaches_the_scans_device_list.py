"""Every card of every vendor reaches the scan's device list.

The scan with --hardware lists each card the reading found (``devices``), whatever its
vendor: an NVIDIA card with its PCI device id and compute capability as its
tool prints them, an AMD card read by its tool or from sysfs, an Intel card
from sysfs with its memory unknown (sysfs gives none), a Windows display
adapter with the ids of its device id, a Mac's unified GPU. Each names the
source its entry came from and, where the system gives them, its PCI address
and on Linux its DRM card and render nodes. Its ``id`` places it among every
vendor's cards: two vendors' card 0 never share one. ``gpus``, which a fit is
sized on, stays as it was.

The machines are invented: a made-up sysfs tree and tool output, with the
vendors' public PCI ids (0x10de, 0x1002, 0x8086) and made-up device ids.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from tests.machine_shapes import device_id, host_scan_document, host_shape

MIB = 1024 * 1024
CSV = "--format=csv,noheader,nounits"


def _tools() -> Any:
    from mcgyvr.serving import rigscan

    return {
        "lscpu": {("lscpu",): "Model name:          Example CPU L8\n"},
        "nvidia-smi": {
            ("nvidia-smi", f"--query-gpu={rigscan.FIRST_QUERY}", CSV): (
                "0, 16376, 1000, 15376, Example Card N\n"
            ),
            ("nvidia-smi", f"--query-gpu={rigscan.SNAPSHOT_QUERY}", CSV): (
                "0, 00000000:01:00.0, 8.6, 1.2.3, 300\n"
            ),
            ("nvidia-smi", f"--query-gpu={rigscan.PCI_ID_QUERY}", CSV): (
                "0, 0x0A1B10DE\n"
            ),
        },
        "rocm-smi": {
            ("rocm-smi", *rigscan.SECOND_BUS_ARGS): json.dumps(
                {"card0": {"PCI Bus": "0000:03:00.0"}}
            ),
            ("rocm-smi", *rigscan.SECOND_ARGS): json.dumps(
                {
                    "card0": {
                        "Card series": "Example Card R",
                        "VRAM Total Memory (B)": str(24560 * MIB),
                        "VRAM Total Used Memory (B)": str(512 * MIB),
                    }
                }
            ),
        },
    }


def _scan(files: Mapping[str, str], installed: Sequence[str]) -> dict[str, Any]:
    """The whole scan of an invented Linux machine: these files under its root,
    these tools installed, each answering only the questions above."""
    from mcgyvr.serving import rigscan

    tools = {name: _tools()[name] for name in installed}

    def run(argv: Sequence[str], *, bound: float = 0.0) -> tuple[str | None, None]:
        if argv[0] not in tools:
            return None, None
        if tuple(argv) not in tools[argv[0]]:
            raise ValueError(f"the invented machine is not asked {argv}")
        return tools[argv[0]][tuple(argv)], None

    def which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in tools else None

    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as w:
        for path, text in {
            "/etc/machine-id": "0123456789abcdef0123456789abcde9\n",
            "/proc/sys/kernel/hostname": "box-9.example\n",
            **files,
        }.items():
            target = Path(root + path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        with (
            mock.patch.object(rigscan, "_run", run),
            mock.patch("mcgyvr.hostos.which_absolute", which),
            mock.patch.object(
                rigscan, "measure_bandwidth", lambda spare_mib=None: None
            ),
            mock.patch("platform.machine", lambda: "x86_64"),
        ):
            return rigscan.scan(w, root=root, system="linux", wider=True)


def _sysfs(
    number: int, bus: str, vendor: str, device: str, **files: str
) -> dict[str, str]:
    """One PCI card in sysfs: its card<N> and renderD<128+N> nodes, both of the
    device at that address, and the device under /sys/bus/pci/devices (where a
    node's `device` link points)."""
    where = f"/sys/class/drm/card{number}/device"
    event = f"DRIVER=example\nPCI_ID={vendor[2:]}:{device[2:]}\nPCI_SLOT_NAME={bus}\n"
    found = {
        f"{where}/vendor": f"{vendor}\n",
        f"{where}/device": f"{device}\n",
        f"/sys/bus/pci/devices/{bus}/vendor": f"{vendor}\n",
        f"/sys/bus/pci/devices/{bus}/device": f"{device}\n",
        f"{where}/uevent": event,
        f"/sys/class/drm/renderD{128 + number}/device/uevent": event,
    }
    found.update({f"{where}/{name}": f"{text}\n" for name, text in files.items()})
    return found


INTEL = _sysfs(1, "0000:02:00.0", "0x8086", "0x0b0b", product_name="Example Card I")
#: The card rocm-smi reads as its card0, shown by sysfs as card3.
ROCM = _sysfs(3, "0000:03:00.0", "0x1002", "0x0d0d")
AMD = _sysfs(
    2,
    "0000:04:00.0",
    "0x1002",
    "0x0c0c",
    product_name="Example Card S",
    mem_info_vram_total=str(16368 * MIB),
    mem_info_vram_used=str(256 * MIB),
)


def _devices(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f"{d['vendor']}.{d['index']}": d for d in document["devices"]}


def test_an_amd_card_its_tool_reads_and_an_intel_card_in_sysfs_reach_the_list() -> None:
    document = _scan({**INTEL, **ROCM}, ["lscpu", "rocm-smi"])
    devices = _devices(document)
    assert set(devices) == {"amd.0", "intel.1"}
    amd, intel = devices["amd.0"], devices["intel.1"]
    assert amd["name"] == "Example Card R"
    assert (amd["total_mib"], amd["used_mib"]) == (24560, 512)
    assert amd["read_from"] == "rocm-smi" and amd["backend"] == "rocm"
    # rocm-smi's card0 is found in sysfs by its PCI address, not by its number.
    assert amd["pci_bus"] == "0000:03:00.0" and amd["id"] == "pci:0000:03:00.0"
    assert (amd["drm_card"], amd["drm_render"]) == ("card3", "renderD131")
    assert (amd["pci_vendor"], amd["pci_device"]) == ("0x1002", "0x0d0d")
    assert intel["name"] == "Example Card I"
    assert (intel["pci_vendor"], intel["pci_device"]) == ("0x8086", "0x0b0b")
    assert intel["total_mib"] is None and intel["read_from"] == "sysfs"
    assert (intel["pci_bus"], intel["drm_card"], intel["drm_render"]) == (
        "0000:02:00.0",
        "card1",
        "renderD129",
    )
    assert intel["compute_cap"] is None
    assert document["gpus"] == []


def test_two_identical_amd_cards_are_each_placed_by_their_own_address() -> None:
    from mcgyvr.serving import rigscan

    card = {
        "Card series": "Example Card R",
        "VRAM Total Memory (B)": str(24560 * MIB),
        "VRAM Total Used Memory (B)": str(512 * MIB),
    }
    tools = _tools()
    tools["rocm-smi"] = {
        ("rocm-smi", *rigscan.SECOND_BUS_ARGS): json.dumps(
            # rocm-smi's own numbers, in the other order from sysfs's.
            {"card0": {"PCI Bus": "0000:06:00.0"}, "card1": {"PCI Bus": "0000:05:00.0"}}
        ),
        ("rocm-smi", *rigscan.SECOND_ARGS): json.dumps({"card0": card, "card1": card}),
    }
    files = {
        **_sysfs(1, "0000:05:00.0", "0x1002", "0x0d0d"),
        **_sysfs(2, "0000:06:00.0", "0x1002", "0x0d0d"),
    }
    with mock.patch(f"{__name__}._tools", lambda: tools):
        devices = _devices(_scan(files, ["lscpu", "rocm-smi"]))
    first, second = devices["amd.0"], devices["amd.1"]
    assert (first["id"], first["drm_card"], first["drm_render"]) == (
        "pci:0000:06:00.0",
        "card2",
        "renderD130",
    )
    assert (second["id"], second["drm_card"], second["drm_render"]) == (
        "pci:0000:05:00.0",
        "card1",
        "renderD129",
    )
    assert first["pci_device"] == second["pci_device"] == "0x0d0d"


def test_an_amd_card_whose_address_rocm_smi_does_not_print_keeps_it_unknown() -> None:
    from mcgyvr.serving import rigscan

    tools = _tools()
    tools["rocm-smi"][("rocm-smi", *rigscan.SECOND_BUS_ARGS)] = '{"card0": {}}'
    with mock.patch(f"{__name__}._tools", lambda: tools):
        amd = _devices(_scan(ROCM, ["lscpu", "rocm-smi"]))["amd.0"]
    assert amd["pci_bus"] is None and amd["drm_card"] is None
    assert amd["pci_device"] is None and amd["id"] == "amd:0"


def test_an_amd_card_no_tool_reads_reaches_the_list_from_sysfs() -> None:
    devices = _devices(_scan({**INTEL, **AMD}, ["lscpu"]))
    amd = devices["amd.2"]
    assert (amd["pci_vendor"], amd["pci_device"]) == ("0x1002", "0x0c0c")
    assert (amd["total_mib"], amd["used_mib"], amd["free_mib"]) == (
        16368,
        256,
        16112,
    )
    assert amd["name"] == "Example Card S" and amd["read_from"] == "sysfs"
    assert (amd["drm_card"], amd["drm_render"]) == ("card2", "renderD130")
    assert devices["intel.1"]["read_from"] == "sysfs"


def test_two_vendors_card_zero_never_share_an_id() -> None:
    files = {**_sysfs(0, "0000:01:00.0", "0x10de", "0x0a1b"), **ROCM}
    devices = _devices(_scan(files, ["lscpu", "nvidia-smi", "rocm-smi"]))
    assert devices["nvidia.0"]["id"] == "pci:0000:01:00.0"
    assert devices["amd.0"]["id"] == "pci:0000:03:00.0"
    from mcgyvr.serving import rigscan

    tools = _tools()
    tools["rocm-smi"][("rocm-smi", *rigscan.SECOND_BUS_ARGS)] = "{}"
    tools["nvidia-smi"][
        ("nvidia-smi", f"--query-gpu={rigscan.SNAPSHOT_QUERY}", CSV)
    ] = "0, [N/A], 8.6, 1.2.3, 300\n"
    with mock.patch(f"{__name__}._tools", lambda: tools):
        unplaced = _devices(_scan({}, ["lscpu", "nvidia-smi", "rocm-smi"]))
    assert {d["id"] for d in unplaced.values()} == {"nvidia:0", "amd:0"}


def test_an_nvidia_card_carries_its_device_id_and_compute_capability() -> None:
    from mcgyvr.serving import rigscan

    files = {**INTEL, **_sysfs(0, "0000:01:00.0", "0x10de", "0x0a1b")}
    tools = _tools()
    # sysfs gives the device id at the card's address: nvidia-smi is not asked
    # again for it (the invented tool refuses a question it was not given).
    del tools["nvidia-smi"][("nvidia-smi", f"--query-gpu={rigscan.PCI_ID_QUERY}", CSV)]
    with mock.patch(f"{__name__}._tools", lambda: tools):
        document = _scan(files, ["lscpu", "nvidia-smi"])
    devices = _devices(document)
    assert set(devices) == {"nvidia.0", "intel.1"}
    nvidia = devices["nvidia.0"]
    assert (nvidia["pci_vendor"], nvidia["pci_device"]) == ("0x10de", "0x0a1b")
    # nvidia-smi prints an 8-digit domain; the address is kept as sysfs names it.
    assert nvidia["pci_bus"] == "0000:01:00.0"
    assert (nvidia["drm_card"], nvidia["drm_render"]) == ("card0", "renderD128")
    assert nvidia["compute_cap"] == "8.6"
    assert nvidia["read_from"] == "nvidia-smi"
    assert nvidia["total_mib"] == 16376
    assert [gpu["index"] for gpu in document["gpus"]] == [0]


@pytest.mark.parametrize(
    "printed",
    ["0, 0x0A1B1002\n", "0, [N/A]\n", "0, 0x10DE10DE\n", "zero, 0x0A1B10DE\n", ""],
    ids=["no-nvidia-half", "not-given", "no-device-half", "no-index", "no-line"],
)
def test_an_nvidia_device_id_the_tool_does_not_give_plainly_is_unknown(
    printed: str,
) -> None:
    from mcgyvr.serving import rigscan

    tools = _tools()
    tools["nvidia-smi"][("nvidia-smi", f"--query-gpu={rigscan.PCI_ID_QUERY}", CSV)] = (
        printed
    )
    with mock.patch(f"{__name__}._tools", lambda: tools):
        devices = _devices(_scan({}, ["lscpu", "nvidia-smi"]))
    assert devices["nvidia.0"]["pci_device"] is None
    assert devices["nvidia.0"]["pci_vendor"] == "0x10de"


def test_a_windows_adapter_and_a_card_its_tool_reads_reach_the_list() -> None:
    other = _devices(host_scan_document(host_shape("windows-other-gpu"), wider=True))
    (adapter,) = other.values()
    assert adapter["read_from"] == "Win32_VideoController"
    assert adapter["pci_vendor"] == "0x1002"
    assert adapter["pci_device"] == "0x" + device_id("Example Card L")
    assert adapter["total_mib"] is None
    # Windows' display adapter list gives no PCI address and no DRM node.
    assert adapter["pci_bus"] is None and adapter["drm_render"] is None
    assert adapter["id"] == "amd:0"
    read = _devices(host_scan_document(host_shape("windows-one-card"), wider=True))
    assert read["nvidia.0"]["read_from"] == "nvidia-smi"
    assert read["nvidia.0"]["pci_device"] == "0x" + device_id("Example Card A")


def test_a_macs_unified_gpu_reaches_the_list_without_pci_ids() -> None:
    document = host_scan_document(host_shape("unified-laptop"), wider=True)
    (gpu,) = document["devices"]
    assert (gpu["vendor"], gpu["kind"], gpu["figure"]) == (
        "apple",
        "unified",
        "estimate",
    )
    assert gpu["pci_vendor"] is None and gpu["pci_device"] is None
    assert gpu["pci_bus"] is None and gpu["id"] == "apple:0"
    assert gpu["read_from"] == "sysctl"


@pytest.mark.parametrize(
    "label", ["linux-one-card", "windows-other-gpu", "unified-laptop"]
)
def test_the_scans_gpus_are_the_ones_it_held_before(label: str) -> None:
    from mcgyvr.scan import Scan

    document = host_scan_document(host_shape(label), wider=True)
    older = {k: v for k, v in document.items() if k not in ("devices", "cpu_detail")}
    whole, before = (Scan.from_json(json.dumps(d)) for d in (document, older))
    assert whole.gpus == before.gpus
    assert whole.devices is not None
    assert len(whole.devices) == len(document["cards"])
