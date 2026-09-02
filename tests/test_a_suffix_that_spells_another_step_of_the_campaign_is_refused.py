"""A run id names its step unambiguously, so a suffix may not forge one.

``RUN_ID`` is ``<date>-<campaign>-<step>[-<suffix>]`` and both the step name
and the suffix may carry dashes. Gate 5 reads the writer of an existing
``RUN_REWRITES`` file back out of its ``run_id`` to decide whether THIS step
may supersede it; with steps ``probe`` and ``probe-again`` in one campaign,
``probe --suffix again`` minted ``…-probe-again``, which then read as the
other step's: ``probe-again`` was let supersede ``probe``'s file, and ``probe``
was refused over its own.

So the door refuses a ``--suffix`` that makes ``<step>-<suffix>`` equal
another step's name or start with ``<other step>-``: every id it mints parses
back to exactly one step by longest match. Refused before gate 1, nothing
written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        repo,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e1", directive="RUN_REWRITES"),
    )
    onedoor.add_step(
        repo,
        "alpha",
        "2-probe-again.sh",
        onedoor.probe_step(tmp_path / "e2", directive="RUN_REWRITES"),
    )
    return repo


@pytest.fixture
def env(root: Path, tmp_path: Path) -> dict[str, str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    return onedoor.door_env(root, stubs)


@pytest.mark.parametrize("suffix", ["again", "again-2"])
def test_a_suffix_that_forges_another_steps_id_is_refused(
    root: Path, env: dict[str, str], tmp_path: Path, suffix: str
) -> None:
    result = onedoor.door(
        root, ["alpha", "probe", "--host", "srv1", "--suffix", suffix], env
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "probe-again" in result.stderr, result.stderr
    assert "--suffix" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e1").exists(), "the step ran under a forged id"


def test_a_suffix_that_forges_no_step_is_accepted(
    root: Path, env: dict[str, str], tmp_path: Path
) -> None:
    result = onedoor.door(
        root, ["alpha", "probe", "--host", "srv1", "--suffix", "pass2"], env
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (
        onedoor.read_env_file(tmp_path / "e1")["RUN_ID"]
        == "2026-09-02-alpha-probe-pass2"
    )
