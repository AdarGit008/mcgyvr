"""A fleet.yaml the lock accepts is a fleet.yaml a run can read.

``mcgyvr fleet lock`` requires every unit to carry its ``unit_id``, and
``mcgyvr.fleet.files`` accepts it. ``mcgyvr.config`` validates the same file
again for ``run``, ``pool``, ``emit`` and ``serve``; if it refused
``unit_id``, every locked setup would be unreadable by the commands that serve
it.
"""

from __future__ import annotations

from mcgyvr import config
from tests._paths import REPO

FLEET = """\
profile: live
units:
  box2_7b:
    rig: box2
    unit_id: "unt-17f274caba402438930c0d11795adb57cfe8611ce6c23a7a42473f9bb9d20a48"
    address: http://box2:8002
    engine: vllm
    model: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    width: 8
    window: 4096
rigs:
  box2:
    rig_id: "rig-3333333333333333333333333333333333333333333333333333333333333333"
fleets:
  b-small:
    layout: {box2: [[box2_7b, awake]]}
    next: []
"""
POLICY = "ladder: [box2_7b]\n"


def test_a_unit_carrying_its_unit_id_loads() -> None:
    loaded = config.parse(FLEET, POLICY)
    unit = loaded.units["box2_7b"]
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
