"""Bounded targeted reads are the one place exploration spends tokens, so these
tests hold :func:`explore` to #49's acceptance — the spend is recorded and
bounded, every read is attributed to the candidate that motivated it, and
exceeding the budget yields an explicit partial plan rather than silent
continuation — plus the region selection that makes the reads *targeted*: a
matched definition is read at its site, and a filename-only match falls back to
the file head instead of being read as nothing.

Explorations run over a real resolution of a small built repo, so the assertions
are about the plan a caller receives, not the windowing internals.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import ExplorationError, explore
from mcgyvr.orchestrator.resolve import resolve


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def build(tmp_path: Path, files: dict[str, str]) -> Index:
    """Init a git repo with ``files`` and return its built index."""
    git(tmp_path, "init", "-q", "-b", "main")
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return build_index(tmp_path)


def big(name: str, lines: int = 60) -> str:
    """A source file with a named function and enough bulk to cost real budget."""
    body = "\n".join(f"    # padding line {n}" for n in range(lines))
    return f"def {name}():\n{body}\n    return 1\n"


# --- the spend is recorded and bounded -------------------------------------


def test_the_spend_is_recorded_and_within_budget(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    plan = explore(index, resolve(index, "the fetch helper"), budget=500)
    assert plan.spent <= plan.budget
    assert plan.spent == sum(r.estimated_tokens for r in plan.reads)
    assert plan.reads  # something was read within a comfortable budget


def test_a_non_positive_budget_is_a_named_failure(tmp_path: Path) -> None:
    index = build(tmp_path, {"a.py": "def f():\n    pass\n"})
    resolution = resolve(index, "f")
    with pytest.raises(ExplorationError, match="must be positive"):
        explore(index, resolution, budget=0)


# --- exceeding the budget forces an explicit decision ----------------------


def test_exceeding_the_budget_defers_rather_than_continues(tmp_path: Path) -> None:
    # Several fat candidates, a budget that fits only some: the rest must be
    # deferred and named, and the plan must announce it is exhausted.
    index = build(
        tmp_path,
        {f"pkg{n}/handler.py": big("handler") for n in range(6)},
    )
    plan = explore(index, resolve(index, "handler"), budget=400)
    assert plan.exhausted is True
    assert plan.complete is False
    assert plan.deferred  # the overflow is recorded, not dropped
    assert plan.spent <= plan.budget
    # A deferral carries the cost it would have added — the overrun is visible.
    assert all(d.estimated_tokens > 0 for d in plan.deferred)


def test_a_budget_too_small_for_any_region_reads_nothing_but_reports(
    tmp_path: Path,
) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper", lines=80)})
    plan = explore(index, resolve(index, "fetch helper"), budget=1)
    assert plan.reads == ()
    assert plan.exhausted is True
    assert plan.deferred  # named failure as a plan, never silent


def test_a_comfortable_budget_completes(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": "def fetch_helper():\n    return 1\n"})
    plan = explore(index, resolve(index, "the fetch helper"), budget=100_000)
    assert plan.exhausted is False
    assert plan.complete is True
    assert plan.deferred == ()


# --- every read is attributed and targeted ---------------------------------


def test_reads_are_attributed_to_the_candidate_that_motivated_them(
    tmp_path: Path,
) -> None:
    index = build(tmp_path, {"src/net.py": "def fetch_helper():\n    return 1\n"})
    plan = explore(index, resolve(index, "the fetch helper"), budget=100_000)
    assert plan.reads
    read = plan.reads[0]
    assert read.candidate_rank == 1
    assert read.path == "src/net.py"
    assert "fetch_helper" in read.reason


def test_a_definition_is_read_at_its_site(tmp_path: Path) -> None:
    # The name sits deep in the file; the read must land on the definition, not
    # the top of the file.
    preamble = "\n".join(f"# line {n}" for n in range(40))
    body = f"{preamble}\ndef target_symbol():\n    return 1\n"
    index = build(tmp_path, {"src/mod.py": body})
    plan = explore(index, resolve(index, "target_symbol"), budget=100_000)
    hit = next(r for r in plan.reads if r.path == "src/mod.py")
    assert hit.start <= 41 <= hit.end  # the def line (1-based) is inside the window
    assert "target_symbol" in hit.text


def test_a_filename_only_match_falls_back_to_the_file_head(tmp_path: Path) -> None:
    # 'settings' names the file but no symbol in it, so the read is the head.
    body = "VALUE = 1\n" + "\n".join(f"# tail {n}" for n in range(30)) + "\n"
    index = build(tmp_path, {"settings.py": body})
    plan = explore(index, resolve(index, "settings"), budget=100_000)
    hit = next(r for r in plan.reads if r.path == "settings.py")
    assert hit.start == 1
    assert "file head" in hit.reason


def test_the_read_text_matches_the_reported_line_range(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper", lines=40)})
    plan = explore(index, resolve(index, "fetch helper"), budget=100_000)
    hit = plan.reads[0]
    expected = "\n".join(
        (tmp_path / hit.path).read_text().split("\n")[hit.start - 1 : hit.end]
    )
    assert hit.text == expected


# --- degenerate inputs -----------------------------------------------------


def test_an_empty_resolution_explores_nothing(tmp_path: Path) -> None:
    index = build(tmp_path, {"a.py": "def real():\n    pass\n"})
    plan = explore(index, resolve(index, "no such target here zzz"), budget=1000)
    assert plan.reads == ()
    assert plan.deferred == ()
    assert plan.exhausted is False  # nothing to defer is not an overrun
    assert plan.spent == 0


def test_overlapping_anchors_are_read_once(tmp_path: Path) -> None:
    # Two definitions a line apart fall inside one window; they must not produce
    # two overlapping reads of the same lines.
    index = build(
        tmp_path,
        {"src/mod.py": "def fetch_one():\n    pass\n\n\ndef fetch_two():\n    pass\n"},
    )
    plan = explore(index, resolve(index, "fetch"), budget=100_000)
    spans = [(r.start, r.end) for r in plan.reads if r.path == "src/mod.py"]
    assert len(spans) == 1  # merged into a single region


def test_an_injected_estimate_is_used_for_the_budget(tmp_path: Path) -> None:
    # A caller with a real tokenizer supplies its own estimate; the budget must
    # be enforced in that caller's unit, not the default one.
    index = build(tmp_path, {"src/net.py": "def fetch_helper():\n    return 1\n"})
    resolution = resolve(index, "fetch helper")
    plan = explore(index, resolution, budget=5, estimate=lambda text: 5)
    assert all(r.estimated_tokens == 5 for r in plan.reads)
    assert plan.spent <= 5
