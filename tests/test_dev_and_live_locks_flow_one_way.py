"""Dev and live keep separate locks, and a fleet moves one way: dev to live.

Owner, 2026-09-15: "(~/.mcgyvr/ for live), (records/fleet/ for dev) - 2
separate locks and fleets - data flows one way dev->live"; "stamped for live =
another fleet setup available for live (no overwrite, not in place of, new
folder new files)"; "~/.mcgyvr/fleets/<name>/   live can switch between fleets
runtime", with a pointer file choosing which fleet is live.

* :func:`mcgyvr.fleet.promote.promote` of a fleet's lock writes a new folder
  ``~/.mcgyvr/fleets/<fleet>@<lock date>/`` (owner, 2026-09-16: "all fleets
  get tagged with date"; the date is the lock's own, pinned in
  ``test_a_promoted_fleet_carries_the_date_of_its_lock_in_its_name``) —
  ``fleet.yaml`` (that fleet's units, rigs and fleet block),
  ``policy.yaml`` (the dev policy, its ladder filtered to those units) and the
  fleet's lock and combination records. It refuses, writing nothing, when the
  folder exists, the dev lock is missing, the layout no longer matches its
  lock, or a combination record is missing.
* ``mcgyvr fleet use <name>`` writes ``~/.mcgyvr/live.json``; it refuses a
  name with no folder or whose folder no longer matches its own lock. It
  switches between any verified fleet (owner, 2026-09-16), and says whether
  the move is one the live lock measured — pinned in
  ``test_use_switches_between_verified_fleets_and_says_whether_the_move_is_locked``.
* The live lock root is the folder ``live.json`` names; with none there is no
  live lock. No reader reads the working directory.
* The config is ``$MCGYVR_CONFIG``, else the live fleet folder — never
  ``./fleet.yaml`` and never ``~/.mcgyvr/config``. ``mcgyvr setup`` with no
  path stages in the override, else a folder of the run's own under the data
  folder, and never in the working directory.
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
from tests._helpers import required
from tests.doors import RUNG_7B, UNITS, compose_dir, compose_file, door_log, ladder
from tests.fleetlocks import (
    BOX1_EVIDENCE,
    BOX1_FLEET,
    EVIDENCE,
    FLEET,
    LOCK_DATE,
    MODELLED,
    POLICY,
    RIG2,
    TOLERANCES,
    U3B,
    U7B,
    cli,
    dev_setup,
    fleets,
    flt05_records,
    home,
    listing,
    live_json,
    name_live,
    promote_fleet,
    tree,
)
from tests.fleetlocks import _flow_lock as _lock

SMALLEST_FLEET = "units:\n  {name}:\n    address: http://localhost:8080\n    model: m\n"
SMALLEST_POLICY = "ladder: [{name}]\n"


def _roots() -> Any:
    return required(
        "name the live lock: the fleet folder live.json names",
        lambda: importlib.import_module("mcgyvr.fleet.roots"),
    )


def small_setup(where: Path, unit: str) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    (where / "fleet.yaml").write_text(
        SMALLEST_FLEET.format(name=unit), encoding="utf-8"
    )
    (where / "policy.yaml").write_text(
        SMALLEST_POLICY.format(name=unit), encoding="utf-8"
    )
    return where


def promoted(fleet: str) -> str:
    """The name ``fleet`` is promoted under: the fleet at the fixture's lock date."""
    return f"{fleet}@{LOCK_DATE}"


def test_the_live_lock_is_the_fleet_folder_live_json_names() -> None:
    roots = _roots()
    assert roots.live_fleet_dir() is None, "no live.json is no live lock"
    name_live("flt-05")
    assert roots.live_fleet_dir() == fleets() / "flt-05"


def test_the_live_waker_wakes_only_from_the_fleet_live_json_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import wake
    from mcgyvr.config import load

    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    spawned = door_log(monkeypatch)
    specs = compose_dir(tmp_path, with_spec=True)
    # In the config folder: held to the live lock whether or not a fleet is
    # named live (`mcgyvr.fleet.roots.runs_live`).
    live = fleets().parent / "live.yaml"
    live.parent.mkdir(parents=True, exist_ok=True)
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

    _lock().write(root, BOX1_FLEET, BOX1_EVIDENCE, policy=policy, tolerances=tolerances)
    under_run_root = up()
    assert under_run_root.returncode != 0 and "gate 1:" in under_run_root.stderr, (
        "a lock under the run root admitted a live serve up.\n"
        f"stderr: {under_run_root.stderr[-1500:]}"
    )

    folder = fleets() / "flt-01"
    _lock().write(
        folder, BOX1_FLEET, BOX1_EVIDENCE, policy=policy, tolerances=tolerances
    )
    unnamed = up()
    assert unnamed.returncode != 0 and "gate 1:" in unnamed.stderr, (
        "a fleet folder nobody named live admitted a live serve up.\n"
        f"stderr: {unnamed.stderr[-1500:]}"
    )

    name_live("flt-01")
    admitted = up()
    assert admitted.returncode == 0, (admitted.stdout, admitted.stderr[-1500:])


def test_promote_writes_a_new_fleet_folder_that_loads_as_a_live_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet.files import load_fleet, load_policy
    from mcgyvr.fleet.layout import layout_sha256

    dev, setup = dev_setup(tmp_path, monkeypatch)
    before = tree(dev)

    assert promote_fleet(dev, setup, "flt-05") == 0

    folder = fleets() / promoted("flt-05")
    lock, record = flt05_records()
    written = tree(folder)
    assert set(written) == {"fleet.yaml", "policy.yaml", lock, record}
    assert written[lock] == before[lock]
    assert written[record] == before[record]
    assert [path.name for path in fleets().iterdir()] == [promoted("flt-05")], (
        "promotion left something beside the folder it renamed into place"
    )

    live_fleet = load_fleet(written["fleet.yaml"].decode("utf-8"))
    assert set(live_fleet["units"]) == {"box2_7b", "box2_3b"}
    assert live_fleet["units"]["box2_7b"]["unit_id"] == U7B
    assert live_fleet["units"]["box2_3b"]["unit_id"] == U3B
    assert live_fleet["rigs"] == {"box2": {"rig_id": RIG2}}
    assert live_fleet["fleets"] == {"flt-05": MODELLED["fleets"]["flt-05"]}

    policy = load_policy(written["policy.yaml"].decode("utf-8"))
    assert policy["ladder"] == ["box2_3b", "box2_7b"]
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
        slots = file_fleet["fleets"]["flt-05"]["layout"]["box2"]
        file_fleet["fleets"]["flt-05"]["layout"]["box2"] = list(reversed(slots))
    dev, setup = dev_setup(tmp_path, monkeypatch, file_fleet=file_fleet)
    if case == "missing-cmb":
        (dev / flt05_records()[1]).unlink()
    if case == "exists":
        existing = fleets() / promoted("flt-05")
        existing.mkdir(parents=True)
        (existing / "keep.txt").write_text("mine", encoding="utf-8")
    before = (listing(home()), tree(home()))

    assert promote_fleet(dev, setup, name) != 0
    assert (listing(home()), tree(home())) == before


def test_use_names_the_live_fleet_among_promoted_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner, 2026-09-16: a switch outside ``next`` is no longer refused.

    That a promoted fleet outside the live lock's ``next`` may be named live
    is pinned in
    ``test_use_switches_between_verified_fleets_and_says_whether_the_move_is_locked``;
    what stays here is that only a promoted folder can be named at all.
    """
    dev, setup = dev_setup(tmp_path, monkeypatch)

    def live() -> Any:
        return json.loads(live_json().read_text(encoding="utf-8"))

    assert cli("fleet", "use", promoted("flt-05")) != 0, (
        "a fleet nobody promoted went live"
    )
    assert not live_json().exists()

    assert promote_fleet(dev, setup, "flt-05") == 0
    assert cli("fleet", "use", promoted("flt-05")) == 0
    assert live()["fleet"] == promoted("flt-05") and live()["since"]

    assert cli("fleet", "use", promoted("flt-02")) != 0, (
        "an unpromoted switch target went live"
    )
    assert promote_fleet(dev, setup, "flt-02") == 0
    assert cli("fleet", "use", promoted("flt-02")) == 0
    assert live()["fleet"] == promoted("flt-02")


def test_use_refuses_a_folder_whose_layout_no_longer_matches_its_own_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev, setup = dev_setup(tmp_path, monkeypatch)
    assert promote_fleet(dev, setup, "flt-05") == 0
    fleet_file = fleets() / promoted("flt-05") / "fleet.yaml"
    edited = yaml.safe_load(fleet_file.read_text(encoding="utf-8"))
    slots = edited["fleets"]["flt-05"]["layout"]["box2"]
    edited["fleets"]["flt-05"]["layout"]["box2"] = list(reversed(slots))
    fleet_file.write_text(yaml.safe_dump(edited, sort_keys=False), encoding="utf-8")

    assert cli("fleet", "use", promoted("flt-05")) != 0
    assert not live_json().exists()


def test_fleet_alerts_reads_the_live_fleets_lock_whatever_the_config(
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
        SMALLEST_FLEET.format(name="u"), encoding="utf-8"
    )
    monkeypatch.setenv("MCGYVR_CONFIG", str(config))
    assert cli("fleet", "alerts", "--journal", journal) == 0

    assert roots_seen == [None, fleets() / "flt-05", fleets() / "flt-05"], roots_seen


def test_the_config_is_the_override_then_the_live_fleet_and_never_the_working_dir(
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
    assert config_path() == folder, "a fleet.yaml where the command runs is not read"
    assert set(load().units) == {"live_unit"}

    named = small_setup(tmp_path / "named", "named_unit")
    monkeypatch.setenv("MCGYVR_CONFIG", str(named))
    assert config_path() == named
    assert set(load().units) == {"named_unit"}


def test_setup_with_no_path_stages_in_the_override_or_the_data_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import cli as climod
    from mcgyvr.initialize import InitResult

    seen: list[Path] = []

    def fake_initialize(path: Path, **_: object) -> InitResult:
        seen.append(path)
        return InitResult(path=path, created=True, written=True)

    monkeypatch.setattr(climod.commands.setup, "initialize", fake_initialize)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    small_setup(fleets() / "flt-05", "live_unit")
    name_live("flt-05")

    from mcgyvr.fleet.roots import data_home

    assert lj.main(["setup"]) == 0
    (staged,) = seen
    assert staged.parent == data_home() / "setup", staged
    assert list(work.iterdir()) == [], "setup wrote the working directory"

    monkeypatch.setenv("MCGYVR_CONFIG", str(tmp_path / "named"))
    assert lj.main(["setup"]) == 0
    assert seen[-1] == tmp_path / "named"


@pytest.mark.parametrize("command", ["config", "local_pool", "emit", "run"])
def test_every_config_help_line_names_the_live_fleet_and_not_the_retired_dir(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lj.main([command, "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "~/.mcgyvr/live.json" in out, out
    assert "~/.mcgyvr/config" not in out, out


def test_setup_help_names_the_staging_folder_and_never_the_working_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lj.main(["setup", "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "~/.local/state/mcgyvr/setup/<run>" in out, out
    assert "never the working directory" in out, out
    assert "~/.mcgyvr/config" not in out, out
