"""A live probe judged against the lock it was taken under."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.reads import UNIT_3B

UNIT_DS = "unt-" + "e" * 64


RIG1 = "rig-" + "0" * 64


RIG2 = "rig-" + "c" * 64


CLASSES = {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}


TOLERANCES: dict[str, Any] = {"warm_decode_class_pct": CLASSES}


FLEET: dict[str, Any] = {
    "profile": "live",
    "units": {
        "srv2_3b": {
            "rig": "srv2",
            "unit_id": UNIT_3B,
            "address": "http://srv2:8001",
            "engine": "vllm",
            "model": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
            "width": 8,
            "window": 4096,
            "output_tokens": 2048,
            "request_timeout_s": 180,
            "room_mib": 3573,
            "kv_cache_memory_bytes": 1207959552,
            "attention_backend": "FLASH_ATTN",
            "container": "mcgyvr-srv2-3b",
        },
        "srv1_deepseek": {
            "rig": "srv1",
            "unit_id": UNIT_DS,
            "address": "http://srv1:8080",
            "engine": "llama.cpp",
            "model": "deepseek-coder-v2-16b",
            "width": 2,
            "window": 8192,
            "output_tokens": 2048,
            "request_timeout_s": 180,
            "room_mib": 5458,
            "launch": {"n_cpu_moe": 19, "flags": ["-c", "8192", "-ngl", "99"]},
        },
    },
    "rigs": {"srv1": {"rig_id": RIG1}, "srv2": {"rig_id": RIG2}},
    "fleets": {
        "b-small": {
            "layout": {
                "srv2": [["srv2_3b", "awake"]],
                "srv1": [["srv1_deepseek", "awake"]],
            },
            "next": [],
        }
    },
}


EVIDENCE: dict[str, Any] = {
    "rigs": {"srv1": {"card_mib": 6144}, "srv2": {"card_mib": 12288}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": [["srv2_3b", "awake"]],
            "passed": True,
            "overhead_mib": 610.5,
            "restarts": {"srv2_3b": 0},
            "warm_decode_tok_s": {"srv2_3b": 126.7},
            "prefill_tok_s": {"srv2_3b": 11500.0},
            "attention_backend": {"srv2_3b": "FLASH_ATTN"},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "evidence/srv2",
        },
        {
            "rig": "srv1",
            "slots": [["srv1_deepseek", "awake"]],
            "passed": True,
            "overhead_mib": 486.22,
            "restarts": {"srv1_deepseek": 0},
            "warm_decode_tok_s": {"srv1_deepseek": 32.56},
            "prefill_tok_s": {"srv1_deepseek": 307.11},
            "card_peak_mib": {"srv1_deepseek": 5458},
            "card_steady_mib": {"srv1_deepseek": 5430},
            "validated_at": "2026-09-13T21:48:11Z",
            "envelope": "evidence/srv1",
        },
    ],
    "moves": [],
}


NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


def live_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fleet: dict[str, Any] = FLEET,
    evidence: dict[str, Any] = EVIDENCE,
) -> Path:
    """A HOME holding one promoted fleet, named live, with its journal in tmp."""
    from mcgyvr.fleet import lock

    home = tmp_path / "home"
    folder = home / ".mcgyvr" / "fleets" / "b-small"
    folder.mkdir(parents=True)
    (folder / "fleet.yaml").write_text(yaml.safe_dump(fleet), encoding="utf-8")
    journal = tmp_path / "journal"
    policy = {
        "ladder": ["srv2_3b", "srv1_deepseek"],
        "journal": {"dir": str(journal)},
    }
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(folder, fleet, evidence, tolerances=TOLERANCES)
    (home / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": "b-small", "since": "2026-09-15T00:00:00Z"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    return journal


class FakeUnits:
    """Both engines' HTTP faces, answering at the rates the test sets.

    The clock moves only inside a request, by the seconds the answer took, so
    a vLLM rate is exactly what ``completion_tokens`` over the wall gives.
    """

    def __init__(self, rates: Mapping[str, float]) -> None:
        self.rates = dict(rates)
        self.now = 1000.0
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def clock(self) -> float:
        return self.now

    def get(self, url: str, timeout: float) -> dict[str, Any]:
        assert url == "http://srv2:8001/v1/models", url
        return {"data": [{"id": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"}]}

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.posts.append((url, payload))
        if url.startswith("http://srv2:8001"):
            if payload["max_tokens"] == 256:
                self.now += 256 / self.rates["3b_decode"]
                return {"usage": {"completion_tokens": 256, "prompt_tokens": 20}}
            if payload["max_tokens"] == 16:
                self.now += 1960 / self.rates["3b_prefill"]
                return {"usage": {"completion_tokens": 16, "prompt_tokens": 1960}}
            self.now += 0.5
            return {"usage": {"completion_tokens": 64, "prompt_tokens": 20}}
        assert url == "http://srv1:8080/completion", url
        if payload["n_predict"] == 256:
            return {"timings": {"predicted_per_second": self.rates["ds_decode"]}}
        if payload["n_predict"] == 16:
            return {"timings": {"prompt_per_second": self.rates["ds_prefill"]}}
        return {"timings": {"predicted_per_second": 1.0}}


def idle(*_: Any) -> int:
    return 0


def run_probe(
    fake: FakeUnits,
    in_flight: Callable[[str, Mapping[str, Any]], int | None] = idle,
    units: list[str] | None = None,
) -> Any:
    from mcgyvr.fleet import probe

    return probe.run(
        transport=fake,
        in_flight=in_flight,
        clock=fake.clock,
        units=units,
        now=NOW,
    )


def rows(journal: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted(journal.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


HOLDING = {"3b_decode": 126.7, "3b_prefill": 11500.0, "ds_decode": 32.56}


STAMP = {
    "fleet": "b-small",
    "rig": "srv1",
    "rig_id": RIG1,
    "combination_id": "cmb-" + "a" * 64,
    "unit_id": UNIT_DS,
}


def lock_root(tmp_path: Path) -> Path:
    """The live fleet folder :func:`live_home` promoted, which holds its locks."""
    return tmp_path / "home" / ".mcgyvr" / "fleets" / "b-small"
