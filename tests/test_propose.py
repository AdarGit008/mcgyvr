"""The proposal is what a stranger's install is actually bound to.

These tests run against the SHIPPED table rather than fixtures, because the
properties that matter — that the ladder does not invert, that the MoE rung
reaches a small card, that an unmeasured model is never bound — are claims
about that data as much as about this code. A fixture would let the table
drift out from under them.

The two cards are the table's own measurement rigs: 6 GB (rig_a) and 12 GB
(rig_b).
"""

from __future__ import annotations

import inspect
from itertools import pairwise

import pytest

from mcgyvr import propose as propose_module
from mcgyvr.capability import load
from mcgyvr.propose import (
    API,
    MIN_QUALITY_GAIN,
    AvailableSource,
    binding_name,
    propose,
)

SMALL_CARD = 6.0
BIG_CARD = 12.0

OLLAMA = AvailableSource("local", "ollama")
LLAMA_SERVER = AvailableSource("local-gguf", "llama-server")
MOE = "qwen3-coder-30b-a3b"
INVERTER = "deepseek-coder-v2:16b"


@pytest.fixture
def table():  # type: ignore[no-untyped-def]
    return load()


# --- the ladder must not invert ------------------------------------------


def test_a_twelve_gb_card_gets_a_ladder_that_does_not_invert(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA, LLAMA_SERVER])
    qualities = [r.quality for r in proposal.rungs]
    assert qualities == sorted(qualities), "rungs must climb in measured quality"
    assert len(set(qualities)) == len(qualities), "two rungs at one quality is one rung"


def test_every_step_up_clears_the_measurable_separation_floor(table) -> None:  # type: ignore[no-untyped-def]
    for card in (SMALL_CARD, BIG_CARD):
        rungs = propose(table, vram_gb=card, sources=[OLLAMA, LLAMA_SERVER]).rungs
        for lower, higher in pairwise(rungs):
            gap = higher.quality - lower.quality
            assert gap >= MIN_QUALITY_GAIN, (
                f"{card:g} GB: {higher.model} is only {gap:.1%} above "
                f"{lower.model} — that is one rung, not two"
            )


def test_the_worked_inversion_case_is_never_bound(table) -> None:  # type: ignore[no-untyped-def]
    """deepseek-coder-v2:16b — 9.4 GB for 72.6% against the 7B's 5.0 GB for 84.1%.

    It fits a 12 GB card, so only the gradient rule keeps it out. A ladder
    built on size would place it above the 7B and make escalation harmful.
    """
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA])
    assert INVERTER not in [r.model for r in proposal.rungs]
    reason = proposal.why(INVERTER)
    assert reason is not None and "dominated by" in reason


def test_a_dominated_model_names_what_beat_it(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA])
    reason = proposal.why(INVERTER)
    assert reason is not None
    assert "qwen2.5-coder:7b" in reason
    assert "not better is not a higher rung" in reason


def test_the_ceiling_is_never_dropped_for_sitting_close_to_a_cheaper_rung(  # type: ignore[no-untyped-def]
    table,
) -> None:
    """Selection runs downward from the best model that fits."""
    for card in (SMALL_CARD, BIG_CARD):
        proposal = propose(table, vram_gb=card, sources=[OLLAMA, LLAMA_SERVER])
        best_available = max(
            (m.best_quality or 0.0)
            for m in table.fitting(card)
            if m.requires_backend in (None, "llama-server")
        )
        assert proposal.rungs[-1].quality == best_available


def test_a_model_is_never_eliminated_by_a_candidate_that_is_itself_dropped(  # type: ignore[no-untyped-def]
    table,
) -> None:
    """Regression: the 7B was being removed by the MoE, which then also went.

    The MoE dominates the 7B on quality-per-GB, but loses the equal-quality
    tie to the 14B on speed. Collapsing ties only after dominance left a
    12 GB card with no 84.1% middle rung at all — eliminated by a model that
    never made the ladder.
    """
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA, LLAMA_SERVER])
    bound = [r.model for r in proposal.rungs]
    assert "qwen2.5-coder:7b" in bound
    assert MOE not in bound


def test_at_equal_quality_the_faster_model_is_the_rung(table) -> None:  # type: ignore[no-untyped-def]
    """14B and the MoE both measure 87.8%; on a card that fits both, speed decides."""
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA, LLAMA_SERVER])
    assert proposal.rungs[-1].model == "qwen2.5-coder:14b"
    reason = proposal.why(MOE)
    assert reason is not None
    assert "same measured quality" in reason
    assert "slower" in reason


def test_throughput_is_not_borrowed_across_backends(table) -> None:  # type: ignore[no-untyped-def]
    """The MoE's ollama figure is Q4 at 8.9 GB — different weights (CAV-02)."""
    moe = table.get(MOE)
    assert moe is not None
    assert moe.requires_backend == "llama-server"
    assert moe.best_throughput == 13.0, "the 24.19 ollama Q4 number must not count"


# --- the small card gets the MoE quality rung ----------------------------


def test_a_six_gb_card_is_proposed_the_moe_quality_rung(table) -> None:  # type: ignore[no-untyped-def]
    """14B-class quality in ~3 GB is the whole reason a small card is viable."""
    proposal = propose(table, vram_gb=SMALL_CARD, sources=[OLLAMA, LLAMA_SERVER])
    bound = [r.model for r in proposal.rungs]
    assert MOE in bound
    assert bound[-1] == MOE, "it is the quality ceiling on this card"
    assert proposal.rungs[-1].quality > 0.85


def test_the_moe_rung_is_bound_to_the_backend_it_was_measured_on(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=SMALL_CARD, sources=[OLLAMA, LLAMA_SERVER])
    rung = next(r for r in proposal.rungs if r.model == MOE)
    assert rung.source == LLAMA_SERVER.name


def test_without_llama_server_the_moe_rung_is_withheld_and_explained(table) -> None:  # type: ignore[no-untyped-def]
    """CAV-02: ollama resolves it to F16, which scored 3.7%. Wrong, not worse."""
    proposal = propose(table, vram_gb=SMALL_CARD, sources=[OLLAMA])
    assert MOE not in [r.model for r in proposal.rungs]
    reason = proposal.why(MOE)
    assert reason is not None
    assert "llama-server" in reason
    assert "wrong answer" in reason
    assert proposal.rungs, "the card still gets a working ladder without it"


def test_a_six_gb_card_still_gets_a_working_ladder(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=SMALL_CARD, sources=[OLLAMA, LLAMA_SERVER])
    assert len(proposal.rungs) >= 2
    for rung in proposal.rungs:
        assert rung.vram_gb + 2.0 <= SMALL_CARD


# --- unmeasured models are never proposed --------------------------------


def test_no_unmeasured_model_is_ever_bound(table) -> None:  # type: ignore[no-untyped-def]
    unmeasured = {m.id for m in table.models if not m.is_measured}
    assert unmeasured, "expected the table to hold back at least one model"
    proposal = propose(table, vram_gb=80.0, sources=[OLLAMA, LLAMA_SERVER])
    assert unmeasured.isdisjoint({r.model for r in proposal.rungs})


def test_a_withheld_model_says_it_was_withheld_on_purpose(table) -> None:  # type: ignore[no-untyped-def]
    """Silence would read as an oversight rather than as a decision."""
    proposal = propose(table, vram_gb=80.0, sources=[OLLAMA, LLAMA_SERVER])
    reason = proposal.why("gpt-oss-20b")
    assert reason is not None
    assert "no valid quality measurement" in reason


# --- a machine with no local backend is coherent, not an error -----------


def test_no_backend_yields_an_empty_local_ladder_rather_than_an_error(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=BIG_CARD, sources=[])
    assert proposal.is_local_empty
    assert proposal.rungs == ()
    assert any("No local backend is reachable" in n for n in proposal.notes)


def test_no_gpu_yields_an_empty_local_ladder_rather_than_an_error(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=None, sources=[OLLAMA])
    assert proposal.is_local_empty
    notes = " ".join(proposal.notes)
    assert "supported install" in notes
    assert "bind an api source" in notes.lower()


def test_a_card_too_small_for_anything_is_still_not_an_error(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=2.0, sources=[OLLAMA])
    assert proposal.is_local_empty
    assert proposal.rejected, "and it says what did not fit"
    assert all(
        "does not fit" in r.reason or "measurement" in r.reason
        for r in proposal.rejected
    )


# --- every binding states why, and what it costs -------------------------


def test_every_rung_states_fit_quality_and_presence(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA, LLAMA_SERVER])
    for rung in proposal.rungs:
        joined = " ".join(rung.reasons)
        assert "fit:" in joined
        assert "quality:" in joined
        assert "gradient:" in joined
        assert "already pulled" in joined or "needs pulling" in joined


def test_already_pulled_models_are_reported_as_such(table) -> None:  # type: ignore[no-untyped-def]
    stocked = AvailableSource(
        "local", "ollama", frozenset({"qwen2.5-coder:7b", "qwen2.5-coder:3b"})
    )
    proposal = propose(table, vram_gb=BIG_CARD, sources=[stocked])
    present = {r.model for r in proposal.rungs if r.already_present}
    assert "qwen2.5-coder:7b" in present
    rung = next(r for r in proposal.rungs if r.model == "qwen2.5-coder:7b")
    assert any("already pulled on local" in reason for reason in rung.reasons)


def test_what_must_be_pulled_is_named_with_its_size(table) -> None:  # type: ignore[no-untyped-def]
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA])
    assert proposal.must_pull
    assert proposal.download_gb > 0
    notes = " ".join(proposal.notes)
    assert "Needs pulling before first use" in notes
    for rung in proposal.must_pull:
        assert rung.model in notes


def test_the_proposal_warns_a_number_does_not_make_a_server_parallel(table) -> None:  # type: ignore[no-untyped-def]
    """#23's third scope bullet: CON-02, stated where the operator will read it.

    The failure it warns about is the invisible kind — a single-slot server
    handed four concurrent requests serializes them rather than refusing them,
    so an over-declared capacity is a queue rather than an error. Worth stating
    because the config schema already carries CON-01's good news about distinct
    models, and good news is the half that gets remembered.
    """
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA])
    notes = " ".join(proposal.notes)

    assert "CON-02" in notes
    assert "parallel-slot setting" in notes
    assert "serializes" in notes
    # It names the source whose backend the operator would have to change.
    assert "local" in notes


def test_a_machine_with_no_ladder_gets_no_concurrency_advice(table) -> None:  # type: ignore[no-untyped-def]
    """Nothing to run concurrently on: the note would be advice about nothing."""
    proposal = propose(table, vram_gb=None)
    assert not any("CON-02" in note for note in proposal.notes)


def test_presence_breaks_ties_without_overriding_the_gradient(table) -> None:  # type: ignore[no-untyped-def]
    """A download is a one-time cost; a weaker rung is a permanent one."""
    bare = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA])
    stocked = propose(
        table,
        vram_gb=BIG_CARD,
        sources=[AvailableSource("local", "ollama", frozenset({INVERTER}))],
    )
    assert [r.model for r in bare.rungs] == [r.model for r in stocked.rungs], (
        "having a dominated model on disk must not promote it into the ladder"
    )


def test_rungs_are_named_by_what_they_are(table) -> None:  # type: ignore[no-untyped-def]
    """`<role>_<locality>_<model>` — a name that survives inserting a rung."""
    proposal = propose(table, vram_gb=BIG_CARD, sources=[OLLAMA, LLAMA_SERVER])
    assert [r.name for r in proposal.rungs] == [
        "local_qwen2.5-coder-1.5b",
        "local_qwen2.5-coder-3b",
        "local_qwen2.5-coder-7b",
        "local_qwen2.5-coder-14b",
    ]


def test_binding_names_are_safe_to_use_as_config_keys() -> None:
    """A model id is not a name: it carries colons and path separators."""
    assert binding_name("qwen2.5-coder:7b") == "local_qwen2.5-coder-7b"
    assert (
        binding_name("Qwen/Qwen2.5-Coder-14B-Instruct-AWQ")
        == "local_qwen2.5-coder-14b-instruct-awq"
    )
    assert binding_name("claude-opus-5", locality=API) == "api_claude-opus-5"


def test_a_tier_name_carries_no_role_token() -> None:
    """The role is derived from where a binding sits, never spelled in a name.

    Only ladder tiers carry a name, and the ladder holds workers only — so a
    role token would be constant everywhere it appeared. This is the
    regression guard for that being re-added.
    """
    assert not hasattr(propose_module, "ORCHESTRATOR")
    assert not hasattr(propose_module, "WORKER")
    assert "role" not in inspect.signature(binding_name).parameters


def test_rung_names_are_unique_within_a_proposal(table) -> None:  # type: ignore[no-untyped-def]
    """The config loader rejects duplicate tier names, so this must hold."""
    for card in (SMALL_CARD, BIG_CARD):
        names = [
            r.name
            for r in propose(table, vram_gb=card, sources=[OLLAMA, LLAMA_SERVER]).rungs
        ]
        assert len(names) == len(set(names))


def test_the_proposal_is_deterministic(table) -> None:  # type: ignore[no-untyped-def]
    """Same inputs, same ladder — a proposal that wobbles cannot be reviewed."""
    runs = [
        propose(table, vram_gb=BIG_CARD, sources=[OLLAMA, LLAMA_SERVER]).rungs
        for _ in range(5)
    ]
    assert all(r == runs[0] for r in runs)


def test_headroom_is_respected_on_every_rung(table) -> None:  # type: ignore[no-untyped-def]
    """CAV-04: a marginal fit degrades rather than failing outright."""
    proposal = propose(table, vram_gb=SMALL_CARD, sources=[OLLAMA, LLAMA_SERVER])
    for rung in proposal.rungs:
        assert rung.vram_gb + 2.0 <= SMALL_CARD
