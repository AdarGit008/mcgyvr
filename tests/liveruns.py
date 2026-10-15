"""A live run admitted by a read of its rigs."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import onedoor
from tests.reads import FLEET_NAME

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
task_type: code
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


FIRST, SECOND = "box2_3b", "box1_deepseek"


UNIT_FIRST = "unt-" + "5" * 64


UNIT_SECOND = "unt-" + "e" * 64


C_FIRST = "3b" * 32


C_SECOND = "de" * 32


SYSTEM = {
    "box2": {"os_machine_id": "6d5d8f1f2bfa5f96", "kernel": "7.0.0-31-generic"},
    "box1": {"os_machine_id": "9f01e96b66e798b2", "kernel": "7.0.0-31-generic"},
}


TOLERANCES = {
    "warm_decode_class_pct": {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}
}


def snapshot_text(host: str, **override: str) -> str:
    return onedoor.snapshot_lines(host, **(SYSTEM[host] | override))


def rig_id_of(host: str) -> str:
    return onedoor.rig_id_of_text(snapshot_text(host))


def fleet() -> dict[str, Any]:
    return {
        "units": {
            FIRST: {
                "rig": "box2",
                "unit_id": UNIT_FIRST,
                "engine": "vllm",
                "address": "http://127.0.0.1:18001",
                "model": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
                "container": "mcgyvr-box2-3b",
                "width": 1,
                "window": 8192,
                "output_tokens": 512,
                "request_timeout_s": 180,
                "room_mib": 3573,
                "kv_cache_memory_bytes": 1207959552,
                "attention_backend": "FLASH_ATTN",
            },
            SECOND: {
                "rig": "box1",
                "unit_id": UNIT_SECOND,
                "engine": "llama.cpp",
                "address": "http://127.0.0.1:18080",
                "model": "deepseek-coder-v2-16b",
                "container": "mcgyvr-box1-deepseek",
                "width": 1,
                "window": 8192,
                "output_tokens": 512,
                "request_timeout_s": 180,
                "room_mib": 5458,
            },
        },
        "rigs": {
            "box2": {"rig_id": rig_id_of("box2")},
            "box1": {"rig_id": rig_id_of("box1")},
        },
        "fleets": {
            FLEET_NAME: {
                "layout": {"box2": [[FIRST, "awake"]], "box1": [[SECOND, "awake"]]},
                "next": [],
            }
        },
    }


EVIDENCE: dict[str, Any] = {
    "rigs": {"box2": {"card_mib": 12288}, "box1": {"card_mib": 6144}},
    "combinations": [
        {
            "rig": "box2",
            "slots": [[FIRST, "awake"]],
            "passed": True,
            "overhead_mib": 610.5,
            "restarts": {FIRST: 0},
            "warm_decode_tok_s": {FIRST: 126.7},
            "prefill_tok_s": {FIRST: 11500.0},
            "attention_backend": {FIRST: "FLASH_ATTN"},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/box2",
        },
        {
            "rig": "box1",
            "slots": [[SECOND, "awake"]],
            "passed": True,
            "overhead_mib": 486.22,
            "restarts": {SECOND: 0},
            "warm_decode_tok_s": {SECOND: 32.56},
            "prefill_tok_s": {SECOND: 307.11},
            "card_peak_mib": {SECOND: 5458},
            "card_steady_mib": {SECOND: 5430},
            "validated_at": "2026-09-13T21:48:11Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/box1",
        },
    ],
    "moves": [],
}


def home() -> Path:
    return Path(os.environ["HOME"])


def write_setup(where: Path, journal: Path) -> Path:
    from mcgyvr.fleet import lock

    where.mkdir(parents=True, exist_ok=True)
    (where / "fleet.yaml").write_text(yaml.safe_dump(fleet()), encoding="utf-8")
    policy = {"ladder": [FIRST, SECOND], "journal": {"dir": str(journal)}}
    (where / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(where, fleet(), EVIDENCE, tolerances=TOLERANCES)
    return where


def go_live(tmp_path: Path) -> Path:
    """Promote the fleet into this HOME and name it live; return its folder."""
    folder = write_setup(
        home() / ".mcgyvr" / "fleets" / FLEET_NAME, tmp_path / "journal"
    )
    (home() / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": FLEET_NAME}), encoding="utf-8"
    )
    return folder


def metrics(running: int) -> str:
    return f"vllm:num_requests_running {running}.0\nvllm:num_requests_waiting 0.0\n"


def matching(host: str) -> str:
    """A reading of ``host`` exactly as the lock names it: its one unit up."""
    if host == "box2":
        extra = (
            f"container=mcgyvr-box2-3b,{C_FIRST},mcgyvr,0\n"
            f"gpu_app=4242,3400,{C_FIRST},python3\n"
            "sleeping=18001,false\n"
            "status=18001," + base64.b64encode(metrics(0).encode()).decode() + "\n"
        )
    else:
        extra = (
            f"container=mcgyvr-box1-deepseek,{C_SECOND},mcgyvr,0\n"
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
        self.readings = {"box1": matching("box1"), "box2": matching("box2")}
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
            *onedoor.split_reading(self.readings[host]),
            run_id=run_id,
            probe=tuple(probe),
            measure=lambda unit, spec: HARNESS,
        )
        return 0


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def _completion(text: str) -> Any:
    from mcgyvr.local_pool import Protocol
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
