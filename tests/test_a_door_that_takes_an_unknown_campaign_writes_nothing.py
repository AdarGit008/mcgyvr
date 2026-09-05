"""The door refuses before it acts, and leaves ``records/`` as it found it.

``python -m mcgyvr.serving.run`` is the one access point to the rigs. Asked
for a campaign that has no directory under ``tools/runs/campaigns/``, a host
``hosts.json`` does not declare, a ``--step`` that is not a file, or no
``--host`` at all, it exits 2 naming what was asked and writes nothing under
``records/``. And ``--help`` shows no ``--skip``, ``--force`` or ``--no-``
anything: there is no way past a gate, so the usage cannot show one.

Where each refusal lands is the door's, and it is not uniform. An absent
``--host`` and a ``--step`` that is not a file stop in argument parsing; an
undeclared host stops at gate 2 before the rig is read; an unknown campaign
stops at gate 5, where the envelope would have been made and ``RUN_ID``
minted — so it costs a rig read (gates 2-4 have run) and no artifact. The
refusal names the campaigns that do exist, so an operator learns the
vocabulary from the door and not from a document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

CAMPAIGNS = ("alpha", "beta")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    for name in CAMPAIGNS:
        onedoor.add_step(repo, name, "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_the_door_is_the_python_module() -> None:
    """The archived script's absence is ``test_one_door.py``'s to assert."""
    assert (onedoor.REPO / onedoor.DOOR_REL).is_file(), "src/mcgyvr/serving/run.py"


def test_an_unknown_campaign_is_refused_at_gate_5_naming_the_known_ones(
    root: Path, tmp_path: Path
) -> None:
    # A real step file, so the refusal is the campaign's and not the step's.
    result = onedoor.door(
        root, Scenario("gamma", "tools/runs/campaigns/alpha/1-probe.sh")
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "no campaign 'gamma' under tools/runs/campaigns/" in result.stderr, (
        result.stderr
    )
    for name in CAMPAIGNS:
        assert name in result.stderr, f"the refusal does not list {name!r}"
    assert onedoor.written_under_records(root) == [], "the door wrote under records/"
    assert not (tmp_path / "e").exists(), "the step ran under an undeclared campaign"


def test_an_undeclared_host_is_refused_at_gate_2_before_the_rig_is_read(
    root: Path, tmp_path: Path
) -> None:
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh", host="srv9"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "srv9" in result.stderr, result.stderr
    assert "hosts.json" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert onedoor.ssh_log(root) == [], "a rig nobody declared was reached"
    assert not (tmp_path / "e").exists()


def test_without_a_host_the_door_does_not_start(root: Path, tmp_path: Path) -> None:
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh", host=""))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "--host" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert onedoor.ssh_log(root) == [] and onedoor.docker_log(root) == []
    assert not (tmp_path / "e").exists()


def test_a_step_that_is_not_a_file_is_refused_before_any_gate(
    root: Path, tmp_path: Path
) -> None:
    result = onedoor.door(root, Scenario("alpha", "9-nope.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "9-nope.sh" in result.stderr and "is not a file" in result.stderr, (
        result.stderr
    )
    assert onedoor.written_under_records(root) == []
    assert onedoor.ssh_log(root) == [] and onedoor.docker_log(root) == []
    assert not (tmp_path / "e").exists()


def test_help_offers_no_way_past_a_gate(root: Path) -> None:
    """The same is pinned against the installed door by
    ``tests/test_serving_door_cli.py::test_help_offers_no_way_past_a_gate``;
    here it is the fixture's copy, the one every test in this suite drives."""
    result = onedoor.door_help(root)
    assert result.returncode == 0, result.stderr
    for hole in ("--skip", "--force", "--no-"):
        assert hole not in result.stdout, f"--help names {hole}"
    for flag in ("--host", "--campaign", "--model", "--step"):
        assert flag in result.stdout, f"--help does not show {flag}"
    assert onedoor.written_under_records(root) == []
