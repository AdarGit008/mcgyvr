"""Offline invariants over the problem pool (#197).

Admission itself executes checkers and needs `node` and `python` in the shape
the contracts declare; none of that belongs in the suite, the same way the
rigs' `--selftest` is a stated precondition rather than a test. What the
suite holds the repository to is everything checkable without running a
candidate:

* **The tree is the manifest.** Every pool task on disk is pinned byte for
  byte in ``admissions.jsonl``, and every pin either matches the tree or
  names its successor. Run directories pin the task set's digests, so an
  unpinned edit is not a tidy-up — it refuses prior runs a resume.
* **The id is the join key.** Directory name, contract id in both arms, and
  the ``p<nnn>-<slug>`` shape all agree, and no pool id collides with any
  other task set's — `tools/finetune/build_dataset.py` keys on the bare id.
* **The front door stays held out.** No pool problem implements a symbol
  whose normalised name is a HumanEval entry point, in either arm's casing.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    """A tool module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


admit = _by_path("pool_admit", REPO / "tools" / "problems" / "admit.py")
breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")


def _pool_ids() -> list[str]:
    ids: set[str] = set()
    for arm in admit.ARMS:
        if arm.root.is_dir():
            ids.update(p.name for p in arm.root.iterdir() if p.is_dir())
    return sorted(ids)


def test_manifest_and_tree_agree() -> None:
    assert admit.verify_manifest() == []


def test_ids_are_shaped_and_agree_across_arms() -> None:
    for problem in _pool_ids():
        assert admit.ID_RE.match(problem), problem
        for arm in admit.ARMS:
            contract = admit.load(arm.root / problem / "contract.yaml")
            assert contract.id == problem
            assert contract.task_type in admit.V1_TYPES


def test_pool_ids_collide_with_no_other_task_set() -> None:
    existing = admit.existing_tasks()
    pool = set(_pool_ids())
    for label, contract in existing.items():
        assert contract.id not in pool, f"{label} shares id {contract.id}"
        assert label.rsplit("/", 1)[-1] not in pool, label


def test_no_pool_symbol_is_a_humaneval_entry_point() -> None:
    blocklist = admit.humaneval_entry_points()
    for problem in _pool_ids():
        for arm in admit.ARMS:
            contract = admit.load(arm.root / problem / "contract.yaml")
            match = arm.interface_re.search(contract.interface)
            if match is not None:
                name = admit._normalise_symbol(match.group(1))
                assert name not in blocklist, f"{problem}: {match.group(1)}"


def test_checkers_meet_the_assertion_floor() -> None:
    for problem in _pool_ids():
        for arm in admit.ARMS:
            text = (arm.root / problem / arm.accept).read_text(encoding="utf-8")
            assert text.count("assert") >= admit.MIN_ASSERTIONS, (
                f"{problem} [{arm.name}]"
            )


def test_pool_tiers_load_pinned_problems_in_both_arms() -> None:
    """The rig seam: pool-ts and pool-py serve every pinned problem.

    Restricted to manifest-pinned ids so a half-written candidate a
    generator is still working on cannot fail the suite — the pinned set
    is the pool; the rest is not yet anything.
    """
    pinned = sorted(
        str(entry["id"])
        for entry in admit.manifest_entries()
        if not entry.get("superseded_by")
    )
    assert pinned, "an empty manifest would make this test vacuous"
    for tier, language in (("pool-ts", "jsts"), ("pool-py", "python")):
        tasks = breadth.load_tier_tasks(tier, only=pinned)
        assert sorted(task.id for task in tasks) == pinned
        assert {task.language.name for task in tasks} == {language}
        assert {task.contract.id for task in tasks} == set(pinned)


def test_pool_tiers_serve_only_admitted_problems() -> None:
    """A candidate on disk but absent from the manifest is not dispatchable.

    The pool grows in batches, so unadmitted directories exist while a batch
    is being written. They must not reach a sweep: a tier's ``tasks_sha256``
    covers what it serves, so an unadmitted candidate would enter a run's
    identity and split the tier into incomparable versions. Caught for real
    on 2026-08-07 — a probe run recorded 157 pool-py digests against 149
    pool-ts while a batch was mid-flight.
    """
    pinned = {
        str(entry["id"])
        for entry in admit.manifest_entries()
        if not entry.get("superseded_by")
    }
    for tier in breadth.POOL_TIERS:
        served = {task.id for task in breadth.load_tier_tasks(tier)}
        assert served <= pinned
        root = breadth.POOL_ROOT / tier.removeprefix("pool-")
        on_disk = {p.name for p in root.iterdir() if p.is_dir()}
        assert served == on_disk & pinned


def test_pool_tiers_are_not_campaign_rungs() -> None:
    """The campaign climbs TIERS; the pool must not be a rung it can reach."""
    for tier in breadth.POOL_TIERS:
        assert tier not in breadth.TIERS
        assert tier not in breadth.VARIANT_TIERS


def test_pool_prose_stays_below_the_near_duplicate_line() -> None:
    specs = {
        problem: admit._words(
            admit.load(admit.ARMS[0].root / problem / "contract.yaml").task
        )
        for problem in _pool_ids()
    }
    names = sorted(specs)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            score = admit.jaccard(specs[a], specs[b])
            assert score < admit.JACCARD_REJECT, f"{a} vs {b}: {score:.2f}"


tail = _by_path("pool_tail", REPO / "tools" / "problems" / "tail.py")


def test_incomplete_reply_is_raised_on_the_stop_reason_not_the_text() -> None:
    """#212's whole reading rests on this, so the suite holds it.

    ``tail.py`` reports ``incomplete-reply`` as a finding about the output
    cap rather than about the reply format, and it may only do that because
    :func:`~mcgyvr.worker.reply.parse_reply` refuses on the stop reason
    before it scans a single fence. If that order ever changed — if the code
    started meaning "the text was malformed" — the 47 refusals #212 read
    would silently become a reply-format finding and the recorded verdict
    would be wrong with nothing failing.
    """
    from mcgyvr.runner import StopReason
    from mcgyvr.worker.reply import ReplyError, parse_reply

    flawless = "```ts\nexport const a = 1;\n```\n"
    assert not isinstance(parse_reply(flawless), ReplyError)

    refused = parse_reply(flawless, stop_reason=StopReason.TRUNCATED)
    assert isinstance(refused, ReplyError)
    assert refused.code == "incomplete-reply"
    assert refused.code in tail.STOP_REASON_CODES

    # ...and a code that *did* read the text is not in that set.
    prose = parse_reply("no code here, sorry")
    assert isinstance(prose, ReplyError)
    assert prose.code == "no-fenced-block"
    assert prose.code not in tail.STOP_REASON_CODES


def test_refusal_shape_separates_the_readings_it_names() -> None:
    """The four shapes must not collapse: each one implies a different owner."""
    cases = {
        "export const a = 1;\n": "no fence: bare text",
        "Here you go:\n\n```ts\nconst a = 1;\n```\n": "prose preamble (14 chars)",
        "```ts\nconst a = 1;\n": "fence opened, never closed",
        "```ts\nconst a = 1;\n```\n": "one closed block",
        "```ts\nconst a = 1;\n```\n```ts\nconst b = 2;\n```\n": "2 blocks",
    }
    for text, expected in cases.items():
        assert tail.refusal_shape(text).reads_as == expected, text

    assert tail.refusal_shape("```\nx\n```").info_string == ""
    assert tail.refusal_shape("```typescript\nx\n```").info_string == "typescript"
    assert tail.refusal_shape("no fence").preamble_chars == -1
    # A reply is only "truncated mid-code" if nothing precedes the fence.
    assert tail.refusal_shape("```ts\nconst a = 1;\n").preamble_chars == 0


def test_standardising_by_size_removes_a_gap_that_is_only_composition() -> None:
    """Two sets with identical per-stratum rates differ only by their mix.

    This is the property the size section exists to exploit: if the newer
    batches are merely bigger, holding size constant zeroes the gap. A
    reweighting that leaked composition would report difficulty that is not
    there, which is exactly the conclusion #212 was asked not to jump to.
    """
    sizes = {"small-a": 10, "small-b": 12, "big-a": 90, "big-b": 95}
    # Same rate within each stratum; the groups differ only in how many of
    # each they hold.
    rates_a = {"small-a": 0.8, "small-b": 0.8, "big-a": 0.2}
    rates_b = {"small-b": 0.8, "big-a": 0.2, "big-b": 0.2}
    crude = sum(rates_a.values()) / len(rates_a) - sum(rates_b.values()) / len(rates_b)
    assert crude > 0.1, "the fixture must have a crude gap worth removing"
    assert tail._adjusted_gap(rates_a, rates_b, sizes) == 0.0


def test_standardising_weights_strata_by_the_baseline_not_evenly() -> None:
    """The adjusted gap is a weighted mean, and the weights are the baseline's.

    Averaging the strata evenly is the tempting simplification and it is a
    different statistic: it would let one thin cell — the 0-35 stratum holds
    5 of #212's 80 — count for as much as a cell forty times its size. The
    numbers here are hand-computable so the test pins the arithmetic rather
    than whatever the code happens to do.
    """
    sizes = {"s1": 10, "s2": 12, "s3": 14, "b1": 90, "b2": 92, "b3": 94, "b4": 96}
    baseline = {"s1": 0.9, "s2": 0.9, "s3": 0.9, "b1": 0.1}  # 3 small : 1 big
    other = {"s1": 0.6, "b2": 0.2, "b3": 0.2, "b4": 0.2}  # 1 small : 3 big

    # Baseline weights are 3 small, 1 big:
    #   baseline (3*0.9 + 1*0.1)/4 = 0.70   other (3*0.6 + 1*0.2)/4 = 0.50
    assert round(tail._adjusted_gap(baseline, other, sizes), 10) == 0.2
    # Weighting the two strata evenly would give (0.5 - 0.4) = 0.1, and
    # differencing the raw means would give 0.7 - 0.3 = 0.4. Neither is this.
    crude = sum(baseline.values()) / 4 - sum(other.values()) / 4
    assert round(crude, 10) == 0.4


def test_standardising_refuses_when_no_stratum_is_shared() -> None:
    """No overlap in size is no comparison — not a gap of zero."""
    sizes = {"tiny": 5, "huge": 200}
    assert tail._adjusted_gap({"tiny": 1.0}, {"huge": 0.0}, sizes) is None


def test_size_strata_are_fixed_and_cover_every_length() -> None:
    """Published strata cannot move: a rerun must not be able to tune them."""
    assert tail.SIZE_EDGES == (0, 35, 50, 70)
    assert [tail.stratum(n) for n in (0, 34, 35, 49, 50, 69, 70, 10_000)] == [
        0,
        0,
        1,
        1,
        2,
        2,
        3,
        3,
    ]


def test_the_published_interval_reproduces() -> None:
    """A quoted bootstrap interval is a number someone must be able to check."""
    sizes = {f"t{i}": 10 + 7 * i for i in range(12)}
    rates_a = {f"t{i}": (i % 3) / 2 for i in range(0, 12, 2)}
    rates_b = {f"t{i}": (i % 4) / 3 for i in range(1, 12, 2)}
    first = tail.bootstrap_gap(rates_a, rates_b, sizes, resamples=200)
    second = tail.bootstrap_gap(rates_a, rates_b, sizes, resamples=200)
    assert first == second
    assert first[0] <= first[1]
    assert tail.bootstrap_gap(rates_a, rates_b, sizes, resamples=200, seed=1) != first
