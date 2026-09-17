"""A tagged live fleet is admitted, read and emitted as its layout.

Owner, 2026-09-16: a promoted fleet is ``<fleet>@<lock date>``. The tag lives
in the folder's name and in ``~/.mcgyvr/live.json``; inside the folder the
fleet is keyed by its plain name, and so is everything derived from it. So a
live read of ``b-small@2026-09-13``:

* resolves to the layout ``b-small`` — ``read.live()``, ``probe._live`` and
  ``admission.admit`` all name that layout, and the lock they hold it to is
  ``records/fleet/b-small.json`` in the tagged folder;
* is the config ``mcgyvr`` finds with nothing else named (``config_path``);
* emits ``compose.<rig>.b-small.yml``, the same file names a plain ``b-small``
  emits, with each container named as the unit states — the door's
  ``door_commands`` name those same files;
* runs: ``mcgyvr run`` under the tagged live fleet is admitted by a read of its
  rigs and dispatched, exactly as under a plain name.
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import livejournal as lj
from tests.test_a_live_run_is_admitted_only_by_a_read_of_its_rigs import (
    EVIDENCE,
    FIRST,
    FLEET_NAME,
    SECOND,
    TOLERANCES,
    FakeDoor,
    climb,
    dispatched,
    fleet,
)

TAGGED = f"{FLEET_NAME}@2026-09-13"


def home() -> Path:
    return Path(os.environ["HOME"])


@pytest.fixture
def events() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def door(monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, str]]) -> FakeDoor:
    """The admission test's door: the CLI's ``read`` files what the reader would."""
    import mcgyvr.wake as wake
    from mcgyvr.fleet import read

    fake = FakeDoor(events)
    monkeypatch.setattr(read, "spawn_read", fake.spawn)

    def no_plan_is_carried_out(argv: Sequence[str], **_: object) -> int:
        raise AssertionError(f"a plan was carried out through the door: {argv}")

    monkeypatch.setattr(wake, "spawn_door", no_plan_is_carried_out)
    return fake


def launchable() -> dict[str, Any]:
    """The admission fixture's fleet, each unit stating what a locked emit renders."""
    doc = copy.deepcopy(fleet("live"))
    doc["units"][FIRST] |= {
        "image": "vllm/vllm-openai@sha256:" + "a" * 64,
        "hf_cache": "/home/x/.cache/huggingface",
        "launch": {"argv": ["--model", "m"], "env": {}},
    }
    doc["units"][SECOND] |= {
        "image": "llamacpp:b10644",
        "launch": {
            "argv": ["--model", "/models/d.gguf"],
            "env": {},
            "volumes": ["/home/x/models:/models:ro"],
        },
    }
    return doc


def go_live_tagged(tmp_path: Path) -> Path:
    from mcgyvr.fleet import lock

    folder = home() / ".mcgyvr" / "fleets" / TAGGED
    folder.mkdir(parents=True)
    doc = launchable()
    (folder / "fleet.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    policy = {"ladder": [FIRST, SECOND], "journal": {"dir": str(tmp_path / "journal")}}
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(folder, doc, EVIDENCE, tolerances=TOLERANCES)
    (home() / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": TAGGED}), encoding="utf-8"
    )
    return folder


def test_the_live_fleet_reads_as_its_layout_from_its_tagged_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.config import config_path
    from mcgyvr.fleet import read
    from mcgyvr.fleet.alerts import live_pulled_units
    from mcgyvr.fleet.probe import _live
    from mcgyvr.fleet.roots import live_fleet, live_fleet_dir, lock_root

    folder = go_live_tagged(tmp_path)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    assert live_fleet() == TAGGED
    assert live_fleet_dir() == folder and lock_root("live") == folder
    assert config_path() == folder

    live = read.live()
    assert (live.name, live.folder) == (FLEET_NAME, folder)
    assert live.combination("srv2") and live.slots("srv1")[0][0] == SECOND
    assert _live(None)[0] == FLEET_NAME
    assert live_pulled_units() == {}


def test_the_tagged_fleet_is_admitted_against_its_own_lock_and_named_by_its_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, door: FakeDoor
) -> None:
    from mcgyvr.fleet.admission import admit, door_commands
    from mcgyvr.fleet.admit import Plan
    from mcgyvr.serving import spec_name

    go_live_tagged(tmp_path)
    monkeypatch.chdir(tmp_path)

    admission = admit(door.spawn)
    assert admission.fleet == FLEET_NAME and admission.admitted, admission
    assert sorted(host for host, _ in door.calls) == ["srv1", "srv2"]

    live = launchable()
    plan = Plan(clean=[("srv2", "mcgyvr-srv2-stray")], restore=[])
    (line,) = door_commands(live, FLEET_NAME, plan)
    assert spec_name("srv2", FLEET_NAME) in line
    assert TAGGED not in line, "the compose file is named by the layout, not the tag"


def test_emit_under_the_tagged_live_fleet_writes_the_layouts_files_and_containers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.serving import spec_name

    go_live_tagged(tmp_path)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "compose"

    assert lj.main(["emit", "--out", str(out)]) == 0, capsys.readouterr().err

    written = sorted(path.name for path in out.iterdir())
    assert written == sorted(spec_name(h, FLEET_NAME) for h in ("srv1", "srv2"))
    srv2 = yaml.safe_load((out / spec_name("srv2", FLEET_NAME)).read_text("utf-8"))
    assert srv2["services"][FIRST]["container_name"] == "mcgyvr-srv2-3b"
    srv1 = yaml.safe_load((out / spec_name("srv1", FLEET_NAME)).read_text("utf-8"))
    assert srv1["services"][SECOND]["container_name"] == "mcgyvr-srv1-deepseek"
    for document in (srv1, srv2):
        assert TAGGED not in yaml.safe_dump(document)


def test_a_live_run_under_the_tagged_fleet_is_admitted_then_dispatched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live_tagged(tmp_path)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)

    code, err = climb(tmp_path, monkeypatch, capsys, events, "tagged")

    assert code == 0, err
    assert sorted(host for host, _ in door.calls) == ["srv1", "srv2"], door.calls
    assert dispatched(events), events
    assert "refused" not in err
