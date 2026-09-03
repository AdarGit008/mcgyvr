"""Gate 2: the rig is compared with its declaration, not only with itself.

``_common.sh`` reads the machine at start and at end and refuses if the two
disagree (``rig_assert_unchanged``). That catches a rig that moved *during* a
run; it says nothing about a rig that moved *before* one. RAM swapped between
srv1 and srv2 twice in six days, srv1's max clock went 4800 -> 4600 unattended,
and every artifact produced in between was internally consistent (BRIEF gate
2: "Today: start==end only").

So ``tools/runs/hosts.json`` carries a ``rig`` block per host — the ten values
read live on 2026-09-02, with the date they were read — and the door compares
a fresh ``rig_snapshot`` with it field by field before the step starts. Any
difference is exit 2, naming the key and both values, having written nothing.
``uptime_since`` is not declared (it changes per boot) and is not compared
here.

``RUN_RIG_SNAPSHOT_CMD`` is the seam: its stdout replaces ``rig_snapshot``'s.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import onedoor


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def _rig_reading(where: Path, host: str, **override: str) -> Path:
    lines = onedoor.snapshot_lines(host, **override)
    return onedoor.executable(
        where / "rig-snapshot", f"#!/usr/bin/env bash\nprintf '%s' '{lines}'\n"
    )


def test_one_field_off_the_declaration_exits_2_naming_key_and_both_values(
    root: Path, tmp_path: Path
) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    reading = _rig_reading(stubs, "srv1", ram_mt_s="2933")
    env = onedoor.door_env(root, stubs, rig=reading)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    for word in ("ram_mt_s", "3600", "2933"):
        assert word in result.stderr, f"{word!r} is not in the refusal: {result.stderr}"
    assert onedoor.written_under_records(root) == [], "gate 2 refused and still wrote"
    assert not (tmp_path / "e").exists(), "the step ran after gate 2 refused"


def test_the_other_rigs_reading_under_this_host_name_is_refused(
    root: Path, tmp_path: Path
) -> None:
    """``--host srv2`` on a machine that reads like srv1 is the wrong rig."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    reading = _rig_reading(stubs, "srv1")
    env = onedoor.door_env(root, stubs, rig=reading)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv2"], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "gpu_name" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []


def test_a_reading_that_matches_the_declaration_proceeds(
    root: Path, tmp_path: Path
) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs, rig=_rig_reading(stubs, "srv1"))
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (onedoor.envelope(root, "alpha") / "probe.tsv").is_file()


# ---------------------------------------------------------------------------
# the declaration itself
# ---------------------------------------------------------------------------


def _declaration() -> dict[str, object]:
    path = onedoor.HOSTS_JSON
    assert path.is_file(), (
        f"{path.relative_to(onedoor.REPO)} does not exist; "
        "tools/bench/serving/configs/hosts.json has not moved (BRIEF layout)"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


@pytest.mark.parametrize("host", ["srv1", "srv2"])
def test_hosts_json_declares_the_rig_as_read_on_its_read_on_date(host: str) -> None:
    document = _declaration()
    entry = document.get(host)
    assert isinstance(entry, dict), f"hosts.json has no {host!r} object"
    rig = entry.get("rig")
    assert isinstance(rig, dict), f"hosts.json[{host!r}] has no 'rig' block"
    assert set(rig) == onedoor.RIG_KEYS, (
        f"hosts.json[{host!r}].rig keys are {sorted(rig)}; "
        f"expected exactly {sorted(onedoor.RIG_KEYS)}"
    )
    wrong = {
        key: (str(rig[key]), want)
        for key, want in onedoor.RIG[host].items()
        if str(rig[key]) != want
    }
    assert not wrong, f"hosts.json[{host!r}].rig differs from the live read: {wrong}"
    assert entry.get("read_on") == onedoor.RIG_READ_ON, (
        f"hosts.json[{host!r}].read_on is {entry.get('read_on')!r}, "
        f"not {onedoor.RIG_READ_ON!r}"
    )
