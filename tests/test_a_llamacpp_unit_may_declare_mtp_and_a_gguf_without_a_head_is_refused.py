"""A llama.cpp unit may declare MTP, and a GGUF without a head is refused.

Native multi-token-prediction self-speculation (``--spec-type draft-mtp``) was
measured on srv2's 12 GB card at +26.5% decode at width 1 and +22% at width 2,
acceptance ~0.90, and nothing in ``src/`` could express it
(``records/evidence/2026-08-28-mtp-ornith/README.md`` §2). The declaration is
two keys on the model block, ``speculative`` (``none`` | ``mtp``) and
``spec_draft_n_max`` (the ``--spec-draft-n-max`` the driver ran, 2), read into
:class:`~mcgyvr.serving.ModelSpec` beside ``kv_cache_dtype_k``.

* A llama.cpp unit whose geometry carries a nextn block builds, and its argv
  carries the two flags.
* A model whose scan has no ``nextn_blocks`` is refused at :func:`unit_for`
  naming the file and saying the GGUF carries no MTP head — every
  hardware-fitting stock GGUF scans 0 MTP tensors, and the head is read off
  the tensor table, never assumed from a name.
* A model nobody has scanned is refused the same way: no table, no head.
* ``speculative`` outside its two values and ``spec_draft_n_max`` below 1 are
  refused by the spec, naming the key.
* The ``launch`` block reads both keys; unset, they are ``none`` and 2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse
from mcgyvr.emit import argv
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, declared_models, unit_for

WINDOW = 4096
GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)
#: The grafted checkpoint of the evidence: block 40 is its MTP head.
KAT = "KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf"
#: A stock checkpoint: ``nextn_blocks`` is ``[]``.
STOCK = "Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"


def scanned(file: str, **declared: Any) -> ModelSpec:
    return ModelSpec(
        name=file[: -len(".gguf")],
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=GEOMETRY[file],
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
        **declared,
    )


def card() -> Scan:
    """A 12 GB card with the host memory to map either blob."""
    return Scan.of(
        host="srv2",
        vram_mib=12288,
        ram_gb=48.0,
        disk_free_gb=120.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def _contains(parts: tuple[str, ...], run: tuple[str, ...]) -> bool:
    return any(parts[i : i + len(run)] == run for i in range(len(parts)))


def test_a_spec_declares_nothing_speculative_unless_told() -> None:
    spec = scanned(STOCK)
    assert spec.speculative == "none"
    assert spec.spec_draft_n_max == 2


def test_a_grafted_gguf_may_declare_mtp_and_its_argv_says_so() -> None:
    unit = unit_for(
        card(), scanned(KAT, speculative="mtp"), width=1, ctx_per_slot=WINDOW
    )
    assert unit.args["--spec-type"] == "draft-mtp"
    assert unit.args["--spec-draft-n-max"] == "2"
    parts = argv(unit)
    assert _contains(parts, ("--spec-type", "draft-mtp"))
    assert _contains(parts, ("--spec-draft-n-max", "2"))


def test_the_declared_draft_width_reaches_the_argv() -> None:
    unit = unit_for(
        card(),
        scanned(KAT, speculative="mtp", spec_draft_n_max=3),
        width=1,
        ctx_per_slot=WINDOW,
    )
    assert unit.args["--spec-draft-n-max"] == "3"


def test_a_gguf_without_a_head_is_refused_by_file_name() -> None:
    """Stock checkpoints scan 0 MTP tensors, and a name says nothing about it."""
    with pytest.raises(UnitError) as refused:
        unit_for(card(), scanned(STOCK, speculative="mtp"), ctx_per_slot=WINDOW)
    message = str(refused.value)
    assert STOCK in message
    assert "no MTP head" in message
    assert "speculative" in message


def test_a_model_nobody_scanned_cannot_declare_mtp() -> None:
    """The head is a fact of the tensor table; without a scan there is none."""
    unscanned = ModelSpec(
        name="qwen2.5-coder-3b",
        vram_gb=2.4,
        ram_gb=0.0,
        disk_gb=2.1,
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
        speculative="mtp",
    )
    with pytest.raises(UnitError) as refused:
        unit_for(card(), unscanned, ctx_per_slot=WINDOW)
    message = str(refused.value)
    assert "qwen2.5-coder-3b.gguf" in message
    assert "no MTP head" in message


def test_a_speculative_value_this_build_does_not_know_is_refused() -> None:
    with pytest.raises(UnitError) as refused:
        scanned(KAT, speculative="eagle")
    message = str(refused.value)
    assert "models.KAT-Coder-V2.5-Dev_Q2_K-AllGPU.speculative" in message
    assert "eagle" in message
    assert "none" in message and "mtp" in message


@pytest.mark.parametrize("width", [0, -1])
def test_a_draft_width_below_one_is_refused(width: int) -> None:
    with pytest.raises(UnitError) as refused:
        scanned(KAT, speculative="mtp", spec_draft_n_max=width)
    message = str(refused.value)
    assert "spec_draft_n_max" in message
    assert str(width) in message


CONFIG = """\
units:
  head:
    address: http://srv2:8080
    engine: llama.cpp
    model: a-model
    rig: srv2
    launch:
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
      speculative: mtp
      spec_draft_n_max: 3
  plain:
    address: http://srv2:8081
    engine: llama.cpp
    model: b-model
    rig: srv2
    launch:
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
ladder:
- head
- plain
"""


def test_the_launch_block_reads_both_keys_and_defaults_the_rest() -> None:
    specs = declared_models(parse(CONFIG))
    assert specs["a-model"].speculative == "mtp"
    assert specs["a-model"].spec_draft_n_max == 3
    assert specs["b-model"].speculative == "none"
    assert specs["b-model"].spec_draft_n_max == 2
