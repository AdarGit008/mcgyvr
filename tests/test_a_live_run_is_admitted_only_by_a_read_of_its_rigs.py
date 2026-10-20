"""A live run is admitted only by a read of its rigs, taken through the door.

``admit_live`` has production callers, and what it is handed as
``observed`` is the door's ``read`` of each rig (``python -m mcgyvr.serving.run
read``), never a guess.

* **Live ``mcgyvr run`` and ``delegate --run``** are admitted before anything
  is opened or dispatched, and refused when no fleet is named, when the layout
  was edited after locking (the refusal says to re-lock), when a rig is not the
  rig it was locked on (naming the rig and the id it read), or when a process
  that is not ours holds a card (naming it). The deterministic floor dispatches
  nothing to the fleet and is not admitted.
* **A non-empty plan refuses** and prints what would be cleaned or restored and
  the door commands that would do it. It runs none of them: carrying a plan out
  is the user's decision still to make.
* **A dev run reads no rig.**
* **A live ``serve sleep`` is always admitted**, and reads no rig: stopping
  starts nothing unapproved. A live ``serve wake`` is admitted like a run.
* **``mcgyvr fleet probe`` takes card MiB and restarts from the same read**,
  judged against ``room_mib`` and 0, and a vLLM unit's decode and prefill from
  ``read --probe``, timed on the rig and judged. A rig the door cannot read
  leaves its vLLM units timed off the rig, recorded and not judged.

The door is substituted where the CLI spawns it,
:func:`mcgyvr.fleet.read.spawn_read`: the stand-in files exactly what the door's
reader would, from a canned rig reading, through
:func:`mcgyvr.fleet.read.record`. No rig, no network, no door process.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.exits import Exit
from tests import onedoor
from tests.liveruns import (
    FIRST,
    SECOND,
    UNIT_FIRST,
    UNIT_SECOND,
    FakeDoor,
    climb,
    dispatched,
    fleet,
    go_live,
    home,
    matching,
    snapshot_text,
    write_setup,
)
from tests.reads import FLEET_NAME

C_STRAY = "5a" * 32


@pytest.fixture
def events() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def door(monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, str]]) -> FakeDoor:
    import mcgyvr.wake as wake
    from mcgyvr.fleet import read

    fake = FakeDoor(events)
    monkeypatch.setattr(read, "spawn_read", fake.spawn)

    def no_plan_is_carried_out(argv: Sequence[str], **_: object) -> int:
        raise AssertionError(f"a plan was carried out through the door: {argv}")

    monkeypatch.setattr(wake, "spawn_door", no_plan_is_carried_out)
    return fake


# --- mcgyvr run -------------------------------------------------------------------


def test_a_live_run_on_rigs_that_read_as_locked_is_admitted_then_dispatched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live(tmp_path)

    code, err = climb(tmp_path, monkeypatch, capsys, events, "admitted")

    assert code == 0, err
    assert sorted(host for host, _ in door.calls) == ["box1", "box2"], door.calls
    first_dispatch = events.index(("dispatch", FIRST))
    assert all(events.index(("read", h)) < first_dispatch for h in ("box1", "box2"))
    assert "refused" not in err


def test_a_live_run_with_no_fleet_named_is_refused_before_any_read_or_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    folder = go_live(tmp_path)
    (home() / ".mcgyvr" / "live.json").unlink()

    code, err = climb(tmp_path, monkeypatch, capsys, events, "unnamed", config=folder)

    assert code == Exit.REFUSED, err
    assert "no fleet is live" in err
    assert door.calls == [] and dispatched(events) == []


def test_a_rig_that_is_not_the_rig_it_was_locked_on_is_refused_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live(tmp_path)
    # Another card at box1's address: another machine, by its rig id.
    moved = snapshot_text("box1", gpu_vram_mib="16384")
    door.readings["box1"] = moved + matching("box1")[len(snapshot_text("box1")) :]
    read_as = onedoor.rig_id_of_text(moved)

    code, err = climb(tmp_path, monkeypatch, capsys, events, "moved")

    assert code == Exit.REFUSED, err
    assert "box1" in err and read_as in err, err
    assert dispatched(events) == []


def test_a_process_that_is_not_ours_refuses_the_run_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live(tmp_path)
    door.readings["box2"] += "gpu_app=5555,1024,none,python3_train.py\n"

    code, err = climb(tmp_path, monkeypatch, capsys, events, "foreign")

    assert code == Exit.REFUSED, err
    assert "box2" in err and "python3_train.py" in err and "5555" in err, err
    assert dispatched(events) == []


def test_a_layout_edited_after_locking_is_refused_and_told_to_relock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    folder = go_live(tmp_path)
    edited = fleet()
    edited["fleets"][FLEET_NAME]["layout"]["box2"] = [[FIRST, "asleep"]]
    (folder / "fleet.yaml").write_text(yaml.safe_dump(edited), encoding="utf-8")

    code, err = climb(tmp_path, monkeypatch, capsys, events, "edited")

    assert code == Exit.REFUSED, err
    assert "re-lock" in err
    assert dispatched(events) == []


def test_a_plan_to_clean_or_restore_refuses_and_names_the_door_commands_it_does_not_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live(tmp_path)
    door.readings["box1"] = snapshot_text("box1")
    door.readings["box2"] += f"container=mcgyvr-box2-stray,{C_STRAY},mcgyvr,0\n"

    code, err = climb(tmp_path, monkeypatch, capsys, events, "plan")

    assert code == Exit.REFUSED, err
    assert "restore" in err and UNIT_SECOND in err, err
    assert "clean" in err and "mcgyvr-box2-stray" in err, err
    assert "python -m mcgyvr.serving.run serve up --host box1" in err
    assert "python -m mcgyvr.serving.run serve down --host box2" in err
    assert dispatched(events) == []


def test_a_run_under_a_staged_setup_reads_no_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    """A setup ``mcgyvr setup`` stages in the data folder is held to no lock,
    with a fleet live or not, so no rig is read."""
    from mcgyvr.fleet.roots import staging_dir

    go_live(tmp_path)
    staged = write_setup(staging_dir("20261015T000000-abcdef01"), tmp_path / "j")

    code, err = climb(tmp_path, monkeypatch, capsys, events, "staged", config=staged)

    assert code == 0, err
    assert door.calls == []
    assert dispatched(events)


# --- mcgyvr serve -----------------------------------------------------------------


def _made(direction: str) -> Any:
    from mcgyvr.wake import Wake

    return Wake(
        host="box2",
        compose_file=Path("compose.box2.b-small.yml"),
        direction=direction,
        seconds=0.1,
        predicted_s=None,
        code=0,
    )


def _serve(monkeypatch: pytest.MonkeyPatch, direction: str) -> tuple[int, list[str]]:
    import mcgyvr.wake as wake
    from mcgyvr.cli import main

    done: list[str] = []

    def card_named(config: Any, host: str) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(host=host, sources=())

    def carried(verb: str) -> Any:
        def act(config: Any, host: str) -> Any:
            done.append(verb)
            return _made("up" if verb == "wake" else "down")

        return act

    monkeypatch.setattr(wake, "card_named", card_named)
    monkeypatch.setattr(wake, "wake", carried("wake"))
    monkeypatch.setattr(wake, "sleep", carried("sleep"))
    return main(["serve", direction, "--host", "box2"]), done


def test_a_live_serve_sleep_is_admitted_and_reads_no_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, door: FakeDoor
) -> None:
    go_live(tmp_path)
    door.readings["box2"] = snapshot_text("box2")

    code, done = _serve(monkeypatch, "sleep")

    assert (code, done) == (0, ["sleep"])
    assert door.calls == []


def test_a_live_serve_wake_is_admitted_only_by_a_read_of_its_rigs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
) -> None:
    go_live(tmp_path)
    door.readings["box2"] = snapshot_text("box2")

    code, done = _serve(monkeypatch, "wake")
    err = capsys.readouterr().err

    assert code == Exit.REFUSED, err
    assert done == [], "a wake the plan does not admit is not carried out"
    assert "restore" in err and UNIT_FIRST in err, err

    door.readings["box2"] = matching("box2")
    code, done = _serve(monkeypatch, "wake")
    assert (code, done) == (0, ["wake"]), capsys.readouterr().err


# --- mcgyvr fleet probe -------------------------------------------------------------


class LlamaUnit:
    """box1_deepseek's HTTP face, answering the lock's llama.cpp harness."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, timeout: float) -> Any:
        self.urls.append(url)
        raise AssertionError(f"nothing is read off the rig by GET: {url}")

    def post(self, url: str, payload: Mapping[str, Any], timeout: float) -> Any:
        self.urls.append(url)
        assert url == "http://127.0.0.1:18080/completion", url
        if payload["n_predict"] == 256:
            return {"timings": {"predicted_per_second": 32.56}}
        if payload["n_predict"] == 16:
            return {"timings": {"prompt_per_second": 307.11}}
        return {"timings": {"predicted_per_second": 1.0}}


def _probe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, LlamaUnit]:
    from datetime import UTC, datetime

    from mcgyvr import cli
    from mcgyvr.fleet import probe

    unit = LlamaUnit()
    measured = probe.run

    def faked(**kwargs: Any) -> Any:
        return measured(
            transport=unit,
            in_flight=lambda *_: 0,
            clock=lambda: 0.0,
            now=datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC),
            **kwargs,
        )

    monkeypatch.setattr(probe, "run", faked)
    capsys.readouterr()
    code = cli.main(["fleet", "probe"])
    return code, capsys.readouterr().out, unit


def _journal_rows(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted((tmp_path / "journal" / "fleet").rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_fleet_probe_takes_card_and_restarts_from_the_read_and_times_vllm_on_the_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
) -> None:
    go_live(tmp_path)

    code, out, unit = _probe(monkeypatch, capsys)

    assert code == 0, out
    assert sorted(door.calls) == [("box1", ()), ("box2", (FIRST,))], door.calls
    assert "not read" not in out, out
    assert f"not judged {FIRST}" not in out, out
    assert not [u for u in unit.urls if ":18001" in u], "vLLM timed off the rig"
    judged = {
        (r["unit_id"], r["field"]): r for r in _journal_rows(tmp_path) if "alert" in r
    }
    for unit_id in (UNIT_FIRST, UNIT_SECOND):
        assert judged[(unit_id, "card_mib")]["alert"] is False
        assert judged[(unit_id, "restarts")]["alert"] is False
    assert judged[(UNIT_FIRST, "warm_decode_tok_s")]["observed"] == 126.7
    assert judged[(UNIT_SECOND, "warm_decode_tok_s")]["alert"] is False


def test_a_rig_the_door_cannot_read_leaves_its_vllm_unit_timed_off_the_rig_unjudged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
) -> None:
    from mcgyvr.fleet import probe

    go_live(tmp_path)
    door.down = {"box2"}

    class Both(LlamaUnit):
        def get(self, url: str, timeout: float) -> Any:
            self.urls.append(url)
            return {"data": [{"id": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"}]}

        def post(self, url: str, payload: Mapping[str, Any], timeout: float) -> Any:
            if ":18001" in url:
                self.urls.append(url)
                return {"usage": {"completion_tokens": 256, "prompt_tokens": 1960}}
            return super().post(url, payload, timeout)

    both = Both()
    measured = probe.run

    def faked(**kwargs: Any) -> Any:
        return measured(transport=both, in_flight=lambda *_: 0, **kwargs)

    monkeypatch.setattr(probe, "run", faked)
    from mcgyvr import cli

    capsys.readouterr()
    code = cli.main(["fleet", "probe"])
    out = capsys.readouterr().out

    assert code == 0, out
    assert f"not read {FIRST}: card_mib, restarts" in out, out
    assert f"not judged {FIRST}" in out, out
    assert f"not read {SECOND}" not in out, out
