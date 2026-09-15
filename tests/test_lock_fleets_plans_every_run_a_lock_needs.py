"""lock-fleets plans every run a lock needs, in one frozen order per use.

Owner, 2026-09-15: "lock-fleets, general campign to lock new fleets in". The
planner (``records/measurements/lock-fleets/plan.py``) reads only the fleet
files, hosts.json and the use's ``use.json``, and writes the use's RUNS.md and
one wrapper per campaign run:

* every combination of every layout, K = 3 cold starts, interleaved by cold
  start; then every switch move, K = 3 runs, interleaved the same way;
* a llama.cpp combination is a campaign unit run, a vLLM group the door's own
  serve up, read, load per unit and serve down;
* each entry carries its exact door command, and each campaign run an artifact
  of its own, declared by its own wrapper (gate 5 reads RUN_ARTIFACTS from the
  step file's text and writes each once);
* the same inputs give the same bytes, and a use whose log holds a row is frozen.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.lockfleets_window import (
    REPO,
    USE,
    fleet_doc,
    make_tree,
    plan_module,
    use_doc,
)

STEPS = f"tools/runs/campaigns/lock-fleets/{USE}"


@pytest.fixture
def frozen(tmp_path: Path) -> Any:
    make_tree(tmp_path)
    return plan_module().freeze(tmp_path, USE)


def _shape(entries: list[Any], rig: str) -> list[tuple[str, str, str]]:
    return [(e.kind, e.fleet, e.run) for e in entries if e.rig == rig]


def test_cold_starts_are_interleaved_and_moves_come_last_on_every_rig(
    frozen: Any,
) -> None:
    moves = [
        ("move", "one", "r1"),
        ("move", "two", "r1"),
        ("move", "one", "r2"),
        ("move", "two", "r2"),
        ("move", "one", "r3"),
        ("move", "two", "r3"),
    ]
    alpha = [
        (kind, fleet, f"c{n}")
        for n in (1, 2, 3)
        for kind, fleet in (("unit", "one"), ("unit", "two"))
    ]
    assert _shape(frozen.entries, "alpha") == alpha + moves
    cycle = ["serve-up", "read", "load", "load", "serve-down"]
    beta = [
        entry
        for n in (1, 2, 3)
        for entry in [("unit", "one", f"c{n}"), *((k, "two", f"c{n}") for k in cycle)]
    ]
    assert _shape(frozen.entries, "beta") == beta + moves
    ids = [e.id for e in frozen.entries]
    assert ids[:2] == ["alpha-01", "alpha-02"] and ids[-1] == "beta-24"


def test_each_entry_carries_its_exact_door_command(frozen: Any) -> None:
    by_id = {e.id: e for e in frozen.entries}
    assert by_id["alpha-01"].argv == (
        "--host", "alpha", "--campaign", "lock-fleets",
        "--step", f"{STEPS}/01-{USE}-alpha-c1-a_solo.sh",
        "--model", "/models/a_solo.gguf", "--parallel", "1",
        "--ctx-per-slot", "8192", "--ubatch", "512", "--date", "@WINDOW_DATE@",
    )  # fmt: skip
    assert by_id["alpha-02"].argv[7:12] == (
        "/models/a_pair.gguf", "--parallel", "2", "--ctx-per-slot", "4096",
    )  # fmt: skip
    assert by_id["beta-02"].argv == (
        "serve", "up", "--host", "beta", "--compose",
        "@COMPOSE_DIR@/compose.beta.two.yml",
        "--suffix", f"{USE}-beta-02", "--date", "@WINDOW_DATE@",
    )  # fmt: skip
    assert by_id["beta-03"].argv == (
        "read", "--host", "beta", "--probe", "b_small", "b_mid",
        "--run-id", "@READ_RUN_ID@",
    )  # fmt: skip
    assert by_id["beta-04"].argv == (
        "read", "--host", "beta", "--probe", "b_small", "--load", "8x4096",
        "--run-id", "@READ_RUN_ID@",
    )  # fmt: skip
    move = by_id["beta-19"]
    assert (move.fleet, move.to) == ("one", "two")
    assert move.argv[6:] == (
        "--model", "/models/b_big.gguf", "--parallel", "4", "--ctx-per-slot", "4096",
        "--ubatch", "512", "--date", "@WINDOW_DATE@",
        "--", "@COMPOSE_DIR@/compose.beta.two.yml",
    )  # fmt: skip
    assert by_id["beta-02"].run_id("2026-09-16") == (
        f"2026-09-16-live-beta-serve-up-{USE}-beta-02"
    )
    assert by_id["alpha-01"].run_id("2026-09-16") == (
        f"2026-09-16-lock-fleets-{USE}-alpha-c1-a_solo"
    )
    assert by_id["beta-03"].run_id("2026-09-16", "run-x") == "run-x"


def test_every_campaign_run_declares_an_artifact_of_its_own(
    tmp_path: Path, frozen: Any
) -> None:
    runs = [e for e in frozen.entries if e.kind in ("unit", "move")]
    assert len({e.artifact for e in runs}) == len(runs) == 21
    assert len({e.step for e in runs}) == len(runs)
    for entry in runs:
        wrapper = tmp_path / entry.wrapper
        text = wrapper.read_text("utf-8")
        assert os.access(wrapper, os.X_OK), entry.wrapper
        assert re.findall(r"^# RUN_ARTIFACTS: (.*)$", text, re.M) == [entry.artifact]
        body = "_unit.sh" if entry.kind == "unit" else "_move.sh"
        assert f'/../{body}" {entry.artifact} ' in text
        assert entry.artifact == f"{entry.step}.json"
    move = next(e for e in runs if e.kind == "move")
    assert (
        f'{move.artifact} alpha one two "$@"' in (tmp_path / move.wrapper).read_text()
    )
    assert sorted(p.name for p in (tmp_path / STEPS).iterdir()) == sorted(
        Path(e.wrapper).name for e in runs
    )


def test_the_same_inputs_freeze_to_the_same_bytes(tmp_path: Path) -> None:
    make_tree(tmp_path)
    plan = plan_module()
    plan.freeze(tmp_path, USE)
    runs_md = tmp_path / "records/measurements/lock-fleets" / USE / "RUNS.md"
    first = {p: p.read_bytes() for p in [runs_md, *(tmp_path / STEPS).iterdir()]}
    plan.freeze(tmp_path, USE)
    assert {
        p: p.read_bytes() for p in [runs_md, *(tmp_path / STEPS).iterdir()]
    } == first


def test_the_frozen_order_reads_back_as_it_was_planned(
    frozen: Any, tmp_path: Path
) -> None:
    runs = plan_module().read_runs(tmp_path, USE)
    assert runs.entries == frozen.entries
    assert runs.log == [] and runs.idle == []


def test_a_use_whose_log_holds_a_row_is_frozen(tmp_path: Path) -> None:
    make_tree(tmp_path)
    plan = plan_module()
    plan.freeze(tmp_path, USE)
    runs = plan.read_runs(tmp_path, USE)
    plan.insert_row(
        runs.path, plan.LOG_HEADER, ["alpha-01", "alpha", "t", "t", "0", "x", "y", ""]
    )
    assert plan.read_runs(tmp_path, USE).logged("alpha-01") is not None
    with pytest.raises(
        plan.PlanRefusedError, match="frozen from its first measurement"
    ):
        plan.freeze(tmp_path, USE)


def test_a_caps_row_is_the_card_less_the_reserve_and_the_other_rooms(
    frozen: Any,
) -> None:
    assert frozen.caps == [
        {
            "rig": "beta",
            "fleet": "two",
            "unit": "b_small",
            "cap_mib": str(12288 - 377 - 8000),
            "from": "12288 card - 377 reserve - 8000 b_mid room",
        },
        {
            "rig": "beta",
            "fleet": "two",
            "unit": "b_mid",
            "cap_mib": str(12288 - 377 - 3500),
            "from": "12288 card - 377 reserve - 3500 b_small room",
        },
    ]


@pytest.mark.parametrize(
    ("rig", "slots"),
    [
        ("alpha", [["a_solo", "awake"], ["a_pair", "awake"]]),
        ("beta", [["b_big", "awake"], ["b_small", "awake"]]),
    ],
    ids=["two-llamacpp-units", "llamacpp-and-vllm"],
)
def test_a_combination_the_campaign_cannot_start_is_refused_by_name(
    tmp_path: Path, rig: str, slots: list[list[str]]
) -> None:
    fleet = fleet_doc()
    fleet["fleets"]["one"]["layout"][rig] = slots
    make_tree(tmp_path, fleet=fleet)
    plan = plan_module()
    with pytest.raises(
        plan.PlanRefusedError, match=r"neither one llama\.cpp unit nor a group"
    ):
        plan.freeze(tmp_path, USE)


def test_log_rows_and_idle_events_land_in_their_own_tables(tmp_path: Path) -> None:
    make_tree(tmp_path)
    plan = plan_module()
    plan.freeze(tmp_path, USE)
    runs = plan.read_runs(tmp_path, USE)
    first = plan._event(runs, "alpha", "finished", "2026-09-16T12:00:00Z")
    plan.insert_row(runs.path, plan.IDLE_HEADER, first)
    runs = plan.read_runs(tmp_path, USE)
    second = plan._event(runs, "beta", "finished", "2026-09-16T12:42:30Z")
    plan.insert_row(runs.path, plan.IDLE_HEADER, second)
    plan.insert_row(
        runs.path, plan.LOG_HEADER, ["beta-01", "beta", "a", "b", "0", "r", "e", "o"]
    )
    runs = plan.read_runs(tmp_path, USE)
    assert [row["idle minutes"] for row in runs.idle] == [
        "the other rig is still running",
        "alpha idle 42.5",
    ]
    assert [row["entry"] for row in runs.log] == ["beta-01"]
    assert len(runs.entries) == 36


def test_the_committed_use_is_its_wrappers_and_its_wrappers_are_the_use() -> None:
    """``rig-id-relock`` as committed: every campaign run's wrapper is there and
    declares that run's artifact, and no other wrapper is."""
    plan = plan_module()
    runs = plan.read_runs(REPO, "rig-id-relock")
    by_rig = {
        rig: [e for e in runs.entries if e.rig == rig] for rig in ("srv1", "srv2")
    }
    assert [len(by_rig["srv1"]), len(by_rig["srv2"])] == [15, 27]
    campaign = [e for e in runs.entries if e.kind in ("unit", "move")]
    folder = REPO / "tools/runs/campaigns/lock-fleets/rig-id-relock"
    assert sorted(p.name for p in folder.glob("*.sh")) == sorted(
        Path(e.wrapper).name for e in campaign
    )
    for entry in campaign:
        text = (REPO / entry.wrapper).read_text("utf-8")
        assert re.findall(r"^# RUN_ARTIFACTS: (.*)$", text, re.M) == [entry.artifact]
        assert os.access(REPO / entry.wrapper, os.X_OK)


def test_a_compose_group_held_to_live_is_paired_with_its_live_file(
    tmp_path: Path,
) -> None:
    held = {"two": "~/live/two", "one": "~/live/one"}
    make_tree(tmp_path, use=use_doc(compose_must_match_live=held))
    plan = plan_module()
    live = Path(os.path.expanduser("~/live/two")) / "compose.beta.two.yml"
    assert plan.live_compose(tmp_path, USE, "beta") == [("compose.beta.two.yml", live)]
    assert plan.live_compose(tmp_path, USE, "alpha") == []


@pytest.mark.parametrize("name", ["RUN_HOST", "DOCKER_HOST"])
def test_the_driver_refuses_a_door_or_daemon_variable_it_inherited(name: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RUN_", "DOCKER_"))}
    done = subprocess.run(
        ["bash", str(REPO / "records/measurements/lock-fleets/drive.sh"), "srv1", "x"],
        cwd=REPO,
        env={**env, name: "set-by-hand"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 2, done.stderr
    assert f"REFUSED — {name} set in the calling environment" in done.stderr
