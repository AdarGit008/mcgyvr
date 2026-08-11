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

from mcgyvr.contract import loads

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


def test_the_emitter_writes_what_the_strict_schema_and_the_gate_read(
    tmp_path: Path,
) -> None:
    """#225: the file shapes b228-b267 were emitted through, pinned by a test.

    The emitter is not a generator — every word of a problem is authored by
    hand — but it owns the mechanical half: the folded `task:` scalar, the
    `demonstration`-versus-`acceptance` split that a bug_fix turns on, and the
    ts-arm-only sidecar. Those are exactly the parts whose breakage costs a
    gate rejection per problem, and the f1 band has tranches left to author.
    """
    emit = _by_path("bench_emit", REPO / "tools" / "bench" / "emit.py")

    pid = "b900-emit-probe"
    spec: dict[str, Any] = {
        "id": pid,
        "type": "bug_fix",
        "file_shape": "multi_symbol",
        "shape": "numeric",
        "steering_band": "f1",
        "prose_ts": "widgetOne is wrong. Fix it. Return the complete fixed file.",
        "prose_py": "widget_one is wrong. Fix it. Return the complete fixed file.",
        "iface_ts": "export function widgetOne(x: number): number",
        "iface_py": "def widget_one(x: int) -> int",
        "stop": "Something the prose leaves unstated.",
        "buggy_ts": "export function widgetOne(x: number): number {\n  return x;\n}\n",
        "buggy_py": "def widget_one(x: int) -> int:\n    return x\n",
        "ref_ts": (
            "export function widgetOne(x: number): number {\n  return x + 1;\n}\n"
        ),
        "ref_py": "def widget_one(x: int) -> int:\n    return x + 1\n",
        "acc_ts": 'import assert from "node:assert/strict";\n',
        "acc_py": "from solution import widget_one\n",
        "target_symbol": {"ts": "widgetOne", "py": "widget_one"},
    }
    emit.emit(spec, root=tmp_path)

    for arm, solution, command in (
        ("ts", "solution.ts", "node accept.mjs"),
        ("py", "solution.py", "python accept.py"),
    ):
        text = (tmp_path / arm / pid / "contract.yaml").read_text()
        parsed = loads(text)
        assert parsed.id == pid
        assert parsed.target == solution
        # A bug_fix declares its command under `demonstration`, never
        # `acceptance` — it must fail on the task's own starting file (#183).
        assert list(parsed.demonstration) == [command]
        assert list(parsed.acceptance) == []
        assert parsed.target_content == spec[f"buggy_{arm}"]

    sidecar = json.loads((tmp_path / "ts" / pid / "meta.json").read_text())
    assert sidecar == {
        "file_shape": "multi_symbol",
        "shape": "numeric",
        "steering_band": "f1",
        "target_symbol": {"ts": "widgetOne", "py": "widget_one"},
    }
    assert not (tmp_path / "py" / pid / "meta.json").exists(), (
        "the sidecar belongs to the ts arm alone"
    )


def test_a_function_implementation_declares_acceptance_not_demonstration(
    tmp_path: Path,
) -> None:
    """The other half of the split, so neither can drift into the other."""
    emit = _by_path("bench_emit", REPO / "tools" / "bench" / "emit.py")
    pid = "b901-emit-probe"
    spec: dict[str, Any] = {
        "id": pid,
        "type": "function_implementation",
        "file_shape": "single_definition",
        "shape": "string",
        "steering_band": "f1",
        "prose_ts": "Implement widgetTwo.",
        "prose_py": "Implement widget_two.",
        "iface_ts": "export function widgetTwo(x: string): string",
        "iface_py": "def widget_two(x: str) -> str",
        "stop": "Something the prose leaves unstated.",
        "ref_ts": "export function widgetTwo(x: string): string {\n  return x;\n}\n",
        "ref_py": "def widget_two(x: str) -> str:\n    return x\n",
        "acc_ts": 'import assert from "node:assert/strict";\n',
        "acc_py": "from solution import widget_two\n",
    }
    emit.emit(spec, root=tmp_path)

    parsed = loads((tmp_path / "ts" / pid / "contract.yaml").read_text())
    assert list(parsed.acceptance) == ["node accept.mjs"]
    assert list(parsed.demonstration) == []
    assert parsed.target_content == "", "no starting file to repair"
    sidecar = json.loads((tmp_path / "ts" / pid / "meta.json").read_text())
    assert "target_symbol" not in sidecar, (
        "single_definition takes its target from the interface, not the sidecar"
    )
