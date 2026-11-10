"""One token of cache is priced by one function, whichever door a model enters by.

The shipped catalog states ``kv_bytes_per_token`` at f16, a rig's hello states it
at the cache type the pool runs heads with (q8_0), and the sizer charges a run
its cache at the run's own types. All three read the scan's ``kv_layers`` and
all three now price them through :func:`vramfit.cache_bytes_per_token`: the
catalog and the hello charge every caching layer the full context, and the
sizer charges the rows that do not slide the full context and the sliding rows
their window, which it counts in cells rather than tokens.

So for one model at one cache type the three agree: on a model with no sliding
layer the sizer's cache is the context times the catalog's (or the hello's)
figure; on a sliding model it is that with ``swa_full``, and below it without,
by exactly the window discount the per-token figures do not take.

The reference sums here are the header's own element counts times the bytes an
element costs at each type (f16 two bytes, q8_0 34 bytes a 32-element block),
not the code under test.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from mcgyvr.knowledge import hub
from mcgyvr.rig import inventory
from mcgyvr.serving import vramfit
from tests._paths import TESTS

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (TESTS / "fixtures" / "gguf_geometry.json").read_text()
)
NO_SLIDING = "deepseek-coder-v2-16b.gguf"
SLIDING = "gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf"


def elements(rows: list[dict[str, Any]]) -> int:
    return sum(r["k_elems"] + r["v_elems"] for r in rows)


@pytest.mark.parametrize("name", sorted(GEOMETRY))
def test_the_catalog_and_the_hello_state_the_one_per_token_figure(name: str) -> None:
    row = GEOMETRY[name]
    rows = row["kv_layers"]
    assert hub._kv_bytes_per_token(row) == elements(rows) * 2
    assert inventory.kv_bytes_per_token(row, "q8_0") == math.ceil(
        elements(rows) * 34 / 32
    )
    for kv_type in ("f16", "q8_0"):
        shared = vramfit.cache_bytes_per_token(
            rows, cache_type_k=kv_type, cache_type_v=kv_type
        )
        assert inventory.kv_bytes_per_token(row, kv_type) == math.ceil(shared)
    assert hub._kv_bytes_per_token(row) == math.ceil(
        vramfit.cache_bytes_per_token(rows, cache_type_k="f16", cache_type_v="f16")
    )


@pytest.mark.parametrize("kv_type", ["f16", "q8_0"])
@pytest.mark.parametrize("n_ctx", [4096, 32768])
def test_without_a_sliding_layer_the_sizer_charges_context_times_that_figure(
    kv_type: str, n_ctx: int
) -> None:
    geometry = GEOMETRY[NO_SLIDING]
    per_token = vramfit.cache_bytes_per_token(
        geometry["kv_layers"], cache_type_k=kv_type, cache_type_v=kv_type
    )
    sized = vramfit.kv_bytes(
        geometry, n_ctx, cache_type_k=kv_type, cache_type_v=kv_type
    )
    assert sized["swa"] == 0
    assert sized["total"] == int(n_ctx * per_token)
    if kv_type == "f16":
        assert sized["total"] == n_ctx * hub._kv_bytes_per_token(geometry)
    hello = inventory.kv_bytes_per_token(geometry, kv_type)
    assert hello is not None and hello * n_ctx - sized["total"] < n_ctx


def test_a_sliding_model_agrees_at_swa_full_and_is_discounted_by_its_window() -> None:
    geometry = GEOMETRY[SLIDING]
    rows = geometry["kv_layers"]
    n_ctx = 32768
    catalog = hub._kv_bytes_per_token(geometry)

    whole = vramfit.kv_bytes(geometry, n_ctx, swa_full=True)
    assert whole["total"] == n_ctx * catalog

    windowed = vramfit.kv_bytes(geometry, n_ctx)
    full_rows = [r for r in rows if not r["is_swa"]]
    sliding_rows = [r for r in rows if r["is_swa"]]
    assert windowed["non_swa"] == n_ctx * elements(full_rows) * 2
    assert windowed["swa"] == windowed["cells_swa"] * elements(sliding_rows) * 2
    assert windowed["cells_swa"] < n_ctx
    assert whole["total"] - windowed["total"] == (
        (n_ctx - windowed["cells_swa"]) * elements(sliding_rows) * 2
    )


def test_the_full_and_sliding_sums_make_up_every_row() -> None:
    rows = GEOMETRY[SLIDING]["kv_layers"]
    every, full, sliding = (
        vramfit.cache_bytes_per_token(
            rows, cache_type_k="q8_0", cache_type_v="f16", only=side
        )
        for side in (None, "full", "sliding")
    )
    assert full > 0 and sliding > 0
    assert full + sliding == every


def test_a_row_without_element_counts_or_an_unstated_slide_is_refused() -> None:
    with pytest.raises(ValueError, match="element counts"):
        vramfit.cache_bytes_per_token(
            [{"layer": 0, "k_elems": 512}], cache_type_k="f16", cache_type_v="f16"
        )
    unstated = GEOMETRY["gpt-oss-20b-MXFP4.gguf"]["kv_layers"]
    assert (
        vramfit.cache_bytes_per_token(unstated, cache_type_k="f16", cache_type_v="f16")
        == elements(unstated) * 2
    )
    with pytest.raises(ValueError, match="slides"):
        vramfit.cache_bytes_per_token(
            unstated, cache_type_k="f16", cache_type_v="f16", only="full"
        )
    assert hub._kv_bytes_per_token({"kv_layers": [{"layer": 0}]}) == 0
    assert inventory.kv_bytes_per_token({"kv_layers": [{"layer": 0}]}, "q8_0") is None
