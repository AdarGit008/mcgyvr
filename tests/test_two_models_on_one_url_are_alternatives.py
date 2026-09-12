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

When this file was written the shape was not merely unsupported, it was wrong in
two ways, both pinned below as the behaviour that had to change:

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

**What this file left open, and how the owner closed it.** A host carrying
*both* alternatives and co-residents — say two models on :8080 and a third on
:8081 that must be up alongside whichever wins — was pinned here as a refusal
that names the problem, because the third belongs in neither alternative's file
and duplicating it into both makes two files that disagree. That is the right
answer for a **partition**, and a partition is what a port gives you. Card
contention does not: owner's ruling 5 of 2026-09-09 says the mix is the normal
case under a fluid ladder, and `serving.launch_specs` answers it as a
**covering** instead — every spec is a set that can really be up, every unit is
in at least one of them, and a unit that can sit beside either alternative is
simply in both files. The refusal is gone; the test that asked for it now
asserts the covering.

**What the card sum still refuses**, since a cut is not a refusal: two units
that alternate can no longer trip it, because each is a launch spec of one and a
spec of one is skipped. Its remaining tooth is drift — a ladder sized against
one reading of a card and checked against a tighter one. `alternate` cannot see
that, because it cuts on the figure each unit recorded when it was sized
(`Fit.card_free_gb`) while `hold_together` adds them up against the scan it is
handed.
"""

from __future__ import annotations

import json
from dataclasses import replace
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


def _with_free_vram(scan: Scan, free_mib: int) -> Scan:
    """The same rig with less of its card left, which is what a second tenant is.

    A card figure is the only thing these tests vary about a host, and varying
    it in place keeps the cores, the bandwidth and the RAM identical — so a
    refusal that fires can only be about the card.
    """
    gpu = scan.gpus[0]
    return replace(
        scan, gpus=(replace(gpu, vram=replace(gpu.vram, free_mib=free_mib)),)
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
    kv_cache_dtype_k: f16
    kv_cache_dtype_v: f16
  "{LITE}":
    geometry_json: {geometry[LITE]}
    kv_cache_dtype_k: f16
    kv_cache_dtype_v: f16
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
    kv_cache_dtype_k: auto
  "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ":
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
    kv_cache_dtype_k: auto
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


#: A host that is genuinely mixed, which srv1's two llama.cpp candidates cannot
#: be: a llama.cpp unit grows to fill whatever card it is given, so two of them
#: never co-reside whatever the card is. Declared figures do not grow, so these
#: three on one 12 GiB card are the shape the refusal was written about — the
#: two 8 GiB models cannot be up together, and the 3 GiB one can be up beside
#: either of them.
SMALL = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
BIG_A = "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ"
BIG_B = "Qwen/Qwen3-14B-AWQ"

MIXED = f"""
version: 1
sources:
  srv2_small:
    base_url: "http://srv2:8001"
    api: openai
    engine: vllm
    context_window: 4096
  srv2_big_a:
    base_url: "http://srv2:8002"
    api: openai
    engine: vllm
    context_window: 4096
  srv2_big_b:
    base_url: "http://srv2:8003"
    api: openai
    engine: vllm
    context_window: 4096
models:
  "{SMALL}":
    vram_gb: 3.0
    disk_gb: 1.95
    hf_cache: "{HF_CACHE}"
    kv_cache_dtype_k: auto
  "{BIG_A}":
    vram_gb: 8.0
    disk_gb: 9.0
    hf_cache: "{HF_CACHE}"
    kv_cache_dtype_k: auto
  "{BIG_B}":
    vram_gb: 8.0
    disk_gb: 9.0
    hf_cache: "{HF_CACHE}"
    kv_cache_dtype_k: auto
ladder:
  tiers:
    - name: local_small
      source: srv2_small
      model: "{SMALL}"
      max_parallel: 8
    - name: local_big_a
      source: srv2_big_a
      model: "{BIG_A}"
      max_parallel: 8
    - name: local_big_b
      source: srv2_big_b
      model: "{BIG_B}"
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


def test_a_pair_that_will_not_sum_is_cut_into_alternatives_and_said_out_loud() -> None:
    """What the card refusal became: a cut, and a sentence about the cut.

    Two units on two ports do share a card, and a pair that will not fit it
    together used to be refused. Under the owner's ruling of 2026-09-09 the card
    is the discriminator rather than a reason to say no, so the pair is emitted
    as two launch specs — which leaves the operator holding two files where they
    had one, only one of which is ever up, decided by arithmetic they never saw.
    `hold_together` returns that sentence and `cli._emit` prints it.
    """
    tight = _with_free_vram(srv2(), 10000)
    units = units_for(parse(CO_RESIDENT), {"srv2": tight}, specs=(), ctx_per_slot=None)

    (said,) = hold_together(units, {"srv2": tight})

    assert "do not sum onto the card and were emitted as 2 alternatives" in said
    assert "compose.srv2.Qwen-Qwen2.5-Coder-3B-Instruct-AWQ.yml" in said
    assert "compose.srv2.Qwen-Qwen2.5-Coder-7B-Instruct-AWQ.yml" in said
    # The file an emit before the cut wrote, which nothing deletes and `serve
    # up` would happily start: both services, one card, and the second dies.
    assert "delete the compose.srv2.yml" in said


def test_the_card_sum_still_refuses_a_ladder_held_against_a_tighter_scan() -> None:
    """The one path alternation cannot cover, and the reason the sum is kept.

    `alternate` cuts on the card figure each unit recorded when it was sized
    (`Fit.card_free_gb`); `hold_together` adds the same units up against the
    scan it is handed. Sized against srv2's whole card the pair co-resides — one
    spec holding both — so nothing cut it, and held against a rig that has since
    had 2 GiB of something else put on it, this sum is what catches it and
    nothing else is.
    """
    units = units_for(parse(CO_RESIDENT), {"srv2": srv2()}, specs=(), ctx_per_slot=None)

    with pytest.raises(UnitError, match="one at a time and not together"):
        hold_together(units, {"srv2": _with_free_vram(srv2(), 10000)})


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


def test_a_host_that_mixes_alternatives_and_co_residents_is_covered(
    tmp_path: Path,
) -> None:
    """The refusal this file pinned, answered by the owner rather than kept.

    Two 8 GiB models that cannot be up together, and a 3 GiB one that can be up
    beside either: the third "belongs in neither alternative's file" only if the
    files are a partition of the host. `launch_specs` returns a covering, so it
    is in both — each file is a set an operator can actually bring up, and
    every unit is reachable from one of them, which is the property that matters
    because a unit no file holds is a rung mcgyvr can never start.
    """
    units = units_for(parse(MIXED), {"srv2": srv2()}, specs=(), ctx_per_slot=None)

    written = emit_all(units, root=tmp_path / "out")

    held = {
        path.name: {service["command"][0] for service in services_of(path).values()}
        for path in written
    }
    assert len(written) == 2, held
    # Every unit reachable, and the two that contend never in one file.
    assert {model for models in held.values() for model in models} == {
        SMALL,
        BIG_A,
        BIG_B,
    }, held
    assert all(not {BIG_A, BIG_B} <= models for models in held.values()), held
    # The shared unit is in both, which is the sentence the refusal denied.
    assert all(SMALL in models for models in held.values()), held


def test_the_command_writes_a_ladder_of_alternatives_rather_than_refusing_it(
    geometry: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal `emit` carried is the one this file overturns.

    ``_emit`` refused any ``base_url`` bound to more than one model — "they
    would contend for the same port. Give each model its own source on its own
    port." That advice is right for co-residents and wrong for the shape the
    ladder is now made of: two rungs on one URL are not a race to bind 8080,
    they are two things that take turns on it, and telling the owner to invent
    a second port is telling them to buy a second card. The refusals that
    remain are the ones that still mean something — the mixed host above, and
    `hold_together` for units that really do share a card.

    Driven through ``main`` rather than ``emit_all`` because the refusal was
    never in the emit layer: every unit test in this file passed while the
    command they describe exited REFUSED and wrote nothing.
    """
    from mcgyvr import scan as scan_module
    from mcgyvr.cli import main
    from mcgyvr.config import CONFIG_PATH_ENV
    from mcgyvr.exits import Exit

    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / "srv1.json").write_text(srv1().to_json(), encoding="utf-8")
    monkeypatch.setenv(scan_module.SCAN_ROOT_ENV, str(scans))

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(alternatives(geometry), encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))

    out = tmp_path / "compose"
    assert main(["emit", "--out", str(out)]) == Exit.OK
    assert {path.name for path in out.iterdir()} == {
        f"compose.srv1.{LITE}.yml",
        f"compose.srv1.{BIG}.yml",
    }

    # And the check reads the same two files. `_report_drift` listed
    # `compose.<host>.yml` from the units it was handed, which for this ladder
    # is a file name nothing ever wrote.
    assert main(["emit", "--check", "--out", str(out)]) == Exit.OK
