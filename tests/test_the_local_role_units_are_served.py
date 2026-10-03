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
from mcgyvr.serving import launch_specs, units_for

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
deployment: local-only
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


def test_a_written_width_on_the_orchestrator_wins_over_users() -> None:
    fleet = """\
users: 4
deployment: local-only
units:
  orch:
    address: http://srv1:8002
    model: small
    rig: srv1
    width: 2
    window: 8192
    launch:
      vram_gb: 2.0
      disk_gb: 2.0
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
ladder:
- orch
orchestrator:
  unit: orch
"""
    widths = {
        unit.port: unit.width.value
        for unit in units_for(parse(fleet), SCANS, specs=(), ctx_per_slot=None)
    }
    assert widths[8002] == 2


RESIDENT_RIG = {"srv1": rig("srv1", vram_mib=12288)}

# A scalar (declared) working set, so the card claim is exactly the number
# written: the orchestrator claims 6 GB, the ladder 2 GB, on a 12 GB card.
RESIDENT_FLEET = """\
users: 2
deployment: local-only
units:
  orchestrator:
    address: http://srv1:8080
    model: heavy
    rig: srv1
    window: 8192
    launch:
      vram_gb: 6.0
      disk_gb: 12.0
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
  cheap:
    address: http://srv1:8081
    model: small
    rig: srv1
    window: 4096
    launch:
      vram_gb: 2.0
      disk_gb: 2.0
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
ladder:
- cheap
orchestrator:
  unit: orchestrator
"""


def test_the_orchestrator_is_sized_first_and_the_ladder_gets_what_is_left() -> None:
    """Resident first: the orchestrator sees the whole card; the ladder the rest."""
    units = units_for(parse(RESIDENT_FLEET), RESIDENT_RIG, specs=(), ctx_per_slot=None)
    by_port = {unit.port: unit for unit in units}
    assert by_port[8080].fit.card_free_gb == 12.0
    assert by_port[8081].fit.card_free_gb == 6.0


def test_the_orchestrator_and_its_ladder_co_reside_not_alternate() -> None:
    """The orchestrator's claim is already inside the ladder's reduced figure,
    so the two are one launch spec, never mutually-exclusive alternatives."""
    units = units_for(parse(RESIDENT_FLEET), RESIDENT_RIG, specs=(), ctx_per_slot=None)
    specs = launch_specs(units)
    assert len(specs) == 1
    assert {unit.port for unit in specs[0].units} == {8080, 8081}


def _with(line: str) -> str:
    """FLEET with one ``key: value`` line set: replaced where present, else
    inserted after the ``users`` line."""
    key = line.split(":")[0]
    lines = FLEET.splitlines()
    for index, existing in enumerate(lines):
        if existing.startswith(key + ":") or existing.startswith(key + " "):
            lines[index] = line
            return "\n".join(lines) + "\n"
    for index, existing in enumerate(lines):
        if existing.startswith("users"):
            lines.insert(index + 1, line)
            return "\n".join(lines) + "\n"
    raise AssertionError("no users line to insert after")  # pragma: no cover


def test_a_local_only_chat_setup_serves_no_orchestrator() -> None:
    """Chat is a raw endpoint, so even a bound local orchestrator unit is not
    provisioned — the plan's ruling, wired into the serving plan."""
    fleet = _with("use_case: chat")
    units = units_for(parse(fleet), SCANS, specs=(), ctx_per_slot=None)
    assert 8002 not in {unit.port for unit in units}, (
        "chat provisions no orchestrator, bound or not"
    )


def test_a_hybrid_setup_serves_no_local_orchestrator() -> None:
    """Hybrid has an API-tier orchestrator, so a local orchestrator unit is not
    provisioned even when one is bound and keyless."""
    fleet = _with("deployment: hybrid")
    units = units_for(parse(fleet), SCANS, specs=(), ctx_per_slot=None)
    assert 8002 not in {unit.port for unit in units}, (
        "hybrid provisions no local orchestrator"
    )
