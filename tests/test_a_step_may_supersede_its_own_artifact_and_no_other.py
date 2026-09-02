"""Gate 5, the second rule: a step may supersede its own artifact and no other's.

Write-once (``# RUN_ARTIFACTS:``) refuses a step whose declared file is already
in the envelope, and two steps of the kernel-arms campaign run twice over one
file by design: ``1-build-ladder.sh`` writes its BUILD and KERNELS stamps before
step 3 has produced the instrument record and re-files the BENCH rows after it
(pass 2 rewrites the pass-1 file), and ``4-kernel-arms.sh --step crash`` appends
to the file step 6 created (``# RUN_APPENDS:``). Through the door the first was
refused until the earlier file was moved aside by hand — a rule that gets waived
on the rig at 02:00, which is how a rule stops existing.

So a step may declare a file under ``# RUN_REWRITES:`` instead, and the door
holds it to three things. An existing file is admitted only if its ``### START``
carries a ``run_id`` whose ``<campaign>-<step>`` stem is this run's: the same
step wrote it. Before the step starts, the file is moved to
``<name>.superseded-<old run_id>.<ext>`` beside itself, so nothing recorded is
ever lost. A file another step wrote, or one with no run id at all (the legacy
shape), is refused with exit 2 naming the file and nothing is moved: the door
does not let one step overwrite another's evidence, and cannot tell who wrote a
file that never said. Gates 7 and 8 treat a rewritten file exactly as a
write-once one — ``### RIGMOVED`` reaches it, and it is parsed before exit 0.

Seams: ``RUN_DATE`` names the envelope; ``RUN_REPO`` roots it; every other gate
runs against the stubs ``tests/onedoor.py`` builds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor

LEGACY_START = (
    f"### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
    "pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600\n"
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        repo,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", directive="RUN_REWRITES"),
    )
    return repo


@pytest.fixture
def env(root: Path, tmp_path: Path) -> dict[str, str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    return onedoor.door_env(root, stubs)


def _start_line(artifact: Path) -> str:
    return next(
        line
        for line in artifact.read_text(encoding="utf-8").splitlines()
        if line.startswith("### START")
    )


def test_the_same_step_run_twice_supersedes_its_own_artifact(
    root: Path, env: dict[str, str], tmp_path: Path
) -> None:
    first = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert first.returncode == 0, (first.stdout, first.stderr)
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    first_text = artifact.read_text(encoding="utf-8")
    first_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"run_id={first_id}" in _start_line(artifact).split()

    second = onedoor.door(
        root, ["alpha", "probe", "--host", "srv1", "--suffix", "pass2"], env
    )
    assert second.returncode == 0, (second.stdout, second.stderr)
    second_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert second_id != first_id, second_id
    assert f"run_id={second_id}" in _start_line(artifact).split(), (
        "the rewritten file does not carry the run that rewrote it"
    )
    superseded = artifact.with_name(f"probe.superseded-{first_id}.tsv")
    assert superseded.is_file(), onedoor.written_under_records(root)
    assert superseded.read_text(encoding="utf-8") == first_text, (
        "the earlier pass was not preserved byte for byte"
    )
    assert "probe.superseded-" in second.stderr, second.stderr


def test_a_different_step_declaring_the_file_is_refused_and_nothing_moves(
    root: Path, env: dict[str, str], tmp_path: Path
) -> None:
    onedoor.add_step(
        root,
        "alpha",
        "2-other.sh",
        onedoor.probe_step(tmp_path / "e2", directive="RUN_REWRITES"),
    )
    first = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert first.returncode == 0, (first.stdout, first.stderr)
    before = onedoor.written_under_records(root)
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    text = artifact.read_text(encoding="utf-8")

    result = onedoor.door(root, ["alpha", "other", "--host", "srv1"], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == before, (
        "the refusal moved or wrote something"
    )
    assert artifact.read_text(encoding="utf-8") == text
    assert not (tmp_path / "e2").exists(), "the step ran over another step's file"


def test_a_legacy_file_with_no_run_id_is_refused(
    root: Path, env: dict[str, str], tmp_path: Path
) -> None:
    out_dir = onedoor.envelope(root, "alpha")
    out_dir.mkdir(parents=True)
    legacy = out_dir / "probe.tsv"
    legacy.write_text(LEGACY_START, encoding="utf-8")
    before = onedoor.written_under_records(root)

    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == before, (
        "the refusal moved or wrote something"
    )
    assert legacy.read_text(encoding="utf-8") == LEGACY_START
    assert not (tmp_path / "e").exists(), "the step ran over a file nobody claimed"


def test_a_rig_that_moves_under_a_rewriting_step_is_stamped_in_its_file(
    tmp_path: Path,
) -> None:
    """Gate 7 reaches a ``RUN_REWRITES`` file the way it reaches a write-once one."""
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(
            tmp_path / "e", after=f"touch '{flag}'", directive="RUN_REWRITES"
        ),
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    rig = onedoor.rig_stub(stubs, "srv1", moved_flag=flag)
    env = onedoor.door_env(root, stubs, rig=rig)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "pl1_uw" in result.stderr, result.stderr
    lines = (onedoor.envelope(root, "alpha") / "probe.tsv").read_text().splitlines()
    moved = [line for line in lines if line.startswith("### RIGMOVED")]
    assert moved, f"no ### RIGMOVED in the rewritten file:\n{lines}"
    assert lines.index(moved[0]) > lines.index(
        next(line for line in lines if line.startswith("### END"))
    )
