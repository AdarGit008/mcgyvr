"""A live unit is judged only by a solo probe run with its lock's own method.

Owner, 2026-09-15 (F2): every dispatch row keeps its decode, prefill and
in-flight figures as data, and only a probe judges. A solo srv2_3b dispatch
of 1206 tokens in and 503 out decoded 114.1 tok/s against a locked 126.7; the
lock was measured at a short prompt and 256 tokens out, so a dispatch is not
the lock's quantity.

* **The probe repeats the lock's measurement.** A vLLM unit gets
  ``records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py``: one
  64-token warm-up, five 256-token decodes (``completion_tokens`` over wall
  seconds) and three 16-token prefills of the long prompt (``prompt_tokens``
  over wall seconds). A llama.cpp unit gets
  ``records/measurements/fleet-setup-2026-09-13/srv1/harness_llama.py``:
  ``/completion`` with ``timings``. Both take the median, as the lock did
  (``fleet-setup/REPORT-srv1.md``, ``REPORT-srv2.md``).
* **It probes only an idle unit.** It reads the unit's own count first and
  again after; a unit busy before is not probed, and one busy after is filed
  as contended and not judged.
* **It stamps every observation** with the fleet, rig, rig id, combination id
  and unit id of the live lock, and files them under ``<journal.dir>/fleet/``.
* **A vLLM figure is recorded, not judged.** Owner, 2026-09-15: "vLLM
  stopwatch on the rig; record till then". The probe times a vLLM request by
  wall clock from off the rig, at the unit's address, while ``measure_vllm.py``
  timed on the rig at 127.0.0.1. The network time alone pulled srv2 in the
  first live probe (:mod:`mcgyvr.fleet.probe`). A llama.cpp figure is the
  server's own ``timings``, and is still judged.
* **The tolerance is one class per unit.** vLLM is ``vllm``; llama.cpp with
  experts on the CPU is ``cpu_experts``; any other llama.cpp is ``llamacpp``.
  The classes are the measured ones in
  ``records/measurements/fleet-identity-2026-09-11/tolerances.json`` (1%, 1%,
  48%), stated in ``tools/runs/derived.json``. The lock's NVMe baseline check
  reads the same class.
* **The lock's plain values are judged.** Decode and prefill fall below by the
  class percent. Card memory rises above the unit's ``room_mib``. Restarts are
  exactly 0.
* **Card and restarts are read on the rig**, and a rig is reached only behind
  the door (``tests/test_one_door.py``). So the probe names both as not read,
  with that reason, rather than reaching a rig by another way.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "records" / "measurements" / "fleet-setup-2026-09-13"
VLLM_HARNESS = HARNESS / "srv2" / "measure_vllm.py"
LLAMA_HARNESS = HARNESS / "srv1" / "harness_llama.py"

UNIT_3B = "unt-" + "5" * 64
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
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv2",
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
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv1",
        },
    ],
    "moves": [],
}

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


def _harness_strings(path: Path) -> dict[str, Any]:
    """The module-level string constants a harness assigns, evaluated as written."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        expr = ast.Expression(node.value)
        ast.fix_missing_locations(expr)
        try:
            value = eval(
                compile(expr, str(path), "eval"),
                {"__builtins__": {}},
                dict(found),
            )
        except Exception:
            continue
        found[target.id] = value
    return {k: v for k, v in found.items() if isinstance(v, str | list)}


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
HOLDING |= {"ds_prefill": 307.11}


# --- the tolerance class ----------------------------------------------------


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ({"engine": "vllm", "launch": {"n_cpu_moe": 4}}, "vllm"),
        ({"engine": "llama.cpp", "launch": {"n_cpu_moe": 19}}, "cpu_experts"),
        ({"engine": "llama.cpp", "launch": {"flags": ["--cpu-moe"]}}, "cpu_experts"),
        (
            {"engine": "llama.cpp", "launch": {"flags": ["--n-cpu-moe", "8"]}},
            "cpu_experts",
        ),
        ({"engine": "llama.cpp", "launch": {"flags": ["-ngl", "99"]}}, "llamacpp"),
        ({"launch": {}}, "llamacpp"),
    ],
)
def test_each_unit_has_one_tolerance_class(unit: dict[str, Any], expected: str) -> None:
    from mcgyvr.fleet.tolerance import tolerance_class

    assert tolerance_class(unit) == expected


def test_the_class_tolerances_are_the_measured_ones_stated_in_derived_json() -> None:
    from mcgyvr import derived

    measured = json.loads(
        (
            REPO / "records/measurements/fleet-identity-2026-09-11/tolerances.json"
        ).read_text(encoding="utf-8")
    )["classes"]
    assert derived.class_tolerances() == {
        name: float(body["tolerance_pct"]) for name, body in measured.items()
    }


def test_an_absent_class_tolerance_is_refused_by_name(tmp_path: Path) -> None:
    from mcgyvr import derived

    doc = json.loads((REPO / "tools/runs/derived.json").read_text(encoding="utf-8"))
    del doc["engine"]["warm_decode_class_pct"]["cpu_experts"]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match="cpu_experts"):
        derived.class_tolerances(path=path)


def test_the_locks_nvme_check_reads_the_same_class(tmp_path: Path) -> None:
    """30 against a 33 baseline is 9.1% slower: inside CPU-experts' 48%, past
    llama.cpp's 1%."""
    from mcgyvr.fleet import lock

    evidence = json.loads(json.dumps(EVIDENCE))
    evidence["combinations"][1]["warm_decode_tok_s"]["srv1_deepseek"] = 30.0
    evidence["combinations"][1]["baseline_tok_s"] = {"srv1_deepseek": 33.0}
    lock.write(tmp_path / "experts", FLEET, evidence, tolerances=TOLERANCES)

    plain = json.loads(json.dumps(FLEET))
    plain["units"]["srv1_deepseek"]["launch"] = {"flags": ["-ngl", "99"]}
    with pytest.raises(lock.LockRefusedError, match="baseline"):
        lock.write(tmp_path / "plain", plain, evidence, tolerances=TOLERANCES)


# --- judging the lock's plain values ----------------------------------------

STAMP = {
    "fleet": "b-small",
    "rig": "srv1",
    "rig_id": RIG1,
    "combination_id": "cmb-" + "a" * 64,
    "unit_id": UNIT_DS,
}
PLAIN = {
    UNIT_DS: {
        "warm_decode_tok_s": 32.56,
        "prefill_tok_s": 307.11,
        "card_peak_mib": 5458,
        "tolerance_pct": 48.0,
        "room_mib": 5458,
    }
}


def judged(field: str, value: float, tmp_path: Path) -> list[dict[str, Any]]:
    from mcgyvr.fleet import alerts

    return list(
        alerts.check(
            [{"unit_id": UNIT_DS, "field": field, "observed": value}],
            approved=PLAIN,
            profile="live",
            journal_dir=tmp_path / field,
            stamp=STAMP,
            run_id="run-20260915T120000-0a1b2c3d",
            lease_id="probe-0a1b2c3d",
        )
    )


@pytest.mark.parametrize(
    ("field", "holds", "alerts_at"),
    [
        ("warm_decode_tok_s", 17.0, 16.9),  # 32.56 x 0.52 = 16.93
        ("prefill_tok_s", 160.0, 159.0),  # 307.11 x 0.52 = 159.70
        ("card_mib", 5458, 5459),  # the unit's room_mib
        ("restarts", 0, 1),
    ],
)
def test_the_locks_plain_values_are_judged_with_the_class_tolerance(
    field: str, holds: float, alerts_at: float, tmp_path: Path
) -> None:
    assert judged(field, holds, tmp_path / "holds") == []
    raised = judged(field, alerts_at, tmp_path / "alerts")
    assert [a["field"] for a in raised] == [field], raised


# --- the probe --------------------------------------------------------------


def test_the_probe_sends_the_locks_own_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_home(tmp_path, monkeypatch)
    fake = FakeUnits(HOLDING)
    run_probe(fake)

    vllm = _harness_strings(VLLM_HARNESS)
    llama = _harness_strings(LLAMA_HARNESS)
    to_3b = [p for u, p in fake.posts if u.startswith("http://srv2:8001")]
    assert [p["max_tokens"] for p in to_3b] == [64] + [256] * 5 + [16] * 3
    assert all(p["temperature"] == 0 for p in to_3b)
    assert [p["ignore_eos"] for p in to_3b] == [False] + [True] * 5 + [False] * 3
    assert all(p["messages"] == vllm["SHORT"] for p in to_3b[:6])
    assert all(
        p["messages"] == [{"role": "user", "content": vllm["LONG"]}] for p in to_3b[6:]
    )
    assert all(p["model"] == "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ" for p in to_3b)

    to_ds = [p for u, p in fake.posts if u.startswith("http://srv1:8080")]
    assert [p["n_predict"] for p in to_ds] == [64] + [256] * 5 + [16] * 3
    assert all(p["temperature"] == 0 for p in to_ds)
    assert all(p["prompt"] == llama["SHORT_PROMPT"] for p in to_ds[:6])
    assert all(p["prompt"] == llama["LONG_PROMPT"] for p in to_ds[6:])
    assert all(p.get("cache_prompt") is False for p in to_ds[1:])


def test_the_probe_files_stamped_observations_under_journal_fleet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = live_home(tmp_path, monkeypatch)
    report = run_probe(FakeUnits(HOLDING))

    assert report.exit_code == 0
    assert report.alerts == []
    filed = rows(journal / "fleet")
    by_unit = {(r["unit_id"], r["field"]): r for r in filed}
    assert set(by_unit) == {
        (UNIT_3B, "warm_decode_tok_s"),
        (UNIT_3B, "prefill_tok_s"),
        (UNIT_DS, "warm_decode_tok_s"),
        (UNIT_DS, "prefill_tok_s"),
    }
    three = by_unit[(UNIT_3B, "warm_decode_tok_s")]
    assert three["observed"] == pytest.approx(126.7)
    assert three["fleet"] == "b-small" and three["rig"] == "srv2"
    assert three["rig_id"] == RIG2
    assert three["combination_id"].startswith("cmb-")
    # The moment srv2_3b's measurement finished: 11.1 s of its requests after
    # the probe began (a 0.5 s warm-up, 5 x 256/126.7 s, 3 x 1960/11500 s).
    assert three["at"] == "2026-09-15T12:00:11"
    assert by_unit[(UNIT_DS, "prefill_tok_s")]["observed"] == pytest.approx(307.11)
    assert by_unit[(UNIT_DS, "prefill_tok_s")]["alert"] is False
    assert not list(tmp_path.glob("journal/*.jsonl")), "filed outside journal/fleet"


def lock_root(tmp_path: Path) -> Path:
    """The live fleet folder :func:`live_home` promoted, which holds its locks."""
    return tmp_path / "home" / ".mcgyvr" / "fleets" / "b-small"


def test_a_llamacpp_unit_below_its_class_tolerance_raises_an_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """16.0 is 50.9% under 32.56: past CPU-experts' 48%."""
    from mcgyvr.fleet import alerts

    journal = live_home(tmp_path, monkeypatch)
    report = run_probe(FakeUnits(HOLDING | {"ds_decode": 16.0}))

    assert [(a["unit_id"], a["field"]) for a in report.alerts] == [
        (UNIT_DS, "warm_decode_tok_s")
    ]
    assert report.exit_code == 0
    flagged = [r for r in rows(journal / "fleet") if r.get("alert")]
    assert [(r["unit_id"], r["field"]) for r in flagged] == [
        (UNIT_DS, "warm_decode_tok_s")
    ]
    assert "srv1_deepseek" not in report.off_the_rig
    pulls = alerts.pulled(journal / "fleet", lock_root(tmp_path))
    assert list(pulls.values()) == [
        [{"unit_id": UNIT_DS, "field": "warm_decode_tok_s", "count": 1}]
    ]


def test_a_vllm_unit_timed_off_the_rig_is_recorded_not_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """60.0 is 52.6% under 126.7 and 5000 is 56.5% under 11500, far past vLLM's
    1%. Both are filed with the probe's stamp, and neither alerts or pulls."""
    from mcgyvr.fleet import alerts

    journal = live_home(tmp_path, monkeypatch)
    report = run_probe(FakeUnits(HOLDING | {"3b_decode": 60.0, "3b_prefill": 5000.0}))

    assert report.alerts == []
    assert report.exit_code == 0
    assert report.probed["srv2_3b"] == {
        "warm_decode_tok_s": pytest.approx(60.0),
        "prefill_tok_s": pytest.approx(5000.0),
    }
    three = {r["field"]: r for r in rows(journal / "fleet") if r["unit_id"] == UNIT_3B}
    assert set(three) == {"warm_decode_tok_s", "prefill_tok_s"}
    assert three["warm_decode_tok_s"]["observed"] == pytest.approx(60.0)
    assert three["prefill_tok_s"]["observed"] == pytest.approx(5000.0)
    for row in three.values():
        assert row["fleet"] == "b-small" and row["rig"] == "srv2"
        assert row["rig_id"] == RIG2 and row["combination_id"].startswith("cmb-")
        # 23.0 s of requests: 0.5 + 5 x 256/60 + 3 x 1960/5000.
        assert row["at"] == "2026-09-15T12:00:23"
        assert row["off_the_rig"] is True
        assert "alert" not in row
    assert alerts.pulled(journal / "fleet", lock_root(tmp_path)) == {}

    assert set(report.off_the_rig) == {"srv2_3b"}
    fields, reason = report.off_the_rig["srv2_3b"]
    assert set(fields) == {"warm_decode_tok_s", "prefill_tok_s"}
    assert "off the rig" in reason and "127.0.0.1" in reason


def test_fleet_probe_prints_a_vllm_unit_as_recorded_not_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli
    from mcgyvr.fleet import probe

    live_home(tmp_path, monkeypatch)
    fake = FakeUnits(HOLDING | {"3b_decode": 60.0})
    measured = probe.run

    def faked(**kwargs: Any) -> Any:
        return measured(
            transport=fake, in_flight=idle, clock=fake.clock, now=NOW, **kwargs
        )

    monkeypatch.setattr(probe, "run", faked)
    assert cli.main(["fleet", "probe"]) == 0
    lines = capsys.readouterr().out.splitlines()

    assert "probed srv2_3b: warm_decode_tok_s 60.00, prefill_tok_s 11500.00" in lines
    marked = [line for line in lines if line.startswith("not judged srv2_3b: ")]
    assert len(marked) == 1, lines
    assert "warm_decode_tok_s, prefill_tok_s recorded" in marked[0]
    assert "off the rig" in marked[0] and "127.0.0.1" in marked[0]
    assert not [line for line in lines if line.startswith("not judged srv1_deepseek")]
    assert not [line for line in lines if line.startswith("alert ")]


def test_card_and_restarts_are_named_as_not_read_behind_the_door(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_home(tmp_path, monkeypatch)
    report = run_probe(FakeUnits(HOLDING))
    assert set(report.not_read) == {"srv2_3b", "srv1_deepseek"}
    for fields, reason in report.not_read.values():
        assert set(fields) == {"card_mib", "restarts"}
        assert "door" in reason


def test_a_busy_unit_is_not_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = live_home(tmp_path, monkeypatch)
    fake = FakeUnits(HOLDING)

    def busy_3b(name: str, unit: Mapping[str, Any]) -> int | None:
        return 2 if name == "srv2_3b" else 0

    report = run_probe(fake, in_flight=busy_3b)
    assert report.busy == {"srv2_3b": 2}
    assert not [u for u, _ in fake.posts if u.startswith("http://srv2:8001")]
    assert {r["unit_id"] for r in rows(journal / "fleet")} == {UNIT_DS}
    assert report.exit_code == 0


def test_a_unit_that_took_work_during_the_probe_is_filed_as_contended_not_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = live_home(tmp_path, monkeypatch)
    reads: dict[str, int] = {}

    def later(name: str, unit: Mapping[str, Any]) -> int | None:
        reads[name] = reads.get(name, 0) + 1
        return 1 if name == "srv2_3b" and reads[name] > 1 else 0

    report = run_probe(FakeUnits(HOLDING | {"3b_decode": 60.0}), in_flight=later)
    assert report.contended == ["srv2_3b"]
    assert report.alerts == []
    three = [r for r in rows(journal / "fleet") if r["unit_id"] == UNIT_3B]
    assert three and all(r.get("contended") is True for r in three)
    assert all("alert" not in r for r in three)


def test_a_unit_whose_count_cannot_be_read_is_a_probe_that_could_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_home(tmp_path, monkeypatch)

    def unreadable(name: str, unit: Mapping[str, Any]) -> int | None:
        return None if name == "srv1_deepseek" else 0

    report = run_probe(FakeUnits(HOLDING), in_flight=unreadable)
    assert "srv1_deepseek" in report.failed
    assert report.exit_code == 1


def test_naming_units_probes_only_those(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_home(tmp_path, monkeypatch)
    fake = FakeUnits(HOLDING)
    run_probe(fake, units=["srv1_deepseek"])
    assert {u.split("/")[2] for u, _ in fake.posts} == {"srv1:8080"}


def test_with_no_live_fleet_the_probe_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import probe

    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(probe.ProbeError, match=r"live\.json"):
        run_probe(FakeUnits(HOLDING))


# --- the command line -------------------------------------------------------


def test_fleet_probe_is_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    from mcgyvr import cli

    with pytest.raises(SystemExit) as done:
        cli.main(["fleet", "probe", "--help"])
    assert done.value.code == 0
    assert "UNIT" in capsys.readouterr().out


def test_fleet_alerts_reads_journal_fleet_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli

    journal = live_home(tmp_path, monkeypatch)
    run_probe(FakeUnits(HOLDING | {"ds_decode": 16.0}))
    capsys.readouterr()
    assert cli.main(["fleet", "alerts"]) == 0
    out = capsys.readouterr().out
    assert UNIT_DS in out and "warm_decode_tok_s" in out, out
    assert (journal / "fleet").is_dir()
