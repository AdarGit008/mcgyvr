"""A step is addressed by ``<n>`` or ``<name>``; an address that fits two is refused.

``resolve_step`` used to return the first ``<n>-<name>.sh`` the glob matched:
a campaign holding ``1-aa.sh`` and ``1-bb.sh`` ran ``aa`` for ``1`` and said
nothing, and one holding ``1-2.sh`` beside ``2-two.sh`` ran step 1 (named
``2``) when the operator asked for step 2. The kernel-arms campaign has
unique numbers and no numeric names, so nothing was misrouted — but a door
that guesses which step you meant is not a door.

So the address must fit exactly one step file, and a campaign directory that
numbers two steps alike is refused whichever step is asked for: the refusal
names every candidate and nothing runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor


def _env(root: Path, tmp_path: Path) -> dict[str, str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    return onedoor.door_env(root, stubs)


@pytest.mark.parametrize("want", ["1", "aa"])
def test_two_steps_with_one_number_are_refused_whichever_is_asked_for(
    tmp_path: Path, want: str
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-aa.sh", onedoor.probe_step(tmp_path / "e-aa"))
    onedoor.add_step(root, "alpha", "1-bb.sh", onedoor.probe_step(tmp_path / "e-bb"))
    result = onedoor.door(root, ["alpha", want, "--host", "srv1"], _env(root, tmp_path))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "1-aa" in result.stderr and "1-bb" in result.stderr, result.stderr
    assert not (tmp_path / "e-aa").exists() and not (tmp_path / "e-bb").exists()
    assert onedoor.written_under_records(root) == []


def test_a_name_that_is_another_steps_number_is_refused(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-2.sh", onedoor.probe_step(tmp_path / "e-one"))
    onedoor.add_step(root, "alpha", "2-two.sh", onedoor.probe_step(tmp_path / "e-two"))
    result = onedoor.door(root, ["alpha", "2", "--host", "srv1"], _env(root, tmp_path))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "1-2" in result.stderr and "2-two" in result.stderr, result.stderr
    assert not (tmp_path / "e-one").exists() and not (tmp_path / "e-two").exists()
