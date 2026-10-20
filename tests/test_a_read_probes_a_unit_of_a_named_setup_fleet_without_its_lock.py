"""A read probes a unit of a named setup fleet, without its lock.

A unit newly declared in the dev setup (``fleet.yaml``) has
no measured card peak until a read loads it, and ``read --probe`` only
reached units of the fleet ``~/.mcgyvr/live.json`` names. Making a fleet live
takes a lock, and a lock takes the whole setup's dev evidence. So
``read --host H --fleet F --probe UNIT [--load WxN]`` reads fleet ``F`` from
the setup the run's config was loaded from, not from the live pointer:

* **The same refusals apply.** F must be a fleet of the setup, H a rig of its
  layout, and every probed unit awake in it on H.
* **Nothing claims to be a lock.** Every row is stamped ``locked=false`` and
  names the setup it came from. A probe's figures are filed *unjudged*,
  because there is no lock record to judge them against. The card, restarts
  and a load's peak are judged as a live read judges them, against the unit's
  declared ``room_mib`` and 0.
* **Without ``--fleet``, nothing changes**: the live fleet is read.

No rig is reached: the reading is canned text, the harness a stand-in, and
the door runs against :mod:`tests.onedoor`'s stubs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import onedoor
from tests.reads import (
    FLEET,
    FLEET_NAME,
    LOAD,
    RUN_ID,
    UNIT_3B,
    UNIT_7B,
    Rig,
    metrics,
    page,
    reading,
    rig_text,
    rows,
    unit_rows,
)


def setup_folder(tmp_path: Path) -> tuple[Path, Path]:
    """A setup holding FLEET, with no lock and no live pointer: (folder, journal)."""
    folder = tmp_path / "setup"
    folder.mkdir()
    (folder / "fleet.yaml").write_text(yaml.safe_dump(FLEET), encoding="utf-8")
    journal = tmp_path / "journal"
    policy = {"ladder": ["box2_3b", "box2_7b"], "journal": {"dir": str(journal)}}
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    assert not (Path(os.environ["HOME"]) / ".mcgyvr" / "live.json").exists()
    return folder, journal / "fleet"


def declared(folder: Path) -> dict[str, Any]:
    """The fleet declaration the setup at ``folder`` holds, as the test wrote it."""
    loaded: dict[str, Any] = yaml.safe_load(
        (folder / "fleet.yaml").read_text(encoding="utf-8")
    )
    return loaded


def record(folder: Path, text: str, rig: Rig, **more: Any) -> Any:
    from mcgyvr.fleet import read

    return read.record(
        "box2",
        *onedoor.split_reading(text),
        run_id=RUN_ID,
        probe=("box2_3b",),
        measure=rig,
        fleet_name=FLEET_NAME,
        setup=folder,
        **more,
    )


# --- resolving the named fleet -----------------------------------------------------


def test_a_named_fleet_is_read_from_the_setup_with_no_live_pointer(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import read

    folder, _ = setup_folder(tmp_path)

    fleet = read.prepare(
        "box2", ("box2_3b",), None, fleet_name=FLEET_NAME, setup=folder
    )

    assert fleet.name == FLEET_NAME
    assert fleet.folder == folder
    assert fleet.locked is False
    assert [name for name, _, _ in fleet.slots("box2")] == ["box2_3b", "box2_7b"]


def test_without_a_name_the_live_fleet_is_still_the_one_read(tmp_path: Path) -> None:
    from mcgyvr.fleet import read

    setup_folder(tmp_path)

    with pytest.raises(read.ReadError, match="live"):
        read.prepare("box2", ("box2_3b",), None)


@pytest.mark.parametrize(
    ("host", "probe", "fleet_name", "said"),
    [
        ("box2", ("box2_3b",), "no-such-fleet", "no-such-fleet"),
        ("box1", (), FLEET_NAME, "box1"),
        ("box2", ("box1_deepseek",), FLEET_NAME, "box1_deepseek"),
    ],
)
def test_a_named_fleet_keeps_the_live_reads_refusals(
    tmp_path: Path, host: str, probe: tuple[str, ...], fleet_name: str, said: str
) -> None:
    from mcgyvr.fleet import read

    folder, _ = setup_folder(tmp_path)

    with pytest.raises(read.ReadError, match=said):
        read.prepare(host, probe, None, fleet_name=fleet_name, setup=folder)


def test_a_named_fleet_needs_a_setup_to_read_it_from() -> None:
    from mcgyvr.fleet import read

    with pytest.raises(read.ReadError, match="setup"):
        read.prepare("box2", ("box2_3b",), None, fleet_name=FLEET_NAME, setup=None)


# --- what it files ------------------------------------------------------------------


def test_every_row_says_it_was_not_a_lock_and_names_its_setup(tmp_path: Path) -> None:
    folder, journal = setup_folder(tmp_path)

    record(folder, rig_text(), Rig())

    rig_id = declared(folder)["rigs"]["box2"]["rig_id"]
    filed = rows(journal)
    assert filed, "the read filed nothing"
    for row in filed:
        assert row["fleet"] == FLEET_NAME
        assert row["locked"] == "false"
        assert row["setup"] == str(folder)
        assert row["rig_id"] == rig_id, "filed under the rig id the setup declares"


def test_a_probe_with_no_lock_is_filed_unjudged_not_failed(tmp_path: Path) -> None:
    folder, journal = setup_folder(tmp_path)

    done = record(folder, rig_text(), Rig())

    assert done.failed == {}
    assert done.probed["box2_3b"]["warm_decode_tok_s"] == 126.7
    three = unit_rows(journal, UNIT_3B)
    assert three["warm_decode_tok_s"]["observed"] == 126.7
    assert three["warm_decode_tok_s"]["judged"] is False
    assert "alert" not in three["warm_decode_tok_s"]
    assert "lock" in three["warm_decode_tok_s"]["why_unjudged"]


def test_the_card_and_a_loads_peak_are_judged_against_the_declared_room(
    tmp_path: Path,
) -> None:
    folder, journal = setup_folder(tmp_path)

    done = record(folder, rig_text(card_3b=3400), Rig(), load=LOAD)

    assert done.loads["box2_3b"]["peak_mib"] == 3500
    three = unit_rows(journal, UNIT_3B)
    assert three["card_mib"]["observed"] == 3400 and three["card_mib"]["alert"] is False
    assert three["load_peak_mib"]["observed"] == 3500
    assert three["load_peak_mib"]["alert"] is False, "the peak is inside room_mib"
    assert "warm_decode_tok_s" not in unit_rows(journal, UNIT_7B)


def test_a_loads_peak_over_the_declared_room_alerts(tmp_path: Path) -> None:
    folder, journal = setup_folder(tmp_path)

    record(folder, rig_text(), Rig(load_mib=(3100, 3600)), load=LOAD)

    assert unit_rows(journal, UNIT_3B)["load_peak_mib"]["alert"] is True


# --- through the door ---------------------------------------------------------------


def test_the_door_reads_a_named_fleet_from_the_config_it_ran_under(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path, host="box2")
    folder, journal = setup_folder(tmp_path)
    reading(root, status=(f"8001,{page(metrics(0))}",))
    measured = {
        "figures": {"warm_decode_tok_s": 125.0, "prefill_tok_s": 11500.0},
        "after_page": metrics(0),
    }
    (onedoor.stubs_dir(root) / "harness.json").write_text(
        json.dumps(measured), encoding="utf-8"
    )
    env = onedoor.door_env(root)
    env["MCGYVR_CONFIG"] = str(folder)
    argv = [sys.executable, str(root / onedoor.DOOR_REL), "read"]
    argv += ["--host", "box2"]
    argv += ["--run-id", RUN_ID, "--fleet", FLEET_NAME, "--probe", "box2_3b"]

    result = subprocess.run(
        argv,
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    three = unit_rows(journal, UNIT_3B)
    assert three["warm_decode_tok_s"]["observed"] == 125.0
    assert three["warm_decode_tok_s"]["judged"] is False
    assert three["card_mib"]["locked"] == "false"
    assert "not the live lock" in result.stdout


def test_read_help_offers_the_fleet_flag(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(root / onedoor.DOOR_REL), "read", "--help"],
        cwd=root,
        env=onedoor.door_env(root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--fleet" in result.stdout
