"""A compose file is a set of units that come up together — which is not always a host.

`emit` writes one file per host, and the reason given is good: a host is what an
operator brings up, and two files for one rig would be two commands with a rule
about which comes first. That reason holds for units that *are* brought up
together — srv2's 3B and 7B share a card, and the `depends_on` inside their one
file is what sequences them. It does not hold for units that can never be up at
the same time.

Two rungs naming **one source** are two models for one process: one URL, one
port, one card. They are alternatives, and the ladder the owner wants is made of
them — srv1 alternating DeepSeek-Coder-V2-Lite with Qwen3.6-35B, srv2 its vLLM
pair with the 80B. That is "sleep funds a wake" in `records/plans/sleep-wake.md`
§17, which the design records as unbuildable *because a host holds only one
launch spec*.

Today the shape is not merely unsupported, it is wrong in two ways, both pinned
below as the behaviour that must change:

* `hold_together` sums both against the card and refuses the pair — 11.83 GiB
  against 6.00 free — for a contention that never happens;
* and if it did not refuse, `_planned` writes one file with both services on
  `--port 8080`, where the second can never bind. A silently broken file is the
  outcome the port is part of `UnitKey` to prevent.

**What this file pins**

1. Two tiers on one source are two units on one port: alternatives, not
   co-residents.
2. Each alternative is its own launch spec, `compose.<host>.<model>.yml`, one
   service per file — so the door has one file per thing it can bring up, which
   is what `serve up --compose` already takes.
3. Alternatives are never summed against the card, because only one is ever on
   it. Co-residents still are.
4. A host whose units all come up together keeps `compose.<host>.yml` exactly as
   it is. No existing fleet's files move.

**What it deliberately leaves open**, as a refusal rather than a guess: a host
carrying *both* alternatives and co-residents — say two models on :8080 and a
third on :8081 that must be up alongside whichever wins. The third belongs in
neither alternative's file and duplicating it into both makes two files that
disagree. That is an owner's decision about what a launch spec means, so the
test asks for a refusal that names the problem, and the design can answer it
later without this file having guessed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.config import parse
from mcgyvr.emit import emit_all
from mcgyvr.scan import Scan
from mcgyvr.serving import UnitError, hold_together, units_for

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)
BIG = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
LITE = "deepseek-coder-v2-16b"
HF_CACHE = "/home/someone/.cache/huggingface"


@pytest.fixture
def geometry(tmp_path: Path) -> dict[str, Path]:
    """The two srv1 candidates, each scanned into a file the config can name."""
    written = {}
    for model in (BIG, LITE):
        path = tmp_path / f"{model}.geometry.json"
        path.write_text(json.dumps(GEOMETRY[f"{model}.gguf"]), encoding="utf-8")
        written[model] = path
    return written


def srv1() -> Scan:
    return Scan.of(
        host="srv1",
        vram_mib=6144,
        ram_gb=14.2,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


def srv2() -> Scan:
    return Scan.of(
        host="srv2",
        vram_mib=12288,
        ram_gb=45.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=27.9,
    )


def alternatives(geometry: dict[str, Path]) -> str:
    """srv1's two candidates behind one URL: the owner's swap layout."""
    return f"""
version: 1
sources:
  srv1_llamacpp:
    base_url: "http://srv1:8080"
    api: openai
    context_window: 4096
models:
  "{BIG}":
    geometry_json: {geometry[BIG]}
  "{LITE}":
    geometry_json: {geometry[LITE]}
ladder:
  tiers:
    - name: local_lite
      source: srv1_llamacpp
      model: "{LITE}"
      max_parallel: 2
    - name: local_big
      source: srv1_llamacpp
      model: "{BIG}"
      max_parallel: 2
"""


CO_RESIDENT = f"""
version: 1
sources:
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
  "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ":
    vram_gb: 3.49
    disk_gb: 1.95
    hf_cache: "{HF_CACHE}"
  "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ":
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
ladder:
  tiers:
    - name: local_3b
      source: srv2_vllm_3b
      model: "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
      max_parallel: 8
    - name: local_7b
      source: srv2_vllm_7b
      model: "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
      max_parallel: 8
"""


def services_of(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8"))["services"])


def test_two_models_on_one_url_are_two_units_on_one_port(
    geometry: dict[str, Path],
) -> None:
    """The ladder implies both processes; what it does not imply is both at once."""
    units = units_for(
        parse(alternatives(geometry)), {"srv1": srv1()}, specs=(), ctx_per_slot=None
    )
    assert len(units) == 2
    assert {unit.port for unit in units} == {8080}
    assert {unit.model for unit in units} == {BIG, LITE}


def test_alternatives_are_never_summed_against_the_card(
    geometry: dict[str, Path],
) -> None:
    """They cannot contend for a card only one of them is ever on.

    `hold_together` exists because two units that *share* a card each fit alone
    and not together. Alternatives share a port, which is the opposite fact:
    the second cannot start until the first is gone, so summing them refuses a
    ladder that would have run.
    """
    units = units_for(
        parse(alternatives(geometry)), {"srv1": srv1()}, specs=(), ctx_per_slot=None
    )
    hold_together(units, {"srv1": srv1()})


def test_co_residents_are_still_summed(geometry: dict[str, Path]) -> None:
    """The check that exists keeps its teeth: two units on two ports do share a
    card, and a pair that does not fit it is still refused."""
    tight = srv2()
    from dataclasses import replace

    gpu = tight.gpus[0]
    tight = replace(tight, gpus=(replace(gpu, vram=replace(gpu.vram, free_mib=10000)),))
    units = units_for(parse(CO_RESIDENT), {"srv2": tight}, specs=(), ctx_per_slot=None)
    with pytest.raises(UnitError, match="one at a time and not together"):
        hold_together(units, {"srv2": tight})


def test_each_alternative_is_its_own_launch_spec(
    geometry: dict[str, Path], tmp_path: Path
) -> None:
    """One file per thing the door can bring up, one service in each.

    `serve up --compose <file>` takes one file and starts what is in it, so a
    file holding two services on one port is a file whose second service never
    binds. Named for the model because that is what distinguishes two units
    that agree on host, engine and port.
    """
    units = units_for(
        parse(alternatives(geometry)), {"srv1": srv1()}, specs=(), ctx_per_slot=None
    )
    written = emit_all(units, root=tmp_path / "out")

    assert len(written) == 2, written
    assert {path.name for path in written} == {
        f"compose.srv1.{LITE}.yml",
        f"compose.srv1.{BIG}.yml",
    }
    for path in written:
        services = services_of(path)
        assert len(services) == 1, (path.name, list(services))


def test_a_host_whose_units_come_up_together_keeps_its_one_file(
    tmp_path: Path,
) -> None:
    """srv2 as it stands, and every fleet emitted before this change: one file
    per host, both services in it, the `depends_on` that sequences them intact.
    Nothing on disk moves for a ladder that has no alternatives."""
    units = units_for(parse(CO_RESIDENT), {"srv2": srv2()}, specs=(), ctx_per_slot=None)
    written = emit_all(units, root=tmp_path / "out")

    assert [path.name for path in written] == ["compose.srv2.yml"]
    services = services_of(written[0])
    assert len(services) == 2, list(services)
    assert any("depends_on" in service for service in services.values()), services


def test_a_host_that_mixes_alternatives_and_co_residents_is_refused(
    geometry: dict[str, Path], tmp_path: Path
) -> None:
    """Two models on :8080 and a third on :8081 that must be up beside whichever
    wins. The third belongs in neither alternative's file, and duplicating it
    into both writes two files that disagree about what is running. Refused by
    name until the owner says what a launch spec means here — see this module's
    docstring."""
    text = f"""
version: 1
sources:
  srv1_llamacpp:
    base_url: "http://srv1:8080"
    api: openai
    context_window: 4096
  srv1_beside:
    base_url: "http://srv1:8081"
    api: openai
    context_window: 4096
models:
  "{BIG}":
    geometry_json: {geometry[BIG]}
  "{LITE}":
    geometry_json: {geometry[LITE]}
ladder:
  tiers:
    - name: local_lite
      source: srv1_llamacpp
      model: "{LITE}"
      max_parallel: 2
    - name: local_big
      source: srv1_llamacpp
      model: "{BIG}"
      max_parallel: 2
    - name: local_beside
      source: srv1_beside
      model: "{LITE}"
      max_parallel: 1
"""
    units = units_for(parse(text), {"srv1": srv1()}, specs=(), ctx_per_slot=None)
    with pytest.raises(UnitError, match="alternative"):
        emit_all(units, root=tmp_path / "out")
