"""Offline invariants over the bench gate (#225).

Admission itself executes checkers and needs `node` and `python` in the
shape the contracts declare — that is the gate's own job, a stated
precondition like the rigs' `--selftest`. What the suite holds here is
everything checkable without running a candidate: the id shape, the two
front-door blocklists, the sidecar's validation rules, the declared-target
stub construction (the check that makes a multi-symbol problem's checker
guarantee mean something), and the manifest's split-agreement check.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _by_path("bench_admit", REPO / "tools" / "bench" / "admit.py")


class _FakeContract:
    """Just enough contract for validate_meta — an interface to read."""

    def __init__(self, interface: str) -> None:
        self.interface = interface


def _contracts(ts: str, py: str) -> dict[str, Any]:
    return {"ts": _FakeContract(ts), "py": _FakeContract(py)}


# --- id shape --------------------------------------------------------------


def test_id_shape_is_the_benchs_own() -> None:
    assert gate.ID_RE.match("b001-ring-buffer")
    assert gate.ID_RE.match("b400-two-word-slug")
    for wrong in ("p001-pool", "t01", "b1-short", "B001-caps", "b001-", "b001"):
        assert not gate.ID_RE.match(wrong), wrong


# --- the two front doors ---------------------------------------------------


def test_blocklist_holds_both_front_doors() -> None:
    blocked = gate.blocklist()
    # 164 HumanEval + 378 MBPP+ entry points, normalised; overlap between the
    # two lists may make the union smaller, never larger.
    assert len(blocked) <= 164 + 378
    assert len(blocked) > 500
    assert "hascloseelements" in blocked  # HumanEval/0
    assert "similarelements" in blocked  # Mbpp/2


# --- the sidecar -----------------------------------------------------------


def test_meta_rejects_the_shapes_it_must() -> None:
    contracts = _contracts(
        "export function chunk(xs: number[], size: number): number[][]",
        "def chunk(xs: list, size: int) -> list",
    )
    assert gate.validate_meta("not an object", contracts)
    assert any(
        "file_shape" in m for m in gate.validate_meta({"shape": "string"}, contracts)
    )
    assert any(
        "steering_band" in m
        for m in gate.validate_meta(
            {"file_shape": "single_definition", "shape": "string"}, contracts
        )
    )


def test_single_definition_demands_exactly_one_declaration() -> None:
    two = _contracts(
        "export function a(): void\nexport function b(): void",
        "def a() -> None",
    )
    meta = {
        "file_shape": "single_definition",
        "shape": "string",
        "steering_band": "d1-like",
    }
    messages = gate.validate_meta(meta, two)
    assert any("exactly one" in m for m in messages)


def test_multi_symbol_demands_a_declared_target_per_arm() -> None:
    contracts = _contracts(
        "export function parseLine(s: string): string\n"
        "export function parseFile(s: string): string[]",
        "def parse_line(s: str) -> str\ndef parse_file(s: str) -> list",
    )
    meta = {
        "file_shape": "multi_symbol",
        "shape": "string",
        "steering_band": "gap-1",
        "target_symbol": {"ts": "parseFile", "py": "parse_file"},
    }
    assert gate.validate_meta(meta, contracts) == []

    undeclared = dict(meta, target_symbol={"ts": "parseAll", "py": "parse_file"})
    assert any("parseAll" in m for m in gate.validate_meta(undeclared, contracts))

    missing = dict(meta, target_symbol={"ts": "parseFile"})
    assert any("target_symbol[py]" in m for m in gate.validate_meta(missing, contracts))


# --- declared-target stubs -------------------------------------------------


def test_py_stub_shadows_and_keeps_helpers() -> None:
    reference = (
        "def helper(x):\n    return x * 2\n\n"
        "def chunk(xs, size):\n    return helper(xs)\n"
    )
    arm = next(a for a in gate.ARMS if a.name == "py")
    stubs = gate.stub_texts(arm, reference, "chunk")
    assert stubs is not None and len(stubs) == 2
    for _, text in stubs:
        assert text.startswith(reference)  # helpers and original intact
        assert text.rstrip().endswith("return None") or "args[0]" in text
        # the shadowing definition comes after the original, so it wins
        assert text.rindex("def chunk(") > text.index("def chunk(")


def test_ts_stub_requires_the_declared_form_exactly_once() -> None:
    arm = next(a for a in gate.ARMS if a.name == "ts")
    good = (
        "function helper(x: number): number { return x * 2; }\n"
        "export function chunk(xs: number[], size: number): number[][] {\n"
        "  return [xs.map(helper)];\n}\n"
    )
    stubs = gate.stub_texts(arm, good, "chunk")
    assert stubs is not None and len(stubs) == 2
    for _, text in stubs:
        assert "function __original_chunk(" in text  # original renamed, kept
        assert "export function chunk(...args: any[]): any" in text
        assert "helper" in text  # helpers intact

    # Absent, or ambiguous, the rule refuses rather than degrading the wrong thing.
    arrow = "const chunk = (x: number) => x;\n"
    assert gate.stub_texts(arm, arrow, "chunk") is None
    twice = good + "export function chunk(x: any): any { return x; }\n"
    assert gate.stub_texts(arm, twice, "chunk") is None


# --- the manifest's split agreement ----------------------------------------


def test_verify_flags_a_moved_problem(tmp_path: Path, monkeypatch: Any) -> None:
    """An entry whose recorded split disagrees with the rule is a re-split."""
    split = sys.modules["bench_split"]
    problem = "b001-ring-buffer"
    wrong = split.RESERVE if split.assignment(problem) == split.BENCH else split.BENCH
    manifest = tmp_path / "admissions.jsonl"
    entry = {"id": problem, "split": wrong, "superseded_by": "b999-x", "files": {}}
    manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "MANIFEST", manifest)
    monkeypatch.setattr(gate, "TASKS", tmp_path / "tasks")
    monkeypatch.setattr(gate, "RESERVE", tmp_path / "reserve")
    messages = gate.verify_manifest()
    assert any("the rule says" in m for m in messages)
