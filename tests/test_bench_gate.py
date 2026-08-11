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


# --- the two screens the gate is structurally unable to run ----------------
#
# Both catch material the gate passes happily, because in both the references
# are correct — they are correct about the wrong thing. See emit.py's docstring.


def _emit_module() -> types.ModuleType:
    return _by_path("bench_emit", REPO / "tools" / "bench" / "emit.py")


def _spec(**over: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "id": "b902-screen-probe",
        "type": "function_implementation",
        "file_shape": "single_definition",
        "shape": "numeric",
        "steering_band": "f1",
        "prose_ts": "Implement widgetThree.",
        "prose_py": "Implement widget_three.",
        "iface_ts": "export function widgetThree(x: number): number",
        "iface_py": "def widget_three(x: int) -> int",
        "stop": "Something the prose leaves unstated.",
        "ref_ts": "export function widgetThree(x: number): number {\n  return x;\n}\n",
        "ref_py": "def widget_three(x: int) -> int:\n    return x\n",
        "acc_ts": "assert.equal(widgetThree(1), 1);\n",
        "acc_py": "assert widget_three(1) == 1\n",
    }
    spec.update(over)
    return spec


def _fatal(findings: list[Any]) -> list[str]:
    return [f.detail for f in findings if f.fatal]


def test_a_rounding_rule_the_two_languages_disagree_about_is_refused() -> None:
    """round(4.5) is 4 in python and 5 in JavaScript.

    A problem whose prose states how a half rounds is two different problems,
    and the idiomatic py answer fails what the idiomatic ts answer passes —
    an arm difference that reads as a language finding and is really a defect
    in the material. Same class as the ValueError-versus-Error checker defect.
    """
    emit = _emit_module()
    assert _fatal(emit.divergences(_spec(ref_py="    return round(x / 2)\n")))
    assert _fatal(emit.divergences(_spec(ref_ts="  return Math.round(x / 2);\n")))
    assert not emit.divergences(_spec(ref_ts="  return Math.floor(x / 2);\n")), (
        "floor and // agree, which is why the brief prefers them"
    )


def test_a_bare_sort_is_refused_over_numbers_and_allowed_over_keys() -> None:
    """JavaScript's bare .sort() orders by string: [2, 10] becomes [10, 2].

    Over strings the two languages agree, and sorting keys is the commonest
    correct use in this tree, so the refusal is narrowed to a visibly numeric
    receiver rather than fired at every bare sort.
    """
    emit = _emit_module()
    numeric = (
        "export function widgetThree(xs: number[]): number[] {\n"
        "  return xs.sort();\n}\n"
    )
    assert _fatal(emit.divergences(_spec(ref_ts=numeric)))

    keys = (
        "export function widgetThree(m: Record<string, number>): string[] {\n"
        "  return Object.keys(m).sort();\n}\n"
    )
    assert not emit.divergences(_spec(ref_ts=keys)), "keys are strings; the two agree"

    stringly = (
        "export function widgetThree(xs: string[]): string[] {\n"
        "  return xs.sort();\n}\n"
    )
    assert not emit.divergences(_spec(ref_ts=stringly))


def test_a_remainder_reached_by_a_negative_warns_but_never_refuses() -> None:
    """-7 % 3 is 2 in python and -1 in JavaScript.

    Whether a negative actually reaches the operator is a dataflow question
    and this screen is a regex, so it must not refuse. The suppressions keep
    the warning worth reading: Math.abs upstream, a divisibility test, and the
    ((x % n) + n) % n idiom all make it safe.
    """
    emit = _emit_module()
    reaches = _spec(
        ref_ts=(
            "export function widgetThree(x: number): number {\n  return x % 360;\n}\n"
        ),
        acc_ts="assert.equal(widgetThree(-30), 330);\n",
    )
    findings = emit.divergences(reaches)
    assert findings and not _fatal(findings), "a dataflow guess never refuses"

    for safe in (
        "  return ((x % 360) + 360) % 360;\n",
        "  return Math.abs(x) % 360;\n",
        "  return x % 4 === 0 ? 1 : 0;\n",
    ):
        probe = _spec(ref_ts=safe, acc_ts="assert.equal(widgetThree(-30), 1);\n")
        assert not emit.divergences(probe), safe


def test_unicode_aware_predicates_warn_because_the_ts_twin_is_ascii() -> None:
    emit = _emit_module()
    findings = emit.divergences(_spec(ref_py="    return x.isdigit()\n"))
    assert findings and not _fatal(findings), (
        "latent: the arms part company outside ASCII, which a checker may never test"
    )


def test_the_same_problem_in_another_domain_is_caught_by_its_shape() -> None:
    """The gate screens prose at 0.55 Jaccard and cannot see a re-skinned twin.

    "the next fan speed, wrapping to the first" and "who takes the next shift,
    wrapping to the first" share almost no vocabulary and are one problem.
    What they share is the shape of their reference, so that is what is
    screened — identifiers, literals and types erased.
    """
    emit = _emit_module()
    original = (
        "export function rotaNext(names: string[], current: string): string {\n"
        "  const place = names.indexOf(current);\n"
        "  if (place === names.length - 1) {\n    return names[0];\n  }\n"
        "  return names[place + 1];\n}\n"
    )
    reskinned = original.replace("rotaNext", "ventCycle").replace("names", "settings")
    known = {"b241-rota-next": {"ts": emit.skeleton(original, "ts")}}

    score, name, arm = emit.siblings(_spec(ref_ts=reskinned), known)[0]
    assert name == "b241-rota-next" and arm == "ts"
    assert score > emit.REFUSE_AT, f"renaming is not a new problem (scored {score})"
    assert _fatal(emit.check(_spec(ref_ts=reskinned), known))

    unrelated = "export function widgetThree(x: number): number {\n  return x * 2;\n}\n"
    assert not emit.check(_spec(ref_ts=unrelated), known)


def test_the_screens_refuse_the_write_rather_than_warning_past_it(
    tmp_path: Path,
) -> None:
    """A screen with an override is a screen that gets overridden."""
    emit = _emit_module()
    spec = _spec(ref_py="    return round(x / 2)\n")
    try:
        emit.emit(spec, root=tmp_path)
    except emit.EmitError:
        pass
    else:  # pragma: no cover - the assertion below reports it
        raise AssertionError("a fatal finding must refuse the write")
    assert not (tmp_path / "ts" / spec["id"]).exists(), "nothing is written"


# --- retirement -------------------------------------------------------------


def test_a_retired_problem_is_gone_from_the_tree_and_the_manifest() -> None:
    """Retirement is a withdrawal, not a flag: no files, no admission record.

    The precedent is b155, b176-b180 and b186, which hold no manifest entry at
    all. What `retired.json` adds over deleting them is the argument and the
    date, so anything that already measured the problem can find out why it
    went.
    """
    withdrawn = gate.retired()
    assert withdrawn, "the declaration is the mechanism"
    admitted = {str(e["id"]) for e in gate.manifest_entries()}
    for name, entry in withdrawn.items():
        assert name not in admitted, f"{name} still holds an admission record"
        for root in (
            REPO / "tools" / "bench" / "tasks",
            REPO / "tools" / "bench" / "reserve",
        ):
            for arm in ("ts", "py"):
                assert not (root / arm / name).exists(), f"{name} still on disk"
        assert entry["kept"] in admitted, (
            f"{name} was retired in favour of {entry['kept']}, which must remain"
        )
        assert entry["date"] and entry["why"], f"{name} needs a dated argument"


def test_a_retired_id_is_never_a_candidate_again() -> None:
    """Ids are not reused, so a retired one must not be re-admitted or re-emitted."""
    withdrawn = gate.retired()
    victim = sorted(withdrawn)[0]
    assert victim not in gate.candidates()

    emit = _emit_module()
    try:
        emit.emit({"id": victim}, root=REPO / "does-not-exist")
    except emit.EmitError as error:
        assert victim in str(error)
    else:  # pragma: no cover - the assertion below reports it
        raise AssertionError("the emitter must refuse a retired id")
