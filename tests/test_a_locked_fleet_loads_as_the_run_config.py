"""A fleet.yaml the lock accepts is a fleet.yaml a run can read.

``mcgyvr fleet lock`` requires every unit to carry its ``unit_id``, and
``mcgyvr.fleet.files`` accepts it. ``mcgyvr.config`` validates the same file
again for ``run``, ``pool``, ``emit`` and ``serve``; when it refuses
``unit_id``, every locked setup is unreadable by the commands that serve it —
``~/.mcgyvr/config`` with the stamped a-solo/b-small/b-big fleets failed
``mcgyvr config`` on 2026-09-14 with ``unknown key 'unit_id'``.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr import config

REPO = Path(__file__).resolve().parent.parent

FLEET = """\
profile: live
units:
  srv2_7b:
    rig: srv2
    unit_id: "unt-17f274caba402438930c0d11795adb57cfe8611ce6c23a7a42473f9bb9d20a48"
    address: http://srv2:8002
    engine: vllm
    model: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    width: 8
    window: 4096
rigs:
  srv2:
    rig_id: "rig-cbe770b55841d616363165e38553a1c7c3768250df01ead1a255f0cbdef98455"
fleets:
  b-small:
    layout: {srv2: [[srv2_7b, awake]]}
    next: []
"""
POLICY = "ladder: [srv2_7b]\n"


def test_a_unit_carrying_its_unit_id_loads() -> None:
    loaded = config.parse(FLEET, POLICY)
    unit = loaded.units["srv2_7b"]
    assert (unit.model, unit.width, unit.window) == (
        "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
        8,
        4096,
    )


def test_the_shipped_example_loads_as_the_run_config() -> None:
    fleet = (REPO / "examples" / "fleet.yaml").read_text(encoding="utf-8")
    policy = (REPO / "examples" / "policy.yaml").read_text(encoding="utf-8")
    loaded = config.parse(fleet, policy)
    assert loaded.units, "the example names no units"


def test_the_stamped_dev_setup_loads_as_the_run_config() -> None:
    fleet = (REPO / "fleet-setup" / "fleet.yaml").read_text(encoding="utf-8")
    policy = (REPO / "fleet-setup" / "policy.yaml").read_text(encoding="utf-8")
    loaded = config.parse(fleet, policy)
    assert set(loaded.ladder.names) <= set(loaded.units)
