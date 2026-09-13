"""No landed test still opens with a RED spec docstring.

These 24 tests pin behaviours that have now landed, yet their module docstring
still carries the RED marker that says the behaviour does not exist. The
assertions are live guards and stay; only the stale RED paragraph goes
(``records/plans/fleet-identity.md`` §10, and the sleep/wake, vramfit and
fleet-identity ports).
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent

#: Landed tests whose module docstring still carries the RED spec marker.
STALE_RED: tuple[str, ...] = (
    "test_a_card_reserve_that_moves_between_boots_is_the_same_rig.py",
    "test_a_config_digest_names_the_setup_and_not_the_schema.py",
    "test_a_config_resolves_the_geometry_it_names_or_refuses.py",
    "test_a_corrupt_wake_cache_does_not_shorten_a_wake.py",
    "test_a_fleet_id_is_a_prefixed_content_digest.py",
    "test_a_fleet_is_a_named_layout_that_moves_only_along_its_switches.py",
    "test_a_launch_spec_this_config_does_not_plan_is_never_woken.py",
    "test_a_measured_scratch_is_used_only_at_the_ubatch_it_was_read_at.py",
    "test_a_rung_whose_model_is_not_resident_does_not_read_as_available.py",
    "test_a_sleeping_rung_is_woken_rather_than_declined.py",
    "test_a_sleeping_unit_does_not_read_as_serving.py",
    "test_a_unit_states_its_kv_cache_dtype_or_is_refused.py",
    "test_a_wake_is_asked_for_in_the_config_and_bounded_by_its_own_budget.py",
    "test_an_alert_pulls_its_combination_until_it_is_revalidated.py",
    "test_card_contention_and_not_the_port_decides_who_alternates.py",
    "test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock.py",
    "test_live_runs_only_a_locked_fleet_and_cleans_what_is_not_in_it.py",
    "test_prefill_is_judged_and_cuda_host_and_the_backend_are_recorded.py",
    "test_sleeping_a_card_takes_every_rung_it_serves.py",
    "test_the_fleet_and_its_policy_are_two_files.py",
    "test_the_fleet_lock_is_written_only_from_passing_dev_runs.py",
    "test_the_lock_pins_each_combinations_headroom_card_peak_backend_and_prefill.py",
    "test_the_numbers_the_fleet_identity_design_waits_on_are_measured.py",
    "test_the_scratch_allowance_for_qwen3next_is_what_it_measured.py",
)


def _docstring(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return ast.get_docstring(tree, clean=False) or ""


def test_no_landed_test_still_opens_with_a_red_spec_docstring() -> None:
    stale = [name for name in STALE_RED if "RED." in _docstring(TESTS / name)]
    assert not stale, (
        f"{len(stale)} landed test(s) still open with a RED spec docstring. "
        f"Drop the RED paragraph, keep the assertions: {stale}"
    )
