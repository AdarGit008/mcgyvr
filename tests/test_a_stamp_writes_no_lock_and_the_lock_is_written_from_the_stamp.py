"""A stamp writes no lock; the fleet lock is written from the stamp.

Owner: "one script that locks a fleet, one script that stamps a fleet without
locking". A green sample's stamp is a folder of its own under the data folder,
``<data folder>/stamps/<fleet>/<run_id>/``, holding the staged setup and the
dev-run evidence, and nothing else: no lock, no promoted folder, no
``live.json``. :func:`mcgyvr.fleet.lock.write_from_stamp` (``mcgyvr fleet lock
--stamp DIR``) is what locks it, into the stamp folder as its dev root, and the
chain every live fleet takes runs from there: lock -> promote -> use.

No rig is reached: the rig is invented and its reads are canned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet.promote import LOCK_DIR
from tests import sample_fleet as fx


def _sample(setup: Path) -> Any:
    from mcgyvr.fleet import sample

    outcomes = (sample.Outcome("gate", unit=fx.UNIT, passed=True),)
    return sample.Sample(setup=setup, fleet=fx.FLEET, reads=fx.READS, outcomes=outcomes)


def _read_twice(setup: Path, **first: Any) -> None:
    fx.read(setup, fx.READS[0], **first)
    fx.read(setup, fx.READS[1], load=None, **first)


@pytest.fixture
def no_lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A run root that holds no lab file, and must stay empty."""
    root = tmp_path / "no-lab-root"
    root.mkdir()
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(root))
    return root


@pytest.fixture
def setup(tmp_path: Path, no_lab: Path) -> Path:
    fx.rig_file()
    return fx.staged(tmp_path)


def _files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


def test_a_green_sample_writes_its_stamp_and_nothing_else(
    setup: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import stamp
    from mcgyvr.fleet.roots import data_home, fleets_dir, live_file

    _read_twice(setup)

    done = stamp.stamp(_sample(setup), run_id="sample-1")

    assert done.green, done.why
    folder = data_home() / "stamps" / fx.FLEET / "sample-1"
    assert done.folder == folder and done.fleet == fx.FLEET
    assert _files(folder) == [
        "evidence.json",
        "setup",
        "setup/fleet.yaml",
        "setup/policy.yaml",
    ], "a stamp is the staged setup and its evidence: no lock"
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["combinations"][0]["passed"] is True
    assert not fleets_dir().exists(), "a stamp promotes nothing"
    assert not live_file().exists(), "a stamp names nothing live"
    assert os.listdir(no_lab) == [], "a stamp writes nothing under the run root"
    said = "\n".join(done.lines())
    assert said.startswith(f"stamped: {fx.FLEET}") and str(folder) in said, said
    assert not hasattr(done, "promoted") and not hasattr(done, "switch")


def test_the_lock_is_written_from_the_stamp_and_the_chain_runs_from_there(
    setup: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import lock, stamp
    from mcgyvr.fleet.promote import promote, use
    from mcgyvr.fleet.roots import fleets_dir, live_fleet

    _read_twice(setup)
    done = stamp.stamp(_sample(setup), run_id="sample-1")
    assert done.folder is not None, done.why

    tree = lock.write_from_stamp(done.folder)

    assert tree == done.folder / LOCK_DIR
    assert (tree / f"{fx.FLEET}.json").is_file()
    folder = promote(done.folder, done.folder / "setup", fx.FLEET)
    assert folder == fleets_dir() / f"{fx.FLEET}@{fx.SAMPLE_DAY}"
    assert use(folder.name).name == folder.name
    assert live_fleet() == folder.name
    assert os.listdir(no_lab) == []


def test_a_second_stamp_of_the_same_lock_is_its_own_stamp_and_promotes_nothing(
    setup: Path,
) -> None:
    from mcgyvr.fleet import lock, stamp
    from mcgyvr.fleet.promote import PromoteRefusedError, promote
    from mcgyvr.fleet.roots import fleets_dir

    _read_twice(setup)
    first = stamp.stamp(_sample(setup), run_id="sample-1")
    again = stamp.stamp(_sample(setup), run_id="sample-2")
    assert first.folder is not None and again.folder is not None

    lock.write_from_stamp(first.folder)
    promoted = promote(first.folder, first.folder / "setup", fx.FLEET)
    lock.write_from_stamp(again.folder)
    with pytest.raises(PromoteRefusedError, match="already exists"):
        promote(again.folder, again.folder / "setup", fx.FLEET)
    assert [p.name for p in fleets_dir().iterdir()] == [promoted.name]


def test_a_run_id_already_stamped_is_red(setup: Path) -> None:
    from mcgyvr.fleet import stamp

    _read_twice(setup)
    assert stamp.stamp(_sample(setup), run_id="sample-1").green
    again = stamp.stamp(_sample(setup), run_id="sample-1")
    assert not again.green and again.folder is None
    assert "sample-1" in "\n".join(again.lines())


def test_a_lock_refusal_is_the_locks_own_message_and_the_stamp_stays(
    setup: Path,
) -> None:
    """The reads name another rig than the one the staged setup pins: the
    sample is stamped, and the lock refuses it by the lock's own message."""
    from mcgyvr.fleet import lock, stamp

    moved = {**fx.SNAPSHOT, "driver": "501.00"}
    _read_twice(setup, text=fx.reader_text(snapshot=moved))
    done = stamp.stamp(_sample(setup), run_id="sample-1")
    assert done.folder is not None, done.why

    with pytest.raises(lock.LockRefusedError, match=fx.rig_id(moved)):
        lock.write_from_stamp(done.folder)
    assert not (done.folder / LOCK_DIR).exists()
    assert (done.folder / "evidence.json").is_file()


@pytest.mark.parametrize(
    ("case", "word"),
    [
        ("no-folder", "stamp"),
        ("no-evidence", "evidence.json"),
        ("bad-evidence", "evidence.json"),
        ("list-evidence", "evidence.json"),
        ("no-fleet", "fleet.yaml"),
        ("no-policy", "policy.yaml"),
    ],
)
def test_a_malformed_stamp_folder_is_refused_by_what_is_wrong(
    setup: Path, tmp_path: Path, case: str, word: str
) -> None:
    from mcgyvr.fleet import lock, stamp

    _read_twice(setup)
    done = stamp.stamp(_sample(setup), run_id="sample-1")
    assert done.folder is not None, done.why
    folder = done.folder
    if case == "no-folder":
        folder = tmp_path / "nowhere"
    elif case == "no-evidence":
        (folder / "evidence.json").unlink()
    elif case == "bad-evidence":
        (folder / "evidence.json").write_text("{", encoding="utf-8")
    elif case == "list-evidence":
        (folder / "evidence.json").write_text("[]", encoding="utf-8")
    else:
        (folder / "setup" / f"{case.removeprefix('no-')}.yaml").unlink()

    with pytest.raises(lock.LockRefusedError, match=word):
        lock.write_from_stamp(folder)
    assert not (folder / LOCK_DIR).exists()


def test_fleet_lock_stamp_locks_the_stamp_folder(
    setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.cli import main
    from mcgyvr.fleet import stamp

    _read_twice(setup)
    done = stamp.stamp(_sample(setup), run_id="sample-1")
    assert done.folder is not None, done.why
    capsys.readouterr()

    assert main(["fleet", "lock", "--stamp", str(done.folder)]) == 0

    assert str(done.folder / LOCK_DIR) in capsys.readouterr().out
    assert (done.folder / LOCK_DIR / f"{fx.FLEET}.json").is_file()


@pytest.mark.parametrize(
    "extra",
    [
        ("--evidence", "e.json"),
        ("--fleet", "f.yaml"),
        ("--policy", "p.yaml"),
        ("--root", "elsewhere"),
    ],
)
def test_fleet_lock_stamp_takes_nothing_the_stamp_already_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: tuple[str, str]
) -> None:
    from mcgyvr.cli import main

    code: object
    try:
        code = main(["fleet", "lock", "--stamp", str(tmp_path), *extra])
    except SystemExit as exited:
        code = exited.code
    assert code == 2
    assert extra[0] in capsys.readouterr().err
    assert not (tmp_path / LOCK_DIR).exists()


def test_fleet_lock_needs_a_stamp_or_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    code: object
    try:
        code = main(["fleet", "lock", "--fleet", "f.yaml"])
    except SystemExit as exited:
        code = exited.code
    assert code == 2
    said = capsys.readouterr().err
    assert "--stamp" in said and "--evidence" in said, said
