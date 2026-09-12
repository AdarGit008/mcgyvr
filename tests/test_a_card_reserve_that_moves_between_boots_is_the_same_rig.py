"""A card reserve that a reboot moves is still the declared rig.

``gpu_reserve_mib`` is the card's ``memory.reserved``. The driver carves it
at boot, and ``rig-snapshot.sh`` says as much at its ``nvidia`` reader: "the
reserve is GSP firmware and differs per boot". Gate 2 (``02-rig.py``,
``main``) nonetheless compares it with ``tools/runs/hosts.json`` the way it
compares the hardware, as a literal string. So a reboot that moves the reserve
by a few MiB tells every door run that this is not the declared machine, and
refuses it.

Measured on srv1, with the same GTX 1660 SUPER, the same driver 580.173.02 and
every other declared key unchanged:

- 399 MiB on the boot of about 05:50Z, 2026-08-31
  (``records/evidence/2026-08-31-inventory/srv1-scan.txt``).
- 401 MiB on the boot of 2026-09-01T08:11:08Z, the value ``hosts.json``
  declared from 2026-09-03.
- 399 MiB on the boot of 2026-09-11T06:34:36Z, read idle by
  ``records/measurements/fleet-identity-2026-09-11/reserve.py`` on branch
  ``red/fleet-identity-measurements``. Gate 2 then refused srv1:
  ``gpu_reserve_mib: declared '401', reads '399'``.

RED. The admission test fails today because gate 2 refuses the measured
reboot, whichever of the two readings ``hosts.json`` declares. The refusal
test passes today and must keep passing: a reserve far from its
declaration is still refused, and still named. How wide the bound is belongs
to the change that makes this green. Neither test pins a number between the
two readings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

#: srv1's reserve on two boots with every other declared key equal: the boot of
#: 2026-09-01T08:11:08Z and the boot of 2026-09-11T06:34:36Z.
MEASURED = ("401", "399")


def _declared() -> str:
    document = json.loads(onedoor.HOSTS_JSON.read_text(encoding="utf-8"))
    value: str = document["srv1"]["rig"]["gpu_reserve_mib"]
    return value


DECLARED = _declared()
#: Whichever measured boot is not the declared one: what a reboot gave srv1.
AFTER_A_REBOOT = next(v for v in MEASURED if v != DECLARED)
NOT_A_REBOOT = str(int(DECLARED) + 100)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_srv1_is_declared_at_one_of_its_measured_reserves() -> None:
    """The fixture's rig reads what hosts.json declares, and that is one of the two
    measured boots, so the other is a reading a reboot really gave."""
    assert DECLARED in MEASURED
    assert onedoor.RIG["srv1"]["gpu_reserve_mib"] == DECLARED


def test_a_reserve_a_reboot_moved_is_admitted_at_gate_2(
    root: Path, tmp_path: Path
) -> None:
    """srv1 read 401 and 399 MiB on two boots with nothing else moved. Whichever
    one is declared, the other opens the door and the step runs."""
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", gpu_reserve_mib=AFTER_A_REBOOT)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert "gpu_reserve_mib" not in result.stderr, result.stderr
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (tmp_path / "e").exists(), "the step never ran"


def test_a_reserve_far_from_its_declaration_is_refused_and_named(
    root: Path, tmp_path: Path
) -> None:
    """100 MiB is not what a reboot moves the reserve by, and nothing on record
    moved it by more than 3. Gate 2 refuses it by name and nothing runs."""
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", gpu_reserve_mib=NOT_A_REBOOT)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    for word in ("gate 2", "gpu_reserve_mib", DECLARED, NOT_A_REBOOT):
        assert word in result.stderr, f"{word!r} is not in the refusal: {result.stderr}"
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists(), "the step ran after gate 2 refused"
