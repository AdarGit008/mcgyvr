"""Two units alternate when their card figures will not sum, whatever ports they hold.

RED. ``serving.alternatives`` groups units by ``(host, port)`` and calls
same-port units alternatives. That catches srv1 by accident — DeepSeek-Coder-V2
and Qwen3.6 both answer on ``:8080`` — and **misses srv2 entirely**: its vLLM
pair sits on ``:8001`` and ``:8002`` and the 80B on ``:8003``, three ports that
never collide, and all three contend for one RTX 3060. That is G11a in
``records/plans/fleet-shape/evidence_and_params.md``, and it is the reason
``serving.alternatives``' own docstring already says "port is a proxy and not
the fact".

**The owner's decision, 2026-09-09: go to port-per-model, and let the port stop
carrying contention information.** Under port-per-model no port ever collides,
so a port test finds nothing and every host reads as co-residents. That is not a
loss — it proves the port was never the fact. What remains is the only thing
that was ever true:

    Two units are alternatives when their card figures will not sum onto the
    card they share.

**What this file pins**

1. Two units on **two ports** that overflow the card they share are
   alternatives: one launch spec each, and no sum against the card.
2. Two units on two ports that **do** sum onto the card are co-residents, one
   launch spec, and nothing on disk moves — the compatibility rule ``d8c5cf0a``
   established.
3. A card holding both shapes at once — srv2's real trio — is cut into the
   feasible combinations rather than into ports: the pair that fits together in
   one spec, the unit that fits alone in another, every unit reachable, and the
   file names deterministic.
4. Host RAM is the second axis and gets the same treatment: the sum runs over
   what a spec brings up together, not over what shares a port.

**What it deliberately does not pin.** Which of several maximal co-resident
subsets a fleet-shape controller should *choose* at runtime. ``emit`` writes
launch specs and stops (``mcgyvr.emit``'s own boundary); picking the resident
set from queue pressure is ``records/plans/fleet-shape/``'s and no line of it is
implemented.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse
from mcgyvr.emit import emit_all
from mcgyvr.scan import Scan
from mcgyvr.serving import UnitError, hold_together, launch_specs, units_for

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)
BIG = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
LITE = "deepseek-coder-v2-16b"
THREE_B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
EIGHTY_B = "Qwen3-Next-80B-A3B"
HF_CACHE = "/home/someone/.cache/huggingface"


@pytest.fixture
def geometry(tmp_path: Path) -> dict[str, Path]:
    """srv1's two candidates, each scanned into a file the config can name."""
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


def srv2(*, vram_mib: int = 12288, ram_gb: float = 45.0) -> Scan:
    return Scan.of(
        host="srv2",
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=27.9,
    )


def port_per_model(geometry: dict[str, Path]) -> str:
    """srv1's two candidates, each on a port of its own — and still alternating.

    This is the layout the owner ruled for. Under the port discriminator it
    reads as two co-residents on one 6 GiB card, which is 11.83 GiB asked of
    6.00 free: a fleet that runs perfectly well either way round, refused for a
    contention the port cannot see and the card can.
    """
    return f"""
version: 1
sources:
  srv1_lite:
    base_url: "http://srv1:8080"
    api: openai
    context_window: 4096
  srv1_big:
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
      source: srv1_lite
      model: "{LITE}"
      max_parallel: 2
    - name: local_big
      source: srv1_big
      model: "{BIG}"
      max_parallel: 2
"""


#: srv2 as the owner wants it: the vLLM pair, which co-reside, plus the 80B,
#: which takes the whole card. Three ports, none of them colliding. Figures are
#: the measured ones -- 3.49 and 7.12 GiB on 2026-09-05, and the 80B at the
#: 11,409 MiB two level-2 sleepers leave (``vllm-sleep-2026-09-09``).
TRIO = f"""
version: 1
sources:
  srv2_3b:
    base_url: "http://srv2:8001"
    api: openai
    engine: vllm
    context_window: 4096
  srv2_7b:
    base_url: "http://srv2:8002"
    api: openai
    engine: vllm
    context_window: 4096
  srv2_80b:
    base_url: "http://srv2:8003"
    api: openai
    engine: vllm
    context_window: 4096
models:
  "{THREE_B}":
    vram_gb: 3.49
    disk_gb: 1.95
    hf_cache: "{HF_CACHE}"
  "{SEVEN_B}":
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
  "{EIGHTY_B}":
    vram_gb: 9.5
    disk_gb: 35.67
    hf_cache: "{HF_CACHE}"
ladder:
  tiers:
    - name: local_3b
      source: srv2_3b
      model: "{THREE_B}"
      max_parallel: 8
    - name: local_7b
      source: srv2_7b
      model: "{SEVEN_B}"
      max_parallel: 8
    - name: local_80b
      source: srv2_80b
      model: "{EIGHTY_B}"
      max_parallel: 2
"""


#: The same card without the 80B: both live rigs as they stand, and every fleet
#: emitted before ``d8c5cf0a``. One file, and nothing on disk moves for it.
PAIR = (
    TRIO.replace(
        """  srv2_80b:
    base_url: "http://srv2:8003"
    api: openai
    engine: vllm
    context_window: 4096
""",
        "",
    )
    .replace(
        f"""  "{EIGHTY_B}":
    vram_gb: 9.5
    disk_gb: 35.67
    hf_cache: "{HF_CACHE}"
""",
        "",
    )
    .replace(
        f"""    - name: local_80b
      source: srv2_80b
      model: "{EIGHTY_B}"
      max_parallel: 2
""",
        "",
    )
)

#: Two units that fit the card together and cannot both have the host's memory:
#: 3.0 + 3.0 GiB onto 12.0 free, against 6.5 + 6.5 GiB of spilled experts and
#: 2.0 GiB of :data:`REFUSAL_RAM_HEADROOM_GB` on 14.2 available. The card is not
#: the only thing two co-residents share (owner's ruling, 2026-09-09).
SPILLING = """
version: 1
sources:
  careful:
    base_url: "http://srv2:8001"
    api: openai
    context_window: 4096
  quick:
    base_url: "http://srv2:8002"
    api: openai
    context_window: 4096
models:
  careful-16b:
    vram_gb: 3.0
    ram_gb: 6.5
    disk_gb: 14.0
  quick-16b:
    vram_gb: 3.0
    ram_gb: 6.5
    disk_gb: 14.0
ladder:
  tiers:
    - name: local_careful
      source: careful
      model: careful-16b
    - name: local_quick
      source: quick
      model: quick-16b
"""


def models_of(spec: Any) -> set[str]:
    return {unit.model for unit in spec.units}


def test_two_ports_that_overflow_one_card_are_alternatives(
    geometry: dict[str, Path],
) -> None:
    """The port says co-resident, the card says take turns, and the card is right.

    Nothing about these two units collides: two sources, two ports, two
    processes. What they cannot both have is the 6 GiB card, and that is the
    only fact that was ever load-bearing.
    """
    units = units_for(
        parse(port_per_model(geometry)), {"srv1": srv1()}, specs=(), ctx_per_slot=None
    )
    assert sorted(unit.port for unit in units) == [8080, 8081]

    specs = launch_specs(units)

    assert len(specs) == 2, [models_of(spec) for spec in specs]
    assert [models_of(spec) for spec in specs].count({BIG}) == 1
    assert [models_of(spec) for spec in specs].count({LITE}) == 1


def test_alternatives_on_two_ports_are_not_summed_against_the_card(
    geometry: dict[str, Path],
) -> None:
    """A contention that cannot happen must not be priced.

    11.83 GiB against 6.00 free is the refusal the port discriminator produced
    for srv1 the moment its two models were given ports of their own — a ladder
    either half of which serves perfectly well.
    """
    units = units_for(
        parse(port_per_model(geometry)), {"srv1": srv1()}, specs=(), ctx_per_slot=None
    )

    hold_together(units, {"srv1": srv1()})


def test_a_card_that_holds_both_shapes_is_cut_into_the_sets_that_fit_it() -> None:
    """srv2's real trio: the pair that fits together, and the one that does not.

    3.49 + 7.12 = 10.61 GiB onto 11.63 free, so the vLLM pair is one launch spec
    and keeps the ``depends_on`` that sequences it. The 80B is 9.5 and fits
    beside neither, so it is a spec of its own. Three ports, no collision, and
    the port discriminator sees one host of three co-residents asking 21.75 GiB
    of a 12 GiB card.
    """
    units = units_for(parse(TRIO), {"srv2": srv2()}, specs=(), ctx_per_slot=None)
    assert sorted(unit.port for unit in units) == [8001, 8002, 8003]

    specs = launch_specs(units)

    assert sorted(sorted(models_of(spec)) for spec in specs) == sorted(
        [sorted({THREE_B, SEVEN_B}), sorted({EIGHTY_B})]
    ), [models_of(spec) for spec in specs]
    assert all(spec.host == "srv2" for spec in specs)
    assert all(spec.model is not None for spec in specs), (
        "a host whose units do not all come up together has no whole-host "
        "launch spec, so every one of its specs needs a name of its own"
    )


def test_every_unit_of_such_a_card_is_reachable_from_some_launch_spec() -> None:
    """The cut is a covering, not a partition, and nothing may fall out of it.

    A unit in no launch spec is a rung mcgyvr can never bring up: the door takes
    one file and starts what is in it, so a unit no file holds is a config lie
    exactly as a rung bound to an unbound port is.
    """
    units = units_for(parse(TRIO), {"srv2": srv2()}, specs=(), ctx_per_slot=None)

    covered = {unit.key.slug for spec in launch_specs(units) for unit in spec.units}

    assert covered == {unit.key.slug for unit in units}


def test_the_cut_is_deterministic_and_so_are_the_files_it_writes(
    tmp_path: Path,
) -> None:
    """``emit --check`` compares bytes, so the same config must give the same bytes.

    Two calls over one config, and the file names as well as their contents have
    to agree. A cut that enumerated feasible sets in whatever order a set
    iterated would produce a different file name per run, and ``emit --check``
    would report drift against a config nobody had touched.
    """
    units = units_for(parse(TRIO), {"srv2": srv2()}, specs=(), ctx_per_slot=None)

    first = emit_all(units, root=tmp_path / "one")
    second = emit_all(units, root=tmp_path / "two")

    assert [path.name for path in first] == [path.name for path in second]
    assert [path.read_text(encoding="utf-8") for path in first] == [
        path.read_text(encoding="utf-8") for path in second
    ]
    assert len(first) == 2, [path.name for path in first]
    services = [
        len(__import__("yaml").safe_load(path.read_text(encoding="utf-8"))["services"])
        for path in first
    ]
    assert sorted(services) == [1, 2], services


def test_a_host_whose_units_all_co_reside_still_writes_one_file(
    tmp_path: Path,
) -> None:
    """The compatibility rule ``d8c5cf0a`` established, restated on the new axis.

    Nothing on disk moves for a fleet whose units fit the card together. srv2's
    pair without the 80B is that fleet, and it is what both live rigs are today.
    """
    units = units_for(parse(PAIR), {"srv2": srv2()}, specs=(), ctx_per_slot=None)

    written = emit_all(units, root=tmp_path / "out")

    assert [path.name for path in written] == ["compose.srv2.yml"], written


def test_host_ram_is_summed_over_what_a_spec_brings_up_together() -> None:
    """The second axis, and it gets the same treatment as the first.

    RAM is per host and VRAM is per card, but both are summed over the units a
    launch spec brings up *together* rather than over the units that share a
    port. These two fit the card together — 3.0 + 3.0 onto 12.0 — so they are
    one launch spec, and the spilling experts they each allocate are then asked
    of one ``MemAvailable`` at once. That is the sum ``6a2e80d4`` landed, and
    what moves under this change is only which units it is taken over.
    """
    units = units_for(
        parse(SPILLING), {"srv2": srv2(ram_gb=14.2)}, specs=(), ctx_per_slot=None
    )

    with pytest.raises(UnitError, match="fit host memory one at a time"):
        hold_together(units, {"srv2": srv2(ram_gb=14.2)})


def test_a_card_nobody_measured_claims_nothing_about_who_alternates() -> None:
    """A unit sized against no card is left where it has always been: co-resident.

    ``fit`` records the free VRAM it judged against so that the cut needs no
    second scan — which is what keeps ``emit_all`` a function of its units. A
    unit built by hand, with no figure recorded, is not evidence that two units
    conflict, and inventing a conflict there would move files for every fleet
    whose units were never sized.
    """
    units = units_for(parse(TRIO), {"srv2": srv2()}, specs=(), ctx_per_slot=None)
    blind = tuple(
        replace(unit, fit=replace(unit.fit, card_free_gb=0.0)) for unit in units
    )

    specs = launch_specs(blind)

    assert len(specs) == 1 and specs[0].model is None, specs
