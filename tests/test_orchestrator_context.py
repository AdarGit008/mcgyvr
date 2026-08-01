"""Agent-supplied context is the one input to exploration that comes from
something fallible, so these tests hold it to #51's acceptance from both sides:
that a *good* hint measurably reduces spend, and that a *wrong* one cannot reach
the plan at all — it does not change which files are targeted, does not overturn
a resolution the index already made, and is reported rather than silently
absorbed. The deterministic pass is asserted to be unskippable: a supplied file
the resolver never shortlisted is never read, however loudly the caller names it.

Everything runs over a real index of a small built repo, so the assertions are
about the plan and the resolution a caller receives.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcgyvr.orchestrator.context import (
    Discrepancy,
    SuppliedContext,
    VerifiedContext,
    accelerate,
    verify,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import Candidate, Resolution, Verdict, resolve


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


def leaning_field() -> Resolution:
    """An ambiguous shortlist that leans: 120 vs 100 is short of the 1.5 dominance
    the resolver demands, but within reach of a single boost."""
    return Resolution(
        query="handler",
        verdict=Verdict.AMBIGUOUS,
        candidates=(
            Candidate(
                path="src/handler.py", score=120.0, evidence=("defines handler",)
            ),
            Candidate(
                path="src/misc.py", score=100.0, evidence=("handler ~ 'handler'",)
            ),
        ),
    )


def named(*paths: str) -> VerifiedContext:
    """Verified context for a caller that named ``paths`` without supplying text."""
    return VerifiedContext(trusted=frozenset(paths), fresh=frozenset(), findings=())


def holding(index: Index, *paths: str) -> VerifiedContext:
    """Verified context for a caller that holds the current text of ``paths``."""
    contents = {
        path: "\n".join(file.lines)
        for file in index.files
        for path in paths
        if file.path == path
    }
    return verify(index, SuppliedContext(paths=paths, contents=contents))


# --- supplied context measurably reduces exploration spend -----------------


def test_supplied_content_is_not_charged_to_the_budget(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    resolution = resolve(index, "the fetch helper")

    baseline = explore(index, resolution, budget=100_000)
    accelerated = explore(
        index, resolution, budget=100_000, supplied=holding(index, "src/net.py")
    )

    assert baseline.spent > 0
    assert accelerated.spent == 0  # the caller already holds every region
    assert accelerated.saved == baseline.spent
    assert [r.path for r in accelerated.reads] == [r.path for r in baseline.reads]
    assert all(r.supplied for r in accelerated.reads)


def test_the_saving_buys_coverage_the_budget_could_not_afford(tmp_path: Path) -> None:
    """The point of the saving: regions that were deferred now fit."""
    index = build(
        tmp_path,
        {"src/net.py": big("fetch_helper"), "src/util.py": big("fetch_retry")},
    )
    resolution = resolve(index, "fetch")

    baseline = explore(index, resolution, budget=200)
    accelerated = explore(
        index, resolution, budget=200, supplied=holding(index, "src/net.py")
    )

    assert baseline.exhausted  # the budget could not cover both files
    assert len(accelerated.reads) > len(baseline.reads)
    assert accelerated.saved > 0


def test_a_read_reports_its_real_cost_even_when_it_was_free(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    plan = explore(
        index,
        resolve(index, "the fetch helper"),
        budget=100_000,
        supplied=holding(index, "src/net.py"),
    )
    free = [r for r in plan.reads if r.supplied]
    assert free
    # The audit trail stays honest: the cost is recorded, it was simply not paid.
    assert all(r.estimated_tokens > 0 for r in free)
    assert plan.saved == sum(r.estimated_tokens for r in free)
    assert plan.spent == sum(r.estimated_tokens for r in plan.reads if not r.supplied)


# --- a wrong hint cannot change which files the plan targets ---------------


def test_a_hint_naming_an_unknown_path_is_dropped_and_reported(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    verified = verify(index, SuppliedContext(paths=("src/imaginary.py",)))

    assert not verified.trusted
    assert not verified
    assert [f.discrepancy for f in verified.findings] == [Discrepancy.UNKNOWN_PATH]
    assert verified.findings[0].path == "src/imaginary.py"


def test_stale_supplied_content_is_rejected_and_the_file_read_normally(
    tmp_path: Path,
) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    stale = SuppliedContext(
        paths=("src/net.py",), contents={"src/net.py": "def fetch_helper(): pass\n"}
    )
    verified = verify(index, stale)

    # The path is real, so it may still re-rank — but its *content* is not
    # believed, so nothing is read for free.
    assert verified.trusted == frozenset({"src/net.py"})
    assert verified.fresh == frozenset()
    assert [f.discrepancy for f in verified.findings] == [Discrepancy.STALE_CONTENT]

    plan = explore(index, resolve(index, "the fetch helper"), supplied=verified)
    assert plan.saved == 0
    assert plan.spent > 0
    assert not any(r.supplied for r in plan.reads)


def test_a_wrong_hint_does_not_change_the_leader_of_a_resolved_shortlist(
    tmp_path: Path,
) -> None:
    """The safety bound, end to end: the boost cannot overtake a dominant leader."""
    index = build(
        tmp_path,
        {
            "src/fetch_helper.py": big("fetch_helper"),
            "src/misc.py": big("fetch_retry_after_backoff"),
        },
    )
    resolution = resolve(index, "fetch helper")
    assert resolution.verdict is Verdict.RESOLVED
    leader = resolution.candidates[0].path
    runner_up = resolution.candidates[1].path

    # A caller insists, wrongly, that the runner-up is the target.
    accelerated = accelerate(resolution, holding(index, runner_up))

    assert accelerated.resolution.candidates[0].path == leader
    assert accelerated.resolution.verdict is Verdict.RESOLVED


def test_a_hint_cannot_add_a_path_to_the_shortlist(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {"src/net.py": big("fetch_helper"), "docs/unrelated.md": "# nothing to do\n"},
    )
    resolution = resolve(index, "the fetch helper")
    targeted = {c.path for c in resolution.candidates}
    assert "docs/unrelated.md" not in targeted

    accelerated = accelerate(resolution, holding(index, "docs/unrelated.md"))

    assert {c.path for c in accelerated.resolution.candidates} == targeted
    assert [f.discrepancy for f in accelerated.findings] == [Discrepancy.UNCORROBORATED]


def test_an_accelerated_resolution_is_never_less_certain(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {
            "src/fetch_helper.py": big("fetch_helper"),
            "src/misc.py": big("fetch_retry_after_backoff"),
        },
    )
    resolution = resolve(index, "fetch helper")
    assert resolution.verdict is Verdict.RESOLVED

    # Boosting the runner-up narrows the gap; the verdict must not degrade.
    accelerated = accelerate(resolution, holding(index, resolution.candidates[1].path))
    assert accelerated.resolution.verdict is Verdict.RESOLVED


def test_a_hint_reorders_an_ambiguous_field_but_does_not_manufacture_certainty(
    tmp_path: Path,
) -> None:
    """On a dead tie the hint decides read *order* and nothing else.

    Two identical candidates are exactly as good as each other; the boost lifts
    the named one to the front so it is read first, but it is capped below the
    dominance threshold, so it cannot promote a coin-flip to "the answer". The
    ambiguity the index reported survives the hint — which is what stops a
    confident caller from turning a guess into a verdict.
    """
    index = build(
        tmp_path,
        {"a/handler.py": big("handler"), "b/handler.py": big("handler")},
    )
    resolution = resolve(index, "handler")
    assert resolution.verdict is Verdict.AMBIGUOUS
    assert resolution.candidates[0].path == "a/handler.py"  # tie broken on path

    accelerated = accelerate(resolution, holding(index, "b/handler.py"))

    assert accelerated.resolution.candidates[0].path == "b/handler.py"
    assert accelerated.promoted == ("b/handler.py",)
    assert accelerated.resolution.verdict is Verdict.AMBIGUOUS


def test_a_hint_can_settle_an_ambiguity_that_was_already_leaning() -> None:
    """Where the index nearly decided, corroboration is enough to finish the job.

    Built from explicit scores rather than a repository: this is a property of
    the boost arithmetic, and pinning it to a fixture would make it hostage to
    the resolver's tuning.
    """
    resolution = leaning_field()
    accelerated = accelerate(resolution, named("src/handler.py"))

    assert accelerated.resolution.verdict is Verdict.RESOLVED
    assert accelerated.resolution.candidates[0].path == "src/handler.py"


def test_promoting_the_underdog_reorders_without_claiming_a_resolution() -> None:
    """A hint against the index's lean is obeyed for order, doubted for verdict."""
    accelerated = accelerate(leaning_field(), named("src/misc.py"))

    assert accelerated.resolution.candidates[0].path == "src/misc.py"
    assert accelerated.resolution.verdict is Verdict.AMBIGUOUS


def test_a_promoted_candidate_says_so_in_its_evidence(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    resolution = resolve(index, "the fetch helper")
    accelerated = accelerate(resolution, holding(index, "src/net.py"))

    best = accelerated.resolution.candidates[0]
    assert "supplied context names this path" in best.evidence
    # The deterministic evidence is kept, not replaced.
    assert set(resolution.candidates[0].evidence) <= set(best.evidence)


# --- the deterministic pass cannot be disabled -----------------------------


def test_a_supplied_file_outside_the_shortlist_is_never_read(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {"src/net.py": big("fetch_helper"), "docs/unrelated.md": "# nothing to do\n"},
    )
    resolution = resolve(index, "the fetch helper")
    plan = explore(index, resolution, supplied=holding(index, "docs/unrelated.md"))

    # Supplying a file is not a request to read it — only the shortlist decides.
    assert "docs/unrelated.md" not in {r.path for r in plan.reads}


def test_regions_are_identical_with_and_without_supplied_context(
    tmp_path: Path,
) -> None:
    """Supplied context changes what a plan *costs*, never what it covers."""
    index = build(
        tmp_path,
        {"src/net.py": big("fetch_helper"), "src/util.py": big("fetch_retry")},
    )
    resolution = resolve(index, "fetch")

    baseline = explore(index, resolution, budget=100_000)
    accelerated = explore(
        index, resolution, budget=100_000, supplied=holding(index, "src/net.py")
    )

    regions = [(r.path, r.start, r.end, r.reason) for r in baseline.reads]
    assert [(r.path, r.start, r.end, r.reason) for r in accelerated.reads] == regions


def test_exploration_without_supplied_context_is_unchanged(tmp_path: Path) -> None:
    """The accelerator is opt-in: absent hints, #49's behaviour is exactly as it was."""
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    plan = explore(index, resolve(index, "the fetch helper"), budget=100_000)

    assert plan.saved == 0
    assert not any(r.supplied for r in plan.reads)
    assert plan.spent == sum(r.estimated_tokens for r in plan.reads)


# --- verification details --------------------------------------------------


def test_supplying_content_alone_counts_as_naming_the_path(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    text = "\n".join(next(f for f in index.files if f.path == "src/net.py").lines)
    verified = verify(index, SuppliedContext(contents={"src/net.py": text}))

    assert verified.trusted == frozenset({"src/net.py"})
    assert verified.fresh == frozenset({"src/net.py"})
    assert verified.findings == ()


def test_a_correct_hint_is_accepted_in_whatever_shape_it_arrives(
    tmp_path: Path,
) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    absolute = str(tmp_path / "src" / "net.py")
    verified = verify(index, SuppliedContext(paths=("./src/net.py", absolute)))

    assert verified.trusted == frozenset({"src/net.py"})
    assert verified.findings == ()


def test_the_empty_verification_is_the_neutral_element(tmp_path: Path) -> None:
    index = build(tmp_path, {"src/net.py": big("fetch_helper")})
    resolution = resolve(index, "the fetch helper")

    assert not VerifiedContext.none()
    assert explore(index, resolution, supplied=VerifiedContext.none()).saved == 0
    assert accelerate(resolution, VerifiedContext.none()).resolution == resolution
