"""One scan, two transports.

A rig's free VRAM and its memory bandwidth are not visible from the laptop, so
"measured, not declared" forces the scan to run *on* the machine it describes.
Access is the only difference between local and remote: same code, same output
shape, different transport. No access is a smaller answer, never a wrong one.
"""

from __future__ import annotations

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.scan import Reach, Scan, machine_id, scan_all, scan_over

SCAN_JSON = """
{"machine": {"id": "%s", "host": "%s", "kernel": "6.8.0"},
 "gpus": [{"index": 0, "name": "RTX 3060", "vram": {"total_mib": 12288, "used_mib": 12, "free_mib": 12276}}],
 "memory": {"total_gb": 47.0, "available_gb": 42.9},
 "cpu": {"cores": 10, "threads": 20},
 "bandwidth": {"measured_gbps": 41.2, "how": "copy loop"},
 "disk": {"path": "/models", "free_gb": 512.0},
 "notes": [], "facts": [{"field": "memory.total_gb", "how": "/proc/meminfo"}]}
"""


class RecordedSsh:
    def __init__(self, reachable: tuple[str, ...]) -> None:
        self.reachable = reachable
        self.commands: list[tuple[str, str]] = []

    def __call__(self, host: str, command: str) -> str:
        self.commands.append((host, command))
        if host not in self.reachable:
            raise scan_module.Unreachable(host)
        return SCAN_JSON % (f"id-{host}", host)


@pytest.fixture
def ssh(monkeypatch: pytest.MonkeyPatch):
    def install(*reachable: str) -> RecordedSsh:
        recorder = RecordedSsh(reachable)
        monkeypatch.setattr(scan_module, "_ssh", recorder)
        return recorder

    return install


@pytest.fixture
def local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scan_module,
        "scan",
        lambda **kwargs: Scan.from_json(SCAN_JSON % ("id-localhost", "localhost")),
    )


def test_both_transports_return_the_same_shape(local, ssh) -> None:
    ssh("desktop-1")
    assert type(scan_over(Reach.local())) is type(scan_over(Reach.ssh("desktop-1")))


def test_a_remote_scan_runs_the_scan_on_the_remote_host(local, ssh) -> None:
    recorder = ssh("desktop-1")
    scan_over(Reach.ssh("desktop-1"))
    assert recorder.commands == [("desktop-1", "mcgyvr scan --json")]


def test_a_local_reach_opens_no_connection(local, ssh) -> None:
    recorder = ssh("desktop-1")
    scan_over(Reach.local())
    assert recorder.commands == []


def test_no_access_yields_the_local_machine_only(local, ssh) -> None:
    ssh()
    result = scan_all(hosts=("desktop-1",))
    assert [each.machine.host for each in result.scans] == ["localhost"]


def test_an_unreachable_host_is_reported_not_raised(local, ssh) -> None:
    ssh()
    assert scan_all(hosts=("desktop-1",)).unreachable == ("desktop-1",)


def test_two_desktops_produce_two_machine_ids(local, ssh) -> None:
    ssh("desktop-1", "desktop-2")
    result = scan_all(hosts=("desktop-1", "desktop-2"))
    assert len({machine_id(each) for each in result.scans}) == 3


def test_a_reachable_host_survives_an_unreachable_neighbour(local, ssh) -> None:
    ssh("desktop-1")
    result = scan_all(hosts=("desktop-1", "desktop-2"))
    assert result.unreachable == ("desktop-2",)
    assert "desktop-1" in {each.machine.host for each in result.scans}


def test_a_remote_scan_never_falls_back_to_a_model_listing(local, ssh) -> None:
    ssh("desktop-1")
    result = scan_over(Reach.ssh("desktop-1"))
    assert result.bandwidth is not None
    assert all(fact.how != "model listing" for fact in result.facts)
