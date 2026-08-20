"""A value that was computed must arrive in the record.

Six defects found on this lane share one shape: **the instrument measured the
right thing and the value did not survive the hand-off to the file.**
``start_seconds`` is computed on every vLLM launch and the return value is never
assigned. ``repeat_spread`` is computed for every ramp and the row builder does
not name it. ``declared_slots`` is readable from ``/props`` and is ``None`` on
every ollama ramp row. The phase duration is printed to a log and not to a
journal. In each case the measurement was taken and then dropped at the sink.

**The guard that existed could not see any of them.** ``launch.py``'s MARKERS
table asserts that a *source file contains a string* — it confirms the
thermometer was installed and cannot notice that nobody wrote the temperature
down. Its entry ``'"repeats": attempts'`` passed on the run that discarded
``repeats``, because ``contract.py`` does produce the field; the row builder two
modules away simply never reads it.

These tests assert the other half of the claim, against the artifact rather than
against the source: for each producer→sink pair, every key the producer returns
is **accounted for** in the row the sink writes — carried, flattened, or
DECLARED dropped with a reason. Adding a field to a producer without deciding
its disposition turns this red, which is the property the MARKERS table cannot
have: it fails on what is *missing* rather than on what is present.

The dispositions live beside the sinks they describe, not here. A test that
carried its own copy of the answer would be a second hand-written field list,
which is the defect.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def calibrate() -> Any:
    return _by_path("serving_calibrate", SERVING / "calibrate.py")


@pytest.fixture(scope="module")
def contract(calibrate: Any) -> Any:
    return calibrate.contract


def _synthetic_level(_base: str, _model: str, n: int) -> dict[str, Any]:
    """A level row shaped like the real one, with no server behind it.

    Patched over ``contract._level`` so :func:`contract.ramp` runs its own body.
    The point is to obtain the producer's key set **from the producer**, never
    from a literal in this file — a hand-copied expectation is the same class of
    defect these tests exist to catch, one file further out.
    """
    return {
        "n": n,
        "wall_s": 1.0,
        "ok": n,
        "counted": n,
        "errors": 0,
        "error_kinds": [],
        "completion_tokens_total": 100 * n,
        "tokens_per_s": 100.0 * n,
        "latency_mean_s": 1.0,
        "latency_max_s": 1.0,
    }


@pytest.fixture
def produced(contract: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What ``contract.ramp`` actually returns, computed by ``contract.ramp``."""
    monkeypatch.setattr(contract, "_level", _synthetic_level, raising=True)
    produced: dict[str, Any] = contract.ramp("http://stub", "stub-model", levels=(1, 2))
    return produced


@pytest.fixture
def written(
    calibrate: Any,
    contract: Any,
    produced: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """The row ``_one_ramp`` writes, given that exact producer output."""
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(contract, "ramp", lambda *a, **k: produced, raising=True)
    monkeypatch.setattr(
        calibrate, "emit", lambda _out, row: rows.append(row), raising=True
    )
    calibrate._one_ramp(
        Path("unused.jsonl"),
        "http://stub",
        "stub-model",
        "stub-host",
        "vllm",
        4,
        475,
        declared={"value": 4, "provenance": "observed"},
    )
    assert len(rows) == 1, "one ramp writes exactly one row"
    return rows[0]


def test_the_sink_declares_a_disposition_for_every_field_the_ramp_produces(
    calibrate: Any, produced: dict[str, Any]
) -> None:
    """The disposition covers the producer's key set exactly.

    Both directions matter and they fail differently. A producer key with no
    entry is the live defect — a field computed and silently dropped. An entry
    for a key the producer no longer returns is a stale declaration, which is
    how a disposition table rots into the prose it replaced.
    """
    disposition = calibrate.RAMP_ROW_DISPOSITION
    undeclared = sorted(set(produced) - set(disposition))
    assert not undeclared, (
        f"contract.ramp() returns {undeclared} and _one_ramp does not say what "
        "becomes of them. Carry the field into the row, or add it to "
        "RAMP_ROW_DISPOSITION as dropped with the reason it is not worth "
        "recording. A field computed and silently discarded is the defect this "
        "test exists for."
    )
    stale = sorted(set(disposition) - set(produced))
    assert not stale, (
        f"RAMP_ROW_DISPOSITION names {stale}, which contract.ramp() no longer "
        "returns. Remove the entry."
    )


def test_every_carried_field_names_a_key_that_is_really_in_the_row(
    calibrate: Any, written: dict[str, Any]
) -> None:
    """A disposition that names a row key must name one that exists.

    This is the half that makes the table an assertion rather than a comment.
    Without it a disposition could claim ``repeat_spread`` is "flattened into
    spread_max" while nothing of the sort is written, and the declaration would
    read as reassurance for as long as nobody checked.
    """
    for field, carried in sorted(calibrate.RAMP_ROW_DISPOSITION.items()):
        if carried is None:
            continue
        missing = sorted(name for name in carried if name not in written)
        assert not missing, (
            f"RAMP_ROW_DISPOSITION says {field!r} reaches the row as {missing}, "
            f"and the row _one_ramp actually wrote has keys "
            f"{sorted(written)}. The declaration and the artifact disagree."
        )


def test_a_dropped_field_states_why(calibrate: Any) -> None:
    """Dropping is allowed; dropping silently is not."""
    reasons = calibrate.RAMP_ROW_DROPPED
    dropped = {
        field
        for field, carried in calibrate.RAMP_ROW_DISPOSITION.items()
        if carried is None
    }
    assert dropped == set(reasons), (
        "every field whose disposition is None must carry a reason in "
        f"RAMP_ROW_DROPPED. Declared dropped: {sorted(dropped)}. "
        f"Reasons given for: {sorted(reasons)}."
    )
    for field, why in sorted(reasons.items()):
        assert why and len(why) > 20, (
            f"{field!r} is dropped with the reason {why!r}, which says nothing "
            "a reader could disagree with. State what is lost and why that is "
            "acceptable."
        )


def test_the_repeat_spread_reaches_the_ramp_row(written: dict[str, Any]) -> None:
    """D6's RAMP_REPEATS answer, specifically.

    Pinned by name rather than left to the disposition table, because this is
    the field the campaign was commissioned to measure. `contract.ramp`'s own
    comment says discarding the losing repeat makes the bias "unrecoverable
    afterwards" — and the ramp journal, where every headline speedup lives, was
    written without it for a whole campaign while a MARKERS entry certified the
    opposite.
    """
    assert "repeat_spread" in written, (
        "the ramp row carries no repeat_spread, so every max_speedup_vs_n1 in "
        "the journal is a point estimate with no error bar and no way to "
        "recover one."
    )


def test_a_ramp_that_raised_is_not_treated_as_done_by_a_plain_resume(
    calibrate: Any, tmp_path: Path
) -> None:
    """A resumed run must be able to tell a failure from a measurement.

    ``key()`` is deliberately the *conditions* and not the result, so that a
    refusal is not paid for twice — that design is right and this test does not
    touch it. But an **exception** is not a refusal. A refusal is an answer
    about this rig at these settings; an exception means nothing was learned and
    the cell is still owed.

    They were treated identically. ``completed()`` dropped failures only under
    ``--retry-failed``, so a plain ``--resume`` — which is what the campaign
    driver runs — counted a cell lost to a transient error as done and skipped
    it forever. Recovering it required knowing to type a flag whose name says
    "failed", for a cell whose console line said nothing at all.
    """
    journal = tmp_path / "ramp.jsonl"
    raised = {
        "phase": "ramp",
        "engine": "vllm",
        "host": "srv1",
        "model": "m",
        "configured_width": 4,
        "tokens": 475,
        "error": "RuntimeError: the server went away mid-ramp",
    }
    refused = {
        "phase": "ramp",
        "engine": "vllm",
        "host": "srv1",
        "model": "m",
        "configured_width": 1,
        "tokens": 475,
        "saturation_n": None,
        "saturation_refused": "a curve that never rises has no saturation point",
    }
    journal.write_text(
        "\n".join(json.dumps(row) for row in (raised, refused)) + "\n",
        encoding="utf-8",
    )

    plain = calibrate.completed(journal)
    assert calibrate.key(raised) not in plain, (
        "a ramp cell that raised is counted as done by a plain --resume, so "
        "the cell is skipped forever and only --retry-failed recovers it."
    )
    assert calibrate.key(refused) in plain, (
        "a refusal IS an answer about this rig at these settings. Re-running it "
        "buys the same refusal, which is what key()'s docstring says and what "
        "--retry-failed exists to override."
    )

    retried = calibrate.completed(journal, retry_failed=True)
    assert calibrate.key(refused) not in retried
    assert calibrate.key(raised) not in retried


CLAIMED = {
    "backend": "vllm",
    "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ",
    "verified": True,
    "checks": {
        "started": {
            "restarted": True,
            "reason": "no server was serving this model",
            "launcher": "pip",
            "command": "vllm serve ...",
            "launched": True,
            "ready": True,
            "start_seconds": 108.7,
            "serve": {"max_model_len": 8192},
        },
        "gpu_used_mib": 4916,
        "allocation_present": True,
        "served_models": ["Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"],
        "engine_config": {"dtype": "half"},
        "weights": {"weights_sha256": "abc123", "digest_seconds": 34.2},
        "weights_sha256_expected": None,
    },
    "declarations_ignored": None,
}


def test_the_launch_sink_declares_a_disposition_for_every_field_claim_returns(
    calibrate: Any,
) -> None:
    """A1's half of the same contract.

    ``vllm.claim``'s return was discarded whole at the call site, so there was
    no sink to conform to. Now there is one, and it is held to the same rule:
    every key the producer returns is carried or declared dropped.
    """
    disposition = calibrate.LAUNCH_ROW_DISPOSITION
    undeclared = sorted(set(CLAIMED) - set(disposition))
    assert not undeclared, (
        f"vllm.claim() returns {undeclared} and _launch_row does not say what "
        "becomes of them."
    )
    stale = sorted(set(disposition) - set(CLAIMED))
    assert not stale, (
        f"LAUNCH_ROW_DISPOSITION names {stale}, which claim() does not return."
    )


def test_the_launch_timing_reaches_the_row(calibrate: Any) -> None:
    """D6's START_TIMEOUT_S evidence, pinned by name.

    ``vllm.claim`` computed this on all ten launches of the 2026-08-19/20
    campaign and the value reached no file, leaving a 900 s timeout resting on
    nothing after the run commissioned to calibrate it.
    """
    row = calibrate._launch_row("srv2", "m", 16, CLAIMED)
    assert row["start_seconds"] == 108.7, (
        "the launch row does not carry start_seconds, so START_TIMEOUT_S stays "
        "uncalibrated no matter how many servers this campaign starts."
    )
    assert row["digest_seconds"] == 34.2, (
        "digest_seconds is DIGEST_TIMEOUT_S's only calibration point and it "
        "must survive to the row for the same reason."
    )


def test_every_carried_launch_field_names_a_key_that_is_really_in_the_row(
    calibrate: Any,
) -> None:
    row = calibrate._launch_row("srv2", "m", 16, CLAIMED)
    for field, carried in sorted(calibrate.LAUNCH_ROW_DISPOSITION.items()):
        if carried is None:
            continue
        missing = sorted(name for name in carried if name not in row)
        assert not missing, (
            f"LAUNCH_ROW_DISPOSITION says {field!r} reaches the row as "
            f"{missing}; the row really written has {sorted(row)}."
        )


def test_the_ollama_ramp_can_state_its_own_slot_count(calibrate: Any) -> None:
    """A4: the ollama arm must not carry a null where /props answers.

    Asserted against the seam rather than the loop, because the loop needs two
    live hosts. The property is that a public seam exists at all: before this,
    the only way to the number was ``describe``, which builds the whole
    ``observed`` block, so the ramp went without and every ollama row read
    ``declared_slots: null``.
    """
    ollama = _by_path("serving_ollama_sink", SERVING / "backends" / "ollama.py")
    assert hasattr(ollama, "slots_now"), (
        "no cheap seam to the declared slot count, so the ramp has no way to "
        "record one without paying for a full capture."
    )
