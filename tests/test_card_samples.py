"""The card, read while the sweep runs (#348).

Every reading that describes the machine already existed as a declared
constant, and the only production caller was the serving *calibration* runner:
`contract.snapshot` at `run.py:287`, `CARD_STATE_COMMAND` at the ramp's level
reader and at a vLLM claim. So a scored sweep that thermally throttled for an
hour recorded slower `latency_s` and nothing on disk that said why — the run
contract's §3 principle stated in the document and unimplemented in the rig
that ships the numbers.

Two properties carry most of the weight here and neither is about a number.
The first is that **an unread card cannot parse as an empty one**, which is the
distinction `COMPUTE_APPS_PROBE`'s sentinel exists for and which this composes
a second reading on top of. The second is that **the recorder cannot damage the
run it records**: a sampler that could raise, or that pays an ssh timeout per
task forever on a host that has gone away, is worse than no sampler at all.

Live-verified on both rigs 2026-08-23 before these were written — srv1 read
49 C / 14.98 W / 300 MHz / `0x…01` and srv2 42 C / 21.15 W / 210 MHz, both with
`placements: []` on an idle card and `why: null` on all four fields.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent

#: One real reading, as srv1 answered it on 2026-08-23. The throttle mask is
#: `0x…01` — bit 0 is "idle", which is what an unloaded card correctly reports —
#: so this is a value and not a stand-in for one.
LIVE_SRV1 = (
    "49, 14.98, 300, 0x0000000000000001\n"
    "__sweep_card_end__\n"
    "__compute_apps_end__\n"
    "0.00 0.00 0.00 1/252 1165571"
)

#: The same shape with a process on the card, so the placement half is exercised
#: against something other than an empty list.
LIVE_LOADED = (
    "71, 118.40, 1875, 0x0000000000000000\n"
    "__sweep_card_end__\n"
    "1133972, 3126 MiB\n"
    "__compute_apps_end__\n"
    "2.31 1.90 1.44 3/252 1165571"
)


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pin() -> Any:
    return _by_path("serving_pin", REPO / "tools" / "bench" / "serving" / "pin.py")


def test_a_live_reading_answers_every_card_field(pin: Any) -> None:
    reading = pin.sweep_reading(LIVE_SRV1)
    assert reading["card"] == {
        "temperature_c": 49,
        "power_w": 14.98,
        "sm_clock_mhz": 300,
        "throttle_reasons": "0x0000000000000001",
        "why": None,
    }
    assert reading["host_loadavg"] == [0.0, 0.0, 0.0]


def test_a_process_on_the_card_is_read_with_the_card_state(pin: Any) -> None:
    """One ssh, three readings, and the middle one is not lost to the slicing."""
    reading = pin.sweep_reading(LIVE_LOADED)
    assert reading["placements"] == [{"pid": 1133972, "card_mib": 3126}]
    assert reading["card"]["sm_clock_mhz"] == 1875
    assert reading["host_loadavg"] == [2.31, 1.90, 1.44]


def test_an_empty_card_is_not_an_unread_one(pin: Any) -> None:
    """`[]` is a card that answered and holds nothing; `None` is no answer.

    This is the distinction `COMPUTE_APPS_PROBE`'s sentinel exists to preserve,
    and the reason its separator is `&&` and not `;`. Collapsing them is how an
    unreachable host records as a clean card — the most dangerous direction a
    reading of this kind can fail in.
    """
    assert pin.sweep_reading(LIVE_SRV1)["placements"] == []
    assert pin.sweep_reading(None)["placements"] is None
    assert pin.sweep_reading(None)["refused"]


def test_a_card_section_without_its_sentinel_did_not_complete(pin: Any) -> None:
    """And the rest of the reading still parses, because the sections are `;`.

    Without the sentinel `head` would be the WHOLE reading, and handing that to
    the card parser would let a line from another section be read as card state.
    """
    raw = "__compute_apps_end__\n0.10 0.20 0.30 1/1 1"
    reading = pin.sweep_reading(raw)
    assert reading["card"]["temperature_c"] is None
    assert reading["card"]["why"] == pin.SWEEP_PROBE
    assert reading["placements"] == []
    assert reading["host_loadavg"] == [0.10, 0.20, 0.30]

    # The case the guard is actually FOR, and the first version of this check
    # did not construct: a card read that failed leaves the next section's
    # output first on stdout, and if that section ever emits four
    # comma-separated fields it parses as card state. `COMPUTE_APPS_COMMAND` is
    # a shared constant that can grow a column, and on the day it does this
    # would read a pid as a temperature. Not a shape the driver is known to
    # produce today — which is the point: the slicing must not depend on it.
    four = "1133972, 3126 MiB, 0, 0x0\n__compute_apps_end__\n0.1 0.2 0.3 1/1 1"
    assert pin.sweep_reading(four)["card"]["temperature_c"] is None


def test_the_probe_is_composed_from_the_declared_constants(pin: Any) -> None:
    """Not a fourth copy of `nvidia-smi` (#348's own first box).

    A second inline copy of a reading is how two readings come to mean
    different things — `contract.COMPUTE_APPS_COMMAND`'s docstring makes that
    argument about itself, and it applies here.
    """
    assert pin.contract.CARD_STATE_COMMAND in pin.SWEEP_PROBE
    assert pin.contract.COMPUTE_APPS_PROBE in pin.SWEEP_PROBE
    assert "&&" in pin.SWEEP_PROBE, "a section's sentinel is conjoined"
    assert pin.SWEEP_PROBE.count(";") >= 2, "sections are separated, not conjoined"


def test_the_sampler_gives_up_rather_than_paying_a_timeout_per_task(
    pin: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorder must not be able to damage the run it is recording.

    An ssh to a host that has gone away costs its ConnectTimeout — 15 s — every
    time, and over a several-hundred-task sweep that is hours of a measurement
    run spent learning one fact repeatedly.
    """
    monkeypatch.setattr(pin.contract, "ssh", lambda host, command, **_: None)
    sampler = pin.CardSampler("srv1", tmp_path / "card.jsonl", give_up_after=3)
    for n in range(3):
        assert sampler.sample(f"t{n}", "2026-08-23T00:00:00+00:00") is not None
    assert sampler.stopped is not None
    assert sampler.sample("t3", "2026-08-23T00:00:00+00:00") is None

    lines = (tmp_path / "card.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3, "the samples before it gave up stand"
    assert json.loads(lines[-1])["sampling_stopped"]


def test_one_good_reading_resets_the_run_of_failures(
    pin: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three CONSECUTIVE, not three in total — one dropped packet is not a dead
    host, and a counter that never resets turns a blip into a silent stop."""
    answers = [None, None, LIVE_SRV1, None, None]
    monkeypatch.setattr(pin.contract, "ssh", lambda host, command, **_: answers.pop(0))
    sampler = pin.CardSampler("srv1", tmp_path / "card.jsonl", give_up_after=3)
    for n in range(5):
        sampler.sample(f"t{n}", "2026-08-23T00:00:00+00:00")
    assert sampler.stopped is None
    assert sampler.consecutive_failures == 2


def test_the_sampler_never_raises_however_the_read_fails(
    pin: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sampler that could end a sweep would be worse than no sampler."""

    def explode(host: str, command: str, **_: Any) -> None:
        raise OSError("ssh binary is gone")

    monkeypatch.setattr(pin.contract, "ssh", explode)
    sampler = pin.CardSampler("srv1", tmp_path / "card.jsonl")
    row = sampler.sample("t0", "2026-08-23T00:00:00+00:00")
    assert row is not None
    assert "OSError" in row["refused"]


def test_every_sample_is_one_appended_line_carrying_its_own_instant(
    pin: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A time series is only a time series if each point says when it was taken."""
    monkeypatch.setattr(pin.contract, "ssh", lambda host, command, **_: LIVE_SRV1)
    sampler = pin.CardSampler("srv1", tmp_path / "card.jsonl")
    sampler.sample("b001", "2026-08-23T01:00:00+00:00")
    sampler.sample("b002", "2026-08-23T01:04:00+00:00")

    rows = [
        json.loads(line)
        for line in (tmp_path / "card.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["label"] for row in rows] == ["b001", "b002"]
    assert [row["at"] for row in rows] == [
        "2026-08-23T01:00:00+00:00",
        "2026-08-23T01:04:00+00:00",
    ]
    assert all(row["host"] == "srv1" for row in rows)


def test_an_endpoint_with_no_host_gets_no_sampler(tmp_path: Path) -> None:
    """A hosted endpoint has no card to read, and that is ordinary, not degraded."""
    breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")
    assert breadth._card_sampler("http://localhost:11434", tmp_path) is None
    assert breadth._card_sampler("not-a-url", tmp_path) is None
    assert breadth._card_sampler("http://srv1:11434", tmp_path) is not None


def test_the_sweep_samples_once_per_task() -> None:
    """Held against the source: this is the call the whole issue is about.

    A reading taken only at open and close describes a multi-hour sweep at the
    two moments it is least loaded, and anything that begins after open and
    ends before close is invisible while both captures agree.
    """
    source = (REPO / "tools" / "breadth" / "measure.py").read_text(encoding="utf-8")
    assert "sampler = _card_sampler(worker.endpoint, args.out)" in source
    loop = source.split("for task in tasks:")[-1]
    assert "sampler.sample(task.id" in loop.split("rows = measure_task(")[0]


#: Where the name may appear: the writer, the runner that opens it, and this
#: file. Same allow-list shape as the `observed` block's, for the same reason.
NAMES_THE_FILE = {
    "tools/bench/serving/pin.py",
    "tools/breadth/measure.py",
    "tests/test_card_samples.py",
}


def test_nothing_gates_on_the_card(pin: Any) -> None:
    """It is a recording, in the run contract's §3 sense.

    Whether a throttled card should REFUSE a measurement is a real question
    with a different owner, and wiring a guard to a throttle mask would answer
    it by accident. `card.jsonl` is comprehensive because nothing is admitted
    from it — the same argument ADR-0027 D7 makes for the `observed` block.
    """
    found = subprocess.run(
        ["git", "grep", "-l", "card.jsonl", "--", "src/", "tools/", "tests/"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    named = {line for line in found.stdout.splitlines() if line}
    assert named <= NAMES_THE_FILE, (
        f"{sorted(named - NAMES_THE_FILE)} name card.jsonl. Nothing reads the "
        "card samples: a throttled card is a fact about a cell, and turning it "
        "into a refusal of one is a separate decision with a separate owner."
    )
