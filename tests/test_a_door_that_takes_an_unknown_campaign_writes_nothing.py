"""There is one door to the rigs, and it refuses before it writes.

Four live entry points reach srv1 and srv2 today and only one of them stamps
rig state, workload digest and build identity (BRIEF "The problem being
solved"). The design collapses them into ``tools/runs/run.sh <campaign> <step>
--host srv1|srv2``: the door discovers campaigns under
``tools/runs/campaigns/<campaign>/`` and steps as ``<n>-<name>.sh`` inside one,
addressed by number or by name.

Pinned here: the executable exists; asked for nothing, or for ``--help``, it
exits 2 and names the campaigns it found, so an operator learns the vocabulary
from the door and not from a document; asked for a campaign it does not have,
a step that is not in it, or a host that ``hosts.json`` does not declare, it
exits 2 and leaves ``records/`` exactly as it found it. Nothing after the
argument check has run — no product check, no rig read — so nothing can have
been written.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import onedoor

CAMPAIGNS = ("alpha", "beta")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    for name in CAMPAIGNS:
        onedoor.add_step(repo, name, "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


@pytest.fixture
def env(root: Path, tmp_path: Path) -> dict[str, str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    return onedoor.door_env(root, stubs)


def test_the_door_exists_and_is_executable() -> None:
    assert onedoor.RUN_SH.is_file(), "tools/runs/run.sh does not exist"
    assert os.access(onedoor.RUN_SH, os.X_OK), "tools/runs/run.sh is not executable"


@pytest.mark.parametrize("argv", [[], ["--help"]])
def test_asked_for_nothing_it_lists_the_campaigns_and_exits_2(
    root: Path, env: dict[str, str], argv: list[str]
) -> None:
    result = onedoor.door(root, argv, env)
    assert result.returncode == 2, result.stderr
    for name in CAMPAIGNS:
        assert name in result.stderr, f"usage does not name campaign {name!r}"
    assert "--host" in result.stderr, "usage does not show the --host argument"
    assert onedoor.written_under_records(root) == []


def test_the_real_checkout_lists_the_kernel_arms_campaign(tmp_path: Path) -> None:
    """The eight ``srv1-*.sh`` steps live under
    ``tools/runs/campaigns/srv1-kernel-arms/`` after the move, and the door
    run from this checkout says so."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(onedoor.REPO, stubs)
    result = onedoor.door(onedoor.REPO, [], env)
    assert result.returncode == 2, result.stderr
    assert "srv1-kernel-arms" in result.stderr


def test_a_campaign_alone_lists_its_steps_and_exits_2(
    root: Path, env: dict[str, str]
) -> None:
    result = onedoor.door(root, ["alpha"], env)
    assert result.returncode == 2, result.stderr
    assert "probe" in result.stderr, "usage for a campaign does not list its steps"
    assert onedoor.written_under_records(root) == []


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["gamma", "1", "--host", "srv1"], "gamma"),
        (["alpha", "9", "--host", "srv1"], "9"),
        (["alpha", "nope", "--host", "srv1"], "nope"),
        (["alpha", "1", "--host", "srv9"], "srv9"),
        (["alpha", "1"], "--host"),
    ],
    ids=[
        "unknown-campaign",
        "unknown-step-number",
        "unknown-step-name",
        "unknown-host",
        "no-host",
    ],
)
def test_an_unknown_campaign_step_or_host_exits_2_and_writes_nothing(
    root: Path, env: dict[str, str], argv: list[str], named: str
) -> None:
    result = onedoor.door(root, argv, env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert named in result.stderr, (
        f"the refusal does not name {named!r}: {result.stderr}"
    )
    assert onedoor.written_under_records(root) == [], "the door wrote under records/"
    assert not (Path(env["RUN_SSH"]).parent / "ssh.reached").exists()
