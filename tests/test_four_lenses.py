"""The four lenses as checks rather than as reading (#251, ADR-0026).

On 2026-08-13 one defect was found eleven times in a day, and **not one was
found by a check** — every instance was found by a person or an agent
re-reading. ADR-0026 states the standard; a sweep that corrects eleven
instances and adds no check leaves the twelfth to be found the same way.

So these are deliberately not assertions about the eleven. Each one computes a
*population* and compares it against a declared allowlist, which means a new
instance fails the build even though nobody wrote it down. The allowlists are
the audit's findings, frozen: an entry is a fact of record, and removing one is
how a fix is proved.

Four classes, one check each:

* **the twin constant** — one value, two definitions, and only a comment
  holding them equal. ``test_duplicated_constants_are_declared``.
* **the unmapped rung** — a declared bar naming rungs the gate cannot emit, so a
  manifest records a bar nothing applied.
  ``test_declared_rungs_name_emitted_checks``.
* **the unjoined field** — recorded on every task and read by no analysis, so
  the capture was never the gap. ``test_recorded_task_fields_have_a_reader``.
* **the underived constant** — a shipped number citing a measurement no test
  recomputes, so the figure and its evidence drift apart.
  ``test_estimate_reserve_is_derived``.

Read ADR-0026 before adding to any allowlist here. The cost of getting this
wrong is not a missed defect; it is a published number nobody can re-derive.
"""

from __future__ import annotations

import ast
import collections
import json
import math
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = (REPO / "src", REPO / "tools")
# Corpora and the vendored toolkit are material, not code: their contents are
# pinned by digest and a sweep there measures the instrument, not the project.
SKIP_PARTS = ("tasks", "baseline", "reserve", "node_modules", ".venv")


def _source_files() -> list[Path]:
    out: list[Path] = []
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            out.append(path)
    return out


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def _where(path: Path, lineno: int) -> str:
    """A location, repo-relative when the file is in the repo at all."""
    stem = _rel(path) if path.is_relative_to(REPO) else str(path)
    return f"{stem}:{lineno}"


# --------------------------------------------------------------------------
# The twin constant — one value, two definitions
# --------------------------------------------------------------------------

# Module-level literal constants that are defined in more than one place.
#
# A duplicate is not automatically a defect — sometimes the coupling is real and
# importing across it would be worse, which `worker/reply.py` says out loud
# before duplicating the extension tuples on purpose. What is never acceptable
# is an *undeclared* duplicate, because the only thing keeping the copies equal
# is that nobody has edited one of them yet.
#
# Each entry is (constant name, whether the copies must hold equal values).
# `False` marks a name collision across unrelated meanings — two modules that
# happen to have picked the same word — which this check must not force into
# agreement.
DECLARED_DUPLICATES: dict[str, bool] = {
    # Must agree. Asserted in a comment at repo.py:46 and by nothing else;
    # git's empty-tree SHA-1 is the same fact on both sides of the seam.
    "_EMPTY_TREE": True,
    # Must agree. symbols.py:44 says "the names match the gate adapters" — if
    # they stop matching, the index and the gate disagree about which files are
    # JavaScript, silently.
    "_TS_EXTENSIONS": True,
    "_TSX_EXTENSIONS": True,
    # Must agree. Both rigs clone the same frames for the same corpus.
    "CLONE_DEPTH": True,
    "REMOTES": True,
    # Must agree: the two rigs sweep the same ladder.
    "LADDER": True,
    # Two copies, and they are no longer the same quantity. #262 reconciled the
    # LIVE instruments to one number: `tools/bench/score.py` declares 120.0 and
    # `tools/problems/admit.py` imports it, so admission rehearses the ceiling
    # that will score it. What is left here is `tools/bundle/measure.py`'s 30.0,
    # which describes a RETIRED instrument's runs already on disk (#240) — it
    # must not move, because moving it would restate what those rows were
    # measured under. Declared False for that reason and not the old one.
    "ACCEPTANCE_TIMEOUT_S": False,
    # Known to disagree, and filed: 1.0 against 2.0, under a docstring at
    # availability.py:55 calling the two "the same trick ... for the same
    # reason". Weaker than the timeout above — the prose is about concurrency
    # rather than the value — but it is the same shape.
    "PROBE_TIMEOUT_S": False,
    # Inherited rather than derived, in two rigs at once (#251 lens 2). Equal
    # today; the defect is that neither copy is derived from anything.
    "MAX_OUTPUT_TOKENS": True,
    # Three independent schema versions that happen to be 1. They version
    # different schemas and are NOT required to agree — but a reader sees one
    # number in three files, so it is declared rather than left to be noticed.
    "SCHEMA_VERSION": False,
    # Name collisions across unrelated meanings.
    "CHECK": False,  # the gate's own per-module check name
    "ARMS": False,  # each rig's arms are its own
    "TIMEOUT_S": False,  # unrelated tools, unrelated ceilings
    "_CACHE": False,
    "_DRIVER": False,
    "_JS_EXTENSIONS": False,  # reply.py's is the whole family; the others are JS only
    "__all__": False,  # every package has one
}


def _module_level_constants(
    files: list[Path] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """name -> {repr(value): [locations]} for every literal module constant.

    ``files`` is injectable so the canary below can hand it a synthetic tree.
    A check that cannot be shown to reject is the defect this file is about.
    """
    found: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for path in _source_files() if files is None else files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a syntax error is its own failure
            continue
        for node in tree.body:
            names: list[str]
            value: ast.expr | None
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
                value = node.value
            else:
                continue
            if value is None:
                continue
            try:
                literal = ast.literal_eval(value)
            except (ValueError, SyntaxError, TypeError):
                continue
            for name in names:
                found[name][repr(literal)].append(_where(path, node.lineno))
    return found


def _duplicated(
    constants: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    """The subset defined in more than one place."""
    return {
        name: values
        for name, values in constants.items()
        if sum(len(locs) for locs in values.values()) > 1
    }


def test_duplicated_constants_are_declared() -> None:
    """A constant defined twice is declared here, or it is a new instance.

    This is the check the ``_EMPTY_TREE`` comment stands in for. The comment
    states a claim; this states the property, so the twelfth instance fails the
    build instead of waiting to be read.
    """
    duplicated = _duplicated(_module_level_constants())
    undeclared = sorted(set(duplicated) - set(DECLARED_DUPLICATES))
    assert not undeclared, (
        "a module-level constant is now defined in more than one place and is "
        "not declared in DECLARED_DUPLICATES:\n"
        + "\n".join(
            f"  {name}: "
            + "; ".join(
                f"{value} at {', '.join(locs)}"
                for value, locs in sorted(duplicated[name].items())
            )
            for name in undeclared
        )
        + "\n\nADR-0026 lens 3: either make one definition the source of the "
        "other, or declare the duplication and say whether the copies must "
        "hold equal values."
    )


def test_declared_duplicates_that_must_agree_do_agree() -> None:
    """The half of the class a comment cannot enforce: the values are equal.

    ``ACCEPTANCE_TIMEOUT_S`` is why this exists. Its comment claimed sameness
    for long enough that a second module built a claim on top of it, and the
    two values were never equal.
    """
    constants = _module_level_constants()
    broken: list[str] = []
    for name, must_agree in sorted(DECLARED_DUPLICATES.items()):
        if not must_agree:
            continue
        values = constants.get(name)
        if values is None:  # the duplication was resolved — nothing to hold
            continue
        if len(values) > 1:
            broken.append(
                f"  {name} disagrees: "
                + "; ".join(
                    f"{value} at {', '.join(locs)}"
                    for value, locs in sorted(values.items())
                )
            )
    assert not broken, (
        "a constant declared as needing to hold equal values does not:\n"
        + "\n".join(broken)
    )


# --------------------------------------------------------------------------
# The unmapped rung — a declared bar naming checks the gate cannot emit
# --------------------------------------------------------------------------

# `GATE_RUNGS` is written verbatim into every bench manifest as the bar a rate
# was measured against. Three of its five names match nothing the gate emits,
# so a reader joining a row's `rejected_by` against the declared bar matches two
# names in nine. The names are a *category* vocabulary; this is the mapping from
# each declared category to the `check=` values it actually covers, and it is
# what makes the declaration checkable rather than decorative.
RUNG_COVERAGE: dict[str, tuple[str, ...]] = {
    "scope": ("scope",),
    "secrets": ("secret",),
    "structured": ("structured-data",),
    "adapters": ("syntax", "structure", "lint", "format"),
    "acceptance": ("acceptance",),
}


def _emitted_check_names(gate: Path | None = None) -> dict[str, list[str]]:
    """Every literal a ``Finding(check=...)`` can carry, resolved by AST."""
    emitted: dict[str, list[str]] = collections.defaultdict(list)
    gate = REPO / "src" / "mcgyvr" / "gate" if gate is None else gate
    for path in sorted(gate.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(
                        node.value.value, str
                    ):
                        constants[target.id] = node.value.value
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            name = (
                func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            )
            if name != "Finding":
                continue
            for keyword in call.keywords:
                if keyword.arg != "check":
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    emitted[value.value].append(_where(path, value.lineno))
                elif isinstance(value, ast.Name) and value.id in constants:
                    emitted[constants[value.id]].append(_where(path, value.lineno))
    return dict(emitted)


def test_declared_rungs_name_emitted_checks() -> None:
    """Every name in the declared bar covers at least one emitted check.

    ADR-0026 lens 3's strong form: a check states what it contains, or it is
    worse than dead weight. ``gate_rungs`` is written byte-identically into both
    arms of every contrast, so a name in it that corresponds to nothing is a bar
    that reads as applied and was not.
    """
    score = _load_bench_score()
    emitted = _emitted_check_names()

    unmapped = sorted(set(score.GATE_RUNGS) - set(RUNG_COVERAGE))
    assert not unmapped, (
        f"GATE_RUNGS declares {unmapped} with no entry in RUNG_COVERAGE — the "
        "manifest would record a rung name that maps to no check the gate can "
        "emit"
    )

    stale = sorted(set(RUNG_COVERAGE) - set(score.GATE_RUNGS))
    assert not stale, (
        f"RUNG_COVERAGE maps {stale}, which GATE_RUNGS no longer declares; the "
        "coverage table has drifted from the bar it describes"
    )

    missing: list[str] = []
    for rung, checks in sorted(RUNG_COVERAGE.items()):
        absent = [c for c in checks if c not in emitted]
        if absent:
            missing.append(f"  {rung} claims to cover {absent}, which nothing emits")
    assert not missing, (
        "a declared rung names a check the gate cannot produce:\n" + "\n".join(missing)
    )

    covered = {c for checks in RUNG_COVERAGE.values() for c in checks}
    # `semantic` is absent from the bar by decision (ADR-0011), not by accident,
    # so it is the one emitted check the bar is allowed not to cover.
    uncovered = sorted(set(emitted) - covered - {"semantic"})
    assert not uncovered, (
        f"the gate emits {uncovered}, which no declared rung covers — a "
        "rejection would be attributed to a bar that does not name it"
    )


def _load_bench_score() -> Any:
    """``tools/bench/score.py``, which is a script rather than a package."""
    import importlib.util
    import sys

    path = REPO / "tools" / "bench" / "score.py"
    spec = importlib.util.spec_from_file_location("bench_score_for_lenses", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module defines frozen dataclasses, and
    # `dataclasses` resolves a field's type through `sys.modules[cls.__module__]`.
    # This is the same dance `tools/bench/report.py:_by_path` does.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The unjoined field — recorded on every task, read by no analysis
# --------------------------------------------------------------------------

# The tools that turn rows into a published figure. A field recorded on a task
# and named in none of these is captured and never joined, which is lens 1's
# corollary: the join is the requirement, not the capture.
ANALYSIS_TOOLS = (
    "tools/bench/report.py",
    "tools/bench/responsiveness.py",
    "tools/bench/ablation_report.py",
    "tools/bench/redundancy.py",
    "tools/bench/matrix.py",
    "tools/bench/split.py",
)

# Fields on a bench task's meta.json that no analysis tool reads today. Each is
# a finding of #251, frozen here so that *adding* an unread field fails, and so
# that giving one a reader is a one-line deletion that proves the fix.
#
# Both are validated at admission and neither is ever used as an axis, which is
# the distinction that matters: the corpus is refused if they are missing, and
# no published figure is ever cut by them.
UNREAD_TASK_FIELDS = frozenset({"shape", "file_shape"})

# Recorded for a reason other than analysis, so their absence from the tools
# above is not a finding. `target_symbol` names the symbol a `multi_symbol`
# task's stub is built around — it is construction input, consumed by
# `tools/bench/admit.py:target_symbol`, not a stratum nobody joined.
CONSTRUCTION_FIELDS = frozenset({"target_symbol"})


def test_recorded_task_fields_have_a_reader() -> None:
    """A field on every task is read by an analysis tool, or it is declared.

    ``shape`` is recorded on all 514 bench tasks and read by nothing, while on
    the only committed multi-condition sweep it stratifies the effect at least
    as widely as language does. Nobody can say whether it matters, because no
    tool has ever looked — which is the point.
    """
    tasks = REPO / "tools" / "bench" / "tasks"
    if not tasks.is_dir():  # pragma: no cover - the corpus is always present
        pytest.skip("no bench corpus")

    recorded: set[str] = set()
    for meta in tasks.rglob("meta.json"):
        recorded |= set(json.loads(meta.read_text(encoding="utf-8")))

    sources = "\n".join(
        (REPO / tool).read_text(encoding="utf-8")
        for tool in ANALYSIS_TOOLS
        if (REPO / tool).is_file()
    )
    unread = {field for field in recorded if f'"{field}"' not in sources}
    # A field named only in prose is not read; require it inside a subscript or
    # a `.get`, which is how these tools actually reach a value.
    unread = {
        field
        for field in unread
        if f"[{field!r}]" not in sources and f"get({field!r}" not in sources
    }

    new = sorted(unread - UNREAD_TASK_FIELDS - CONSTRUCTION_FIELDS)
    assert not new, (
        f"a bench task records {new}, which no analysis tool reads. ADR-0026 "
        "lens 1: record what cannot be reconstructed, and join what is "
        "recorded — the capture was never the gap. If the field is consumed "
        "when the task is built rather than when it is analysed, declare it in "
        "CONSTRUCTION_FIELDS and say which function reads it."
    )

    fixed = sorted(UNREAD_TASK_FIELDS - unread)
    assert not fixed, (
        f"{fixed} now has a reader — remove it from UNREAD_TASK_FIELDS so the "
        "allowlist keeps naming only what is still unjoined"
    )


# --------------------------------------------------------------------------
# The underived constant — a shipped number no test recomputes
# --------------------------------------------------------------------------

TOKEN_UNITS = REPO / "records" / "measurements" / "tokens-2026-08-03" / "units.jsonl"
TOKEN_VOCABS = (
    "qwen2.5-coder",
    "deepseek-coder-v2",
    "gpt-oss",
    "qwen3-coder",
)


def _p05(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(0.05 * len(ordered)) - 1)
    return ordered[index]


def test_estimate_reserve_is_derived() -> None:
    """The shipped reserve is re-derived from the data it cites, not asserted.

    ``ESTIMATE_RESERVE = 0.32`` is enforced in ``check_prompt_fits`` and cited
    to CLM-0011 as "the worst vocabulary's p05, rounded up". Until #251 the only
    test on it asserted a band (``0.30 <= x <= 0.35``), which is a claim about
    the number rather than a derivation of it: the units could change and the
    band would still pass.
    """
    from mcgyvr.gate.preflight import ESTIMATE_RESERVE

    if not TOKEN_UNITS.is_file():  # pragma: no cover - the evidence is vendored
        pytest.skip("CLM-0011's units are not vendored")
    rows = [
        json.loads(line)
        for line in TOKEN_UNITS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    worst = min(
        _p05([r[f"error.{v}"] for r in rows if r.get(f"error.{v}") is not None])
        for v in TOKEN_VOCABS
    )
    derived = math.ceil(abs(worst) * 100) / 100
    assert pytest.approx(derived) == ESTIMATE_RESERVE, (
        f"ESTIMATE_RESERVE is {ESTIMATE_RESERVE}, but CLM-0011's own units give "
        f"a worst-vocabulary p05 of {worst:.4f}, i.e. {derived}. The constant "
        "and the measurement it cites have drifted apart."
    )


# The stratum CLM-0011's own statement calls out: "the band is language-
# dependent". A pooled reserve over a heterogeneous stratum is what ADR-0026's
# consequences forbid a *report* from doing, and the same argument applies to a
# shipped constant. These are the per-language figures the audit measured; the
# check pins them so the gap cannot widen unnoticed while the pooled number
# stays put.
RESERVE_BY_LANGUAGE = {"javascript": 0.36, "python": 0.29}


def test_pooled_reserve_is_recorded_against_its_strata() -> None:
    """The per-language reserves are re-derived, so the pooling stays visible.

    This does not assert that the shipped constant is wrong — that is #251's
    finding and its own work to fix. It asserts that the size of the gap is a
    computed fact rather than a sentence in an audit nobody re-runs.
    """
    if not TOKEN_UNITS.is_file():  # pragma: no cover
        pytest.skip("CLM-0011's units are not vendored")
    rows = [
        json.loads(line)
        for line in TOKEN_UNITS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_language: dict[str, float] = {}
    for language in RESERVE_BY_LANGUAGE:
        worst = min(
            _p05(
                [
                    r[f"error.{v}"]
                    for r in rows
                    if r.get("language") == language and r.get(f"error.{v}") is not None
                ]
            )
            for v in TOKEN_VOCABS
        )
        by_language[language] = math.ceil(abs(worst) * 100) / 100
    assert by_language == RESERVE_BY_LANGUAGE, (
        f"the per-language reserves moved: {by_language} against a recorded "
        f"{RESERVE_BY_LANGUAGE}. One pooled constant still ships for both."
    )


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------
#
# ADR-0026 lens 3 is two-sided: a declaration of content, *and* a positive
# control proving the declaration is live. A digest with no control records
# precisely which inert bar was applied. Every check above therefore has a
# canary here — a synthetic new instance it must reject. If a canary stops
# failing, the check above it has gone inert and is reporting health while
# applying nothing, which is the state this whole file exists to detect.


def test_control_an_undeclared_twin_is_rejected(tmp_path: Path) -> None:
    """The duplicate sweep rejects a constant it has never seen."""
    (tmp_path / "one.py").write_text("NEW_SHARED_CEILING_S = 5.0\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("NEW_SHARED_CEILING_S = 9.0\n", encoding="utf-8")
    duplicated = _duplicated(
        _module_level_constants([tmp_path / "one.py", tmp_path / "two.py"])
    )
    assert "NEW_SHARED_CEILING_S" in duplicated
    assert sorted(duplicated["NEW_SHARED_CEILING_S"]) == ["5.0", "9.0"]
    assert "NEW_SHARED_CEILING_S" not in DECLARED_DUPLICATES


def test_control_a_must_agree_twin_that_drifts_is_rejected(tmp_path: Path) -> None:
    """The must-agree half rejects two copies that stopped being equal."""
    (tmp_path / "a.py").write_text("_EMPTY_TREE = 'aaa'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("_EMPTY_TREE = 'bbb'\n", encoding="utf-8")
    constants = _module_level_constants([tmp_path / "a.py", tmp_path / "b.py"])
    assert DECLARED_DUPLICATES["_EMPTY_TREE"] is True
    assert len(constants["_EMPTY_TREE"]) > 1, (
        "two different values for a must-agree constant did not register as a "
        "disagreement — test_declared_duplicates_that_must_agree_do_agree is inert"
    )


def test_control_a_rung_that_maps_to_no_check_is_rejected(tmp_path: Path) -> None:
    """The rung check rejects a declared name that maps to no emitted check."""
    gate = tmp_path / "gate"
    gate.mkdir()
    (gate / "only.py").write_text(
        'CHECK = "acceptance"\n'
        "def f():\n"
        '    return Finding(check="scope", path="p", message="m")\n'
        "def g():\n"
        '    return Finding(check=CHECK, path="p", message="m")\n',
        encoding="utf-8",
    )
    emitted = _emitted_check_names(gate)
    # Both forms resolve: the literal, and the module constant `check=CHECK`
    # that `acceptance.py` and `semantic.py` actually use.
    assert set(emitted) == {"scope", "acceptance"}
    # `adapters` is exactly the shape the real GATE_RUNGS carries: a category
    # name that is not itself a check. Without RUNG_COVERAGE it maps to nothing.
    assert "adapters" not in emitted


def test_control_a_field_no_analysis_reads_is_rejected() -> None:
    """The readership check rejects a field named in no analysis tool."""
    sources = "\n".join(
        (REPO / tool).read_text(encoding="utf-8")
        for tool in ANALYSIS_TOOLS
        if (REPO / tool).is_file()
    )
    invented = "steering_band_v2"
    assert f'"{invented}"' not in sources
    assert f"[{invented!r}]" not in sources
    assert f"get({invented!r}" not in sources
    # And the fields the audit found are genuinely absent from those tools —
    # the allowlist is a finding, not a way of passing.
    for field in sorted(UNREAD_TASK_FIELDS):
        assert f"[{field!r}]" not in sources and f"get({field!r}" not in sources, (
            f"{field} now has a reader; UNREAD_TASK_FIELDS is stale"
        )


def test_control_the_reserve_moves_with_its_evidence() -> None:
    """The reserve check rejects a constant that stopped matching its units."""
    if not TOKEN_UNITS.is_file():  # pragma: no cover
        pytest.skip("CLM-0011's units are not vendored")
    rows = [
        json.loads(line)
        for line in TOKEN_UNITS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    worst = min(
        _p05([r[f"error.{v}"] for r in rows if r.get(f"error.{v}") is not None])
        for v in TOKEN_VOCABS
    )
    derived = math.ceil(abs(worst) * 100) / 100
    # Perturb the evidence: one unit far past the current p05 moves the floor,
    # and the shipped constant does not follow it. That is the drift the band
    # assertion in test_structured_and_preflight.py cannot see.
    perturbed = rows + [{"error.deepseek-coder-v2": -0.99, "language": "python"}] * (
        len(rows) // 10
    )
    moved = min(
        _p05([r[f"error.{v}"] for r in perturbed if r.get(f"error.{v}") is not None])
        for v in TOKEN_VOCABS
    )
    assert math.ceil(abs(moved) * 100) / 100 != derived, (
        "the derivation did not move when its evidence did — "
        "test_estimate_reserve_is_derived would pass against any data"
    )
