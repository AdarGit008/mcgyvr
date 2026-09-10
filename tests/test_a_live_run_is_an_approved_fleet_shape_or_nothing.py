"""A live run serves an approved fleet shape on its approved rigs, or refuses.

RED. ``fleet_shape`` is not a config key, ``mcgyvr.fleet.fleet_shape`` does not
exist, and the Waker wakes whatever ``serving.compose_dir`` holds. The intent is
``records/plans/fleet-identity.md``, "live and dev" and "approval".

Owner's rulings: live must run an existing approved fleet shape; approval is a
dev validation of every rig shape in it, then a commit; nothing changes on live
except a transition between approved fleet shapes, enforced where a live run acts and
not at load. Today a wake starts the one
compose file a directory holds (``src/mcgyvr/wake.py:368``), and live srv2 runs
a compose ``emit --check`` names as not what the tree emits
(flexibility-2026-09-09, Defects: "srv2's live compose is not what the tree emits") with
nothing to refuse it.
"""

from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required
from tests.test_a_sleeping_rung_is_woken_rather_than_declined import (
    RUNG_7B,
    compose_dir,
    door_log,
    ladder,
)

BASE = """version: 1
sources:
  s:
    base_url: http://srv2:8001
    api: openai
ladder:
  tiers:
    - name: r
      source: s
      model: m
"""
FSH = "fsh-" + "f" * 64
RSH_1 = "rsh-" + "1" * 64
RSH_2 = "rsh-" + "2" * 64
RIG_2 = "rig-" + "2" * 64
COMPOSE = "c" * 64


def _fleet_shape() -> Any:
    return required(
        "admit a live run only on an approved fleet shape, and approve one only "
        "on a passing validation of every rig shape in it",
        lambda: importlib.import_module("mcgyvr.fleet.fleet_shape"),
    )


def approved(tmp_path: Path) -> Path:
    where = tmp_path / "records" / "fleet"
    where.mkdir(parents=True)
    (where / f"{FSH}.json").write_text(
        json.dumps(
            {
                "fleet_shape_id": FSH,
                "rig_shapes": [
                    {
                        "rig_shape_id": RSH_2,
                        "host": "srv2",
                        "rig_id": RIG_2,
                        "compose_sha256": COMPOSE,
                        "validation": {"passed": True, "envelope": "records/x"},
                    }
                ],
                "tolerances": {},
            }
        ),
        encoding="utf-8",
    )
    return where


def test_a_live_config_without_a_fleet_shape_loads_and_cannot_act(
    tmp_path: Path,
) -> None:
    """The rule sits where a live run acts, never at load.

    ``profile`` defaults to ``live`` (``src/mcgyvr/config.py:794-795``, ruling
    R4), so a load-time refusal would refuse every config that says nothing,
    ``init`` and ``config`` included. ``fleet_shape`` is an optional key; what a
    live run without one cannot do is act — dispatch, serve, wake, sleep — and
    the refusal names the missing field.
    """
    from mcgyvr.config import ConfigSchemaError, parse

    assert parse(BASE).get("profile") == "live"
    try:
        named = parse(BASE + f"fleet_shape: {FSH}\n")
    except ConfigSchemaError as unknown:
        pytest.fail(
            f"fleet_shape must be an optional config key: {unknown}", pytrace=False
        )
    assert named.get("fleet_shape") == FSH

    fleet_shape = _fleet_shape()
    where = approved(tmp_path)
    live = {"srv2": {"rig_id": RIG_2, "compose_sha256": COMPOSE}}
    with pytest.raises(fleet_shape.LiveRefusedError, match="fleet_shape"):
        fleet_shape.admit_live(None, where, live)


def test_an_unapproved_fleet_shape_is_refused(tmp_path: Path) -> None:
    fleet_shape = _fleet_shape()
    where = approved(tmp_path)
    live = {"srv2": {"rig_id": RIG_2, "compose_sha256": COMPOSE}}
    with pytest.raises(fleet_shape.LiveRefusedError, match="not approved"):
        fleet_shape.admit_live("fsh-" + "0" * 64, where, live)


def test_a_rig_that_is_not_the_rig_it_was_approved_on_is_refused(
    tmp_path: Path,
) -> None:
    fleet_shape = _fleet_shape()
    where = approved(tmp_path)
    moved = {"srv2": {"rig_id": "rig-" + "9" * 64, "compose_sha256": COMPOSE}}
    with pytest.raises(fleet_shape.LiveRefusedError, match="srv2"):
        fleet_shape.admit_live(FSH, where, moved)


def test_a_compose_that_is_not_the_approved_one_is_refused(tmp_path: Path) -> None:
    fleet_shape = _fleet_shape()
    where = approved(tmp_path)
    drifted = {"srv2": {"rig_id": RIG_2, "compose_sha256": "d" * 64}}
    with pytest.raises(fleet_shape.LiveRefusedError, match="compose"):
        fleet_shape.admit_live(FSH, where, drifted)


def test_the_approved_fleet_shape_on_its_own_rigs_is_admitted(tmp_path: Path) -> None:
    fleet_shape = _fleet_shape()
    where = approved(tmp_path)
    live = {"srv2": {"rig_id": RIG_2, "compose_sha256": COMPOSE}}
    assert fleet_shape.admit_live(FSH, where, live) is None


def test_approval_is_refused_without_a_passing_validation_of_every_rig_shape() -> None:
    fleet_shape = _fleet_shape()
    passed = {"passed": True, "envelope": "records/evidence/x"}
    with pytest.raises(fleet_shape.ApprovalRefusedError, match=RSH_2):
        fleet_shape.approve(FSH, [RSH_1, RSH_2], {RSH_1: passed}, {})
    failed = {RSH_1: passed, RSH_2: {"passed": False, "envelope": "records/y"}}
    with pytest.raises(fleet_shape.ApprovalRefusedError, match=RSH_2):
        fleet_shape.approve(FSH, [RSH_1, RSH_2], failed, {})


def test_the_waker_does_not_wake_toward_a_shape_nobody_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused port on a live config with no approved fleet shape spawns nothing.

    The config is written here rather than through ``config_file``: this is the
    live, no-fleet-shape case itself, and it must not borrow a helper whose
    callers now declare ``profile: dev``.
    """
    from mcgyvr import wake
    from mcgyvr.config import load

    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    spawned = door_log(monkeypatch)
    specs = compose_dir(tmp_path, with_spec=True)
    config = tmp_path / "live.yaml"
    config.write_text(
        ladder(engine="vllm")
        + f"journal:\n  dir: {tmp_path / 'j'}\n"
        + f"serving:\n  enable_sleep_wake: true\n  compose_dir: {specs}\n",
        encoding="utf-8",
    )
    waker = wake.for_config(load(config))
    woke = waker.wake_for(RUNG_7B) if waker is not None else False
    assert spawned == [], f"the door was spawned toward an unapproved shape: {spawned}"
    assert woke is False
