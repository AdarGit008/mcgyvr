"""Two units on one card are sequenced, and `service_started` does not sequence.

`_sequence_on_one_card` chains co-residents, because two units started together
race for the card. A chain on
`service_started` does not hold: it releases the waiter as soon as the daemon
has *started* the process ahead of it — not when that process has taken its
card — so the pair still contends, a unit crash-restarts during a cold start,
and `restart: unless-stopped` hides every restart behind a wake that merely
looks slow.

`service_healthy` is the condition that waits for the card. It needs the service
ahead to declare a healthcheck, so these two land together or neither works.

Blast radius is deliberately small: a healthcheck is written **only** where a
`depends_on` is, which is only where two units share a card. A host serving
one unit gets neither, and its compose file must not move.
"""

from __future__ import annotations

from typing import Any

import yaml

from mcgyvr.config import parse
from mcgyvr.emit import _document
from mcgyvr.scan import Scan
from mcgyvr.serving import units_for

HF_CACHE = "/home/someone/.cache/huggingface"
THREE_B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
BIG = "Qwen3.6-35B-A3B-UD-IQ3_XXS"


def rig(host: str, *, vram_mib: int, ram_gb: float) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


SCANS = {
    "box1": rig("box1", vram_mib=6144, ram_gb=48.0),
    "box2": rig("box2", vram_mib=12288, ram_gb=45.0),
}

FLEET = f"""\
units:
  local_big:
    address: http://box1:8080
    model: '{BIG}'
    rig: box1_llamacpp
    width: 2
    window: 8192
    launch:
      vram_gb: 3.0
      disk_gb: 12.31
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
  local_3b:
    address: http://box2:8001
    model: '{THREE_B}'
    rig: box2_vllm_3b
    width: 8
    window: 4096
    engine: vllm
    hf_cache: '{HF_CACHE}'
    launch:
      vram_gb: 3.49
      disk_gb: 2.15
      kv_cache_dtype_k: auto
  local_7b:
    address: http://box2:8002
    model: '{SEVEN_B}'
    rig: box2_vllm_7b
    width: 8
    window: 4096
    engine: vllm
    hf_cache: '{HF_CACHE}'
    launch:
      vram_gb: 7.12
      disk_gb: 4.93
      kv_cache_dtype_k: auto
ladder:
- local_big
- local_3b
- local_7b
"""


def composed() -> dict[str, dict[str, Any]]:
    """Every host's compose document, by host, from one config."""
    on_host: dict[str, list[Any]] = {}
    for unit in units_for(parse(FLEET), SCANS, specs=(), ctx_per_slot=None):
        on_host.setdefault(unit.host, []).append(unit)
    return {
        host: yaml.safe_load(_document(tuple(here))) for host, here in on_host.items()
    }


def test_the_waiter_waits_for_a_healthy_neighbour_and_not_a_started_one() -> None:
    """`service_started` is what let the 3B and the 7B contend for one card.

    The daemon releases the waiter the moment the process ahead exists, which
    on this fleet is roughly a second and always long before that process has
    sized its cache off what is free."""
    box2 = composed()["box2"]["services"]
    waiting = {
        name: body["depends_on"] for name, body in box2.items() if "depends_on" in body
    }
    assert waiting, "two units share box2's card and one of them must wait"
    for name, on in waiting.items():
        for ahead, how in on.items():
            assert how == {"condition": "service_healthy"}, (
                f"{name} waits on {ahead} with {how}"
            )


def test_the_unit_that_is_waited_on_declares_a_healthcheck() -> None:
    """`service_healthy` against a service with no healthcheck never releases —
    compose treats it as an error, and the door would report NOT ANSWERING for
    a pair that was never allowed to start. The two are one change."""
    box2 = composed()["box2"]["services"]
    awaited = {ahead for body in box2.values() for ahead in body.get("depends_on", {})}
    assert awaited, "something is waited on"
    for name in awaited:
        check = box2[name].get("healthcheck")
        assert check is not None, f"{name} is waited on and declares no healthcheck"
        assert "test" in check, check
        # It must ask this unit's own port, not a default: two units on one host
        # under host networking differ only by the number.
        assert "8001" in str(check["test"]) or "8002" in str(check["test"]), check


def test_a_host_serving_one_unit_gets_neither() -> None:
    """box1 has one unit, contends with nothing, and its compose file must not
    move. A healthcheck there would be drift with no failure behind it — and
    `emit --check` would report every single-unit rig on the fleet."""
    box1 = composed()["box1"]["services"]
    assert len(box1) == 1
    only = next(iter(box1.values()))
    assert "depends_on" not in only
    assert "healthcheck" not in only
