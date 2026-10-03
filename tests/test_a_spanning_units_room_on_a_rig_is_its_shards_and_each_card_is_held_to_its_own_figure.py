"""A spanning unit's room is its shards' sum, and each card is held to its figure.

The lock fits every unit's room, plus the combination's overhead, into what dev
measured. For a unit that spans cards or rigs:

* its room on a rig is the SUM of its shards' ``room_mib`` on that rig, each of
  which must be stated (a sum with a missing term is a guess, so it is refused by
  name); a unit that spans nothing keeps its own ``room_mib``;
* a llama.cpp unit's card peak on a rig is held to its room on that rig;
* what the head measures (decode, prefill) is not asked of a worker rig;
* a rig whose dev evidence states ``cards``, each card's own MiB beside
  ``card_mib``, is held to each card: every unit on it names its cards, and each
  card's rooms plus the combination's overhead must fit that card's figure. A rig
  without ``cards`` is held to its one figure, as before;
* the approved entry of a unit records its cards on that rig only when it names
  them, so a lock of units that name none is what it was.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet import lock, promote
from tests import span_fleet as sf

#: ``big_model`` needs 5500 on A and 2000 on B, ``small`` 1500 on A, and each
#: combination's overhead is 600: A needs 7600, B needs 2600.
A_NEEDS = sf.BIG_ROOM_A + sf.SMALL_ROOM + sf.OVERHEAD
B_NEEDS = sf.BIG_ROOM_B + sf.OVERHEAD


def write(
    root: Path,
    fleet: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    used = sf.fleet() if fleet is None else fleet
    lock.write(
        root,
        used,
        sf.evidence(used) if evidence is None else evidence,
        tolerances=sf.TOLERANCES,
    )


def records(root: Path, rig_id: str) -> list[dict[str, Any]]:
    where = root / promote.LOCK_DIR / "rigs" / rig_id
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(where.glob("cmb-*.json"))
    ]


def refused(root: Path, fleet: dict[str, Any], evidence: dict[str, Any]) -> str:
    with pytest.raises(lock.LockRefusedError) as raised:
        write(root, fleet, evidence)
    return str(raised.value)


# --- a room is a sum --------------------------------------------------------


def test_a_spanning_units_room_on_a_rig_is_the_sum_of_its_shards_there(
    tmp_path: Path,
) -> None:
    """A holds 3000 + 2500 of ``big_model`` and 1500 of ``small``: with the
    overhead, 7600 fits a card of 7600 MiB and not of 7599."""
    fleet = sf.fleet()
    evidence = sf.evidence(fleet)
    evidence["rigs"][sf.A]["card_mib"] = A_NEEDS
    write(tmp_path / "fits", fleet, evidence)

    evidence["rigs"][sf.A]["card_mib"] = A_NEEDS - 1
    said = refused(tmp_path / "over", fleet, evidence)
    assert sf.A in said and f"{A_NEEDS - 1}" in said, said
    assert f"room {sf.BIG_ROOM_A + sf.SMALL_ROOM} MiB" in said, said


def test_each_rig_a_unit_spans_is_fitted_with_that_rigs_shards_alone(
    tmp_path: Path,
) -> None:
    fleet = sf.fleet()
    evidence = sf.evidence(fleet)
    evidence["rigs"][sf.B]["card_mib"] = B_NEEDS
    write(tmp_path / "fits", fleet, evidence)

    evidence["rigs"][sf.B]["card_mib"] = B_NEEDS - 1
    said = refused(tmp_path / "over", fleet, evidence)
    assert sf.B in said and f"room {sf.BIG_ROOM_B} MiB" in said, said


def test_a_shard_that_states_no_room_is_refused_by_unit_and_rig(
    tmp_path: Path,
) -> None:
    fleet = sf.fleet()
    del fleet["units"][sf.BIG]["launch"]["shards"][2]["room_mib"]
    said = refused(tmp_path, fleet, sf.evidence(fleet))
    assert sf.BIG in said and sf.B in said and "room_mib" in said, said


def test_a_spanning_unit_does_not_borrow_a_room_it_states_for_itself(
    tmp_path: Path,
) -> None:
    """A unit-level ``room_mib`` of a unit that spans cards is not the sum, and is
    not used in its place."""
    fleet = sf.fleet()
    fleet["units"][sf.BIG]["room_mib"] = 1
    del fleet["units"][sf.BIG]["launch"]["shards"][1]["room_mib"]
    said = refused(tmp_path, fleet, sf.evidence(fleet))
    assert sf.BIG in said and "card 1" in said, said


def test_a_unit_that_spans_nothing_keeps_its_own_room(tmp_path: Path) -> None:
    fleet = sf.fleet()
    del fleet["units"][sf.SMALL]["room_mib"]
    said = refused(tmp_path, fleet, sf.evidence(fleet))
    assert sf.SMALL in said and "no room_mib" in said, said


def test_a_pinned_unit_may_state_its_room_once_but_not_two_different_ones(
    tmp_path: Path,
) -> None:
    pinned = sf.with_small_on_a_card(sf.fleet())
    del pinned["units"][sf.SMALL]["launch"]["shards"][0]["room_mib"]
    write(tmp_path / "once", pinned)

    twice = sf.with_small_on_a_card(sf.fleet())
    twice["units"][sf.SMALL]["launch"]["shards"][0]["room_mib"] = sf.SMALL_ROOM - 100
    said = refused(tmp_path / "twice", twice, sf.evidence(twice))
    assert sf.SMALL in said and "two rooms" in said, said


def test_a_llama_cpp_peak_is_held_to_the_units_room_on_that_rig(
    tmp_path: Path,
) -> None:
    for rig, room in ((sf.A, sf.BIG_ROOM_A), (sf.B, sf.BIG_ROOM_B)):
        fleet = sf.fleet()
        evidence = sf.evidence(fleet)
        for row in evidence["combinations"]:
            if row["rig"] == rig:
                row["card_peak_mib"][sf.BIG] = room + 1
        said = refused(tmp_path / rig, fleet, evidence)
        assert sf.BIG in said and f"{room + 1} MiB exceeds its room {room}" in said


def test_the_head_is_measured_and_a_worker_rig_is_not_asked_for_decode(
    tmp_path: Path,
) -> None:
    write(tmp_path)  # the fixture's worker rig states no decode or prefill
    on_b = records(tmp_path, sf.RIG_B)[0]["approved"][sf.BIG]
    assert "warm_decode_tok_s" not in on_b and "card_peak_mib" in on_b

    fleet = sf.fleet()
    evidence = sf.evidence(fleet)
    for row in evidence["combinations"]:
        if row["rig"] == sf.A:
            row["warm_decode_tok_s"].pop(sf.BIG, None)
    assert "warm_decode_tok_s" in refused(tmp_path / "head", fleet, evidence)


def test_a_reply_the_head_cannot_finish_in_time_is_still_refused(
    tmp_path: Path,
) -> None:
    fleet = sf.fleet()
    evidence = sf.evidence(fleet)
    for row in evidence["combinations"]:
        if row["rig"] == sf.A:
            row["warm_decode_tok_s"][sf.BIG] = 1.0
    assert "request_timeout_s" in refused(tmp_path, fleet, evidence)


def test_an_approved_unit_records_its_cards_only_when_it_names_them(
    tmp_path: Path,
) -> None:
    write(tmp_path)
    on_a = records(tmp_path, sf.RIG_A)
    approved = [record["approved"] for record in on_a if sf.BIG in record["approved"]]
    assert approved[0][sf.BIG]["cards"] == {"0": 3000, "1": 2500}
    assert "cards" not in approved[0][sf.SMALL], (
        "a unit that spans nothing is as before"
    )
    on_b = records(tmp_path, sf.RIG_B)
    assert on_b[0]["approved"][sf.BIG]["cards"] == {"0": sf.BIG_ROOM_B}
    assert all("cards" not in record for record in on_a + on_b)


# --- per-card figures -------------------------------------------------------


def per_card(fleet: dict[str, Any], figures: dict[str, int]) -> dict[str, Any]:
    evidence = sf.evidence(fleet)
    evidence["rigs"][sf.A] = {"card_mib": 20000, "cards": figures}
    return evidence


def test_every_card_must_fit_its_rooms_plus_the_overhead(tmp_path: Path) -> None:
    """Card 1 holds 2500 of ``big_model`` and 1500 of ``small``: with the
    overhead 4600, which fits 4600 MiB and not 4599."""
    fleet = sf.with_small_on_a_card(sf.fleet(), gpu=1)
    fits = sf.SMALL_ROOM + 2500 + sf.OVERHEAD
    write(tmp_path / "fits", fleet, per_card(fleet, {"0": 3600, "1": fits}))

    said = refused(
        tmp_path / "over", fleet, per_card(fleet, {"0": 3600, "1": fits - 1})
    )
    assert sf.A in said and "card 1" in said and f"{fits - 1}" in said, said
    assert "overhead" in said, said

    said = refused(tmp_path / "other", fleet, per_card(fleet, {"0": 3599, "1": fits}))
    assert "card 0" in said and "3599" in said, said


def test_a_rig_with_card_figures_is_not_held_to_one_sum_of_all_its_cards(
    tmp_path: Path,
) -> None:
    """The rooms on A sum to more than any one card holds, and fit card by card."""
    fleet = sf.with_small_on_a_card(sf.fleet(), gpu=1)
    figures = {"0": 3600, "1": 4600}
    assert sum(figures.values()) < A_NEEDS * 2 and max(figures.values()) < A_NEEDS
    write(tmp_path, fleet, per_card(fleet, figures))
    record = next(r for r in records(tmp_path, sf.RIG_A) if sf.BIG in r["approved"])
    assert record["cards"] == {"0": 3600, "1": 4600}
    assert records(tmp_path, sf.RIG_B)[0]["card_mib"] == 9000, "B keeps its figure"


def test_a_unit_that_names_no_card_is_refused_on_a_rig_with_card_figures(
    tmp_path: Path,
) -> None:
    fleet = sf.fleet()  # small names no card
    said = refused(tmp_path, fleet, per_card(fleet, {"0": 9000, "1": 9000}))
    assert sf.SMALL in said and "launch.shards" in said and sf.A in said, said


def test_a_unit_on_a_card_dev_stated_no_figure_for_is_refused(tmp_path: Path) -> None:
    fleet = sf.with_small_on_a_card(sf.fleet(), gpu=1)
    said = refused(tmp_path, fleet, per_card(fleet, {"0": 9000}))
    assert "occupies card 1" in said and sf.A in said, said


def test_card_figures_that_are_not_a_card_to_mib_mapping_are_refused(
    tmp_path: Path,
) -> None:
    fleet = sf.with_small_on_a_card(sf.fleet(), gpu=1)
    evidence = per_card(fleet, {"zero": 9000})
    assert "whole number" in refused(tmp_path / "name", fleet, evidence)
    evidence = per_card(fleet, {"0": 9000, "1": None})  # type: ignore[dict-item]
    assert "card 1" in refused(tmp_path / "figure", fleet, evidence)


def test_without_card_figures_the_one_figure_rule_is_unchanged(
    tmp_path: Path,
) -> None:
    """The fixture's rig A states only ``card_mib``, so ``small`` needs no card."""
    fleet = sf.fleet()
    evidence = sf.evidence(fleet)
    assert "cards" not in evidence["rigs"][sf.A]
    write(tmp_path, fleet, copy.deepcopy(evidence))
    assert records(tmp_path, sf.RIG_A)[0]["card_mib"] == 20000
