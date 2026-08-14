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
    for entry in ("src/mcgyvr", "tools/breadth", "tools/bundle", "tools/bench"):
        (root / entry).mkdir(parents=True, exist_ok=True)
    (root / "src/mcgyvr/runner.py").write_text("x = 1\n")
    (root / "src/mcgyvr/worker").mkdir(exist_ok=True)
    (root / "src/mcgyvr/worker/prompt.py").write_text("y = 2\n")
    (root / "tools/breadth/measure.py").write_text("m = 3\n")
    (root / "tools/bundle/measure.py").write_text("b = 4\n")
    (root / "tools/bench/score.py").write_text("s = 5\n")
    (root / "tools/bench/matrix.py").write_text("mx = 6\n")
    (root / "tools/bench/matrix.json").write_text("{}\n")
    (root / "tools/bench/product.py").write_text("p = 7\n")
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


def test_tasks_are_not_in_the_surface(product: Any) -> None:
    """`tasks_sha256` pins them; folding them in would close a round on authoring."""
    assert not any("tasks" in entry for entry in product.SURFACE)


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
    "tools/bench/product.py": "the pin the declaration reads",
    "tools/bench/regrade.py": "re-scores rows in place; it reports verdicts moved",
    "tools/power/mde.py": "the arithmetic; it has no run directories to describe",
}

# Keyed by repo-relative path, not basename: `tools/bench/report.py` and
# `tools/power/report.py` are different tools with the same file name, and a
# basename key would let one of them inherit the other's classification.
CHECKED = {
    "tools/bench/eligibility.py",
    "tools/bench/null.py",
    "tools/bench/control.py",
    "tools/bench/lintless.py",
    "tools/bench/ablation_report.py",
    "tools/bench/responsiveness.py",
    "tools/bench/redundancy.py",
    "tools/bench/report.py",
    "tools/power/report.py",
}


def _figure_tools() -> list[str]:
    found = []
    for directory in (REPO / "tools" / "bench", REPO / "tools" / "power"):
        found.extend(
            sorted(
                p.relative_to(REPO).as_posix()
                for p in directory.glob("*.py")
                if p.is_file()
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
