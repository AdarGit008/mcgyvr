"""Gate 1: a checkout that has moved off the open round does not start a run.

Only ``tools/breadth/measure.py`` checks the product round today (BRIEF "The
problem being solved"); the sweep scripts stamp nothing about it, so an arm
measured on a tree three commits past the pin lands in the same table as one
measured on the pin (ADR-0018: every arm in a round runs against one revision).
The door runs ``tools/bench/product.require_pinned()`` before anything else
and exits 2 on its refusal — having written nothing.

``RUN_PRODUCT_CHECK`` is the seam: a command that stands in for the
``require_pinned`` call. It exits non-zero with the refusal on stderr, or
prints ``round=<id> product_sha256=<hex>`` and exits 0, in which case the run
proceeds and the two values reach the artifact's ``### ROUND`` stamp
(``test_an_artifact_names_the_run_and_the_round_that_produced_it``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_a_refused_round_check_exits_2_with_its_reason_and_writes_nothing(
    root: Path, tmp_path: Path
) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs, pinned=False)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "moved off round" in result.stderr, (
        f"the product check's own words are not on stderr: {result.stderr}"
    )
    assert onedoor.written_under_records(root) == [], "gate 1 refused and still wrote"
    assert not (tmp_path / "e").exists(), "the step ran after gate 1 refused"


def test_a_pinned_round_lets_the_run_proceed(root: Path, tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs, pinned=True)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    handed = onedoor.read_env_file(tmp_path / "e")
    assert handed["RUN_ROUND"] == onedoor.ROUND_ID, handed
    assert handed["RUN_PRODUCT_SHA256"] == onedoor.PRODUCT_SHA256, handed
    assert (onedoor.envelope(root, "alpha") / "probe.tsv").is_file()
