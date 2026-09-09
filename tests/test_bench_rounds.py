"""The round, the product pin, and the mode every figure has to declare (#231).

Checks 3 and 6 of the commissioning gate. Both exist because a number on this
bench is quotable only if a reader can tell what produced it:

* **check 3** — every arm in a round runs against one product revision, and an
  adopted change lands at the round boundary rather than mid-flight (ADR-0018).
  The bench pinned its tasks and its system prompt; the user-message render, the
  reply parser and the whole of ``Gate.run`` were unpinned, so two arms could be
  scored by two different bars and laid in one table.
* **check 6** — a rate says whether it describes one tier or the whole ladder.
  With escalation live a floor failure is rescued by a higher rung and the floor
  is invisible, so 12.8% means two different things and the number cannot carry
  the distinction.

The last test in this file is the one that matters most: it **discovers** the
tools that produce bench figures rather than naming them, so a tool added later
is checked by default. This project has already paid for the other shape twice —
``report.COMPARABLE`` named five fields and permitted the sixth silently, and
the mode declaration itself was a string literal in two reports while seven
other figure-producing tools said nothing at all.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mode() -> Any:
    return _by_path("bench_mode_t", REPO / "tools" / "bench" / "mode.py")


@pytest.fixture(scope="module")
def product() -> Any:
    return _by_path("bench_product_t", REPO / "tools" / "bench" / "product.py")


# --- the product digest -----------------------------------------------------


def _tree(root: Path) -> Path:
    """A miniature repo with one file at each declared surface path."""
    for entry in ("src/mcgyvr", "tools/breadth", "tools/bundle", "tools/bench", "data"):
        (root / entry).mkdir(parents=True, exist_ok=True)
    (root / "src/mcgyvr/runner.py").write_text("x = 1\n")
    (root / "src/mcgyvr/worker").mkdir(exist_ok=True)
    (root / "src/mcgyvr/worker/prompt.py").write_text("y = 2\n")
    (root / "src/mcgyvr/prompts").mkdir(exist_ok=True)
    (root / "src/mcgyvr/prompts/python.md").write_text("You are a worker.\n")
    (root / "tools/breadth/measure.py").write_text("m = 3\n")
    (root / "tools/bundle/measure.py").write_text("b = 4\n")
    (root / "tools/bench/score.py").write_text("s = 5\n")
    (root / "tools/bench/matrix.py").write_text("mx = 6\n")
    (root / "tools/bench/matrix.json").write_text("{}\n")
    (root / "tools/bench/product.py").write_text("p = 7\n")
    # The bar: its configuration and the lockfiles that decide which checker
    # applies it (#291).
    (root / "pyproject.toml").write_text("[tool.ruff]\nline-length = 88\n")
    (root / "eslint.config.mjs").write_text("export default [];\n")
    # The format half of the JS/TS bar (#262). Absent from this fixture until
    # there was a config to stage — prettier ran on its release's defaults, so
    # only `package-lock.json` covered it.
    (root / "prettier.config.mjs").write_text("export default {};\n")
    (root / "uv.lock").write_text("version = 1\n")
    (root / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
    (root / "data/task-catalog.json").write_text('{"task_types": []}\n')
    return root


def test_the_digest_moves_when_any_product_file_changes(
    product: Any, tmp_path: Path
) -> None:
    """A curated subset permits what it omits, so the surface is coarse."""
    tree = _tree(tmp_path)
    before = product.digest(tree)
    (tree / "src/mcgyvr/worker/prompt.py").write_text("y = 99\n")
    assert product.digest(tree) != before


def test_the_digest_moves_on_a_rename_with_no_content_change(
    product: Any, tmp_path: Path
) -> None:
    """Paths are in the hashed text, not only contents."""
    tree = _tree(tmp_path)
    before = product.digest(tree)
    (tree / "src/mcgyvr/runner.py").rename(tree / "src/mcgyvr/dispatch.py")
    assert product.digest(tree) != before


def test_the_digest_is_stable_across_calls(product: Any, tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    assert product.digest(tree) == product.digest(tree)


def test_a_missing_surface_entry_raises_rather_than_shrinking_the_pin(
    product: Any, tmp_path: Path
) -> None:
    """A deleted rig file must not make the pin weaker while looking identical."""
    tree = _tree(tmp_path)
    (tree / "tools/bench/score.py").unlink()
    with pytest.raises(product.ProductError, match="not a file or a directory"):
        product.digest(tree)


def test_the_task_set_is_not_in_the_surface(product: Any) -> None:
    """`tasks_sha256` pins them; folding them in would close a round on authoring.

    Named by directory rather than by the substring `tasks`, which
    `data/task-catalog.json` would otherwise trip. The catalog is the vocabulary
    a contract is validated against and it *is* in the surface; the problems are
    the corpus and are not.
    """
    assert not any(entry.endswith("/tasks") for entry in product.SURFACE)
    assert "data/task-catalog.json" in product.SURFACE


def test_the_bar_is_in_the_surface(product: Any) -> None:
    """#291: the pin covered the scorer and not the scorer's configuration.

    Both lockfiles or neither. The arms are paired ts/py (ADR-0021, ADR-0025),
    so pinning ruff while eslint floats puts a language effect inside every
    contrast rather than a visible refusal.

    Both *halves* or neither, for the same reason. `prettier.config.mjs` joined
    in the change that created it (#262, ADR-0035): before that the JS/TS format
    bar was prettier's built-in defaults and only the version could be pinned,
    so a declared config the round did not hold would restate this test's own
    defect — the pin covering the scorer and not its configuration.
    """
    for entry in (
        "pyproject.toml",
        "eslint.config.mjs",
        "prettier.config.mjs",
        "uv.lock",
        "package-lock.json",
    ):
        assert entry in product.SURFACE


def test_changing_the_lint_config_moves_the_digest(
    product: Any, tmp_path: Path
) -> None:
    """A rule flipped to `warn` narrows the bar; until #291 no round refused."""
    tree = _tree(tmp_path)
    before = product.digest(tree)
    (tree / "eslint.config.mjs").write_text("export default [{rules: {}}];\n")
    assert product.digest(tree) != before
    after = product.digest(tree)
    (tree / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
    assert product.digest(tree) != after


def test_changing_the_format_config_moves_the_digest(
    product: Any, tmp_path: Path
) -> None:
    """`printWidth` decides a verdict as surely as an eslint rule does.

    The format rung rejects a worker-added line prettier would reflow, so a
    column count is a bar. Until #262 there was no file to change and the round
    could not have noticed.
    """
    tree = _tree(tmp_path)
    before = product.digest(tree)
    (tree / "prettier.config.mjs").write_text("export default {printWidth: 100};\n")
    assert product.digest(tree) != before


def test_a_non_python_file_under_a_declared_directory_is_covered(
    product: Any, tmp_path: Path
) -> None:
    """`src/mcgyvr/prompts/*.md` is the text a worker is sent (#291)."""
    tree = _tree(tmp_path)
    before = product.digest(tree)
    (tree / "src/mcgyvr/prompts/python.md").write_text("You are a different worker.\n")
    assert product.digest(tree) != before


def test_a_derived_artifact_does_not_move_the_digest(
    product: Any, tmp_path: Path
) -> None:
    """Otherwise the pin would depend on whether the tree had been imported."""
    tree = _tree(tmp_path)
    before = product.digest(tree)
    cache = tree / "src/mcgyvr/__pycache__"
    cache.mkdir()
    (cache / "runner.cpython-312.pyc").write_bytes(b"\x00compiled")
    (tree / "src/mcgyvr/runner.pyc").write_bytes(b"\x00also")
    assert product.digest(tree) == before


def test_the_open_round_is_complete(product: Any) -> None:
    """Every field a reader needs to place a measurement, or the round is a stamp.

    Deliberately *not* an assertion that this tree matches the open round. A
    round is opened when a campaign begins; between campaigns the product moves,
    and requiring the two to agree at all times would mean opening a round per
    commit, which makes the boundary meaningless. What must hold at all times is
    that the open round says which revision it pins, when, and why — the refusal
    in ``require_pinned`` is what compares it to the tree, and it fires at
    dispatch, where the rig time is about to be spent.
    """
    current = product.open_round()
    for field in ("id", "opened", "product_sha256", "why", "files"):
        assert current.get(field), f"the open round declares no {field}"
    assert len(current["product_sha256"]) == 64


# --- the round --------------------------------------------------------------


def _rounds(tmp_path: Path, *entries: dict[str, Any]) -> Path:
    path = tmp_path / "rounds.json"
    path.write_text(json.dumps({"rounds": list(entries)}))
    return path


def test_the_open_round_is_the_last_entry(product: Any, tmp_path: Path) -> None:
    path = _rounds(
        tmp_path,
        {"id": "r1", "product_sha256": "aaa"},
        {"id": "r2", "product_sha256": "bbb"},
    )
    assert product.open_round(path)["id"] == "r2"


def test_a_moved_tree_is_refused_and_the_boundary_is_named(
    product: Any, tmp_path: Path
) -> None:
    """This is check 3's teeth: a stamp records, a refusal prevents."""
    tree = _tree(tmp_path / "tree")
    path = _rounds(tmp_path, {"id": "r1", "product_sha256": "not-this-tree"})
    with pytest.raises(product.ProductError) as caught:
        product.require_pinned(tree, path)
    message = str(caught.value)
    assert "moved off round `r1`" in message
    assert "--open" in message
    assert "re-baselines" in message


def test_the_refusal_names_which_files_moved(product: Any, tmp_path: Path) -> None:
    tree = _tree(tmp_path / "tree")
    files = {line.split(" ")[0]: line.split(" ")[1] for line in product._lines(tree)}
    files["src/mcgyvr/worker/prompt.py"] = "0" * 64
    path = _rounds(tmp_path, {"id": "r1", "product_sha256": "stale", "files": files})
    with pytest.raises(product.ProductError, match=r"src/mcgyvr/worker/prompt\.py"):
        product.require_pinned(tree, path)


# --- the batching rule (#291, ADR-0032) -------------------------------------


def test_the_shipped_doctrine_carries_the_batching_clause(product: Any) -> None:
    """The rule lived only in the body of a closed issue until #291.

    Asserted against the shipped `rounds.json` rather than a fixture: the defect
    was that the rule was *not in the repository*, and a fixture would pass with
    the file still empty.
    """
    clauses = product.load_doctrine().get("clauses", [])
    assert clauses, "rounds.json declares no doctrine"
    assert any("DRAINED" in c for c in clauses), (
        "no clause says a boundary carries every pending identity change; a "
        "driver reading rounds.json learns only that rounds exist"
    )


def test_a_driver_who_reads_only_product_py_learns_the_batching_rule(
    product: Any,
) -> None:
    """#291 acceptance 1. The docstring is where a driver actually looks."""
    text = product.__doc__ or ""
    assert "every pending identity change lands in the same boundary" in text.lower()


def test_a_file_with_no_doctrine_block_yields_an_empty_one(
    product: Any, tmp_path: Path
) -> None:
    """Doctrine constrains a judgement; a round opened without it is still a round."""
    path = _rounds(tmp_path, {"id": "r1", "product_sha256": "aaa"})
    assert product.load_doctrine(path) == {}


def _open_in(
    product: Any,
    monkeypatch: pytest.MonkeyPatch,
    tree: Path,
    rounds: Path,
    **kwargs: Any,
) -> int:
    monkeypatch.setattr(product, "REPO", tree)
    monkeypatch.setattr(product, "ROUNDS_FILE", rounds)
    args = argparse.Namespace(
        open="r2", opened="2026-08-17", issue=291, why="the batch", adopted=[]
    )
    for key, value in kwargs.items():
        setattr(args, key, value)
    return int(product._open_cli(args))


def test_opening_a_round_without_naming_the_batch_is_refused(
    product: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_open_cli` appended unconditionally, which is where the rule was violable."""
    tree = _tree(tmp_path / "tree")
    rounds = _rounds(tmp_path, {"id": "r1", "product_sha256": "aaa"})
    with pytest.raises(product.ProductError, match="--adopted"):
        _open_in(product, monkeypatch, tree, rounds)


def test_a_named_batch_is_recorded_in_the_round(
    product: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The tool records the batch; it cannot verify it, and the entry is the claim."""
    tree = _tree(tmp_path / "tree")
    rounds = _rounds(tmp_path, {"id": "r1", "product_sha256": "aaa"})
    assert (
        _open_in(
            product, monkeypatch, tree, rounds, adopted=["#291 the bar", "#285 digests"]
        )
        == 0
    )
    entry = json.loads(rounds.read_text())["rounds"][-1]
    assert entry["id"] == "r2"
    assert entry["adopted"] == ["#291 the bar", "#285 digests"]
    # The digest and the file map describe the same tree. They did not: the
    # helpers took the repo root as a *default argument*, bound at definition
    # time, so `digest()` read the real repository while `_lines(REPO)` read
    # whatever the global had been pointed at. Same paths in production, two
    # different trees in one round entry under anything that redirects them.
    assert entry["product_sha256"] == product.digest(tree)
    assert set(entry["files"]) == {
        p.relative_to(tree).as_posix() for p in product.surface_files(tree)
    }


def test_the_doctrine_is_printed_at_the_moment_the_rule_is_violable(
    product: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rule a driver has to go looking for is the rule lane/261 walked past."""
    tree = _tree(tmp_path / "tree")
    path = tmp_path / "rounds.json"
    path.write_text(
        json.dumps(
            {
                "doctrine": {"clauses": ["A round boundary is DRAINED, not TAKEN."]},
                "rounds": [{"id": "r1", "product_sha256": "aaa"}],
            }
        )
    )
    _open_in(product, monkeypatch, tree, path, adopted=["#291"])
    assert "DRAINED" in capsys.readouterr().out


def test_opening_a_round_does_not_drop_the_doctrine(
    product: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_open_cli` rewrites the whole file, so the block has to survive the write."""
    tree = _tree(tmp_path / "tree")
    path = tmp_path / "rounds.json"
    doctrine = {"clauses": ["A round boundary is DRAINED, not TAKEN."]}
    path.write_text(json.dumps({"doctrine": doctrine, "rounds": [{"id": "r1"}]}))
    _open_in(product, monkeypatch, tree, path, adopted=["#291"])
    assert json.loads(path.read_text())["doctrine"] == doctrine


def test_a_run_with_no_round_is_described_rather_than_skipped(product: Any) -> None:
    """Those runs are readable; what is true of them is that nothing recorded it."""
    line = product.declare({})
    assert "none recorded" in line
    assert "cannot be laid beside" in line


def test_a_figure_across_two_revisions_says_mixed(product: Any) -> None:
    line = product.banner(
        [
            {"round": "r1", "product_sha256": "aaa"},
            {"round": "r2", "product_sha256": "bbb"},
        ]
    )
    assert "mixed" in line and "r1" in line and "r2" in line


# --- the mode ---------------------------------------------------------------


def test_a_manifest_without_the_field_is_answered_not_guessed(mode: Any) -> None:
    """No rig here has ever escalated, so the absence is answerable from the code."""
    assert mode.of({}) == mode.SINGLE_TIER
    assert "not recorded in this manifest" in mode.declare({})


def test_a_recorded_mode_is_declared_without_the_caveat(mode: Any) -> None:
    line = mode.declare({"mode": mode.SINGLE_TIER})
    assert "single-tier" in line
    assert "not recorded" not in line


def test_the_ladder_mode_says_a_rescue_counts_as_a_pass(mode: Any) -> None:
    """ADR-0017 P3: the second mode must not be invented under pressure."""
    line = mode.declare({"mode": mode.FULL_LADDER})
    assert "full-ladder" in line
    assert "rescued by a higher rung" in line


def test_an_unknown_mode_is_refused(mode: Any) -> None:
    with pytest.raises(mode.ModeError, match="not one of"):
        mode.of({"mode": "whatever"})


def test_a_figure_mixing_the_two_modes_is_refused(mode: Any) -> None:
    """A pooled rate answers neither question, and the honest response is to stop."""
    with pytest.raises(mode.ModeError, match="drawn across"):
        mode.banner([{"mode": mode.SINGLE_TIER}, {"mode": mode.FULL_LADDER}])


def test_a_cell_is_read_by_path_or_by_run_arm_name(mode: Any, tmp_path: Path) -> None:
    cell = tmp_path / "run-x" / "bench-py"
    cell.mkdir(parents=True)
    (cell / "run.json").write_text(json.dumps({"mode": mode.SINGLE_TIER}))
    assert len(mode.read(cell)) == 1
    assert mode.read(tmp_path / "run-x" / "absent") == []


# --- the guard that discovers rather than names -----------------------------

# Tools under `tools/bench/` and `tools/power/` that do not produce a figure a
# reader could quote a rate from, with the reason each is exempt. A tool absent
# from both this set and the checked set below fails the test — which is the
# point: the default for a new tool is "must declare", not "was forgotten".
NOT_A_FIGURE = {
    "tools/bench/admit.py": "the admission gate; it admits problems and states no rate",
    "tools/bench/emit.py": "authoring scaffolding for candidate problems",
    "tools/bench/split.py": "the blind bench/reserve assignment rule",
    "tools/bench/matrix.py": "the condition matrix loader",
    "tools/bench/score.py": "the scorer itself, wrapped by the rigs",
    "tools/bench/mode.py": "the declaration",
    "tools/bench/serving/launch.py": (
        "the harness marker check (D8). It reads the serving source for the "
        "decision markers and reports which are missing; the door's gate 2 "
        "(02-rig.py) runs it as sub-check 2b and it launches nothing itself. "
        "It measures "
        "nothing, states no rate, and describes no run"
    ),
    "tools/bench/product.py": "the pin the declaration reads",
    "tools/bench/regrade.py": "re-scores rows in place; it reports verdicts moved",
    "tools/power/mde.py": "the arithmetic; it has no run directories to describe",
    "tools/bench/prose.py": "reads contracts only; it states no rate, describes no run",
    "tools/bench/families.py": "cross-executes references; it reads no run and no rate",
    "tools/bench/ratecard.py": (
        "what a null costs per task (#289). It states a cost rate in seconds, "
        "not a pass rate, and describes no outcome — so there is no tier "
        "attribution to declare and no escalation that could hide a floor"
    ),
    "tools/bench/idempotency.py": (
        "the language-idempotency census (#295). It reads contracts and "
        "references through emit.py's divergence screen and reports a share of "
        "the CORPUS — how much of it could be rendered into both arms — so it "
        "describes no run and states no pass rate, the same exemption prose.py "
        "holds for the same reason"
    ),
    "tools/bench/identity.py": (
        "run identity and its migration tag (ADR-0027). It reads every manifest "
        "and states what each one can and cannot say about itself; it states no "
        "pass rate and describes no outcome, so there is no mode to declare"
    ),
    "tools/bench/headers.py": (
        "the run headers (#330, the half of #322 that is not the gate). It "
        "lists what each run is FOR — the question, the arms, the cost and its "
        "source — and counts how many headers carry a run block against the "
        "review point. It reads no run directory and no row, states no rate, "
        "and describes no outcome; the one number it prints is a count of "
        "files"
    ),
    "tools/bench/serving/run.py": (
        "the serving survey's orchestrator (#286 lane). It records what is on "
        "the machines and how they are configured — models held, endpoints "
        "answered, service settings, measured batch width — and reads no run "
        "directory and no row. It states a throughput in tokens per second, "
        "which is the same exemption `ratecard.py` holds for a rate in "
        "seconds: not a pass rate, so there is no tier attribution to declare "
        "and no escalation that could hide a floor"
    ),
    "tools/bench/serving/pin.py": (
        "binds a run to what the serving host said, as three falsifiable "
        "claims — same machine, same process, same configuration (#286 lane). "
        "It reads no run directory and no row, and states no rate: what it "
        "produces is a boolean about whether other readings can be trusted"
    ),
    "tools/bench/serving/fingerprint.py": (
        "the serving-configuration fingerprint (#286 lane). It parses what a "
        "server says it was configured with and pins it as two digests — "
        "semantic and operational — and reads no run directory, no row and no "
        "rate. It states nothing about outcomes at all"
    ),
    "tools/bench/serving/knobs.py": (
        "the knob surface (#357): declared, accepted, effective. It reads the "
        "sweep's records into a table of launch outcomes and single-flag "
        "throughput ratios; no task is scored and no pass rate is stated"
    ),
    "tools/bench/serving/calibrate.py": (
        "the constants campaign (#286 lane). It measures the thresholds and "
        "timeouts `serving/` was built on — array sizes, load durations, VRAM "
        "fractions, the concurrency ramp at several token counts — and writes "
        "every sample as it is taken. Its figures are tokens per second and "
        "speedup RATIOS against a single request: properties of a server, not "
        "of a run. It reads no run directory and no row, so there is no tier "
        "attribution to declare, the same exemption `run.py` holds beside it"
    ),
    "tools/bench/serving/contract.py": (
        "the backend interface and the pieces no engine owns — the ramp and "
        "the machine readings. It describes servers, never runs"
    ),
    "tools/bench/serving/backends/llamacpp.py": (
        "one serving backend: how that engine yields the card, takes it and "
        "describes itself. It states no rate about any run"
    ),
    "tools/bench/serving/backends/ollama.py": (
        "one serving backend: how that engine yields the card, takes it and "
        "describes itself. It states no rate about any run"
    ),
    "tools/bench/serving/backends/vllm.py": (
        "one serving backend: how that engine yields the card, takes it and "
        "describes itself. It states no rate about any run"
    ),
    "tools/bench/observed.py": (
        "the `observed` block's writer (#286, ADR-0027 D7). It captures what a "
        "serving endpoint says about itself and writes it beside the manifest; "
        "it reads no rows, states no rate and describes no outcome. The mode "
        "declaration would be doubly meaningless here, since nothing reads this "
        "block for comparison at all — the property its own test suite pins"
    ),
    "tools/bench/ceiling.py": (
        "what the acceptance ceiling bounds (#262, ADR-0035). It reports "
        "DURATIONS — the reference sweep it runs, and the `acceptance_s` field "
        "of rows already recorded — so it states no pass rate and describes no "
        "outcome. The same exemption `ratecard.py` holds, and for the same "
        "reason: a rate in seconds is not a rate a tier could hide a floor in"
    ),
}

# Keyed by repo-relative path, not basename: `tools/bench/report.py` and
# `tools/power/report.py` are different tools with the same file name, and a
# basename key would let one of them inherit the other's classification.
CHECKED = {
    "tools/bench/eligibility.py",
    "tools/bench/null.py",
    "tools/bench/resolution.py",
    "tools/bench/responsive.py",
    "tools/bench/control.py",
    "tools/bench/lintless.py",
    "tools/bench/ablation_report.py",
    "tools/bench/responsiveness.py",
    "tools/bench/redundancy.py",
    # Checked rather than exempt, unlike its neighbour `regrade.py`. That one
    # re-runs acceptance and reports only how many verdicts moved; this one
    # restates a whole run's pass rate under a *different scorer*, which is a
    # figure a reader will quote against the gate-scored sweeps. So it declares
    # the mode and the round pin its rows were produced under (#224 A2).
    "tools/bench/gate_rescore.py",
    "tools/bench/report.py",
    "tools/power/report.py",
    # Checked rather than exempt, though it states no *pass* rate. Its figures
    # are agreement and concordance over recorded verdicts, and a reader will
    # quote "the arms agree on 84%" against a sweep — so the row has to say
    # which tier's verdicts it agrees about (#295, #231 check 6).
    "tools/bench/arms.py",
}


#: Directory names under the figure trees that hold CORPUS rather than tools.
#: `reserve/` and `tasks/` are problems — an `accept.py` is a task's acceptance
#: script, not something that could state a rate — so they are named here and
#: everything else is swept in. Excluding by name rather than including by name
#: keeps the property this file is built on: the default for a new directory of
#: code is "must declare", not "was forgotten".
NOT_TOOLS = {"__pycache__", "reserve", "tasks", "problems"}


def _figure_tools() -> list[str]:
    """Every tool under the figure-producing trees, at any depth.

    ``rglob`` rather than ``glob``: the flat form let a whole subdirectory
    escape the classification this check exists to enforce, so a tool added
    under ``tools/bench/<anything>/`` would never have to declare whether it
    states a rate. A default of "was forgotten" is exactly what this test is
    for, and it cannot apply to files it never looks at.
    """
    found = []
    for directory in (REPO / "tools" / "bench", REPO / "tools" / "power"):
        found.extend(
            sorted(
                p.relative_to(REPO).as_posix()
                for p in directory.rglob("*.py")
                if p.is_file() and not NOT_TOOLS.intersection(p.parts)
            )
        )
    return found


def test_every_figure_tool_is_classified() -> None:
    """A tool that is neither checked nor exempted fails here, by construction."""
    unclassified = [
        p for p in _figure_tools() if p not in NOT_A_FIGURE and p not in CHECKED
    ]
    assert not unclassified, (
        f"{unclassified} produce output nobody has said is or is not a bench "
        "figure. #231 check 6 requires every figure to declare its mode; add "
        "the declaration and list the tool in CHECKED, or say why it states no "
        "rate in NOT_A_FIGURE."
    )


def test_nothing_is_both_checked_and_exempt() -> None:
    assert not (set(CHECKED) & set(NOT_A_FIGURE))


@pytest.mark.parametrize("relative", sorted(CHECKED))
def test_the_declaration_is_in_the_source_of_every_checked_tool(relative: str) -> None:
    """Read statically: some of these take minutes to re-score a run."""
    text = (REPO / relative).read_text(encoding="utf-8")
    assert "mode.declare(" in text or "mode.banner(" in text, (
        f"{relative} states no mode for its figures"
    )
