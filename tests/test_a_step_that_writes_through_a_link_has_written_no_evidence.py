"""A declared artifact is one regular file of the envelope; a link is not evidence.

A hostile step inside a legitimate run planted ``ln -sf <other envelope>/
sizing.tsv $RUN_OUT_DIR/probe.tsv`` after gate 5 had passed write-once (the
name was free) and wrote through it. Committed evidence in the other envelope
was overwritten under a green line, and gate 8, reading ``probe.tsv`` by name,
parsed the victim — a perfectly formed file — as this run's artifact.

So every gate that reads, stamps or parses a declared artifact first asks
``gatelib.artifact_escape``: the name must be a regular file, not a symlink
(named with its target and where it lands), not a hard link (named with the
count of names), whose resolved path is inside the resolved ``RUN_OUT_DIR``;
and the envelope itself must not be a symlink. Gate 8 (``08-parse.py``) and
gate 7's ``### RIGMOVED`` stamping (``07-teardown.py``) exit 1 naming the path
and where it points, and never read or write through it; gate 5
(``05-envelope.py``) refuses, exit 2, a declared name that is already such a
link before the step, on the ``RUN_ARTIFACTS``, ``RUN_REWRITES`` and
``RUN_APPENDS`` paths alike — a dangling symlink passed ``exists()`` and the
step would have created the target somewhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def _victim(root: Path) -> tuple[Path, str]:
    """A committed artifact in ANOTHER envelope, as an earlier run left it."""
    other = onedoor.envelope(root, "beta", date="2026-09-04")
    other.mkdir(parents=True)
    path = other / "sizing.tsv"
    text = (
        f"### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600 "
        "run_id=2026-09-04-beta-probe\n"
        f"### ROUND id={onedoor.ROUND_ID} product_sha256={onedoor.PRODUCT_SHA256}\n"
        f"srv1\tsizing\tCONFIG\timg=sha256:{onedoor.LOCAL_ID_HEX}\n"
        f"### END uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "cpu_max_mhz=4600 ram_mt_s=3600 run_id=2026-09-04-beta-probe\n"
    )
    path.write_text(text, encoding="utf-8")
    return path, text


def _symlinking_step(env_file: Path, victim: Path) -> str:
    """The probe step, but it points its declared name at ``victim`` first."""
    body = onedoor.probe_step(env_file)
    return body.replace(
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n',
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n' + f"ln -sf '{victim}' \"$out\"\n",
    )


def test_a_symlink_planted_after_gate_5_is_exit_1_naming_where_it_points(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    victim, _ = _victim(root)
    onedoor.add_step(
        root, "alpha", "1-probe.sh", _symlinking_step(tmp_path / "e", victim)
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr and "is a symlink to" in result.stderr, (
        result.stderr
    )
    assert str(victim) in result.stderr, f"the target is not named: {result.stderr}"
    assert "artifact(s) parse" not in result.stdout, "gate 8 called the run green"


def test_the_victim_is_not_parsed_as_this_runs_artifact(tmp_path: Path) -> None:
    """The step DID write through the link (the door cannot undo that: the
    step is operator code); what the door refuses is to read the victim back
    as evidence of this run, and it says which file it would have read."""
    root = onedoor.fixture_repo(tmp_path)
    victim, before = _victim(root)
    onedoor.add_step(
        root, "alpha", "1-probe.sh", _symlinking_step(tmp_path / "e", victim)
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"run_id={run_id}" in victim.read_text(encoding="utf-8"), (
        "the step's write did not go through the link; the scenario is not reproduced"
    )
    assert victim.read_text(encoding="utf-8") != before
    assert "not this run's evidence" in result.stderr, result.stderr


def test_a_rig_that_moved_is_not_stamped_through_a_link(tmp_path: Path) -> None:
    """Gate 7 writes ``### RIGMOVED`` into every declared file this run wrote;
    through a link it would stamp the victim. It names the link instead."""
    root = onedoor.fixture_repo(tmp_path)
    victim, _ = _victim(root)
    flag = tmp_path / "step-ran"
    body = _symlinking_step(tmp_path / "e", victim).replace(
        '} > "$out"\n', '} > "$out"\n' + f"touch '{flag}'\n"
    )
    onedoor.add_step(root, "alpha", "1-probe.sh", body)
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", moved_flag=flag)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "pl1_uw" in result.stderr, "gate 7 did not see the rig move"
    assert "RIGMOVED" not in victim.read_text(encoding="utf-8"), (
        "gate 7 stamped through the link into another envelope"
    )
    assert "left unstamped" in result.stderr and str(victim) in result.stderr, (
        result.stderr
    )


def test_a_hard_link_is_named_with_its_count_of_names(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    victim, _ = _victim(root)
    body = onedoor.probe_step(tmp_path / "e").replace(
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n',
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n' + f"ln '{victim}' \"$out\"\n",
    )
    onedoor.add_step(root, "alpha", "1-probe.sh", body)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr and "hard link" in result.stderr, result.stderr
    assert "2 names on disk" in result.stderr, result.stderr


def test_an_envelope_that_is_a_symlink_is_refused_before_anything_is_minted(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    envelope = onedoor.envelope(root, "alpha")
    envelope.parent.mkdir(parents=True)
    os.symlink(elsewhere, envelope)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "is a symlink to" in result.stderr and str(elsewhere) in result.stderr, (
        result.stderr
    )
    assert not (tmp_path / "e").exists(), "the step ran into a linked envelope"
    assert list(elsewhere.iterdir()) == [], "something was written through the link"


@pytest.mark.parametrize("directive", ["RUN_ARTIFACTS", "RUN_REWRITES", "RUN_APPENDS"])
def test_a_declared_name_that_is_already_a_link_is_refused_before_the_step(
    tmp_path: Path, directive: str
) -> None:
    """A dangling symlink under the declared name: ``exists()`` is False, so
    write-once admitted it and the step would have created the target
    wherever the link pointed. Refused, exit 2, on every directive."""
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", directive=directive),
    )
    envelope = onedoor.envelope(root, "alpha")
    envelope.mkdir(parents=True)
    target = tmp_path / "outside" / "created-by-the-step.tsv"
    os.symlink(target, envelope / "probe.tsv")
    result = onedoor.door(root, PROBE)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe.tsv" in result.stderr and "is a symlink to" in result.stderr, (
        result.stderr
    )
    assert str(target) in result.stderr, result.stderr
    assert not target.exists(), "the step wrote through the dangling link"
    assert not (tmp_path / "e").exists(), "the step ran over a linked name"
