"""A probe keeps every sample it took beside the median it is judged by.

Owner ruling N7, 2026-09-15: keep the raw samples. The srv1 CPU-experts prefill
tolerance is re-derived by the M1 rule, which needs every single sample, not
only the median.

* :func:`mcgyvr.fleet.harness.measure_vllm` and
  :func:`mcgyvr.fleet.harness.measure_llamacpp`, asked ``with_samples=True``,
  return ``decode_samples`` and ``prefill_samples`` — every sample, a float, in
  the order it was taken — beside ``warm_decode_tok_s`` and ``prefill_tok_s``.
  Asked nothing, they return the two medians alone, which is what
  ``mcgyvr fleet probe`` (:mod:`mcgyvr.fleet.probe`) reads.
* A probe still takes ``DECODE_SAMPLES`` (5) decodes and ``PREFILL_SAMPLES`` (3)
  prefills and sends no extra request; each median is its samples' median.
* :func:`mcgyvr.fleet.harness.on_the_rig`, which ``read --probe`` runs on the rig,
  carries the samples in its figures.
* :func:`mcgyvr.fleet.read.record` files them on the unit's rows as
  ``decode_samples`` and ``prefill_samples``, unjudged. The medians are judged
  exactly as before, and the rig row's ``probed`` stays the medians.

No rig is reached: the units are fakes, and the harness runs against a server on
127.0.0.1.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests.test_a_read_measures_before_it_judges_and_loads_a_unit import rig_text
from tests.test_a_rig_is_read_through_the_door_without_leasing_it import (
    HARNESS_PY,
    RUN_ID,
    UNIT_3B,
    _Unit,
    go_live,
    metrics,
    rig_row,
    unit_rows,
)

DECODE = [120.0, 130.0, 125.0, 128.0, 122.0]
PREFILL = [11000.0, 11600.0, 11400.0]
#: A llama.cpp unit with experts on the CPU, prefill slower than decode is fast.
LLAMA_DECODE = [32.1, 33.0, 32.56, 31.9, 32.8]
LLAMA_PREFILL = [300.0, 310.0, 295.0]


class VllmFace:
    """A vLLM unit whose i-th decode and prefill run at the rates given."""

    def __init__(self, decode: list[float], prefill: list[float]) -> None:
        self.decode = list(decode)
        self.prefill = list(prefill)
        self.now = 0.0
        self.asked: list[int] = []

    def clock(self) -> float:
        return self.now

    def get(self, url: str, timeout: float) -> Any:
        return {"data": [{"id": "m"}]}

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        self.asked.append(int(payload["max_tokens"]))
        if payload["max_tokens"] == 256:
            self.now += 256 / self.decode.pop(0)
            return {"usage": {"completion_tokens": 256, "prompt_tokens": 20}}
        if payload["max_tokens"] == 16:
            self.now += 1960 / self.prefill.pop(0)
            return {"usage": {"completion_tokens": 16, "prompt_tokens": 1960}}
        self.now += 0.5
        return {"usage": {"completion_tokens": 64, "prompt_tokens": 20}}


class LlamaFace:
    """A llama.cpp unit whose i-th decode and prefill report the rates given."""

    def __init__(self, decode: list[float], prefill: list[float]) -> None:
        self.decode = list(decode)
        self.prefill = list(prefill)
        self.asked: list[int] = []

    def get(self, url: str, timeout: float) -> Any:
        raise AssertionError(f"a llama.cpp probe reads nothing by GET: {url}")

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        self.asked.append(int(payload["n_predict"]))
        if payload["n_predict"] == 256:
            return {"timings": {"predicted_per_second": self.decode.pop(0)}}
        if payload["n_predict"] == 16:
            return {"timings": {"prompt_per_second": self.prefill.pop(0)}}
        return {"timings": {"predicted_per_second": 1.0}}


def test_measure_vllm_keeps_every_sample_in_order_beside_its_median() -> None:
    from mcgyvr.fleet import harness

    face = VllmFace(DECODE, PREFILL)
    figures = harness.measure_vllm(
        "http://127.0.0.1:1", face, face.clock, with_samples=True
    )

    assert figures["decode_samples"] == pytest.approx(DECODE)
    assert figures["prefill_samples"] == pytest.approx(PREFILL)
    assert all(isinstance(s, float) for s in figures["decode_samples"])
    assert figures["warm_decode_tok_s"] == pytest.approx(statistics.median(DECODE))
    assert figures["prefill_tok_s"] == pytest.approx(statistics.median(PREFILL))
    assert (harness.DECODE_SAMPLES, harness.PREFILL_SAMPLES) == (5, 3)
    assert face.asked == [64] + [256] * 5 + [16] * 3, "no extra request"

    plain = VllmFace(DECODE, PREFILL)
    medians = harness.measure_vllm("http://127.0.0.1:1", plain, plain.clock)
    assert set(medians) == {"warm_decode_tok_s", "prefill_tok_s"}


def test_measure_llamacpp_keeps_every_sample_in_order_beside_its_median() -> None:
    from mcgyvr.fleet import harness

    face = LlamaFace(LLAMA_DECODE, LLAMA_PREFILL)
    figures = harness.measure_llamacpp("http://127.0.0.1:1", face, with_samples=True)

    assert figures["decode_samples"] == pytest.approx(LLAMA_DECODE)
    assert figures["prefill_samples"] == pytest.approx(LLAMA_PREFILL)
    assert all(isinstance(s, float) for s in figures["prefill_samples"])
    assert figures["warm_decode_tok_s"] == pytest.approx(32.56)
    assert figures["prefill_tok_s"] == pytest.approx(300.0)
    assert face.asked == [64] + [256] * 5 + [16] * 3, "no extra request"

    plain = LlamaFace(LLAMA_DECODE, LLAMA_PREFILL)
    medians = harness.measure_llamacpp("http://127.0.0.1:1", plain)
    assert set(medians) == {"warm_decode_tok_s", "prefill_tok_s"}


def test_the_harness_on_the_rig_carries_every_sample_in_its_figures() -> None:
    """``harness.py`` as ``read --probe`` runs it: ``python3 -``, isolated."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Unit)
    _Unit.seen = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec = json.dumps({"engine": "vllm", "port": server.server_address[1]})
        done = subprocess.run(
            [sys.executable, "-I", "-", "mcgyvr-harness", spec],
            input=HARNESS_PY.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    figures = json.loads(done.stdout)["figures"]
    assert len(figures["decode_samples"]) == 5
    assert len(figures["prefill_samples"]) == 3
    assert figures["warm_decode_tok_s"] == statistics.median(figures["decode_samples"])
    assert figures["prefill_tok_s"] == statistics.median(figures["prefill_samples"])


def test_a_read_files_every_sample_on_the_units_rows_unjudged(tmp_path: Path) -> None:
    from mcgyvr.fleet import read

    journal = go_live(tmp_path)
    decode = [126.1, 127.4, 126.7, 125.9, 128.0]
    prefill = [11480.0, 11500.0, 11620.0]

    def measure(unit: str, spec: str) -> str:
        figures = {
            "warm_decode_tok_s": 126.7,
            "prefill_tok_s": 11500.0,
            "decode_samples": decode,
            "prefill_samples": prefill,
        }
        return json.dumps({"figures": figures, "after_page": metrics(0)})

    done = read.record(
        "srv2",
        rig_text(),
        run_id=RUN_ID,
        profile="live",
        probe=("srv2_3b",),
        measure=measure,
    )

    rows = unit_rows(journal, UNIT_3B)
    assert rows["decode_samples"]["observed"] == decode
    assert rows["prefill_samples"]["observed"] == prefill
    assert "alert" not in rows["decode_samples"]
    assert "alert" not in rows["prefill_samples"]
    assert rows["warm_decode_tok_s"]["observed"] == 126.7
    assert rows["warm_decode_tok_s"]["alert"] is False
    assert rows["prefill_tok_s"]["alert"] is False
    medians = {"warm_decode_tok_s": 126.7, "prefill_tok_s": 11500.0}
    assert done.probed["srv2_3b"] == medians
    assert rig_row(journal)["probed"]["srv2_3b"] == medians, (
        "mcgyvr fleet probe reads the rig row's probed figures as floats"
    )
