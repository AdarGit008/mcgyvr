"""Gate 5: the envelope, the run id, and a step that will not run without one.

The same drivers the campaign scripts drive can be run bare from the repo root
and print byte-compatible rows with no stamps at all; a step script run by
hand skips every gate the door would have applied. So the door mints
``RUN_ID`` and exports it, makes the envelope
``records/evidence/<date>-<campaign>/`` under the repo, and refuses to start a
step whose declared artifact is already there (artifacts are write-once).
Every driver and every step script exits 2 the moment ``RUN_ID`` is unset —
before it parses a single argument, so ``--help`` is not a way around it
either — and names the door.

A step names its artifacts on a ``# RUN_ARTIFACTS:`` line the door reads
without running it. ``RUN_ID`` is ``<date>-<campaign>-<step name>`` with an
optional ``-<suffix>``, whitespace-free and legal as a docker container-name
prefix (gate 7 filters ``docker ps`` by it); the step name is the step file's
stem minus its ``<n>-`` prefix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

RUN_ID_SHAPE = re.compile(rf"{onedoor.RUN_DATE}-alpha-probe(-[A-Za-z0-9_.-]+)?")
DOOR_NAME = "mcgyvr.serving.run"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_the_door_makes_the_envelope_and_hands_the_step_its_run_id(
    root: Path, tmp_path: Path
) -> None:
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 0, (result.stdout, result.stderr)
    out_dir = onedoor.envelope(root, "alpha")
    assert out_dir.is_dir(), onedoor.written_under_records(root)
    handed = onedoor.read_env_file(tmp_path / "e")
    assert RUN_ID_SHAPE.fullmatch(handed["RUN_ID"]), handed["RUN_ID"]
    assert Path(handed["RUN_OUT_DIR"]).resolve() == out_dir.resolve(), handed
    assert handed["RUN_HOST"] == "srv1", handed
    assert handed["RUN_STEP"] == "probe", handed
    artifact = out_dir / "probe.tsv"
    assert artifact.is_file()
    start = next(
        line
        for line in artifact.read_text(encoding="utf-8").splitlines()
        if line.startswith("### START")
    )
    assert f"run_id={handed['RUN_ID']}" in start.split(), start


def test_an_artifact_already_in_the_envelope_is_not_overwritten(
    root: Path, tmp_path: Path
) -> None:
    out_dir = onedoor.envelope(root, "alpha")
    out_dir.mkdir(parents=True)
    existing = out_dir / "probe.tsv"
    existing.write_text("### START run_id=an-earlier-run\n", encoding="utf-8")
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr, result.stderr
    assert existing.read_text(encoding="utf-8") == "### START run_id=an-earlier-run\n"
    assert not (tmp_path / "e").exists(), "the step ran into an occupied envelope"


@pytest.mark.parametrize("name", onedoor.DRIVER_NAMES)
def test_every_driver_exits_2_without_a_run_id(tmp_path: Path, name: str) -> None:
    """Under a stand-in door, so the ancestry proof passes and RUN_ID is the
    only thing missing; ``tests/test_one_door.py`` runs the same drivers with
    no door at all."""
    stubs = tmp_path / "stubs"
    digest = onedoor.LCP_DIGEST if name == "lcp_sweep.py" else onedoor.VLLM_DIGEST
    env = onedoor.bare_env(stubs, **{onedoor.DRIVER_IMG_VAR[name]: digest})
    assert "RUN_ID" not in env
    result = onedoor.driver(name, env, door=onedoor.fake_door(tmp_path))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "RUN_ID" in result.stderr, result.stderr
    assert DOOR_NAME in result.stderr, result.stderr
    assert onedoor.docker_log(stubs) == []


def _kernel_arms_steps() -> list[Path]:
    assert onedoor.KERNEL_ARMS.is_dir(), (
        f"{onedoor.KERNEL_ARMS.relative_to(onedoor.REPO)} does not exist"
    )
    steps = sorted(onedoor.KERNEL_ARMS.glob("[0-9]*-*.sh"))
    names = {re.sub(r"^[0-9]+-", "", p.name).removesuffix(".sh") for p in steps}
    assert names == onedoor.STEP_NAMES, (
        f"steps under srv1-kernel-arms are {sorted(names)}, "
        f"expected {sorted(onedoor.STEP_NAMES)}"
    )
    return steps


@pytest.mark.parametrize("argv", [["--help"], []], ids=["help", "no-args"])
def test_every_kernel_arms_step_refuses_before_parsing_without_a_run_id(
    tmp_path: Path, argv: list[str]
) -> None:
    env = onedoor.bare_env(tmp_path / "stubs", RUN_REPO=str(onedoor.REPO))
    for step in _kernel_arms_steps():
        result = onedoor.bash(" ".join(["exec", f"'{step}'", *argv]), env, onedoor.REPO)
        assert result.returncode == 2, (
            f"{step.name} {argv}: exit {result.returncode}, not 2 — "
            f"stderr={result.stderr[-300:]!r}"
        )
        assert "RUN_ID" in result.stderr, f"{step.name}: {result.stderr[-300:]!r}"
        assert DOOR_NAME in result.stderr, (
            f"{step.name}: the refusal does not name the door: {result.stderr[-300:]!r}"
        )
