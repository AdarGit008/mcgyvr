"""Gate 7: teardown — the containers are gone and the rig reads as it started.

A hard lock wipes the BIOS profile: srv1 read PL1 95 W at 05:23 and 4095 W at
05:57, and a lock takes the ssh pipe with it, so the run whose end state is
unknown is exactly the one that ended silently
(``test_a_row_without_the_rigs_live_state_is_not_comparable``). A step
compares its own start and end readings and the comparison lives inside the
step; a step that dies before ``end_stamp`` compares nothing. The door owns
the trap (gate 7, ``07-teardown.py``): after the step, whatever its exit,
``docker ps`` filtered by the run's names must be empty, and a fresh reading
of the rig must equal the one gate 2 took before the step. A leftover
container is exit 1 naming it; a rig that moved is ``### RIGMOVED`` appended
to the artifact and exit 1 — the file must say so, because the rows in it
were produced under two machines.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def test_a_container_still_named_for_the_run_is_exit_1_and_named(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'"),
    )
    onedoor.docker_stub(onedoor.stubs_dir(root), leftover_flag=flag)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"{run_id}-lcps" in result.stderr, (
        f"the leftover container is not named on stderr: {result.stderr}"
    )
    assert any(line.startswith("ps") for line in onedoor.docker_log(root)), (
        "the door never asked docker ps"
    )


def test_a_rig_that_reads_differently_after_the_step_is_stamped_rigmoved(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'"),
    )
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", moved_flag=flag)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "pl1_uw" in result.stderr, result.stderr
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    lines = artifact.read_text(encoding="utf-8").splitlines()
    moved = [line for line in lines if line.startswith("### RIGMOVED")]
    assert moved, f"no ### RIGMOVED in the artifact:\n{artifact.read_text()}"
    assert lines.index(moved[0]) > lines.index(
        next(line for line in lines if line.startswith("### END"))
    ), "RIGMOVED must be appended after the step's own ### END"
