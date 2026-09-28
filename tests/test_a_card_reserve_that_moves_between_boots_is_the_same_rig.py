"""A card reserve that a reboot moves is still the declared rig.

``gpu_reserve_mib`` is the card's ``memory.reserved``. The driver carves it
at boot, and ``rig-snapshot.sh`` says as much at its ``nvidia`` reader: "the
reserve is GSP firmware and differs per boot". Gate 2 (``02-rig.py``) compares
every other key with ``tools/runs/hosts.json`` as a literal string; compared
the same way, a reboot that moves the reserve by a few MiB would tell every
door run that this is not the declared machine, and refuse it. So gate 2
admits a reserve within ``RESERVE_TOLERANCE_MIB`` of its declaration and
refuses one beyond it, naming the key and both values.

The rig here is invented — its name, its card and its numbers — so the test
holds the behaviour and pins no machine of the fleet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import onedoor
from tests._helpers import by_path
from tests.onedoor import Scenario

GATE_2 = by_path("gate_02_rig", onedoor.SERVING_SRC / "gate-scripts" / "02-rig.py")
#: How far gate 2 lets a reserve move from its declaration, from the gate itself.
ALLOWANCE = int(GATE_2.RESERVE_TOLERANCE_MIB)

HOST = "rig_a"
#: A made-up rig: no card, clock or reserve of any machine of the fleet.
RIG: dict[str, str] = {
    "cpu_max_mhz": "4000",
    "cpu_model": "Example_CPU_@_4.00GHz",
    "ram_mt_s": "3000",
    "pl1_uw": "65000000",
    "pl2_uw": "90000000",
    "gpu_name": "Example_GPU_8GB",
    "gpu_vram_mib": "8192",
    "gpu_cc": "8.0",
    "driver": "580.178.04",
    "gpu_reserve_mib": "250",
    "docker": "29.7.2",
}
DECLARED = int(RIG["gpu_reserve_mib"])
#: What the reader prints beyond the declared keys, idle, under this rig's name.
LIVE: dict[str, str] = {**onedoor.LIVE["srv1"], "hostname": HOST}


def _declare(root: Path) -> None:
    """The fixture's hosts.json declares only the invented rig, and its reader
    answers as that rig; the tree is pinned again, since hosts.json moved."""
    hosts = {"hosts": [HOST], HOST: {"rig": RIG, "read_on": onedoor.RIG_READ_ON}}
    (root / "tools" / "runs" / "hosts.json").write_text(
        json.dumps(hosts, indent=2) + "\n", encoding="utf-8"
    )
    onedoor.pin(root)


def _reads(root: Path, reserve: int) -> None:
    """The rig reads as declared except its reserve, which reads ``reserve``."""
    values = {
        "uptime_since": onedoor.UPTIME,
        **RIG,
        **LIVE,
        "gpu_reserve_mib": str(reserve),
    }
    (onedoor.stubs_dir(root) / "snapshot.txt").write_text(
        "".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8"
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    _declare(repo)
    return repo


@pytest.mark.parametrize(
    "reserve",
    [DECLARED, DECLARED - 1, DECLARED + ALLOWANCE, DECLARED - ALLOWANCE],
    ids=["as-declared", "one-below", "allowance-above", "allowance-below"],
)
def test_a_reserve_within_the_allowance_is_admitted_at_gate_2(
    root: Path, tmp_path: Path, reserve: int
) -> None:
    """A reboot moved the reserve by no more than the allowance, nothing else
    moved: the door opens and the step runs."""
    _reads(root, reserve)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh", host=HOST))
    assert "gpu_reserve_mib" not in result.stderr, result.stderr
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (tmp_path / "e").exists(), "the step never ran"


@pytest.mark.parametrize(
    "reserve",
    [DECLARED + ALLOWANCE + 1, DECLARED - ALLOWANCE - 1, DECLARED + 100],
    ids=["one-past-above", "one-past-below", "far"],
)
def test_a_reserve_beyond_the_allowance_is_refused_and_named(
    root: Path, tmp_path: Path, reserve: int
) -> None:
    """One MiB past the allowance is not a reboot's move: gate 2 refuses it by
    name, with both values, and nothing runs."""
    _reads(root, reserve)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh", host=HOST))
    assert result.returncode == 2, (result.stdout, result.stderr)
    for word in ("gate 2", "gpu_reserve_mib", str(DECLARED), str(reserve)):
        assert word in result.stderr, f"{word!r} is not in the refusal: {result.stderr}"
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists(), "the step ran after gate 2 refused"
