"""Dev and live keep separate locks, and a fleet moves one way: dev to live.

Owner, 2026-09-15: "(~/.mcgyvr/ for live), (records/fleet/ for dev) - 2
separate locks and fleets - data flows one way dev->live"; "stamped for live =
another fleet setup available for live (no overwrite, not in place of, new
folder new files)"; "~/.mcgyvr/fleets/<name>/   live can switch between fleets
runtime", with a pointer file choosing which fleet is live.

* ``mcgyvr fleet promote <fleet> --setup <dev dir>`` writes a new folder
  ``~/.mcgyvr/fleets/<fleet>/`` — ``fleet.yaml`` (profile live, that fleet's
  units, rigs and fleet block), ``policy.yaml`` (the dev policy, its ladder
  filtered to those units) and the fleet's lock and combination records. It
  refuses, writing nothing, when the folder exists, the dev lock is missing,
  the layout no longer matches its lock, or a combination record is missing.
* ``mcgyvr fleet use <fleet>`` writes ``~/.mcgyvr/live.json``; it refuses a
  fleet with no folder or whose folder no longer matches its own lock, and
  once a fleet is live, one its locked ``next`` does not list.
* The live lock root is the folder ``live.json`` names; with none there is no
  live lock. Dev reads the run root. No reader reads the working directory.
* The config is ``$MCGYVR_CONFIG``, then ``./fleet.yaml``, then the live fleet
  folder — never ``~/.mcgyvr/config``. ``mcgyvr init`` with no path writes the
  override, else the working directory.
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

from tests import livejournal as lj
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

#: The lock fixture's fleet, every unit naming a model so a folder loads.
MODELLED: dict[str, Any] = copy.deepcopy(FLEET)
for _name, _unit in MODELLED["units"].items():
    _unit.setdefault("model", f"model-{_name}")

#: The dev policy a setup directory holds: a ladder over every unit, and one
#: other key that promotion copies as it is.
SETUP_POLICY: dict[str, Any] = {"ladder": list(POLICY["ladder"]), "fanout": "idle"}

SMALLEST_FLEET = "units:\n  {name}:\n    address: http://localhost:8080\n    model: m\n"
SMALLEST_POLICY = "ladder: [{name}]\n"


def _roots() -> Any:
    return required(
        "name the lock root by profile: the live fleet folder live.json names, "
        "or the run root for dev",
        lambda: importlib.import_module("mcgyvr.fleet.roots"),
    )


def _lock() -> Any:
    return importlib.import_module("mcgyvr.fleet.lock")


def home() -> Path:
    return Path.home() / ".mcgyvr"


def fleets() -> Path:
    return home() / "fleets"


def live_json() -> Path:
    return home() / "live.json"


def name_live(fleet: str) -> None:
    live_json().parent.mkdir(parents=True, exist_ok=True)
    live_json().write_text(
        json.dumps({"fleet": fleet, "since": "2026-09-15T00:00:00+00:00"}),
        encoding="utf-8",
    )


def tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root``, by relative path, with its bytes."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def listing(root: Path) -> list[str]:
    """Every file and directory under ``root``, empty ones included."""
    if not root.exists():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def small_setup(where: Path, unit: str) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    (where / "fleet.yaml").write_text(
        SMALLEST_FLEET.format(name=unit), encoding="utf-8"
    )
    (where / "policy.yaml").write_text(
        SMALLEST_POLICY.format(name=unit), encoding="utf-8"
    )
    return where


def dev_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    locked_fleet: dict[str, Any] = MODELLED,
    file_fleet: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """A dev root holding a lock of ``locked_fleet``, and a setup directory."""
    dev = tmp_path / "dev"
    _lock().write(dev, locked_fleet, EVIDENCE, policy=POLICY, tolerances=TOLERANCES)
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(dev))
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(
        yaml.safe_dump(
            {"profile": "dev", **(locked_fleet if file_fleet is None else file_fleet)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (setup / "policy.yaml").write_text(
        yaml.safe_dump(SETUP_POLICY, sort_keys=False), encoding="utf-8"
    )
    return dev, setup


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


def flt05_records() -> tuple[str, str]:
    from mcgyvr.fleet.layout import combination_id

    cmb = combination_id(RIG2, [(U7B, "awake"), (U3B, "asleep")])
    return "records/fleet/flt-05.json", f"records/fleet/rigs/{RIG2}/{cmb}.json"


def test_the_live_lock_is_the_fleet_folder_live_json_names_and_dev_is_the_run_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots()
    monkeypatch.delenv("MCGYVR_RUN_ROOT", raising=False)
    assert roots.lock_root("live") is None, "no live.json is no live lock"
    name_live("flt-05")
    assert roots.lock_root("live") == fleets() / "flt-05"
    assert roots.lock_root("dev") == REPO
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    assert roots.lock_root("dev") == tmp_path
    with pytest.raises(ValueError, match="prod"):
        roots.lock_root("prod")


def test_the_live_waker_wakes_only_from_the_fleet_live_json_names(
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

    def wake_once() -> None:
        waker = wake.for_config(load(live))
        assert waker is not None
        waker.wake_for(RUNG_7B)

    work = tmp_path / "work"
    _lock().write(work, FLEET, EVIDENCE, policy=POLICY, tolerances=TOLERANCES)
    monkeypatch.chdir(work)
    wake_once()
    assert spawned == [], f"a lock in the working directory woke a card: {spawned}"

    folder = fleets() / "flt-05"
    _lock().write(folder, FLEET, EVIDENCE, policy=POLICY, tolerances=TOLERANCES)
    wake_once()
    assert spawned == [], f"a fleet nobody named live woke a card: {spawned}"

    name_live("flt-05")
    wake_once()
    assert len(spawned) == 1, f"the live fleet's lock woke nothing: {spawned}"


def test_gate_1_admits_a_live_serve_up_only_from_the_fleet_live_json_names(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    tolerances = {"warm_decode_class_pct": {"llamacpp": 5.0}}
    policy = {"ladder": ["a", "b"]}

    def up() -> Any:
        return onedoor.serve_door(root, "up", compose)

    _lock().write(root, SRV1_FLEET, SRV1_EVIDENCE, policy=policy, tolerances=tolerances)
    under_run_root = up()
    assert under_run_root.returncode != 0 and "gate 1:" in under_run_root.stderr, (
        "a lock under the run root admitted a live serve up.\n"
        f"stderr: {under_run_root.stderr[-1500:]}"
    )

    folder = fleets() / "flt-01"
    _lock().write(
        folder, SRV1_FLEET, SRV1_EVIDENCE, policy=policy, tolerances=tolerances
    )
    unnamed = up()
    assert unnamed.returncode != 0 and "gate 1:" in unnamed.stderr, (
        "a fleet folder nobody named live admitted a live serve up.\n"
        f"stderr: {unnamed.stderr[-1500:]}"
    )

    name_live("flt-01")
    admitted = up()
    assert admitted.returncode == 0, (admitted.stdout, admitted.stderr[-1500:])


def test_fleet_lock_writes_the_dev_root_and_refuses_anything_under_home_mcgyvr(
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
    args = ("fleet", "lock", "--fleet", str(fleet_file), "--evidence", str(evidence))

    assert cli(*args) == 0
    assert (dev / "records" / "fleet" / "flt-05.json").is_file()
    assert tree(work) == {}, "fleet lock wrote into the working directory"

    assert cli(*args, "--root", str(fleets() / "flt-05")) != 0, (
        "fleet lock wrote a lock straight into a live fleet folder"
    )
    assert listing(home()) == []


def test_promote_writes_a_new_fleet_folder_that_loads_as_a_live_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet.files import load_fleet, load_policy
    from mcgyvr.fleet.layout import layout_sha256

    dev, setup = dev_setup(tmp_path, monkeypatch)
    before = tree(dev)

    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0

    folder = fleets() / "flt-05"
    lock, record = flt05_records()
    written = tree(folder)
    assert set(written) == {"fleet.yaml", "policy.yaml", lock, record}
    assert written[lock] == before[lock]
    assert written[record] == before[record]
    assert [path.name for path in fleets().iterdir()] == ["flt-05"], (
        "promotion left something beside the folder it renamed into place"
    )

    live_fleet = load_fleet(written["fleet.yaml"].decode("utf-8"))
    assert live_fleet["profile"] == "live"
    assert set(live_fleet["units"]) == {"srv2_7b", "srv2_3b"}
    assert live_fleet["units"]["srv2_7b"]["unit_id"] == U7B
    assert live_fleet["units"]["srv2_3b"]["unit_id"] == U3B
    assert live_fleet["rigs"] == {"srv2": {"rig_id": RIG2}}
    assert live_fleet["fleets"] == {"flt-05": MODELLED["fleets"]["flt-05"]}

    policy = load_policy(written["policy.yaml"].decode("utf-8"))
    assert policy["ladder"] == ["srv2_3b", "srv2_7b"]
    assert policy["fanout"] == "idle"

    admit = required(
        "name a layout's combination ids through a public admit helper",
        lambda: importlib.import_module("mcgyvr.fleet.admit").layout_ids,
    )
    ids = admit(live_fleet, live_fleet["fleets"]["flt-05"]["layout"])
    assert layout_sha256(ids) == json.loads(before[lock])["layout_sha256"]

    assert cli("config", str(folder)) == 0
    assert tree(dev) == before, "promote wrote into the dev root"


@pytest.mark.parametrize("case", ["exists", "no-dev-lock", "layout", "missing-cmb"])
def test_promote_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    name = "flt-05"
    file_fleet: dict[str, Any] | None = None
    if case == "no-dev-lock":
        file_fleet = copy.deepcopy(MODELLED)
        file_fleet["fleets"]["flt-09"] = copy.deepcopy(MODELLED["fleets"]["flt-05"])
        name = "flt-09"
    if case == "layout":
        file_fleet = copy.deepcopy(MODELLED)
        slots = file_fleet["fleets"]["flt-05"]["layout"]["srv2"]
        file_fleet["fleets"]["flt-05"]["layout"]["srv2"] = list(reversed(slots))
    dev, setup = dev_setup(tmp_path, monkeypatch, file_fleet=file_fleet)
    if case == "missing-cmb":
        (dev / flt05_records()[1]).unlink()
    if case == "exists":
        existing = fleets() / "flt-05"
        existing.mkdir(parents=True)
        (existing / "keep.txt").write_text("mine", encoding="utf-8")
    before = (listing(home()), tree(home()))

    assert cli("fleet", "promote", name, "--setup", str(setup)) != 0
    assert (listing(home()), tree(home())) == before


def test_use_names_the_live_fleet_among_promoted_folders_and_then_along_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fleet = copy.deepcopy(MODELLED)
    fleet["fleets"]["flt-07"] = {"layout": {"srv2": copy.deepcopy(FLT02)}, "next": []}
    _dev, setup = dev_setup(tmp_path, monkeypatch, locked_fleet=fleet)

    def live() -> Any:
        return json.loads(live_json().read_text(encoding="utf-8"))

    assert cli("fleet", "use", "flt-05") != 0, "a fleet nobody promoted went live"
    assert not live_json().exists()

    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0
    assert cli("fleet", "use", "flt-05") == 0
    assert live()["fleet"] == "flt-05" and live()["since"]

    assert cli("fleet", "use", "flt-02") != 0, "an unpromoted switch target went live"
    assert cli("fleet", "promote", "flt-02", "--setup", str(setup)) == 0
    assert cli("fleet", "use", "flt-02") == 0
    assert live()["fleet"] == "flt-02"

    assert cli("fleet", "promote", "flt-07", "--setup", str(setup)) == 0
    assert cli("fleet", "use", "flt-07") != 0, "flt-02 lists no switch to flt-07"
    assert live()["fleet"] == "flt-02"


def test_use_refuses_a_folder_whose_layout_no_longer_matches_its_own_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dev, setup = dev_setup(tmp_path, monkeypatch)
    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0
    fleet_file = fleets() / "flt-05" / "fleet.yaml"
    edited = yaml.safe_load(fleet_file.read_text(encoding="utf-8"))
    slots = edited["fleets"]["flt-05"]["layout"]["srv2"]
    edited["fleets"]["flt-05"]["layout"]["srv2"] = list(reversed(slots))
    fleet_file.write_text(yaml.safe_dump(edited, sort_keys=False), encoding="utf-8")

    assert cli("fleet", "use", "flt-05") != 0
    assert not live_json().exists()


def test_fleet_alerts_reads_the_lock_root_the_profile_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import alerts

    roots_seen: list[Path | None] = []

    def pulled(journal: Path, lock_root: Path | None) -> dict[str, Any]:
        roots_seen.append(None if lock_root is None else Path(lock_root))
        return {}

    monkeypatch.setattr(alerts, "pulled", pulled)
    dev = tmp_path / "dev"
    dev.mkdir()
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(dev))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    journal = str(tmp_path / "journal")

    assert cli("fleet", "alerts", "--journal", journal) == 0
    assert roots_seen == [None], "no fleet named live is no lock to clear a pull"

    small_setup(fleets() / "flt-05", "live_unit")
    name_live("flt-05")
    assert cli("fleet", "alerts", "--journal", journal) == 0

    config = small_setup(tmp_path / "dev-config", "u")
    (config / "fleet.yaml").write_text(
        "profile: dev\n" + SMALLEST_FLEET.format(name="u"), encoding="utf-8"
    )
    monkeypatch.setenv("MCGYVR_CONFIG", str(config))
    assert cli("fleet", "alerts", "--journal", journal) == 0

    assert roots_seen == [None, fleets() / "flt-05", dev], roots_seen


def test_the_config_is_the_override_then_the_working_directory_then_the_live_fleet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.config import ConfigMissingError, config_path, load

    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    small_setup(home() / "config", "retired_unit")
    with pytest.raises(ConfigMissingError):
        load()

    folder = small_setup(fleets() / "flt-05", "live_unit")
    name_live("flt-05")
    assert config_path() == folder
    assert set(load().units) == {"live_unit"}

    small_setup(work, "cwd_unit")
    assert config_path() == work
    assert set(load().units) == {"cwd_unit"}

    named = small_setup(tmp_path / "named", "named_unit")
    monkeypatch.setenv("MCGYVR_CONFIG", str(named))
    assert config_path() == named
    assert set(load().units) == {"named_unit"}


def test_init_with_no_path_writes_the_override_or_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import cli as climod
    from mcgyvr.initialize import InitResult

    seen: list[Path] = []

    def fake_initialize(path: Path, **_: object) -> InitResult:
        seen.append(path)
        return InitResult(path=path, created=True, written=True)

    monkeypatch.setattr(climod, "initialize", fake_initialize)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    small_setup(fleets() / "flt-05", "live_unit")
    name_live("flt-05")

    assert lj.main(["init"]) == 0
    assert seen == [work], "init with no path must write the working directory"

    monkeypatch.setenv("MCGYVR_CONFIG", str(tmp_path / "named"))
    assert lj.main(["init"]) == 0
    assert seen[-1] == tmp_path / "named"


@pytest.mark.parametrize("command", ["config", "pool", "emit", "run"])
def test_every_config_help_line_names_the_live_fleet_and_not_the_retired_dir(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lj.main([command, "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "~/.mcgyvr/live.json" in out, out
    assert "~/.mcgyvr/config" not in out, out


def test_init_help_names_the_working_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lj.main(["init", "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "working directory" in out, out
    assert "~/.mcgyvr/config" not in out, out
