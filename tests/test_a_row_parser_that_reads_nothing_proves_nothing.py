"""The canary for a suite that is otherwise almost entirely xfail.

An ``xfail(strict=True)`` whose body raises for the *wrong* reason still xfails,
silently. Nearly every file in this campaign is parked that way, so the helper
they all depend on — :mod:`tests.sweeprows` — would have no live exercise and a
broken parser could hide inside a dozen expected failures.

This file gives it one, against an artifact that is committed today. It also
pins the defect the new run exists not to repeat: ``srv1-nomma-dp4a-ab.tsv``
records two arms under byte-identical labels, separated by a ``### IMAGE``
comment and by file order alone.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import EVIDENCE, read

AB = EVIDENCE / "2026-09-01-bandwidth-and-ncmoe-floor" / "srv1-nomma-dp4a-ab.tsv"


def test_the_parser_reads_the_committed_ab_file() -> None:
    sweep = read(AB)
    assert len(sweep.levels()) == 18, "3 cells x 3 widths across two arms"
    assert {r.fields["img"] for r in sweep.of_kind("CONFIG")} == {
        "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644",
        "llamacpp:b10644-nomma-dp4a",
    }


def test_the_committed_ab_file_cannot_tell_its_two_arms_apart() -> None:
    """Not a lament — the control for the rule
    ``test_a_row_that_does_not_name_its_arm_is_not_a_measurement`` encodes.

    Every reader in this repo collapses rows by label (``run.py:93``, last write
    wins). Against this file, doing so keeps the no-MMA arm and discards stock
    without a word. If a future edit gives these rows an ``arm=``, this test goes
    red and the rule it anchors is already satisfied — delete it then.
    """
    sweep = read(AB)
    markers_per_label: dict[str, set[str]] = {}
    for row in sweep.levels():
        markers_per_label.setdefault(row.label, set()).add(row.marker)
    assert any(len(v) > 1 for v in markers_per_label.values()), (
        "labels no longer collide across arms in the 2026-09-01 A/B file"
    )
    assert not any("arm" in r.fields for r in sweep.levels()), (
        "the A/B file now carries arm identity on its rows"
    )


def test_prefill_in_this_repos_tsvs_is_not_an_independent_measurement() -> None:
    """``prefill = pin/wall`` and ``agg = gen/wall`` over the SAME wall, so
    ``prefill/agg`` is ``ptok/otok`` identically.

    Green today and permanently, because it is a statement about arithmetic in
    ``lcp_sweep_31-08-2026.py:221-222``. It is here so that anyone who later
    quotes a "prefill gain" is contradicted by a passing test rather than by a
    note. It goes red only if a driver starts timing prefill separately — which
    is the change ``test_a_prefill_verdict_needs_an_instrument_that_measures_prefill``
    asks for.
    """
    sweep = read(AB)
    measured = [r for r in sweep.levels() if "ptok" in r.fields]
    assert len(measured) == 17, (
        "one level row of eighteen carries no ptok — the mling n=8 ERR, which is "
        "the MoE crash this campaign exists to fix. If that count changes, the "
        "artifact changed."
    )
    for row in measured:
        prompt, output = row.draw()
        assert row.num("prefill") / row.num("agg") == pytest.approx(
            prompt / output, rel=0.01
        ), (
            f"line {row.lineno}: prefill/agg and ptok/otok have diverged. Either "
            "a driver now measures prefill, or one of the two is wrong."
        )
