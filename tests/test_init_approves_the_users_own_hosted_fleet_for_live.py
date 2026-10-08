"""``mcgyvr init`` approves the user's own fleet for live work, and no more.

A fresh ``init`` writes ``profile: live``, and live admission refuses a run
until the config folder's ``live.json`` names a promoted fleet whose lock it can
hold the rigs to. A stranger has no dev evidence to lock from, so ``init``
approves what it bound itself, through the one path live reads:

* **Only hosted units bound:** ``init`` writes a fleet folder of its own beside
  the promoted ones, ``<config folder>/fleets/own@<today>/``, holding the setup
  it wrote, a fleet ``own`` whose layout names no rig, and that fleet's lock,
  which says ``mcgyvr init`` approved it. ``live.json`` names it, as ``mcgyvr
  fleet use`` would. Live admission then admits a run without reading any rig:
  the fleet has none, and a hosted unit is not a machine of the user's.
* **A unit on a rig:** nothing is approved. A machine is approved for live work
  only by a read of it, which ``init`` does not take; ``init`` says so, and
  admission refuses as before.
* **A fleet already live** is never replaced, and an ``init`` that wrote
  nothing approves nothing.

The machines are invented; detection is substituted, so nothing is probed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.detect import Backend, Detection
from mcgyvr.fleet import admission
from mcgyvr.fleet.admit import LiveRefusedError
from mcgyvr.fleet.promote import LOCK_DIR
from mcgyvr.fleet.roots import fleets_dir, live_file, live_fleet

HOSTED = "model=hosted-model,address=http://127.0.0.1:9,api_key_env=HOSTED_KEY"
HOSTED_UNIT = "api_hosted-model"


def _found(*backends: Backend) -> Detection:
    return Detection(backends=backends, provenance={"backends": "substituted"})


#: A server on a machine of the user's, as init would find it.
LOCAL = Backend(
    name="llama.cpp",
    base_url="http://localhost:8080/v1",
    api="openai",
    models=("small-model",),
    how="substituted",
)


def _init(
    monkeypatch: pytest.MonkeyPatch,
    setup: Path,
    *flags: str,
    found: Detection,
) -> int:
    monkeypatch.setattr("mcgyvr.initialize.detect", lambda _targets: found)
    return cli.main(["init", *flags, str(setup)])


def _no_read(rig: str, run_id: str, probe: Sequence[str]) -> int:
    raise AssertionError(f"admission read {rig}, and the own fleet has no rig")


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def test_a_fresh_init_of_hosted_units_makes_its_own_fleet_live(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = tmp_path / "setup"
    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found()) == 0
    said = capsys.readouterr().out

    name = f"own@{_today()}"
    assert live_fleet() == name
    folder = fleets_dir() / name
    assert str(folder) in said and str(live_file()) in said, said

    # The setup init wrote, as a fleet whose layout names no rig.
    wrote = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert live["profile"] == "live"
    assert live["units"] == wrote["units"]
    assert live["fleets"] == {"own": {"layout": {}}}
    policy = yaml.safe_load((folder / "policy.yaml").read_text(encoding="utf-8"))
    assert policy["ladder"] == [HOSTED_UNIT]

    # The lock says who approved it: init, not dev evidence.
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["approved_by"] == "mcgyvr init"
    assert lock["next"] == [] and lock["switches"] == []

    admitted = admission.admit(reader=_no_read)
    assert admitted.fleet == "own"
    assert admitted.admitted and admitted.commands == []


def test_a_unit_on_a_rig_is_not_approved_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = tmp_path / "setup"
    found = _found(LOCAL)
    assert _init(monkeypatch, setup, "--api", HOSTED, found=found) == 0
    said = capsys.readouterr().out

    assert not live_file().exists()
    assert not fleets_dir().exists()
    assert "No fleet was made live" in said and "llama.cpp" in said, said
    with pytest.raises(LiveRefusedError, match="no fleet is live"):
        admission.admit(reader=_no_read)


def test_a_fleet_already_live_is_never_replaced_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_file().parent.mkdir(parents=True)
    pointer = json.dumps({"fleet": "elsewhere@2026-01-02", "since": "then"})
    live_file().write_text(pointer, encoding="utf-8")

    assert _init(monkeypatch, tmp_path / "setup", "--api", HOSTED, found=_found()) == 0
    said = capsys.readouterr().out

    assert live_file().read_text(encoding="utf-8") == pointer
    assert not fleets_dir().exists()
    assert "elsewhere@2026-01-02 is live" in said, said


def test_an_init_that_wrote_nothing_approves_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text("units: {}\n", encoding="utf-8")

    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found()) == 0
    capsys.readouterr()

    assert not live_file().exists()
    assert not fleets_dir().exists()
