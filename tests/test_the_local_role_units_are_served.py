"""The local role units — orchestrator and verifier — are served, not just bound.

Before the use-case expansion, `units_for` served only the ladder, so a role
bound to a local unit was sized nowhere and `emit` wrote no launch spec for it.
The ruling (increment 5c) is that both role units enter the serving plan when
they are local: the orchestrator joins the ladder as its dearest rung, and the
verifier is served beside the ladder without joining it.

The orchestrator unit's width is the user count when nobody wrote a width on
it: the slot count it is served at is `users`.
"""

from __future__ import annotations

from mcgyvr.config import parse
from mcgyvr.scan import Scan
from mcgyvr.serving import units_for

HF_CACHE = "/home/someone/.cache/huggingface"
THREE_B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"


def rig(host: str, *, vram_mib: int) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=64.0,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


SCANS = {"srv1": rig("srv1", vram_mib=16384)}


FLEET = f"""\
users: 4
units:
  cheap:
    address: http://srv1:8001
    model: '{THREE_B}'
    rig: srv1
    engine: vllm
    width: 2
    window: 4096
    hf_cache: '{HF_CACHE}'
    launch:
      kv_cache_dtype_k: auto
  orchestrator:
    address: http://srv1:8002
    model: '{SEVEN_B}'
    rig: srv1
    engine: vllm
    hf_cache: '{HF_CACHE}'
    window: 8192
    launch:
      kv_cache_dtype_k: auto
  verifier:
    address: http://srv1:8003
    model: '{THREE_B}'
    rig: srv1
    engine: vllm
    hf_cache: '{HF_CACHE}'
    window: 4096
    launch:
      kv_cache_dtype_k: auto
ladder:
- cheap
orchestrator:
  unit: orchestrator
verifier:
  enabled: true
  unit: verifier
"""


def served() -> dict[int, tuple[str, ...]]:
    """Each served unit's port → its rungs, from one config."""
    return {
        unit.port: unit.rungs
        for unit in units_for(parse(FLEET), SCANS, specs=(), ctx_per_slot=None)
    }


def test_the_local_orchestrator_unit_is_served() -> None:
    """A role bound to a local unit is brought up, not left sized nowhere."""
    assert served()[8002] == ("orchestrator",)


def test_the_local_verifier_unit_is_served_beside_the_ladder() -> None:
    assert served()[8003] == ("verifier",)


def test_the_orchestrator_units_width_is_the_user_count_when_unwritten() -> None:
    widths = {
        unit.port: unit.width.value
        for unit in units_for(parse(FLEET), SCANS, specs=(), ctx_per_slot=None)
    }
    assert widths[8002] == 4
