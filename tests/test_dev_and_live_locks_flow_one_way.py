"""Dev and live keep two locks, and a lock moves one way: dev to live.

Owner, 2026-09-15: "(~/.mcgyvr/ for live), (records/fleet/ for dev) - 2
separate locks and fleets - data flows one way dev->live", with the dev lock
committed in the repository (committing is the approval) and promoted by
command.

* One resolver names the lock root by profile: ``~/.mcgyvr`` for live, the
  checkout (``$MCGYVR_RUN_ROOT`` when the door names one) for dev.
* Every lock reader asks it: the live waker, gate 1 and ``fleet alerts``. None
  reads the working directory.
* ``mcgyvr fleet lock`` writes the dev root and refuses the live one.
* ``mcgyvr fleet promote <fleet>`` copies a dev lock, its combinations and the
  fleet's units, rigs and fleet block into ``~/.mcgyvr``; it refuses a fleet
  with no dev lock, a layout that no longer matches its dev lock, and a live
  unit or rig of the same name with a different identity, and it never writes
  the dev root.
* ``mcgyvr fleet use <fleet>`` names the live fleet among promoted fleets, and
  once one is live only along its ``next``.
"""

from __future__ import annotations

import copy
import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import onedoor
from tests.red_port.conftest import required
from tests.test_a_sleeping_rung_is_woken_rather_than_declined import (
    RUNG_7B,
    compose_dir,
    door_log,
    ladder,
)
from tests.test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock import (
    SRV1_EVIDENCE,
    SRV1_FLEET,
)
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    EVIDENCE,
    FLEET,
    FLT02,
    POLICY,
    RIG2,
    TOLERANCES,
    U3B,
    U7B,
)

REPO = Path(__file__).resolve().parent.parent


def _roots() -> Any:
    return required(
        "name the lock root by profile: ~/.mcgyvr for live, the checkout for dev",
        lambda: importlib.import_module("mcgyvr.fleet.roots"),
    )


def _lock() -> Any:
    return importlib.import_module("mcgyvr.fleet.lock")


def live_root() -> Path:
    return Path.home() / ".mcgyvr"


def tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root``, by relative path, with its bytes."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def dev_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    locked_fleet: dict[str, Any] = FLEET,
    file_fleet: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """A dev checkout holding a lock of ``locked_fleet`` and a fleet file."""
    dev = tmp_path / "dev"
    _lock().write(dev, locked_fleet, EVIDENCE, policy=POLICY, tolerances=TOLERANCES)
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(dev))
    fleet_file = tmp_path / "dev-fleet.yaml"
    fleet_file.write_text(
        yaml.safe_dump(
            {"profile": "dev", **(locked_fleet if file_fleet is None else file_fleet)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return dev, fleet_file


def cli(*argv: str) -> int:
    from mcgyvr.cli import main

    try:
        return main(list(argv))
    except SystemExit as exited:
        pytest.fail(
            f"mcgyvr must be able to: `mcgyvr {' '.join(argv)}`\n"
            f"  argparse exited {exited.code}",
            pytrace=False,
        )


def test_live_locks_under_home_mcgyvr_and_dev_under_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots()
    monkeypatch.delenv("MCGYVR_RUN_ROOT", raising=False)
    assert roots.lock_root("live") == live_root()
    assert roots.lock_root("dev") == REPO
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    assert roots.lock_root("dev") == tmp_path
    with pytest.raises(ValueError, match="prod"):
        roots.lock_root("prod")


def test_the_live_waker_reads_the_lock_under_home_and_never_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import wake
    from mcgyvr.config import load

    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    spawned = door_log(monkeypatch)
    specs = compose_dir(tmp_path, with_spec=True)
    live = tmp_path / "live.yaml"
    live.write_text(
        ladder(engine="vllm")
        + f"journal:\n  dir: {tmp_path / 'j'}\n"
        + f"serving:\n  enable_sleep_wake: true\n  compose_dir: {specs}\n",
        encoding="utf-8",
    )
    work = tmp_path / "work"
    _lock().write(work, FLEET, EVIDENCE, policy=POLICY, tolerances=TOLERANCES)
    monkeypatch.chdir(work)

    waker = wake.for_config(load(live))
    assert waker is not None
    waker.wake_for(RUNG_7B)
    assert spawned == [], f"a lock in the working directory woke a card: {spawned}"

    _lock().write(live_root(), FLEET, EVIDENCE, policy=POLICY, tolerances=TOLERANCES)
    waker = wake.for_config(load(live))
    assert waker is not None
    waker.wake_for(RUNG_7B)
    assert len(spawned) == 1, f"the lock under ~/.mcgyvr woke nothing: {spawned}"


def test_gate_1_admits_a_live_serve_up_from_the_lock_under_home_not_the_run_root(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    tolerances = {"warm_decode_pct": {"llama.cpp": 5.0}}
    policy = {"ladder": ["a", "b"]}

    _lock().write(root, SRV1_FLEET, SRV1_EVIDENCE, policy=policy, tolerances=tolerances)
    refused = onedoor.serve_door(root, "up", compose)
    assert refused.returncode != 0 and "gate 1:" in refused.stderr, (
        "a lock under the run root admitted a live serve up.\n"
        f"exit {refused.returncode}\nstderr: {refused.stderr[-1500:]}"
    )

    _lock().write(
        live_root(), SRV1_FLEET, SRV1_EVIDENCE, policy=policy, tolerances=tolerances
    )
    admitted = onedoor.serve_door(root, "up", compose)
    assert admitted.returncode == 0, (admitted.stdout, admitted.stderr[-1500:])


def test_fleet_lock_writes_the_dev_root_and_refuses_the_live_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev = tmp_path / "dev"
    dev.mkdir()
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(dev))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    fleet_file = tmp_path / "fleet.yaml"
    fleet_file.write_text(yaml.safe_dump(FLEET, sort_keys=False), encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(EVIDENCE), encoding="utf-8")

    assert (
        cli("fleet", "lock", "--fleet", str(fleet_file), "--evidence", str(evidence))
        == 0
    )
    assert (dev / "records" / "fleet" / "flt-05.json").is_file()
    assert tree(work) == {}, "fleet lock wrote into the working directory"

    code = cli(
        "fleet", "lock", "--fleet", str(fleet_file), "--evidence", str(evidence),
        "--root", str(live_root()),
    )  # fmt: skip
    assert code != 0, "fleet lock wrote a lock straight into the live root"
    assert tree(live_root()) == {}


def test_promote_copies_the_lock_its_combinations_and_its_units_into_home_mcgyvr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet.files import load_fleet
    from mcgyvr.fleet.layout import combination_id

    dev, fleet_file = dev_setup(tmp_path, monkeypatch)
    before = tree(dev)

    assert cli("fleet", "promote", "flt-05", "--fleet", str(fleet_file)) == 0

    lock = Path("records") / "fleet" / "flt-05.json"
    assert (live_root() / lock).read_bytes() == (dev / lock).read_bytes()
    cmb = combination_id(RIG2, [(U7B, "awake"), (U3B, "asleep")])
    record = Path("records") / "fleet" / "rigs" / RIG2 / f"{cmb}.json"
    assert (live_root() / record).read_bytes() == (dev / record).read_bytes()

    live_fleet = load_fleet(
        (live_root() / "config" / "fleet.yaml").read_text(encoding="utf-8")
    )
    assert live_fleet["profile"] == "live"
    assert live_fleet["units"]["srv2_7b"]["unit_id"] == U7B
    assert live_fleet["units"]["srv2_3b"]["unit_id"] == U3B
    assert live_fleet["rigs"]["srv2"]["rig_id"] == RIG2
    assert live_fleet["fleets"]["flt-05"] == FLEET["fleets"]["flt-05"]
    assert tree(dev) == before, "promote wrote into the dev root"


def test_promote_refuses_a_fleet_with_no_dev_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unlocked = copy.deepcopy(FLEET)
    unlocked["fleets"]["flt-09"] = copy.deepcopy(FLEET["fleets"]["flt-05"])
    _dev, fleet_file = dev_setup(tmp_path, monkeypatch, file_fleet=unlocked)

    assert cli("fleet", "promote", "flt-09", "--fleet", str(fleet_file)) != 0
    assert tree(live_root()) == {}


def test_promote_refuses_a_layout_that_no_longer_matches_its_dev_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited = copy.deepcopy(FLEET)
    edited["fleets"]["flt-05"]["layout"]["srv2"] = list(
        reversed(edited["fleets"]["flt-05"]["layout"]["srv2"])
    )
    _dev, fleet_file = dev_setup(tmp_path, monkeypatch, file_fleet=edited)

    assert cli("fleet", "promote", "flt-05", "--fleet", str(fleet_file)) != 0
    assert tree(live_root()) == {}


@pytest.mark.parametrize(
    ("block", "name", "key"),
    [("units", "srv2_7b", "unit_id"), ("rigs", "srv2", "rig_id")],
)
def test_promote_refuses_a_live_unit_or_rig_of_the_same_name_that_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, block: str, name: str, key: str
) -> None:
    _dev, fleet_file = dev_setup(tmp_path, monkeypatch)
    live_fleet = copy.deepcopy(FLEET)
    prefix = live_fleet[block][name][key][:4]
    live_fleet[block][name][key] = prefix + "e" * 64
    config = live_root() / "config"
    config.mkdir(parents=True)
    (config / "fleet.yaml").write_text(
        yaml.safe_dump({"profile": "live", **live_fleet}, sort_keys=False),
        encoding="utf-8",
    )
    before = tree(live_root())

    assert cli("fleet", "promote", "flt-05", "--fleet", str(fleet_file)) != 0
    assert tree(live_root()) == before


def test_use_names_the_live_fleet_among_promoted_fleets_and_then_along_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fleet = copy.deepcopy(FLEET)
    fleet["fleets"]["flt-07"] = {"layout": {"srv2": copy.deepcopy(FLT02)}, "next": []}
    _dev, fleet_file = dev_setup(tmp_path, monkeypatch, locked_fleet=fleet)
    live_name = live_root() / "records" / "fleet" / "live.json"

    assert cli("fleet", "use", "flt-05") != 0, "a fleet nobody promoted went live"
    assert not live_name.exists()

    assert cli("fleet", "promote", "flt-05", "--fleet", str(fleet_file)) == 0
    assert cli("fleet", "use", "flt-05") == 0
    assert json.loads(live_name.read_text(encoding="utf-8"))["fleet"] == "flt-05"

    assert cli("fleet", "use", "flt-02") != 0, "an unpromoted switch target went live"
    assert cli("fleet", "promote", "flt-02", "--fleet", str(fleet_file)) == 0
    assert cli("fleet", "use", "flt-02") == 0
    assert json.loads(live_name.read_text(encoding="utf-8"))["fleet"] == "flt-02"

    assert cli("fleet", "promote", "flt-07", "--fleet", str(fleet_file)) == 0
    assert cli("fleet", "use", "flt-07") != 0, "flt-02 lists no switch to flt-07"
    assert json.loads(live_name.read_text(encoding="utf-8"))["fleet"] == "flt-02"


def test_fleet_alerts_reads_the_lock_root_the_profile_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import alerts

    roots_seen: list[Path] = []

    def pulled(journal: Path, lock_root: Path) -> dict[str, Any]:
        roots_seen.append(Path(lock_root))
        return {}

    monkeypatch.setattr(alerts, "pulled", pulled)
    dev = tmp_path / "dev"
    dev.mkdir()
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(dev))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    journal = tmp_path / "journal"

    assert cli("fleet", "alerts", "--journal", str(journal)) == 0
    config = tmp_path / "dev-config"
    config.mkdir()
    (config / "fleet.yaml").write_text(
        "profile: dev\nunits:\n  u:\n    address: http://localhost:8080\n"
        "    model: m\n",
        encoding="utf-8",
    )
    (config / "policy.yaml").write_text("ladder: [u]\n", encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(config))
    assert cli("fleet", "alerts", "--journal", str(journal)) == 0

    assert roots_seen == [live_root(), dev], roots_seen
