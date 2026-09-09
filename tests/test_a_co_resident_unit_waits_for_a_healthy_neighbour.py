"""Two units on one card are sequenced, and `service_started` does not sequence.

`_sequence_on_one_card` has chained co-residents since 2026-09-05 on a measured
failure: started together the 7B got 0.89 GiB of KV cache, started second it got
2.77. What the 2026-09-09 campaign then found is that the chain does not hold.
`service_started` releases the waiter as soon as the daemon has *started* the
process ahead of it — not when that process has taken its card — so the pair
still contends, the 3B crash-restarts one to two times per cold start, and
`restart: unless-stopped` hides every one of them behind a wake that merely
looks slow. The 168 s pair figure the wake budget was argued from is a wake plus
those retries, and the 86 s subtraction built on it is void.

`service_healthy` is the condition that waits for the card. It needs the service
ahead to declare a healthcheck, so these two land together or neither works.

Blast radius is deliberately small: a healthcheck is written **only** where a
`depends_on` is, which is only where two units share a card. srv1 serves one
unit and its compose file must not move.
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
    "srv1": rig("srv1", vram_mib=6144, ram_gb=48.0),
    "srv2": rig("srv2", vram_mib=12288, ram_gb=45.0),
}

FLEET = f"""
version: 1
sources:
  srv1_llamacpp:
    base_url: "http://srv1:8080"
    api: openai
    context_window: 8192
  srv2_vllm_3b:
    base_url: "http://srv2:8001"
    api: openai
    engine: vllm
    context_window: 4096
  srv2_vllm_7b:
    base_url: "http://srv2:8002"
    api: openai
    engine: vllm
    context_window: 4096
models:
  "{BIG}":
    vram_gb: 3.0
    disk_gb: 12.31
  "{THREE_B}":
    vram_gb: 3.49
    disk_gb: 2.15
    hf_cache: "{HF_CACHE}"
  "{SEVEN_B}":
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
ladder:
  tiers:
    - name: local_big
      source: srv1_llamacpp
      model: "{BIG}"
      max_parallel: 2
    - name: local_3b
      source: srv2_vllm_3b
      model: "{THREE_B}"
      max_parallel: 8
    - name: local_7b
      source: srv2_vllm_7b
      model: "{SEVEN_B}"
      max_parallel: 8
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
    srv2 = composed()["srv2"]["services"]
    waiting = {
        name: body["depends_on"] for name, body in srv2.items() if "depends_on" in body
    }
    assert waiting, "two units share srv2's card and one of them must wait"
    for name, on in waiting.items():
        for ahead, how in on.items():
            assert how == {"condition": "service_healthy"}, (
                f"{name} waits on {ahead} with {how}"
            )


def test_the_unit_that_is_waited_on_declares_a_healthcheck() -> None:
    """`service_healthy` against a service with no healthcheck never releases —
    compose treats it as an error, and the door would report NOT ANSWERING for
    a pair that was never allowed to start. The two are one change."""
    srv2 = composed()["srv2"]["services"]
    awaited = {ahead for body in srv2.values() for ahead in body.get("depends_on", {})}
    assert awaited, "something is waited on"
    for name in awaited:
        check = srv2[name].get("healthcheck")
        assert check is not None, f"{name} is waited on and declares no healthcheck"
        assert "test" in check, check
        # It must ask this unit's own port, not a default: two units on one host
        # under host networking differ only by the number.
        assert "8001" in str(check["test"]) or "8002" in str(check["test"]), check


def test_a_host_serving_one_unit_gets_neither() -> None:
    """srv1 has one unit, contends with nothing, and its compose file must not
    move. A healthcheck there would be drift with no failure behind it — and
    `emit --check` would report every single-unit rig on the fleet."""
    srv1 = composed()["srv1"]["services"]
    assert len(srv1) == 1
    only = next(iter(srv1.values()))
    assert "depends_on" not in only
    assert "healthcheck" not in only
