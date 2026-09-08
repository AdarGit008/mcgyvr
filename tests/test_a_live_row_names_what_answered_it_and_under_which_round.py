"""A live row names what answered it, what it was asked, and under which round.

``tools/bench/identity.py`` settled what a measurement records — four groups,
one block — after five lists disagreed and a manifest mutated in the sixth field
produced a byte-identical report. The product's own journal wrote none of those
names: a row said ``rung`` and ``model`` and could not be laid beside a bench
cell, because it did not say which endpoint served it, which system prompt it
carried or which product revision dispatched it. The brief (*Live journal
(WP0)*) gives each live row the identity fields it can know at dispatch time:

* ``endpoint``, ``model``, ``protocol``, ``condition == "stock"``,
  ``orchestrator``, ``rung``, ``bundle_sha256`` (the system prompt, hashed the
  way ``tools/bundle/measure.py`` hashes it) — always;
* ``round`` and ``product_sha256`` — when the process runs inside this repo
  checkout, read from ``tools/bench/product`` loaded by path the way
  ``tools/breadth/measure.py`` loads it. Off-round is NOT refused for live
  work (the reader flags it), so the digest recorded is the tree's, whether or
  not it matches the open round's pin.

Absent-is-honest applies to the last pair: an install that is not this checkout
has no round to name, and a row that carried ``round: null`` or a made-up id
would read to ``product.declare`` as a run that recorded something.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import fold, observe

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

REPO = Path(__file__).resolve().parent.parent

# RED-phase typing: ``messages`` and ``endpoint`` are the keyword arguments this
# change adds to ``observe``; the alias keeps mypy strict clean before and after.
_observe = cast("Callable[..., Any]", observe)

SYSTEM = "You are a careful worker. Answer with one fenced block."
USER = "Set VALUE to 1 in src/pkg/messy.py."
ENDPOINT = "http://localhost:8080"


def _bench_product() -> types.ModuleType:
    """``tools/bench/product.py`` by path, through the slot measure.py uses."""
    cached = sys.modules.get("bench_product")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "bench_product", REPO / "tools" / "bench" / "product.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _completion() -> Completion:
    return Completion(
        text="```python\nVALUE = 1\n```",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _record(sink: Path) -> dict[str, Any]:
    _observe(
        _completion,
        path=sink,
        attempt_id="agent-a:impl:local_qwen-7b:1",
        orchestrator="agent-a",
        rung="local_qwen-7b",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        endpoint=ENDPOINT,
    )
    (row,) = fold(path=sink)
    return row


def test_a_row_names_the_endpoint_the_model_the_protocol_and_the_condition(
    tmp_path: Path,
) -> None:
    row = _record(tmp_path / "journal" / "agent-a.jsonl")

    assert row["endpoint"] == ENDPOINT
    assert row["model"] == "qwen2.5-coder:7b"
    assert row["protocol"] == "openai"
    # Live work is the stock product, never an ablation; the field is what lets
    # a live row and a bench cell be told apart by content rather than by path.
    assert row["condition"] == "stock"
    assert row["orchestrator"] == "agent-a"
    assert row["rung"] == "local_qwen-7b"
    # The system prompt, hashed the way the bench hashes it (sha256 over utf-8).
    assert row["bundle_sha256"] == hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest()


def test_inside_the_checkout_the_row_carries_the_round_and_the_product_digest(
    tmp_path: Path,
) -> None:
    product = _bench_product()
    row = _record(tmp_path / "journal" / "agent-a.jsonl")

    assert row["round"] == product.open_round()["id"]
    # The tree's digest, not the round's pin: live work is not refused
    # off-round, so what is recorded is what actually dispatched.
    assert row["product_sha256"] == product.digest(REPO)


def test_outside_the_checkout_the_round_and_the_digest_are_absent(
    tmp_path: Path,
) -> None:
    """The same package, imported from a tree that has no ``tools/bench/product.py``.

    A copy of ``src/mcgyvr`` alone, on ``PYTHONPATH`` ahead of the editable
    install, is what a wheel install looks like from inside the process: the
    package resolves, the repo around it does not. ``cwd`` is the copy too, so a
    resolver that walked from the working directory finds no checkout either.
    """
    site = tmp_path / "elsewhere" / "src"
    shutil.copytree(
        REPO / "src" / "mcgyvr",
        site / "mcgyvr",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    sink = tmp_path / "journal" / "agent-a.jsonl"
    script = f"""
import json, sys
import mcgyvr
from pathlib import Path
from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import fold, observe

completion = Completion(
    text="x", stop_reason=StopReason.COMPLETE, raw_stop_reason="stop",
    model="m", source="workstation", protocol=Protocol.OPENAI,
    max_output_tokens=8, latency_s=0.0,
)
sink = Path({str(sink)!r})
observe(
    lambda: completion, path=sink, attempt_id="a:1", orchestrator="a", rung="r",
    messages=[{{"role": "system", "content": "s"}}, {{"role": "user", "content": "u"}}],
    endpoint="http://localhost:8080",
)
(row,) = fold(path=sink)
print(json.dumps({{"file": mcgyvr.__file__, "keys": sorted(row)}}))
"""
    env = {**os.environ, "PYTHONPATH": str(site)}
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=site.parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    # Fixture sanity: the copy is what ran, not the checkout.
    assert Path(out["file"]).is_relative_to(site), out["file"]
    assert "round" not in out["keys"], out["keys"]
    assert "product_sha256" not in out["keys"], out["keys"]
    # And the fields that need no checkout are still there.
    assert "prompt_sha256" in out["keys"]
    assert "bundle_sha256" in out["keys"]
