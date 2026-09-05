"""Gate 1: a checkout that has moved off the open round does not start a run.

An arm measured on a tree three commits past the pin must not land in the
same table as one measured on the pin (ADR-0018: every arm in a round runs
against one revision). The door runs ``tools/bench/product.require_pinned()``
as gate 1 (``01-round.py``), before anything else, and exits 2 on its refusal
— having written nothing and having read no rig.

The fixture pins the tree it builds (``tests/onedoor.py:pin``); ``unpin``
declares a digest the tree does not have. When the pin holds, the run
proceeds and the two values reach the step as ``RUN_ROUND`` and
``RUN_PRODUCT_SHA256``, and from there the artifact's ``### ROUND`` stamp
(``test_an_artifact_names_the_run_and_the_round_that_produced_it``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_a_refused_round_check_exits_2_with_its_reason_and_writes_nothing(
    root: Path, tmp_path: Path
) -> None:
    onedoor.unpin(root)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "moved off round" in result.stderr, (
        f"the product check's own words are not on stderr: {result.stderr}"
    )
    assert onedoor.ROUND_ID in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == [], "gate 1 refused and still wrote"
    assert onedoor.ssh_log(root) == [], "gate 1 refused and the rig was still read"
    assert onedoor.docker_log(root) == []
    assert not (tmp_path / "e").exists(), "the step ran after gate 1 refused"


def test_a_pinned_round_lets_the_run_proceed(root: Path, tmp_path: Path) -> None:
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    handed = onedoor.read_env_file(tmp_path / "e")
    round_id, digest = onedoor.pinned(root)
    assert handed["RUN_ROUND"] == round_id == onedoor.ROUND_ID, handed
    assert handed["RUN_PRODUCT_SHA256"] == digest, handed
    assert (onedoor.envelope(root, "alpha") / "probe.tsv").is_file()
