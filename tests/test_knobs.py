"""The knob surface (#357): three columns, five states, every cell cited.

What these pin:

- A refusal with its reason, a refusal whose reason the harness lost, a
  harness defect that mangled the value, and a declared-but-untried flag are
  four different facts and never share a label. The 2026-08-24 sweep's own
  stage 1 wrote three untested cells per rig as "refused"; the surface reads
  those same records and calls them what they are.
- The effective column states the regime: a contrast carries the ratio at
  every concurrency level both cells ran, not one number.
- The committed surface is what the tool produces from the evidence directory
  today. A hand edit, or a change to the reader that moves a cell, fails here.
- The help parser reads argparse's layout: flag, choices, metavar, default.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"
SWEEP = REPO / "records" / "evidence" / "2026-08-24-config-sweep"
SURFACE = REPO / "records" / "evidence" / "2026-08-24-knob-surface"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def knobs() -> Any:
    return _by_path("serving_knobs", SERVING / "knobs.py")


WRAPPER_LOG = "\n".join(
    [
        '(APIServer pid=1)   File "/x/utils.py", line 1272, in wait_for_engine_startup',
        "(APIServer pid=1)     raise RuntimeError(",
        "(APIServer pid=1) RuntimeError: Engine core initialization failed. "
        "See root cause above. Failed core proc(s): {}",
    ]
)
CAUSE_LOG = "\n".join(
    [
        "(EngineCore_DP0 pid=99) ValueError: fp8 KV cache needs compute capability 8.0",
        WRAPPER_LOG,
    ]
)
SPEC_JSON = '{"method": "ngram", "num_speculative_tokens": 3}'
SHELL_SPLIT_LOG = (
    "vllm serve: error: argument --speculative-config/-sc: Value {method: "
    "cannot be converted to <function loads at 0x7f>."
)


def _cell(cell: str, flags: list[str], ok: bool, log: str = "", **levels: Any) -> dict:
    rec: dict[str, Any] = {
        "host": "rigA",
        "model": "m",
        "cell": cell,
        "flags": flags,
        "axis": "t",
        "launch": {"ok": ok}
        if ok
        else {"ok": False, "reason": "container exited", "log": log},
    }
    if ok:
        rec["levels"] = [
            {"n": int(n), "agg_tok_s": v}
            for n, v in sorted(levels.items(), key=lambda kv: int(kv[0]))
        ]
    return rec


def _evidence(tmp_path: Path, records: list[dict]) -> Path:
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "rigA-m.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    return ev


BASE = ["--max-num-seqs", "16", "--enforce-eager"]


def test_four_kinds_of_absence_never_share_a_label(knobs: Any, tmp_path: Path) -> None:
    ev = _evidence(
        tmp_path,
        [
            _cell("baseline", BASE, True, **{"1": 10.0, "16": 100.0}),
            _cell("kv-fp8", [*BASE, "--kv-cache-dtype", "fp8"], False, CAUSE_LOG),
            _cell("dtype-bf16", [*BASE, "--dtype", "bfloat16"], False, WRAPPER_LOG),
            _cell(
                "spec",
                [*BASE, "--speculative-config", SPEC_JSON],
                False,
                SHELL_SPLIT_LOG,
            ),
        ],
    )
    out = tmp_path / "out"
    out.mkdir()
    (out / "declared-vllm-abc123.json").write_text(
        json.dumps(
            {
                "digest": "sha256:abc123def456",
                "count": 5,
                "with_default": 4,
                "flags": [
                    {"flag": f}
                    for f in (
                        "--max-num-seqs",
                        "--enforce-eager",
                        "--kv-cache-dtype",
                        "--dtype",
                        "--speculative-config",
                        "--ubatch-size",
                    )
                ],
            }
        )
    )
    surface = knobs.build(ev, out)
    rows = {r["cell"]: r for r in surface["accepted"][0]["cells"]}
    assert rows["baseline"]["state"] == "accepted"
    assert rows["kv-fp8"]["state"] == "refused"
    assert rows["kv-fp8"]["reason_captured"] is True
    assert "compute capability" in rows["kv-fp8"]["reason"]
    assert rows["dtype-bf16"]["state"] == "refused_reason_lost"
    assert rows["dtype-bf16"]["reason_captured"] is False
    assert rows["spec"]["state"] == "harness_defect"
    assert rows["spec"]["engine_saw"] == "{method:"
    assert rows["spec"]["record_holds"] == SPEC_JSON
    assert surface["declared"]["captured"] is True
    assert surface["declared"]["untried"] == ["--ubatch-size"]
    states = {r["state"] for r in rows.values()} | {"untried"}
    assert len(states) == 5 and states == set(surface["states"])


def test_untried_is_unknown_not_zero_until_the_declared_column_lands(
    knobs: Any, tmp_path: Path
) -> None:
    ev = _evidence(tmp_path, [_cell("baseline", BASE, True, **{"1": 10.0})])
    out = tmp_path / "out"
    surface = knobs.build(ev, out)
    assert surface["declared"]["captured"] is False
    assert surface["declared"]["untried"]["unknown"] is True
    assert surface["declared"]["untried"]["searched"]
    assert "--help=all" in surface["declared"]["command"]


def test_a_contrast_states_the_regime_not_one_number(
    knobs: Any, tmp_path: Path
) -> None:
    """fp8 KV: inert at n=16, decisive at n=256 -- both must be in the row."""
    ctx = ["--max-num-seqs", "256"]
    ev = _evidence(
        tmp_path,
        [
            _cell("plain", ctx, True, **{"16": 1000.0, "256": 6000.0}),
            _cell(
                "fp8",
                [*ctx, "--kv-cache-dtype", "fp8"],
                True,
                **{"16": 1000.0, "256": 6600.0},
            ),
            # A cell two flags away is not a contrast with either.
            _cell(
                "far",
                [*ctx, "--kv-cache-dtype", "fp8", "--dtype", "half"],
                True,
                **{"16": 1.0},
            ),
        ],
    )
    surface = knobs.build(ev, tmp_path / "out")
    contrasts = surface["effective"][0]["contrasts"]
    fp8 = [
        c
        for c in contrasts
        if c["knob"] == "--kv-cache-dtype" and c["from"] == "absent"
    ]
    assert len(fp8) == 1
    (c,) = fp8
    assert c["to"] == "fp8"
    assert c["context"] == {"--max-num-seqs": "256"}
    assert [(p["n"], p["ratio"]) for p in c["per_n"]] == [(16, 1.0), (256, 1.1)]
    assert c["largest_effect"] == {"n": 256, "ratio": 1.1}
    assert c["cites"] == [
        {"file": "rigA-m.jsonl", "cell": "plain"},
        {"file": "rigA-m.jsonl", "cell": "fp8"},
    ]
    # `far` differs from `fp8` by one key and IS a contrast on --dtype; from
    # `plain` by two and is not.
    assert {c["knob"] for c in contrasts} == {"--kv-cache-dtype", "--dtype"}


def test_flag_order_does_not_make_two_configs(knobs: Any) -> None:
    a = knobs.assignments(["--a", "1", "--b", "--c", "x"])
    b = knobs.assignments(["--c", "x", "--b", "--a", "1"])
    assert a == b == {"--a": "1", "--b": True, "--c": "x"}


def test_the_help_parser_reads_argparse_layout(knobs: Any) -> None:
    text = """usage: vllm serve [model_tag] [options]

options:
  -h, --help            show this help message and exit
  --max-model-len MAX_MODEL_LEN
                        Model context length. If unspecified, will be derived
                        from the model config. (default: None)
  --dtype {auto,bfloat16,float16,float32,half}
                        Data type for model weights. (default: auto)
  --enforce-eager, --no-enforce-eager
                        Always use eager-mode PyTorch. (default: False)
  --speculative-config SPECULATIVE_CONFIG, -sc SPECULATIVE_CONFIG
                        JSON. (default: None)
  --served-model-name SERVED_MODEL_NAME [SERVED_MODEL_NAME ...]
                        The model name(s) used in the API.

group:
  --seed SEED           Random seed. (default: 0)
"""
    rows = {r["flag"]: r for r in knobs.parse_help(text)}
    assert set(rows) == {
        "--help",
        "--max-model-len",
        "--dtype",
        "--enforce-eager",
        "--speculative-config",
        "--served-model-name",
        "--seed",
    }
    assert rows["--dtype"]["shape"] == "choice"
    assert rows["--dtype"]["choices"] == [
        "auto",
        "bfloat16",
        "float16",
        "float32",
        "half",
    ]
    assert rows["--dtype"]["default"] == "auto"
    assert rows["--enforce-eager"]["shape"] == "flag"
    assert rows["--enforce-eager"]["aliases"] == ["--no-enforce-eager"]
    assert rows["--enforce-eager"]["default"] == "False"
    assert rows["--max-model-len"]["shape"] == "value"
    assert rows["--max-model-len"]["default"] == "None"
    assert rows["--speculative-config"]["aliases"] == ["-sc"]
    assert rows["--served-model-name"]["default"] is None
    assert rows["--seed"]["default"] == "0"
    assert rows["--help"]["aliases"] == ["-h"]


# --------------------------------------------------------------------------
# the committed surface


@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    return json.loads((SURFACE / "surface.json").read_text())


def test_the_committed_surface_is_what_the_evidence_produces(
    knobs: Any, committed: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    for declared in SURFACE.glob("declared-*.json"):
        (out / declared.name).write_text(declared.read_text())
    rebuilt = knobs.build(SWEEP.relative_to(REPO), out)
    assert rebuilt == committed, "regenerate with knobs.py build; do not hand-edit"
    assert (out / "surface.md").read_text() == (SURFACE / "surface.md").read_text()


def test_every_cell_cites_the_run_it_was_read_from(committed: dict[str, Any]) -> None:
    files = set(committed["files"])
    for block in committed["accepted"]:
        for row in block["cells"]:
            assert row["cite"]["file"] in files, row
            assert row["cite"]["cell"]
    for block in committed["effective"]:
        for c in block["contrasts"]:
            assert len(c["cites"]) == 2
            assert all(x["file"] in files for x in c["cites"]), c


def test_the_shell_split_cells_read_as_harness_defect_not_refused(
    committed: dict[str, Any],
) -> None:
    """Stage 1 wrote three untested speculative cells per rig as refused."""
    by = {(b["host"], b["model"].split("/")[-1]): b for b in committed["accepted"]}
    for host in ("srv1", "srv2"):
        rows = {
            r["cell"]: r for r in by[(host, "Qwen2.5-Coder-1.5B-Instruct-AWQ")]["cells"]
        }
        for cell in ("spec-ngram-3", "spec-ngram-5", "spec-suffix-3"):
            assert rows[cell]["state"] == "harness_defect", (host, cell)
            assert rows[cell]["engine_saw"] == "{method:"
        # The stage-2 re-run of the same value is the measurement.
        assert rows["s2-spec-ngram-3"]["state"] == "accepted"
        assert rows["s2-spec-suffix-3"]["state"] == "refused"
        assert "arctic-inference" in rows["s2-spec-suffix-3"]["reason"]


def test_a_lost_reason_is_recorded_as_lost(committed: dict[str, Any]) -> None:
    by = {(b["host"], b["model"].split("/")[-1]): b for b in committed["accepted"]}
    srv1 = {
        r["cell"]: r for r in by[("srv1", "Qwen2.5-Coder-1.5B-Instruct-AWQ")]["cells"]
    }
    assert srv1["kv-fp8"]["state"] == "refused_reason_lost"
    assert srv1["kv-fp8"]["reason_captured"] is False
    assert srv1["ubatch-2"]["state"] == "refused"
    assert "Microbatching" in srv1["ubatch-2"]["reason"]
    lost = sum(b["counts"].get("refused_reason_lost", 0) for b in committed["accepted"])
    assert lost == 26, "the number the sweep's 25-line tail could not attribute"


def test_the_regime_is_visible_in_the_committed_surface(
    committed: dict[str, Any],
) -> None:
    """srv2, fp8 KV under graphs at seqs 256: inert low, decisive high."""
    (srv2,) = [
        b
        for b in committed["effective"]
        if b["host"] == "srv2" and b["model"].endswith("1.5B-Instruct-AWQ")
    ]
    fp8 = [
        c
        for c in srv2["contrasts"]
        if c["knob"] == "--kv-cache-dtype"
        and c["to"] == "fp8"
        and c["context"].get("--max-num-seqs") == "256"
    ]
    assert len(fp8) == 1
    per_n = {p["n"]: p["ratio"] for p in fp8[0]["per_n"]}
    # The sign flips with concurrency: a cost at low n, the winner at 256.
    # One number per knob would have hidden this.
    assert per_n[256] > 1.04
    assert min(r for n, r in per_n.items() if n <= 32) < 0.9
