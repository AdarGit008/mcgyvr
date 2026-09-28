"""A live run is admitted only by a read of its rigs, taken through the door.

Owner ruling F2: ``admit_live`` has production callers, and what it is handed as
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
  is the owner's decision still to make.
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

import base64
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.exits import Exit
from tests import onedoor

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/fetch.py"
BASE = "def fetch(url):\n    return url\n"
ACCEPTED = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"
CONTRACT = f"""
id: retry
task_type: function_implementation
task: Give the fetch helper a retry budget named RETRY.
target: {TARGET}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
demonstration: ["sh -c 'grep -q RETRY {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

FIRST, SECOND = "srv2_3b", "srv1_deepseek"
UNIT_FIRST = "unt-" + "5" * 64
UNIT_SECOND = "unt-" + "e" * 64
C_FIRST = "3b" * 32
C_SECOND = "de" * 32
C_STRAY = "5a" * 32
FLEET_NAME = "b-small"
SYSTEM = {
    "srv2": {"os_machine_id": "6d5d8f1f2bfa5f96", "kernel": "7.0.0-31-generic"},
    "srv1": {"os_machine_id": "9f01e96b66e798b2", "kernel": "7.0.0-31-generic"},
}
TOLERANCES = {
    "warm_decode_class_pct": {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}
}


def snapshot_text(host: str, **override: str) -> str:
    return onedoor.snapshot_lines(host, **(SYSTEM[host] | override))


def rig_id_of(host: str) -> str:
    from mcgyvr.fleet.ids import rig_id

    text = snapshot_text(host)
    return rig_id(dict(line.split("=", 1) for line in text.splitlines() if line))


def fleet(profile: str = "live") -> dict[str, Any]:
    return {
        "profile": profile,
        "units": {
            FIRST: {
                "rig": "srv2",
                "unit_id": UNIT_FIRST,
                "engine": "vllm",
                "address": "http://127.0.0.1:18001",
                "model": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
                "container": "mcgyvr-srv2-3b",
                "width": 1,
                "window": 8192,
                "output_tokens": 512,
                "request_timeout_s": 180,
                "room_mib": 3573,
                "kv_cache_memory_bytes": 1207959552,
                "attention_backend": "FLASH_ATTN",
            },
            SECOND: {
                "rig": "srv1",
                "unit_id": UNIT_SECOND,
                "engine": "llama.cpp",
                "address": "http://127.0.0.1:18080",
                "model": "deepseek-coder-v2-16b",
                "container": "mcgyvr-srv1-deepseek",
                "width": 1,
                "window": 8192,
                "output_tokens": 512,
                "request_timeout_s": 180,
                "room_mib": 5458,
            },
        },
        "rigs": {
            "srv2": {"rig_id": rig_id_of("srv2")},
            "srv1": {"rig_id": rig_id_of("srv1")},
        },
        "fleets": {
            FLEET_NAME: {
                "layout": {"srv2": [[FIRST, "awake"]], "srv1": [[SECOND, "awake"]]},
                "next": [],
            }
        },
    }


EVIDENCE: dict[str, Any] = {
    "rigs": {"srv2": {"card_mib": 12288}, "srv1": {"card_mib": 6144}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": [[FIRST, "awake"]],
            "passed": True,
            "overhead_mib": 610.5,
            "restarts": {FIRST: 0},
            "warm_decode_tok_s": {FIRST: 126.7},
            "prefill_tok_s": {FIRST: 11500.0},
            "attention_backend": {FIRST: "FLASH_ATTN"},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv2",
        },
        {
            "rig": "srv1",
            "slots": [[SECOND, "awake"]],
            "passed": True,
            "overhead_mib": 486.22,
            "restarts": {SECOND: 0},
            "warm_decode_tok_s": {SECOND: 32.56},
            "prefill_tok_s": {SECOND: 307.11},
            "card_peak_mib": {SECOND: 5458},
            "card_steady_mib": {SECOND: 5430},
            "validated_at": "2026-09-13T21:48:11Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv1",
        },
    ],
    "moves": [],
}


def home() -> Path:
    return Path(os.environ["HOME"])


def write_setup(where: Path, journal: Path, profile: str) -> Path:
    from mcgyvr.fleet import lock

    where.mkdir(parents=True, exist_ok=True)
    (where / "fleet.yaml").write_text(yaml.safe_dump(fleet(profile)), encoding="utf-8")
    policy = {"ladder": [FIRST, SECOND], "journal": {"dir": str(journal)}}
    (where / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(where, fleet(profile), EVIDENCE, tolerances=TOLERANCES)
    return where


def go_live(tmp_path: Path) -> Path:
    """Promote the fleet into this HOME and name it live; return its folder."""
    folder = write_setup(
        home() / ".mcgyvr" / "fleets" / FLEET_NAME, tmp_path / "journal", "live"
    )
    (home() / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": FLEET_NAME}), encoding="utf-8"
    )
    return folder


def metrics(running: int) -> str:
    return f"vllm:num_requests_running {running}.0\nvllm:num_requests_waiting 0.0\n"


def matching(host: str) -> str:
    """A reading of ``host`` exactly as the lock names it: its one unit up."""
    if host == "srv2":
        extra = (
            f"container=mcgyvr-srv2-3b,{C_FIRST},mcgyvr,0\n"
            f"gpu_app=4242,3400,{C_FIRST},python3\n"
            "sleeping=18001,false\n"
            "status=18001," + base64.b64encode(metrics(0).encode()).decode() + "\n"
        )
    else:
        extra = (
            f"container=mcgyvr-srv1-deepseek,{C_SECOND},mcgyvr,0\n"
            f"gpu_app=4343,5200,{C_SECOND},llama-server\n"
        )
    return snapshot_text(host) + extra


#: What the lock's harness answers on the rig for the vLLM unit.
HARNESS = json.dumps(
    {
        "figures": {"warm_decode_tok_s": 126.7, "prefill_tok_s": 11500.0},
        "after_page": metrics(0),
    }
)


class FakeDoor:
    """Where the CLI spawns ``read``: files what the door's reader would."""

    def __init__(self, events: list[tuple[str, str]]) -> None:
        self.events = events
        self.readings = {"srv1": matching("srv1"), "srv2": matching("srv2")}
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.down: set[str] = set()

    def spawn(self, host: str, run_id: str, probe: Sequence[str] = ()) -> int:
        from mcgyvr.fleet import read

        self.calls.append((host, tuple(probe)))
        self.events.append(("read", host))
        if host in self.down:
            return 2
        read.record(
            host,
            self.readings[host],
            run_id=run_id,
            profile="live",
            probe=tuple(probe),
            measure=lambda unit, spec: HARNESS,
        )
        return 0


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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def _completion(text: str) -> Any:
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="m",
        source="s",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def climb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    events: list[tuple[str, str]],
    label: str,
    config: Path | None = None,
) -> tuple[int, str]:
    """One ``mcgyvr run`` in a fresh repository: its exit and its stderr."""
    import mcgyvr.drive as drive
    from mcgyvr.cli import main

    repo = tmp_path / f"repo-{label}"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / TARGET).write_text(BASE, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    contract = tmp_path / f"retry-{label}.yaml"
    contract.write_text(CONTRACT, encoding="utf-8")

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Any:
        events.append(("dispatch", rung))
        if rung == FIRST:
            return _completion("I would rather not write any code today.")
        return _completion(f"```python\n{ACCEPTED}```\n")

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    argv = ["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"]
    if config is not None:
        argv += ["--config", str(config)]
    code = main(argv)
    return code, capsys.readouterr().err


def dispatched(events: list[tuple[str, str]]) -> list[str]:
    return [what for kind, what in events if kind == "dispatch"]


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
    assert sorted(host for host, _ in door.calls) == ["srv1", "srv2"], door.calls
    first_dispatch = events.index(("dispatch", FIRST))
    assert all(events.index(("read", h)) < first_dispatch for h in ("srv1", "srv2"))
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
    assert "no fleet named" in err
    assert door.calls == [] and dispatched(events) == []


def test_a_rig_that_is_not_the_rig_it_was_locked_on_is_refused_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    from mcgyvr.fleet.ids import rig_id

    go_live(tmp_path)
    moved = snapshot_text("srv1", kernel="7.0.0-32-generic")
    door.readings["srv1"] = moved + matching("srv1")[len(snapshot_text("srv1")) :]
    read_as = rig_id(dict(line.split("=", 1) for line in moved.splitlines() if line))

    code, err = climb(tmp_path, monkeypatch, capsys, events, "moved")

    assert code == Exit.REFUSED, err
    assert "srv1" in err and read_as in err, err
    assert dispatched(events) == []


def test_a_process_that_is_not_ours_refuses_the_run_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live(tmp_path)
    door.readings["srv2"] += "gpu_app=5555,1024,none,python3_train.py\n"

    code, err = climb(tmp_path, monkeypatch, capsys, events, "foreign")

    assert code == Exit.REFUSED, err
    assert "srv2" in err and "python3_train.py" in err and "5555" in err, err
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
    edited["fleets"][FLEET_NAME]["layout"]["srv2"] = [[FIRST, "asleep"]]
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
    door.readings["srv1"] = snapshot_text("srv1")
    door.readings["srv2"] += f"container=mcgyvr-srv2-stray,{C_STRAY},mcgyvr,0\n"

    code, err = climb(tmp_path, monkeypatch, capsys, events, "plan")

    assert code == Exit.REFUSED, err
    assert "restore" in err and UNIT_SECOND in err, err
    assert "clean" in err and "mcgyvr-srv2-stray" in err, err
    assert "python -m mcgyvr.serving.run serve up --host srv1" in err, err
    assert "python -m mcgyvr.serving.run serve down --host srv2" in err, err
    assert dispatched(events) == []


def test_a_dev_run_reads_no_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    door: FakeDoor,
    events: list[tuple[str, str]],
) -> None:
    go_live(tmp_path)
    dev = write_setup(tmp_path / "dev-setup", tmp_path / "dev-journal", "dev")

    code, err = climb(tmp_path, monkeypatch, capsys, events, "dev", config=dev)

    assert code == 0, err
    assert door.calls == []
    assert dispatched(events)


# --- mcgyvr serve -----------------------------------------------------------------


def _made(direction: str) -> Any:
    from mcgyvr.wake import Wake

    return Wake(
        host="srv2",
        compose_file=Path("compose.srv2.b-small.yml"),
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
    return main(["serve", direction, "--host", "srv2"]), done


def test_a_live_serve_sleep_is_admitted_and_reads_no_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, door: FakeDoor
) -> None:
    go_live(tmp_path)
    door.readings["srv2"] = snapshot_text("srv2")

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
    door.readings["srv2"] = snapshot_text("srv2")

    code, done = _serve(monkeypatch, "wake")
    err = capsys.readouterr().err

    assert code == Exit.REFUSED, err
    assert done == [], "a wake the plan does not admit is not carried out"
    assert "restore" in err and UNIT_FIRST in err, err

    door.readings["srv2"] = matching("srv2")
    code, done = _serve(monkeypatch, "wake")
    assert (code, done) == (0, ["wake"]), capsys.readouterr().err


# --- mcgyvr fleet probe -------------------------------------------------------------


class LlamaUnit:
    """srv1_deepseek's HTTP face, answering the lock's llama.cpp harness."""

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
    assert sorted(door.calls) == [("srv1", ()), ("srv2", (FIRST,))], door.calls
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
    door.down = {"srv2"}

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
