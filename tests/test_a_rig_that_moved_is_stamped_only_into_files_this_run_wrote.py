"""``### RIGMOVED`` lands in the files this invocation wrote, and says which run.

Gate 7 (``07-teardown.py``) stamps a rig that moved into "every declared
artifact that exists". With ``RUN_APPENDS`` in the declaration that reached a
file this invocation never opened — ``4-kernel-arms.sh --step serve`` declared
step 6's ``srv1-moe-slots.tsv`` and, under a moved rig, wrote a stamp into it
claiming step 6's rows were produced under two machine states, with nothing
in the line saying which run wrote it.

So an appended file is stamped only when this run appended to it, and every
``### RIGMOVED`` carries ``run_id=<RUN_ID>`` as its first field.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario
from tests.test_an_appending_step_may_only_append_to_a_file_the_door_produced import (
    appender,
)

OTHER = Scenario("alpha", "1-other.sh")
PROBE = Scenario("alpha", "2-probe.sh")


def _rigmoved(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("### RIGMOVED")
    ]


def test_an_appended_file_this_run_never_touched_is_not_stamped(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root, "alpha", "1-other.sh", onedoor.probe_step(tmp_path / "e-other")
    )
    flag = tmp_path / "step-ran"
    body = (
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'")
        .replace(
            "# RUN_ARTIFACTS: probe.tsv\n",
            "# RUN_ARTIFACTS: mine.tsv\n# RUN_APPENDS: probe.tsv\n",
        )
        .replace('out="${RUN_OUT_DIR:?}/probe.tsv"', 'out="${RUN_OUT_DIR:?}/mine.tsv"')
    )
    onedoor.add_step(root, "alpha", "2-probe.sh", body)
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", moved_flag=flag)
    first = onedoor.door(root, OTHER)
    assert first.returncode == 0, (first.stdout, first.stderr)
    untouched = onedoor.envelope(root, "alpha") / "probe.tsv"
    before = untouched.read_text(encoding="utf-8")

    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "pl1_uw" in result.stderr, result.stderr
    assert untouched.read_text(encoding="utf-8") == before, (
        "a stamp landed in a file this run never wrote"
    )
    mine = onedoor.envelope(root, "alpha") / "mine.tsv"
    stamps = _rigmoved(mine)
    assert stamps, mine.read_text(encoding="utf-8")
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert stamps[0].split()[2] == f"run_id={run_id}", stamps[0]


def test_an_appended_file_this_run_wrote_is_stamped_with_the_run(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root, "alpha", "1-other.sh", onedoor.probe_step(tmp_path / "e-other")
    )
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root, "alpha", "2-probe.sh", appender(tmp_path / "e") + f"touch '{flag}'\n"
    )
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", moved_flag=flag)
    first = onedoor.door(root, OTHER)
    assert first.returncode == 0, (first.stdout, first.stderr)

    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    stamps = _rigmoved(artifact)
    assert len(stamps) == 1, artifact.read_text(encoding="utf-8")
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert stamps[0].split()[2] == f"run_id={run_id}", stamps[0]
    lines = artifact.read_text(encoding="utf-8").splitlines()
    assert lines.index(stamps[0]) > max(
        i for i, line in enumerate(lines) if line.startswith("### END")
    )
