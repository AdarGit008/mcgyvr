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

import ast
import datetime
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import types
from collections import Counter
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


#: What the level reader's one ssh prints on a rig (#327): the card line as
#: `nvidia-smi --format=csv,noheader,nounits` prints it (srv1, 2026-08-21,
#: with the throttle mask changed to the SW power cap), then `/proc/loadavg`.
CARD_LINE = "71, 180.50, 1695, 0x0000000000000004"
LOAD_LINE = "1.23 0.98 0.77 3/512 40123"
LEVEL_STATE_STDOUT = f"{CARD_LINE}\n{LOAD_LINE}"


class _Rig:
    """A server with nothing behind it, and the per-level reader beside it.

    ``one`` is patched over ``contract._one`` so :func:`contract._level` runs
    its own body -- threads, wall clock, the state read at the end -- and
    ``read`` is the seam ``contract.ramp`` takes. The point is to obtain the
    producer's key set **from the producer**, never from a literal in this
    file: the fixture this replaced was a hand-copied level row, and a field
    added to ``_level`` in a scratch copy passed every test here.

    ``seen`` records how many completions had finished when each read was
    taken, which is how "read at the level's end" is asserted. Each
    completion takes a moment before it lands: a read taken after the
    threads were started but before they were joined then sees none of
    them, which is what makes that mutation visible (it was green without
    the delay, because a stub that returns at once finishes inside
    ``Thread.start``). ``client`` stands in for ``os.getloadavg`` and counts
    its reads, so one driver-side read copied onto every row is visible too.
    ``ssh`` answers as the rig does, and records which host was asked.
    """

    def __init__(self, answer: str | None = LEVEL_STATE_STDOUT) -> None:
        self.answer = answer
        self.completions = 0
        self.seen: list[int] = []
        self.client_reads = 0
        self.hosts: list[str] = []

    def one(
        self, _base: str, _model: str, out: list[dict[str, Any]], lock: Any, *_: Any
    ) -> None:
        time.sleep(0.02)
        with lock:
            self.completions += 1
            out.append({"latency_s": 1.0, "completion_tokens": 100, "prompt_tokens": 8})

    def read(self) -> str | None:
        self.seen.append(self.completions)
        return self.answer

    def client(self) -> list[float]:
        self.client_reads += 1
        return [float(self.client_reads), 0.5, 0.25]

    def ssh(self, host: str, command: str, timeout: float | None = None) -> str | None:
        self.hosts.append(host)
        return self.read() if "temperature.gpu" in command else "1 MiB"


@pytest.fixture
def rig_for_ramp(contract: Any, monkeypatch: pytest.MonkeyPatch) -> _Rig:
    rig = _Rig()
    monkeypatch.setattr(contract, "_one", rig.one, raising=True)
    monkeypatch.setattr(contract, "client_loadavg", rig.client, raising=True)
    return rig


@pytest.fixture
def produced(contract: Any, rig_for_ramp: _Rig) -> dict[str, Any]:
    """What ``contract.ramp`` actually returns, computed by ``contract.ramp``."""
    produced: dict[str, Any] = contract.ramp(
        "http://stub", "stub-model", levels=(1, 2), reader=rig_for_ramp.read
    )
    return produced


@pytest.fixture
def written(
    calibrate: Any,
    contract: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """The row ``_one_ramp`` writes, with ``contract.ramp`` run for real.

    The ramp used to be stubbed here with the ``produced`` fixture's output,
    and a ``_one_ramp`` that forgot to pass ``host`` to the ramp stayed green
    while every level row of a real campaign would have carried a null card.
    Now the one seam below ``ramp`` is ssh, stubbed as the rig, and the rig
    records which host it was asked for.
    """
    rows: list[dict[str, Any]] = []
    rig = _Rig()
    monkeypatch.setattr(contract, "_one", rig.one, raising=True)
    monkeypatch.setattr(contract, "client_loadavg", rig.client, raising=True)
    monkeypatch.setattr(contract, "ssh", rig.ssh, raising=True)
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
    assert set(rig.hosts) == {"stub-host"}, (
        f"the level reader asked {set(rig.hosts)}; _one_ramp was given stub-host"
    )
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


# --- #327: what the card and both machines were doing, on every level ---


def _level_rows(ramp: dict[str, Any]) -> list[dict[str, Any]]:
    """Every level row a ramp result holds: the kept ones and every repeat."""
    return list(ramp["levels"]) + [row for group in ramp["repeats"] for row in group]


CARD_PARSED = {
    "temperature_c": 71,
    "power_w": 180.5,
    "sm_clock_mhz": 1695,
    "throttle_reasons": "0x0000000000000004",
    "why": None,
}


def test_every_level_row_carries_the_card_state_it_ran_under(
    contract: Any, rig_for_ramp: _Rig, produced: dict[str, Any], written: dict[str, Any]
) -> None:
    """Every ``nvidia-smi`` under tools/bench/serving/ asked for ``memory.used``;
    none asked what the silicon was doing. The width-16 gap between the rigs
    (96% against 23% of linear) was attributed to hardware on rows that could
    not tell a slower card from one throttling by its fifth width.

    The read is taken at the level's END -- after its ``n`` requests came
    back -- which is when a throttle shows, and it reaches both the kept row
    and every repeat, in the producer's result and in the row the sink writes.
    """
    for row in _level_rows(produced):
        assert row["card"] == CARD_PARSED, (
            f"level n={row['n']} carries card={row.get('card')!r}; the rig "
            f"answered {CARD_LINE!r}"
        )
    # levels=(1, 2), RAMP_REPEATS=2: the warm-up's one completion is read by
    # nobody; then each recorded level is read once its own requests are in.
    assert rig_for_ramp.seen == [2, 3, 5, 7], (
        f"the reader saw {rig_for_ramp.seen} completions done at each read; "
        "a read taken before the level's requests returned measures the "
        "previous level's card"
    )
    for row in _level_rows(written):
        assert row["card"] == CARD_PARSED, (
            f"the written row's level n={row['n']} lost the card: {row.get('card')!r}"
        )


def test_every_level_row_carries_the_load_of_both_machines(
    produced: dict[str, Any], written: dict[str, Any]
) -> None:
    """``wall_s`` is read off the driver's clock and the tokens come off the
    rig; E14 (launch.py) puts client-side contention at 12-21% and the
    2026-08-18 record measured 1%, and no row carried either machine's load.
    """
    for row in _level_rows(produced) + _level_rows(written):
        ambient = row["ambient"]
        assert ambient["host_loadavg"] == [1.23, 0.98, 0.77], (
            f"level n={row['n']}: host_loadavg={ambient.get('host_loadavg')!r} "
            f"from {LOAD_LINE!r}"
        )
        client = ambient["client_loadavg"]
        assert isinstance(client, list) and len(client) == 3, (
            f"level n={row['n']}: client_loadavg={client!r}; os.getloadavg() "
            "answers three figures on the machine the clock is on"
        )
        assert all(isinstance(figure, float) for figure in client)
        assert ambient["why"] is None
    # One driver-side read PER LEVEL, not one per ramp copied onto every row:
    # the rig's stub counts its reads into the first figure.
    for result in (produced, written):
        firsts = [
            row["ambient"]["client_loadavg"][0]
            for group in result["repeats"]
            for row in group
        ]
        assert firsts == sorted(firsts) and len(set(firsts)) == len(firsts), (
            f"client_loadavg reads {firsts}: every recorded level reads its own"
        )


def test_the_driver_load_is_three_figures_off_os_getloadavg(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And off `os.getloadavg`, which is the half the shape cannot show.

    The rig fixtures stub `client_loadavg` to count reads, so this is the only
    test that runs the real body -- and asserting its SHAPE alone passed on a
    body returning a constant, which is #327's box 2 ("the driver's
    `os.getloadavg()`") going unchecked. The sentinel is asserted first, then
    the shape is read off the machine this actually runs on.
    """
    monkeypatch.setattr(contract.os, "getloadavg", lambda: (1.234, 2.345, 3.456))
    assert contract.client_loadavg() == [1.23, 2.35, 3.46]
    monkeypatch.undo()
    figures = contract.client_loadavg()
    assert isinstance(figures, list) and len(figures) == 3
    assert all(isinstance(figure, float) for figure in figures)
    assert figures == [round(figure, 2) for figure in figures]


def test_a_card_or_ambient_read_that_failed_is_null_with_a_reason(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``snapshot``'s rule (``gpu_idle`` is None when the card did not answer,
    never False) applied per level and per field: a seam returning ``None``
    yields ``null`` plus a ``why`` naming the command -- never ``0``, never an
    absent key. Three ways the read can fail, each leaving what DID answer.
    """
    rig = _Rig(answer=None)
    monkeypatch.setattr(contract, "_one", rig.one, raising=True)
    nothing = contract.ramp("http://stub", "m", levels=(1, 2), reader=rig.read)
    for row in _level_rows(nothing):
        card = row["card"]
        assert set(card) == set(contract.CARD_FIELDS) | {"why"}
        assert all(card[field] is None for field in contract.CARD_FIELDS), card
        assert card["why"] == contract.LEVEL_STATE_COMMAND
        assert 0 not in card.values() and 0.0 not in card.values()
        ambient = row["ambient"]
        assert ambient["host_loadavg"] is None
        assert contract.LEVEL_STATE_COMMAND in ambient["why"]
        assert ambient["client_loadavg"] is not None, (
            "the rig not answering says nothing about the driver's own load"
        )

    # nvidia-smi failed, /proc/loadavg did not: the card is null, the load is
    # not. `nvidia-smi` reports its failures on STDOUT, in prose, and `ssh`
    # returns stdout whatever the exit code; the prose must not be taken for
    # the load line, nor the load line for the card.
    for answer in (
        LOAD_LINE,
        f"No devices were found\n{LOAD_LINE}",
        f"Failed to initialize NVML: Driver/library version mismatch\n\n{LOAD_LINE}",
        f"NVIDIA-SMI has failed because it couldn't communicate with the "
        f"NVIDIA driver. Make sure that the latest NVIDIA driver is installed "
        f"and running.\n{LOAD_LINE}",
    ):
        half = contract.ramp("http://stub", "m", levels=(1,), reader=_Rig(answer).read)
        for row in _level_rows(half):
            assert row["card"]["why"] == contract.LEVEL_STATE_COMMAND, answer
            assert row["card"]["temperature_c"] is None, answer
            assert row["ambient"]["host_loadavg"] == [1.23, 0.98, 0.77], answer
            assert row["ambient"]["why"] is None, answer

    # One field the driver prints as "[N/A]", through the ramp: that field
    # null, the others kept, the why naming the command -- on the row.
    na = contract.ramp(
        "http://stub",
        "m",
        levels=(1,),
        reader=lambda: f"71, [N/A], 1695, 0x0000000000000004\n{LOAD_LINE}",
    )
    for row in _level_rows(na):
        assert row["card"]["power_w"] is None and row["card"]["temperature_c"] == 71
        assert row["card"]["why"] == contract.LEVEL_STATE_COMMAND
        assert 0 not in row["card"].values() and 0.0 not in row["card"].values()

    partial = contract.card_state("71, [N/A], 1695, 0x0000000000000004")
    assert partial["power_w"] is None and partial["temperature_c"] == 71
    assert partial["why"] == contract.CARD_STATE_COMMAND

    # The driver's own read failing is named as its own thing.
    monkeypatch.setattr(contract, "client_loadavg", lambda: None, raising=True)
    no_client = contract.ramp("http://stub", "m", levels=(1,), reader=_Rig().read)
    for row in _level_rows(no_client):
        assert row["ambient"]["client_loadavg"] is None
        assert row["ambient"]["why"] == contract.CLIENT_LOADAVG_COMMAND
        assert row["ambient"]["host_loadavg"] == [1.23, 0.98, 0.77]

    # No host and no reader: nothing is asked -- no ssh, no driver read -- and
    # every row says so with the commands that were not run.
    asked: list[str] = []
    monkeypatch.setattr(contract, "ssh", lambda h, c, timeout=None: asked.append(c))
    hostless = contract.ramp("http://stub", "m", levels=(1,))
    assert asked == []
    for row in _level_rows(hostless):
        assert row["card"]["why"] == contract.LEVEL_STATE_COMMAND
        assert contract.CLIENT_LOADAVG_COMMAND in row["ambient"]["why"]


def test_one_ssh_per_recorded_level_carries_card_and_load_together(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read costs one round trip per recorded level and not one per field:
    the card query and ``/proc/loadavg`` travel in one command. The discarded
    warm-up reads nothing. The reader's docstring states the cost in the terms
    the record measures -- calls times ``ssh_step_seconds`` -- and fixes no
    budget; the next run's record prices it against its own durations.
    """
    commands: list[str] = []

    def ssh(host: str, command: str, timeout: float | None = None) -> str:
        commands.append(command)
        return LEVEL_STATE_STDOUT

    monkeypatch.setattr(contract, "ssh", ssh, raising=True)
    monkeypatch.setattr(contract, "_one", _Rig().one, raising=True)
    reads: list[str] = []
    reader = contract.read_level_state

    def counted(host: str) -> str | None:
        reads.append(host)
        answer: str | None = reader(host)
        return answer

    monkeypatch.setattr(contract, "read_level_state", counted, raising=True)
    levels = (1, 2, 3)
    result = contract.ramp("http://stub", "m", levels, host="rig")
    assert reads == ["rig"] * (len(levels) * contract.RAMP_REPEATS), (
        "every recorded level reads through read_level_state -- the function "
        "whose docstring prices the read -- and nothing else does"
    )
    assert len(commands) == len(levels) * contract.RAMP_REPEATS, (
        f"{len(commands)} ssh calls for {len(levels)} levels x "
        f"{contract.RAMP_REPEATS} repeats; the warm-up must read nothing and "
        "no level may read twice"
    )
    assert set(commands) == {contract.LEVEL_STATE_COMMAND}
    assert contract.CARD_STATE_QUERY in contract.LEVEL_STATE_COMMAND
    assert "/proc/loadavg" in contract.LEVEL_STATE_COMMAND
    for row in _level_rows(result):
        assert row["card"] == CARD_PARSED and row["ambient"]["why"] is None

    doc = reader.__doc__ or ""
    for term in ("RAMP_REPEATS", "ssh_step_seconds", "README.md:20", "README.md:554"):
        assert term in doc, f"the reader's docstring does not price itself by {term}"


def test_the_level_sink_declares_a_disposition_for_every_field_a_level_produces(
    calibrate: Any, contract: Any, rig_for_ramp: _Rig, written: dict[str, Any]
) -> None:
    """The ``emit()`` census (#324) enumerates sinks; a level row is a value
    inside one, so no census reaches it, and the fixture this file used to
    carry was a literal of ``_level``'s shape -- a key added to ``_level`` in
    a scratch copy passed 14 tests. The key set here comes from running
    ``_level`` itself, with the completion stubbed, and the table is held to
    it both ways and to the row really written.
    """
    level = contract._level("http://stub", "m", 2, reader=rig_for_ramp.read)
    name = "LEVEL_ROW_DISPOSITION"
    _disposition_matches_producer(calibrate.LEVEL_ROW_DISPOSITION, set(level), name)
    _dropped_state_why(
        calibrate.LEVEL_ROW_DISPOSITION, calibrate.LEVEL_ROW_DROPPED, name
    )
    rows = _level_rows(written)
    assert rows, "the written ramp row carries no level rows at all"
    for row in rows:
        _carried_are_in_row(calibrate.LEVEL_ROW_DISPOSITION, row, name)


def test_the_order_the_levels_ran_in_reaches_the_ramp_row(
    calibrate: Any, contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The order is a measurement condition -- width 16 at n=24 was the last
    cell of every host's block, with the most load behind it -- and no row
    said so. ``levels`` on the row is sorted; ``levels_run`` is what was
    offered, in the order it was offered, with the order's name and seed.
    Asserted against the row the sink writes, not against a literal.
    """
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(contract, "_one", _Rig().one, raising=True)
    monkeypatch.setattr(contract, "ssh", lambda *a, **k: LEVEL_STATE_STDOUT)
    monkeypatch.setattr(calibrate, "emit", lambda _out, row: rows.append(row))
    for order, seed in (("descending", None), ("shuffled", 7)):
        calibrate._one_ramp(
            Path("unused.jsonl"),
            "http://stub",
            "m",
            "rig",
            "vllm",
            4,
            475,
            order=order,
            seed=seed,
        )
    offered = contract.RAMP_LEVELS
    descending, shuffled = rows
    assert descending["levels_run"] == sorted(offered, reverse=True)
    assert descending["level_order"] == "descending"
    assert descending["level_seed"] is None
    assert shuffled["levels_run"] == list(contract.order_levels(offered, "shuffled", 7))
    assert shuffled["levels_run"] != sorted(offered)
    assert shuffled["level_order"] == "shuffled"
    assert shuffled["level_seed"] == 7
    for row in rows:
        assert [level["n"] for level in row["levels"]] == sorted(offered), (
            "the curve the plateau is read from must be sorted whichever order ran"
        )
        assert [group[0]["n"] for group in row["repeats"]] == sorted(offered)


def test_a_shuffle_without_a_seed_draws_one_and_writes_it(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shuffle nobody can reproduce is not a condition; the seed is drawn by
    ``ramp`` when none is given, so the row can carry it."""
    monkeypatch.setattr(contract, "_one", _Rig().one, raising=True)
    result = contract.ramp(
        "http://stub", "m", levels=(1, 2, 3), reader=_Rig().read, order="shuffled"
    )
    assert isinstance(result["level_seed"], int)
    replay = contract.order_levels((1, 2, 3), "shuffled", result["level_seed"])
    assert list(replay) == result["levels_run"]
    with pytest.raises(ValueError):
        contract.ramp(
            "http://stub", "m", levels=(1,), reader=_Rig().read, order="random"
        )


def test_the_order_flag_reaches_every_ramp_the_phase_runs(
    calibrate: Any,
    contract: Any,
    claimed: dict[str, Any],
    ollama_attempt: dict[str, Any],
    rig: _Host,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``--level-order``/``--level-seed`` travel ``main`` -> ``ramp`` ->
    ``_widths`` / the ollama call -> ``_one_ramp`` -> ``contract.ramp``. A
    kwarg dropped at any of those seams runs every ramp ascending while the
    row says so honestly -- the re-run's condition silently not applied.
    Driven from the command line, through the real ``emit``, to the rows.
    """
    ollama: Any = _by_path("serving_ollama_order", SERVING / "backends" / "ollama.py")
    vllm: Any = _by_path("serving_vllm_order", SERVING / "backends" / "vllm.py")
    for module in (ollama, vllm):
        monkeypatch.setattr(module, "release", lambda host: {"card_idle": True})
    monkeypatch.setattr(ollama, "probe", lambda host: "http://h:11434")
    monkeypatch.setattr(ollama, "inventory", lambda host, base: ["m"])
    monkeypatch.setattr(ollama, "claim", lambda *a, **k: dict(ollama_attempt))
    monkeypatch.setattr(ollama, "slots_now", lambda host: {"value": 2})
    monkeypatch.setattr(vllm, "claim", lambda *a, **k: dict(claimed))
    monkeypatch.setattr(vllm, "declared_slots", lambda serve, host: {"value": 1})
    monkeypatch.setattr(vllm, "serving_config", lambda base: {"refused": "stub"})
    backends = {"ollama": ollama, "vllm": vllm}
    monkeypatch.setattr(contract, "load_backend", lambda n: backends[n])
    monkeypatch.setattr(contract, "_one", _Rig().one, raising=True)
    monkeypatch.setattr(calibrate, "_awq", lambda host, vllm: "m")
    out = tmp_path / "ramp.jsonl"
    assert (
        calibrate.main(
            [
                "--phase",
                "ramp",
                "--hosts",
                "h",
                "--out",
                str(out),
                "--widths",
                "1",
                "--tokens",
                "475",
                "--level-order",
                "shuffled",
                "--level-seed",
                "7",
            ]
        )
        == 0
    )
    ramps = [row for row in _rows(out) if row.get("metric") == "ramp"]
    assert {row["engine"] for row in ramps} == {"ollama", "vllm"}, ramps
    expected = list(contract.order_levels(contract.RAMP_LEVELS, "shuffled", 7))
    for row in ramps:
        assert row["level_order"] == "shuffled", row["engine"]
        assert row["level_seed"] == 7, row["engine"]
        assert row["levels_run"] == expected, row["engine"]
        assert [level["n"] for level in row["levels"]] == sorted(contract.RAMP_LEVELS)


def test_a_ramp_that_raised_keeps_the_order_it_was_running(
    calibrate: Any, contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timeout at high n is D4's expected failure, and a shuffled ramp that
    died there could not be replayed if its seed had been drawn inside the
    ramp and lost with it. The seed is drawn before the ramp; the error row
    carries the sequence, its order and its seed."""
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(calibrate, "emit", lambda _out, row: rows.append(row))

    def dies(*a: Any, **k: Any) -> dict[str, Any]:
        raise TimeoutError("level n=24 ran out of budget")

    monkeypatch.setattr(contract, "ramp", dies)
    calibrate._one_ramp(
        Path("unused.jsonl"),
        "http://stub",
        "m",
        "rig",
        "vllm",
        4,
        475,
        order="shuffled",
    )
    (row,) = rows
    assert "error" in row and row["level_order"] == "shuffled"
    assert isinstance(row["level_seed"], int)
    assert row["levels_run"] == list(
        contract.order_levels(contract.RAMP_LEVELS, "shuffled", row["level_seed"])
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


#: What the digest script prints on the serving host (vllm.py's
#: _DIGEST_SCRIPT, last line), so `weights_sha256` parses its real shape.
DIGEST_OUTPUT = {
    "weights_sha256": "abc123",
    "snapshot": "/home/someone/.cache/huggingface/hub/models--q/snapshots/abc",
    "shards": ["model.safetensors"],
    "tensors": 731,
    "bytes": 1_610_000_000,
    "mtime": 1_755_000_000.0,
}

STARTED = {
    "restarted": True,
    "reason": "no server was serving this model",
    "launcher": "pip",
    "command": "vllm serve ...",
    "launched": True,
    "ready": True,
    # srv2's real figure from 2026-08-19, the number D6 asked for.
    "start_seconds": 108.7,
    "serve": {"max_model_len": 8192},
}


@pytest.fixture(scope="module")
def claimed() -> dict[str, Any]:
    """What ``vllm.claim`` really returns, obtained from ``vllm.claim``.

    **This fixture was a hand-written literal and that was the same defect one
    file out.** A mutation sweep on 2026-08-20 added a field to ``claim``'s
    success branch and every test here still passed, because they were comparing
    the disposition against a copy of the answer rather than against the
    producer. Seven of eight mutations were caught; this was the eighth.

    So the seams are stubbed and the function runs its own body: whatever key
    set ``claim`` builds today is the key set the disposition is held to.
    """
    vllm: Any = _by_path("serving_vllm_sink", SERVING / "backends" / "vllm.py")
    model = "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"
    # None forces the restart branch, which is the branch that has a start time
    # to report -- an already-serving host is not a launch and records none.
    vllm._running_config = lambda *a, **k: {"max_seq_len": 8192, "dtype": "float16"}
    vllm._start = lambda *a, **k: dict(STARTED)
    vllm.inventory = lambda *a, **k: [model]
    vllm.launcher = lambda host: "pip"
    vllm._DIGEST_CACHE.clear()

    def ssh(host: str, command: str, timeout: float | None = None) -> str:
        # #326: `weights_sha256` runs its own body, so its key set is the
        # producer's -- a hand-written dict here was the defect one file out.
        if "MCGYVR_EOF" in command:
            return json.dumps(DIGEST_OUTPUT)
        if "temperature.gpu" in command:
            return CARD_LINE
        return "4916 MiB"

    # The contract module is shared with every other test; patched for the
    # claim and restored, not left behind.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(vllm.contract, "ssh", ssh)
        patch.setattr(vllm.contract, "first_int", lambda *a, **k: 4916)
        result: dict[str, Any] = vllm.claim(
            "srv2",
            "http://srv2:8000",
            model,
            {"max_num_seqs": 8},
            {"weights_sha256": "abc123"},
        )
    assert result.get("verified") is True, "the stubbed claim must reach its ok branch"
    return result


def test_the_launch_sink_declares_a_disposition_for_every_field_claim_returns(
    calibrate: Any, claimed: dict[str, Any]
) -> None:
    """A1's half of the same contract.

    ``vllm.claim``'s return was discarded whole at the call site, so there was
    no sink to conform to. Now there is one, and it is held to the same rule:
    every key the producer returns is carried or declared dropped.
    """
    disposition = calibrate.LAUNCH_ROW_DISPOSITION
    undeclared = sorted(set(claimed) - set(disposition))
    assert not undeclared, (
        f"vllm.claim() returns {undeclared} and _launch_row does not say what "
        "becomes of them."
    )
    stale = sorted(set(disposition) - set(claimed))
    assert not stale, (
        f"LAUNCH_ROW_DISPOSITION names {stale}, which claim() does not return."
    )


def test_the_launch_timing_reaches_the_row(
    calibrate: Any, claimed: dict[str, Any]
) -> None:
    """D6's START_TIMEOUT_S evidence, pinned by name.

    ``vllm.claim`` computed this on all ten launches of the 2026-08-19/20
    campaign and the value reached no file, leaving a 900 s timeout resting on
    nothing after the run commissioned to calibrate it.
    """
    row = calibrate._launch_row("srv2", "m", 16, claimed)
    assert row["start_seconds"] == 108.7, (
        "the launch row does not carry start_seconds, so START_TIMEOUT_S stays "
        "uncalibrated no matter how many servers this campaign starts."
    )
    assert row["digest_seconds"] == claimed["checks"]["weights"]["digest_seconds"], (
        "digest_seconds is DIGEST_TIMEOUT_S's only calibration point and it "
        "must survive to the row for the same reason."
    )


def test_the_card_state_before_launch_reaches_the_launch_row(
    calibrate: Any, claimed: dict[str, Any]
) -> None:
    """#327: ``vllm.claim`` reads the card beside ``gpu_used_mib`` -- the state
    every level of the ramp that follows is measured against -- and it arrives
    on the launch row under ``LAUNCH_ROW_DISPOSITION["checks"]``, so the
    both-direction test over that table holds it there.
    """
    assert claimed["checks"]["card"] == CARD_PARSED, (
        f"claim read the card as {claimed['checks'].get('card')!r} from {CARD_LINE!r}"
    )
    row = calibrate._launch_row("srv2", "m", 16, claimed)
    assert row["card"] == CARD_PARSED, (
        f"the launch row carries card={row.get('card')!r}; the claim read it"
    )
    assert "card" in calibrate.LAUNCH_ROW_DISPOSITION["checks"]

    # The `claimed` fixture forces the restart branch. A server that was
    # already serving the configuration is a launch row too, and it reads
    # the same card -- not a null with no why.
    vllm: Any = _by_path("serving_vllm_serving", SERVING / "backends" / "vllm.py")
    model = "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"
    vllm._running_config = lambda *a, **k: {"model": model, "max_seq_len": 8192}
    vllm._start = lambda *a, **k: pytest.fail("already serving: no restart")
    vllm.inventory = lambda *a, **k: [model]
    vllm._DIGEST_CACHE.clear()

    def ssh(host: str, command: str, timeout: float | None = None) -> str:
        if "MCGYVR_EOF" in command:
            return json.dumps(DIGEST_OUTPUT)
        return CARD_LINE if "temperature.gpu" in command else "4916 MiB"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(vllm.contract, "ssh", ssh)
        serving = vllm.claim("srv2", "http://srv2:8000", model, {}, None)
    assert serving["checks"]["started"]["restarted"] is False
    assert serving["checks"]["card"] == CARD_PARSED


def test_every_carried_launch_field_names_a_key_that_is_really_in_the_row(
    calibrate: Any, claimed: dict[str, Any]
) -> None:
    row = calibrate._launch_row("srv2", "m", 16, claimed)
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


# A5: the three ways a sleep cell used to report a verdict it had not earned.
# Each row below is what `sleep_state` would hold at the moment the verdict is
# computed, with one thing having gone wrong.
UNMEASURED_SLEEP = {
    "the card was never read": {
        "awake_mib": None,
        "asleep_mib": None,
        "sleep_call": {"status": 200},
        "is_sleeping_after": {"is_sleeping": True},
    },
    "the sleep call was refused": {
        "awake_mib": 4916,
        "asleep_mib": 4914,
        "sleep_call": {"status": 404},
        "is_sleeping_after": {"is_sleeping": True},
    },
    "the endpoint went silent": {
        "awake_mib": 11109,
        "asleep_mib": 189,
        "sleep_call": {"status": 200},
        "is_sleeping_after": None,
    },
}


@pytest.mark.parametrize("case", sorted(UNMEASURED_SLEEP))
def test_a_sleep_cell_that_measured_nothing_says_so(calibrate: Any, case: str) -> None:
    """A5: a transient failure must not read as a clean measurement.

    The control arm is where this bit hardest. DE-12 is right that only the
    ``enabled`` arm can fail — a control freeing nothing is the finding — so a
    control whose card read returned ``None`` recorded ``failed: false`` and was
    indistinguishable from the measurement it was there to make.
    """
    assert calibrate._sleep_unmeasured(UNMEASURED_SLEEP[case]) is not None, (
        f"{case}: the row reports a verdict it did not earn."
    )


def test_a_sleep_cell_that_did_measure_is_not_refused(calibrate: Any) -> None:
    """The negative control — otherwise the guard above could just return a string.

    These are srv2's real enabled-arm readings from 2026-08-20: 11,109 MiB down
    to 189, the run that showed the flag works.
    """
    good = {
        "awake_mib": 11109,
        "asleep_mib": 189,
        "sleep_call": {"status": 200},
        "is_sleeping_after": {"is_sleeping": True},
    }
    assert calibrate._sleep_unmeasured(good) is None


def test_an_unmeasured_sleep_cell_is_re_done_by_a_plain_resume(
    calibrate: Any, tmp_path: Path
) -> None:
    """A5 composes with A6: unmeasured is owed, not answered.

    ``_succeeded`` alone was not enough — it already returned False for these
    rows once they carried a marker, but ``completed`` forgave everything except
    under ``--retry-failed``. The pair is what makes an unmeasured cell recover
    on the resume the driver actually runs.
    """
    journal = tmp_path / "sleep.jsonl"
    row = {
        "phase": "sleep",
        "host": "srv1",
        "arm": "control_no_flag",
        "model": "m",
        "error": calibrate._sleep_unmeasured(
            UNMEASURED_SLEEP["the card was never read"]
        ),
    }
    journal.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert calibrate.key(row) not in calibrate.completed(journal)


# --------------------------------------------------------------------------
# #324: the census. ADR-0037 rule 5 -- coverage of rule 4 is mechanical, not
# counted. Everything above holds a sink to its producer; nothing above says
# which sinks exist, so a new `emit()` with a dict producer and no disposition
# shipped green. The census enumerates every write and demands each be either
# DISPOSED (a `*_ROW_DISPOSITION` beside the sink) or EXEMPT with a reason
# that names what is discarded. Modelled on
# tests/test_bench_rounds.py::test_every_figure_tool_is_classified.
# --------------------------------------------------------------------------

CALIBRATE = SERVING / "calibrate.py"
RUN = SERVING / "run.py"

#: The rule SINK_EXEMPT applies, stated once: a sink is DISPOSED when its
#: producer is a dict this repo's code builds (`contract.ramp`, `vllm.claim`,
#: `ollama.claim`, `describe`, `residents`), and EXEMPT -- with a reason naming
#: what is discarded -- when the producer is a scalar, a literal row, or a
#: remote server's document.
SINK_DISPOSED: dict[str, str] = {
    "calibrate.py::load::row": "LOAD_ROW_DISPOSITION",
    # #326: both rows take the serving pins after the builder, so the site
    # is the name the row is held in.
    "calibrate.py::_widths::row": "LAUNCH_ROW_DISPOSITION",
    "calibrate.py::_one_ramp::row": "RAMP_ROW_DISPOSITION",
    # The unmeasured early write and the terminal write are the same row.
    "calibrate.py::sleep_state::row#1": "SLEEP_ROW_DISPOSITION",
    "calibrate.py::sleep_state::row#2": "SLEEP_ROW_DISPOSITION",
    "run.py::run::row": "SURVEY_ROW_DISPOSITION",
}

SINK_EXEMPT: dict[str, str] = {
    "calibrate.py::fast::fast/idle_gpu_mib": (
        "scalar: one integer parsed out of nvidia-smi's csv line by "
        "first_int; the raw line is discarded"
    ),
    "calibrate.py::fast::fast/ssh_step_seconds": (
        "scalar: a wall-clock duration; the shell output of `free -m` and "
        "/proc/loadavg it timed is discarded unread"
    ),
    "calibrate.py::fast::fast/discovery_seconds": (
        "scalar: a wall-clock duration; the HTTP body of /api/tags, /api/ps "
        "or /api/version it timed is discarded unread"
    ),
    "calibrate.py::fast::fast/capture_show_seconds": (
        "scalar: a wall-clock duration and the byte length of /api/show's "
        "body; the body itself (a remote server's document) is discarded"
    ),
    "calibrate.py::fast::fast/array_length": (
        "scalar: the length of one list inside /api/show's body; the list's "
        "contents are discarded"
    ),
    "calibrate.py::load::load/vram_fraction": (
        "a re-emission of one load-row field under its own metric so the "
        "fraction can be read as a series; nothing new is produced or dropped"
    ),
    "calibrate.py::ramp::ramp/refused#1": (
        "literal row: ollama's probe returned None; nothing was produced to dispose of"
    ),
    "calibrate.py::ramp::ramp/refused#2": (
        "literal row: the inventory was empty; the empty list is the whole "
        "of what was produced"
    ),
    "calibrate.py::ramp::ramp/refused#3": (
        "literal row: `_awq` found no checkpoint; the ssh listing (a shell "
        "string, possibly None) is discarded"
    ),
    "calibrate.py::ramp::ramp/error": (
        "literal row: ollama.claim raised in the ramp phase; the exception "
        "text is carried. The attempt trail is the load phase's to record "
        "(its row carries it whole since #326); this row is the ramp's."
    ),
    "calibrate.py::_widths::ramp/error": (
        "literal row: vllm.claim or declared_slots raised; the exception "
        "text is carried and nothing else was produced"
    ),
    "calibrate.py::_widths::ramp/refused": (
        "literal row: the declared slots contradicted the request; the "
        "`declared` dict is carried whole and the ramp never ran"
    ),
    "calibrate.py::_one_ramp::ramp/error": (
        "literal row: contract.ramp raised; the exception text is carried and "
        "no levels were produced"
    ),
    "calibrate.py::sleep_state::sleep/refused": (
        "literal row: no AWQ checkpoint on the host; the ssh listing (a "
        "shell string, possibly None) is discarded"
    ),
    "run.py::run::row_out#1": (
        "literal refusal row: the backend would not yield the card; the "
        "release dict is carried as `yielded` and nothing else was produced"
    ),
    "run.py::run::row_out#2": (
        "literal refusal row: claim raised; the exception's `reasons`, text "
        "and attempt trail (#326) are carried whole under `refusal`"
    ),
    # #325: the phase rows. Scalars off the clock seam; nothing is dropped.
    "calibrate.py::main::?/phase": (
        "scalar: the phase's own span and its length, read off contract.now "
        "at the run's start and end; the phase name is argv's, hence `?`"
    ),
    "run.py::run::span": (
        "scalar: the survey's own span and its length, read off contract.now; "
        "the same dict is set on the document as result['run']"
    ),
}

PHASE_FUNCTIONS = {
    "calibrate.py": {"fast", "load", "ramp", "_widths", "_one_ramp", "sleep_state"},
    "run.py": {"run"},
}


def _row_site(row: ast.expr) -> str:
    """A sink's site label.

    A dict literal is keyed by its `phase`/`metric` constants -- or by the
    name it unpacks, when it is `{..., **row}`. A call is its builder. A name
    is itself.
    """
    if isinstance(row, ast.Dict):
        unpacked = [v for k, v in zip(row.keys, row.values, strict=True) if k is None]
        if unpacked:
            return ast.unparse(unpacked[-1])
        consts: dict[str, str] = {
            str(k.value): (str(v.value) if isinstance(v, ast.Constant) else "?")
            for k, v in zip(row.keys, row.values, strict=True)
            if isinstance(k, ast.Constant)
        }
        metric = consts.get("metric") or (
            "refused" if "refused" in consts else "error" if "error" in consts else "-"
        )
        return f"{consts.get('phase', '?')}/{metric}"
    if isinstance(row, ast.Call):
        return ast.unparse(row.func)
    return ast.unparse(row)


def _sink_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _sinks(path: Path) -> dict[str, tuple[str, int]]:
    """Every `emit(out, row)` and `record(row)` in ``path``: key -> (func, line).

    The key is ``<file>::<function>::<site>``, with ``#n`` appended when the
    same site label occurs more than once in one function. The whole tree is
    walked -- methods, nested functions and module level included -- and a
    call through an attribute (``calibrate.emit``) counts, so a sink cannot
    hide from the census by where it is written. Module-level calls are
    attributed to ``<module>``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    enclosing: dict[ast.AST, str] = {}

    def _label(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = (
                child.name
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                else owner
            )
            enclosing[child] = name
            _label(child, name)

    _label(tree, "<module>")
    found: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _sink_name(node.func)
        # A keyword spelling -- `emit(out=o, row=r)` -- must not be a way to
        # write a row the census does not see.
        keyed_row = next((kw.value for kw in node.keywords if kw.arg == "row"), None)
        if name == "emit" and len(node.args) >= 2:
            row = node.args[1]
        elif name == "record" and len(node.args) >= 1:
            row = node.args[0]
        elif name in ("emit", "record") and keyed_row is not None:
            row = keyed_row
        else:
            continue
        found.append((enclosing[node], _row_site(row), node.lineno))
    counts = Counter((f, s) for f, s, _ in found)
    seen: Counter[tuple[str, str]] = Counter()
    keyed: dict[str, tuple[str, int]] = {}
    for name, site, line in sorted(found, key=lambda t: t[2]):
        label = site
        if counts[(name, site)] > 1:
            seen[(name, site)] += 1
            label = f"{site}#{seen[(name, site)]}"
        keyed[f"{path.name}::{name}::{label}"] = (name, line)
    return keyed


def _unclassified(sinks: dict[str, Any]) -> set[str]:
    return set(sinks) - set(SINK_DISPOSED) - set(SINK_EXEMPT)


@pytest.fixture(scope="module")
def census() -> dict[str, tuple[str, int]]:
    return {**_sinks(CALIBRATE), **_sinks(RUN)}


def test_every_sink_is_classified(
    calibrate: Any, census: dict[str, tuple[str, int]]
) -> None:
    """Every write is DISPOSED or EXEMPT, and both tables point at real things."""
    unclassified = _unclassified(census)
    assert not unclassified, (
        "a sink with neither a disposition nor an exemption. Either add a "
        "*_ROW_DISPOSITION beside it (its producer is a dict this repo builds) "
        "or add it to SINK_EXEMPT with a reason naming what is discarded: "
        f"{sorted(unclassified)}"
    )
    stale = (set(SINK_DISPOSED) | set(SINK_EXEMPT)) - set(census)
    assert not stale, (
        f"the census tables name sinks that no longer exist: {sorted(stale)}"
    )
    runner: Any = _by_path("serving_run_census", RUN)
    for site, table in sorted(SINK_DISPOSED.items()):
        module = runner if site.startswith("run.py") else calibrate
        assert isinstance(getattr(module, table, None), dict), (
            f"{site} claims {table}, which {site.split('::')[0]} does not define"
        )
    for site, why in sorted(SINK_EXEMPT.items()):
        assert len(why) > 20, f"{site}: {why!r} does not say what is discarded"


def test_the_census_finds_a_sink_in_every_phase_function(
    census: dict[str, tuple[str, int]],
) -> None:
    """A census that finds nothing reads red, not vacuously green."""
    for file, wanted in PHASE_FUNCTIONS.items():
        found = {func for key, (func, _) in census.items() if key.startswith(file)}
        missing = wanted - found
        assert not missing, f"{file}: no sink found inside {sorted(missing)}"


def test_nothing_is_both_disposed_and_exempt() -> None:
    both = set(SINK_DISPOSED) & set(SINK_EXEMPT)
    assert not both, sorted(both)


def test_a_sink_added_without_a_disposition_is_refused(tmp_path: Path) -> None:
    """The mutation that shipped green before #324, re-applied on a copy."""
    anchor = (
        "def fast(out: Path, hosts: list[str], repeats: int = 30) -> None:\n"
        '    """Idle readings, step durations, discovery durations, array sizes."""\n'
    )
    source = CALIBRATE.read_text(encoding="utf-8")
    assert anchor in source
    mutated = tmp_path / "calibrate.py"
    mutated.write_text(
        source.replace(
            anchor,
            anchor + '    emit(out, {"phase": "fast", "metric": "undeclared_new_sink", '
            '"value": 1})\n',
        ),
        encoding="utf-8",
    )
    assert _unclassified(_sinks(mutated)) == {
        "calibrate.py::fast::fast/undeclared_new_sink"
    }


def test_a_sink_cannot_hide_from_the_census(tmp_path: Path) -> None:
    """A method, a nested def, an alias through an attribute, module level."""
    hidden = tmp_path / "hidden.py"
    hidden.write_text(
        "class Journal:\n"
        "    def write(self, out, row):\n"
        '        emit(out, {"phase": "p", "metric": "in_a_method"})\n'
        "def phase(out):\n"
        "    def inner():\n"
        '        emit(out, {"phase": "p", "metric": "in_a_nested_def"})\n'
        '    calibrate.emit(out, {"phase": "p", "metric": "via_attribute"})\n'
        '    emit(out=out, row={"phase": "p", "metric": "by_keyword"})\n'
        'emit(None, {"phase": "p", "metric": "at_module_level"})\n',
        encoding="utf-8",
    )
    assert set(_sinks(hidden)) == {
        "hidden.py::write::p/in_a_method",
        "hidden.py::inner::p/in_a_nested_def",
        "hidden.py::phase::p/via_attribute",
        "hidden.py::phase::p/by_keyword",
        "hidden.py::<module>::p/at_module_level",
    }


def _disposition_matches_producer(
    disposition: dict[str, tuple[str, ...] | None], produced: set[str], name: str
) -> None:
    undeclared = sorted(produced - set(disposition))
    assert not undeclared, (
        f"the producer returns {undeclared} and {name} does not say what "
        "becomes of them"
    )
    stale = sorted(set(disposition) - produced)
    assert not stale, f"{name} names {stale}, which the producer no longer returns"


def _carried_are_in_row(
    disposition: dict[str, tuple[str, ...] | None], row: dict[str, Any], name: str
) -> None:
    for field, carried in sorted(disposition.items()):
        if carried is None:
            continue
        missing = sorted(k for k in carried if k not in row)
        assert not missing, (
            f"{name} says {field!r} reaches the row as {missing}; the row really "
            f"written has {sorted(row)}"
        )


def _dropped_state_why(
    disposition: dict[str, tuple[str, ...] | None], reasons: dict[str, str], name: str
) -> None:
    dropped = {f for f, c in disposition.items() if c is None}
    assert dropped == set(reasons), (
        f"{name}: dropped {sorted(dropped)}, reasons for {sorted(reasons)}"
    )
    for field, why in reasons.items():
        assert len(why) > 20, f"{name}: {field!r} dropped with {why!r}"


@pytest.fixture(scope="module")
def ollama_attempt() -> dict[str, Any]:
    """The attempt record ``ollama.claim`` returns on success, from ``claim``.

    Seams stubbed, body run -- the `claimed` fixture's idiom. The key set is
    whatever `claim` builds today.
    """
    ollama: Any = _by_path(
        "serving_ollama_load_sink", SERVING / "backends" / "ollama.py"
    )
    model = "qwen2.5-coder:1.5b"
    ollama.release = lambda host: {"card_idle": True, "card_used_mib": 1}
    ollama._resident = lambda host: [{"name": model, "size": 1000, "size_vram": 1000}]
    ollama._digest = lambda base, m: "sha256:abc"
    ollama._server = lambda host: {"instances": [{"pid": 1}]}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ollama.contract, "ssh", lambda *a, **k: "200")
        patch.setattr(ollama.contract, "drop_page_cache", lambda host: None)
        patch.setattr(
            ollama.contract,
            "first_int",
            lambda *a, **k: ollama.IDLE_BEFORE_LOAD_MIB + 4000,
        )
        claimed: dict[str, Any] = ollama.claim("srv1", "http://srv1:11434", model)
    assert claimed["verified"] is True and len(claimed["attempts"]) == 1
    return claimed


def test_the_load_sink_declares_a_disposition_for_every_field_an_attempt_carries(
    calibrate: Any, ollama_attempt: dict[str, Any]
) -> None:
    """Before #324 the load row kept 3 of the attempt record's 21 keys."""
    attempt = ollama_attempt["attempts"][-1]
    _disposition_matches_producer(
        calibrate.LOAD_ROW_DISPOSITION, set(attempt), "LOAD_ROW_DISPOSITION"
    )
    row = calibrate._load_row("srv1", "m", 0, 1.5, True, None, ollama_attempt)
    _carried_are_in_row(calibrate.LOAD_ROW_DISPOSITION, row, "LOAD_ROW_DISPOSITION")
    _dropped_state_why(
        calibrate.LOAD_ROW_DISPOSITION,
        calibrate.LOAD_ROW_DROPPED,
        "LOAD_ROW_DISPOSITION",
    )
    # D6: does a second attempt ever rescue a first? Only answerable if the
    # ordinal reaches the row.
    assert row["attempt"] == len(ollama_attempt["attempts"]) == 1
    assert row["model_sha256"] == "sha256:abc"
    assert row["card_idle_before_load"] is True


def test_a_failed_load_writes_no_attempt_ordinal(calibrate: Any) -> None:
    row = calibrate._load_row("srv1", "m", 0, 1.5, False, "RefusedError: x", {})
    assert row["attempt"] is None and row["ok"] is False


class _SleepVllm:
    NAME = "vllm"
    PORT = 8000

    def __init__(self, claimed: dict[str, Any]) -> None:
        self.claimed = claimed
        self.launches = 0

    def claim(self, *a: Any, **k: Any) -> dict[str, Any]:
        self.launches += 1
        return dict(self.claimed)

    def release(self, host: str) -> None:
        pass

    def serving_config(self, base: str) -> dict[str, Any]:
        return {"refused": "stub: no /server_info"}

    def resolved_serving(
        self, host: str, base: str, serve: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"serving_resolved_sha256": None, "refused": "stub: no host log"}


class _SleepOllama:
    def release(self, host: str) -> None:
        pass


class _SleepRun:
    """What ``sleep_state`` wrote, and every document its dict producers handed it.

    The endpoint seams (``_post``, ``get_json``) return a fresh dict per call
    and each is remembered, so the set of row keys that hold one of them is
    read off the row by identity -- the producer key set comes from the sink's
    behaviour, not from a literal in this file.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.documents: list[dict[str, Any]] = []
        self.vllm: Any = None

    def document(self, body: dict[str, Any]) -> dict[str, Any]:
        self.documents.append(body)
        return body

    def keys_holding_a_document(self, row: dict[str, Any]) -> set[str]:
        ids = {id(d) for d in self.documents}
        return {k for k, v in row.items() if id(v) in ids}


@pytest.fixture
def sleep_run(
    calibrate: Any, claimed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> _SleepRun:
    """One host, both arms, every seam stubbed."""
    run = _SleepRun()
    cards = iter([11109, 189, 11000] * 4)
    backends = {"vllm": _SleepVllm(claimed), "ollama": _SleepOllama()}
    run.vllm = backends["vllm"]
    monkeypatch.setattr(calibrate.contract, "load_backend", lambda n: backends[n])
    monkeypatch.setattr(
        calibrate.contract,
        "get_json",
        lambda *a, **k: run.document({"is_sleeping": True}),
    )
    monkeypatch.setattr(calibrate, "_awq", lambda host, vllm: "m")
    monkeypatch.setattr(calibrate, "_card_mib", lambda host: next(cards))
    monkeypatch.setattr(
        calibrate,
        "_post",
        lambda *a, **k: run.document({"status": 200, "seconds": 0.1}),
    )
    monkeypatch.setattr(calibrate.time, "sleep", lambda s: None)
    monkeypatch.setattr(calibrate, "emit", lambda _out, row: run.rows.append(row))
    calibrate.sleep_state(Path("unused.jsonl"), ["srv2"])
    assert [r["arm"] for r in run.rows] == ["control_no_flag", "enabled"]
    return run


def test_the_sleep_launch_timing_reaches_the_row(
    calibrate: Any, claimed: dict[str, Any], sleep_run: _SleepRun
) -> None:
    """A1 one function down: `sleep_state` discarded `vllm.claim`'s return, so
    the three sleep-arm launches that came up on 2026-08-19/20 recorded no
    `start_seconds`."""
    row = sleep_run.rows[1]
    assert row["start_seconds"] == 108.7
    assert row["digest_seconds"] == claimed["checks"]["weights"]["digest_seconds"]
    assert row["failed"] is False and row["actually_freed"] is True
    # The claim's keys from the claim; the endpoint documents from where the
    # sink actually put them. Four documents were handed over per arm and
    # each must be on the row under its own key.
    documents = sleep_run.keys_holding_a_document(row)
    assert len(documents) == 4, documents
    _disposition_matches_producer(
        calibrate.SLEEP_ROW_DISPOSITION,
        set(claimed) | documents,
        "SLEEP_ROW_DISPOSITION",
    )
    for each in sleep_run.rows:
        _carried_are_in_row(
            calibrate.SLEEP_ROW_DISPOSITION, each, "SLEEP_ROW_DISPOSITION"
        )
    _dropped_state_why(
        calibrate.SLEEP_ROW_DISPOSITION,
        calibrate.SLEEP_ROW_DROPPED,
        "SLEEP_ROW_DISPOSITION",
    )
    # Carried whole, not summarised: the documents are the evidence.
    assert row["is_sleeping_after"] == {"is_sleeping": True}
    assert row["sleep_call"] == {"status": 200, "seconds": 0.1}


def test_a_finished_sleep_cell_is_recognised_on_resume(
    calibrate: Any, sleep_run: _SleepRun, tmp_path: Path
) -> None:
    """The row the sink writes must be the row the resume check looks for.

    Found in review of #324: merging the claim's fields put `engine` on the
    row, `key()` reads `engine`, and the done-lookup in `sleep_state` built
    its probe without it -- so every finished sleep cell was re-launched on
    `--resume` while refused cells (no claim, no `engine`) were skipped.
    """
    journal = tmp_path / "sleep.jsonl"
    journal.write_text(
        "".join(json.dumps(r) + "\n" for r in sleep_run.rows), encoding="utf-8"
    )
    done = calibrate.completed(journal)
    launched_before = sleep_run.vllm.launches
    calibrate.sleep_state(Path("unused.jsonl"), ["srv2"], done=done)
    assert sleep_run.vllm.launches == launched_before, (
        "a finished sleep cell was relaunched on resume: the key sleep_state "
        "probes with does not match the row it writes"
    )


class _SurveyBackend:
    """A backend whose every producer returns a distinct, findable document."""

    NAME = "alpha"
    PORT = 11434

    def __init__(self, resident: list[str] | Exception) -> None:
        self.resident = resident
        self.returned: dict[str, Any] = {}

    def probe(self, host: str) -> str:
        return f"http://{host}:{self.PORT}"

    def inventory(self, host: str, base: str) -> list[str]:
        return ["m", "n"]

    def readings(self, host: str) -> dict[str, Any]:
        return {}

    def release(self, host: str) -> dict[str, Any]:
        return {"released": True}

    def claim(self, *a: Any, **k: Any) -> dict[str, Any]:
        claimed: dict[str, Any] = {
            "backend": "alpha",
            "verified": True,
            "attempts": [{"attempt": 1}],
        }
        self.returned["claim"] = claimed
        return claimed

    def describe(self, *a: Any, **k: Any) -> dict[str, Any]:
        described: dict[str, Any] = {
            "capture": {"x": 1},
            "declared_slots": {"value": 4, "provenance": "observed"},
        }
        self.returned["describe"] = described
        return described

    def residents(self, host: str) -> list[str]:
        if isinstance(self.resident, Exception):
            raise self.resident
        resident = list(self.resident)
        self.returned["residents"] = resident
        return resident

    def placements(self, host: str) -> list[dict[str, Any]]:
        """#335: where each of those names sits. A distinct document."""
        if isinstance(self.resident, Exception):
            raise self.resident
        placed = [
            {"name": name, "size": 1000, "size_vram": 68, "fraction": 0.068}
            for name in self.resident
        ]
        self.returned["placements"] = placed
        return placed


def _survey_row(
    resident: list[str] | Exception, journal: Path | None = None
) -> tuple[dict[str, Any], _SurveyBackend, dict[str, Any]]:
    """One survey cell's row. With ``journal``, the real sink writes there."""
    runner: Any = _by_path("serving_run_survey_sink", RUN)
    backend = _SurveyBackend(resident)
    ramp = {"saturation": {"n": 4}, "levels": [1], "repeats": 2}
    # Restored on the way out: the contract module is shared, and a seam
    # left patched here reached calibrate's identity read in another test.
    kept = {
        k: getattr(runner.contract, k) for k in ("load_backend", "snapshot", "ramp")
    }
    runner.contract.load_backend = lambda name: backend
    runner.contract.snapshot = lambda host: {}
    runner.contract.ramp = lambda *a, **k: dict(ramp)
    rows: list[dict[str, Any]] = []
    if journal is None:
        runner._journal = lambda path, stamp=None: rows.append
    else:
        real = runner._journal

        def spy(path: Path | None, stamp: dict[str, Any] | None = None) -> Any:
            append = real(path, stamp)

            def both(record: dict[str, Any]) -> None:
                rows.append(record)
                append(record)

            return both

        runner._journal = spy
    runner.run(
        {
            "hosts": ["h"],
            "backends": ["alpha"],
            "models": [
                {
                    "label": "pair",
                    "backend": "alpha",
                    "id": "m",
                    "coresident_with": ["n"],
                    "concurrency": {"measure": True, "expect": 4},
                }
            ],
        },
        journal=journal or Path("unused.jsonl"),
    )
    for k, v in kept.items():
        setattr(runner.contract, k, v)
    cells = [r for r in rows if r.get("metric") != "phase"]
    assert len(cells) == 1 and len(rows) == 2, "one cell row and the phase row"
    return cells[0], backend, ramp


def _at(row: dict[str, Any], dotted: str) -> Any:
    node: Any = row
    for part in dotted.split("."):
        assert isinstance(node, dict) and part in node, (
            f"{dotted}: {part!r} is not in "
            f"{sorted(node) if isinstance(node, dict) else node!r}"
        )
        node = node[part]
    return node


def test_the_survey_sink_carries_each_producer_whole_or_says_what_it_picks() -> None:
    row, backend, ramp = _survey_row(["n"])
    runner: Any = sys.modules["serving_run_survey_sink"]
    disposition = runner.SURVEY_ROW_DISPOSITION
    # Every producer the row was built from is named, and named producers ran.
    produced = set(backend.returned) | {"contract.ramp"}
    assert set(disposition) == produced, (set(disposition), produced)
    # Every named path is really in the row.
    for paths in disposition.values():
        for path in paths:
            _at(row, path)
    # Whole, not picked: the producer's document is the row's, unchanged.
    assert row["claim"] == backend.returned["claim"]
    assert row["description"] == backend.returned["describe"]
    assert row["declared_slots"] == backend.returned["describe"]["declared_slots"]
    assert {
        k: v
        for k, v in row["concurrency"].items()
        if k not in ("expected", "matches_expected")
    } == ramp
    assert row["concurrency"]["matches_expected"] is True
    assert row["coresidency_after"]["resident"] == ["n"]
    assert row["coresidency_after"]["held"] is True and row["outcome"] == "ok"
    # #335: the verdict and the placement it is silent about, side by side —
    # `held` is True for a neighbour sitting 93% on the CPU, which is the whole
    # reason the second field exists.
    assert row["coresidency_after"]["placements"][0]["fraction"] == 0.068


def test_the_survey_sink_records_a_residency_read_that_raised() -> None:
    row, _, _ = _survey_row(RuntimeError("ssh died"))
    assert row["coresidency_after_error"] == "ssh died"
    assert row["coresidency_after"]["resident"] == []
    assert row["outcome"] == "ramp_failed"


# --- #325: a clock on every row, and the tree that ran -----------------------
#
# Every duration the harness recorded was a `time.monotonic()` delta, which
# cannot be placed on a timeline. On the 2026-08-20 campaign 8,185.3 s of the
# 14,404 s ramp phase belonged to no row, and no journal named the commit, a
# config digest or the run's start. These tests hold the stamp to its
# disposition, the spans to every sink and claim attempt, and show the phase's
# remainder to be a sum of named terms rather than a number nobody can account
# for.


def _is_utc_instant(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    when = datetime.datetime.fromisoformat(text)
    return when.utcoffset() == datetime.timedelta(0)


FAKE_STAMP: dict[str, Any] = {
    "commit": "deadbeef",
    "commit_unknown_reason": None,
    "tree_dirty": False,
    "harness_sha256": "0" * 64,
    "config_sha256": None,
    "argv": ["--phase", "ramp"],
    "run_started_at": "2026-08-21T00:00:00.000+00:00",
}


def test_provenance_names_the_tree_that_ran_or_says_why_it_cannot(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`commit` and `tree_dirty` travel together; no git is said, not raised."""

    def git(status: str | None, head: str | None = "abc123\n") -> Any:
        return lambda *args: head if args[0] == "rev-parse" else status

    monkeypatch.setattr(contract, "_git", git(""))
    clean = contract.provenance()
    assert set(clean) == set(contract.PROVENANCE_DISPOSITION), (
        "the stamp's key set is PROVENANCE_DISPOSITION's, both directions"
    )
    assert clean["commit"] == "abc123" and clean["tree_dirty"] is False
    assert clean["commit_unknown_reason"] is None
    assert len(clean["harness_sha256"]) == 64
    assert _is_utc_instant(clean["run_started_at"])

    monkeypatch.setattr(contract, "_git", git(" M tools/bench/serving/run.py\n"))
    assert contract.provenance()["tree_dirty"] is True

    monkeypatch.setattr(contract, "_git", git(None, head=None))
    without = contract.provenance()
    assert without["commit"] is None and without["tree_dirty"] is None
    assert isinstance(without["commit_unknown_reason"], str)
    assert "git" in without["commit_unknown_reason"]
    # Every field is carried: nothing to explain in a DROPPED table.
    for field, keys in contract.PROVENANCE_DISPOSITION.items():
        assert keys == (field,)


def test_the_digests_move_when_a_harness_byte_or_an_underscore_key_is_edited(
    contract: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`config_sha256` is over the bytes read, so a `_`-key edit moves it --
    the 2026-08-20 campaign's `_`-key hand-edit is recorded nowhere -- and
    `harness_sha256` moves on one byte of the harness."""
    monkeypatch.setattr(contract, "_git", lambda *a: None)
    body = b'{"hosts": ["h"]}'
    edited = b'{"hosts": ["h"], "_note": "decided by hand"}'
    assert (
        contract.provenance(body)["config_sha256"] == hashlib.sha256(body).hexdigest()
    )
    assert (
        contract.provenance(body)["config_sha256"]
        != contract.provenance(edited)["config_sha256"]
    )
    assert contract.provenance()["config_sha256"] is None, "calibrate has no config"
    assert contract.provenance(argv=["--phase", "ramp"])["argv"] == ["--phase", "ramp"]

    contract._product()  # loaded from the real tree before REPO is moved
    harness = tmp_path / "tools" / "bench" / "serving"
    harness.mkdir(parents=True)
    (harness / "contract.py").write_bytes(b"RAMP_TOKENS = 475\n")
    (harness / "__pycache__").mkdir()
    (harness / "__pycache__" / "contract.pyc").write_bytes(b"derived")
    monkeypatch.setattr(contract, "REPO", tmp_path)
    before = contract.provenance()["harness_sha256"]
    (harness / "__pycache__" / "contract.pyc").write_bytes(b"re-derived")
    assert contract.provenance()["harness_sha256"] == before, "derived files are out"
    (harness / "contract.py").write_bytes(b"RAMP_TOKENS = 476\n")
    assert contract.provenance()["harness_sha256"] != before


def _git_in(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_tree_dirty_answers_about_the_harness_and_not_about_the_runs_own_output(
    contract: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#334: `tree_dirty` asked `git status` about the whole working tree.

    A run writes its journal into `records/` *while it runs*, so every row of
    every future run would have read `tree_dirty: true` caused by nothing but
    its own output -- a field true on every real run, which states no property
    (ADR-0026 lens 3). The D7 evidence does not show it only because those rows
    predate #325 and carry no provenance block at all.

    Both directions, because a check that cannot be shown to reject is the
    MARKERS table again: the run's own output must not move it, and one byte
    under the declared surface must.
    """
    contract._product()  # loaded from the real tree before REPO is moved
    harness = tmp_path / "tools" / "bench" / "serving"
    harness.mkdir(parents=True)
    (harness / "contract.py").write_bytes(b"RAMP_TOKENS = 475\n")
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / ".gitkeep").write_bytes(b"")
    _git_in(tmp_path, "init", "-q", "-b", "main")
    _git_in(tmp_path, "add", "-A")
    _git_in(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.setattr(contract, "REPO", tmp_path)
    assert contract.provenance()["tree_dirty"] is False, "committed harness is clean"

    # What a run does to its own tree: the journal, then the survey document.
    (tmp_path / "records" / "d7-ramp.jsonl").write_text('{"metric": "ramp"}\n')
    (tmp_path / "survey.out.json").write_text("{}\n")
    clean = contract.provenance()
    assert clean["tree_dirty"] is False, "#334: a run's own output is not the harness"
    unscoped = contract._git("status", "--porcelain", "--untracked-files=all")
    assert unscoped is not None and unscoped.strip(), (
        "the question that shipped would have said true here, which is the defect"
    )

    # One byte under the declared surface, and both halves of the pair move.
    (harness / "contract.py").write_bytes(b"RAMP_TOKENS = 476\n")
    dirty = contract.provenance()
    assert dirty["tree_dirty"] is True
    assert dirty["harness_sha256"] != clean["harness_sha256"], (
        "`tree_dirty` and `harness_sha256` answer about one surface"
    )

    # An untracked file *inside* the surface counts: it is code that ran.
    (harness / "contract.py").write_bytes(b"RAMP_TOKENS = 475\n")
    assert contract.provenance()["tree_dirty"] is False
    (harness / "patch.py").write_bytes(b"# applied by hand on the rig\n")
    assert contract.provenance()["tree_dirty"] is True


def test_the_surface_provenance_declares_is_the_surface_it_reads(
    contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PROVENANCE_SURFACE` is not documentation beside the computation, it is
    the computation's input: a narrowed declaration narrows the pathspec, so
    the two cannot be edited apart. `commit` is absent from the table and its
    `rev-parse` carries no pathspec -- `HEAD` is the repository's."""
    assert set(contract.PROVENANCE_SURFACE) <= set(contract.PROVENANCE_DISPOSITION)
    seen: list[tuple[str, ...]] = []

    def spy(*args: str) -> str | None:
        seen.append(args)
        return "abc123\n" if args[0] == "rev-parse" else ""

    monkeypatch.setattr(contract, "_git", spy)
    monkeypatch.setattr(
        contract,
        "PROVENANCE_SURFACE",
        dict.fromkeys(
            ("tree_dirty", "harness_sha256"), ("tools/bench/serving/contract.py",)
        ),
    )
    narrowed = contract.provenance()
    status = [args for args in seen if args[0] == "status"]
    assert len(status) == 1, seen
    assert status[0][status[0].index("--") + 1 :] == (
        "tools/bench/serving/contract.py",
    ), "the pathspec is the declaration's, verbatim"
    assert [args for args in seen if args[0] == "rev-parse" and "--" not in args], (
        "`commit` is asked unscoped"
    )

    # The digest half reads the same table, so narrowing one field's surface
    # does not leave the other half hashing the wide one.
    product = contract._product()
    assert narrowed["harness_sha256"] == product.digest(
        contract.REPO, ("tools/bench/serving/contract.py",)
    )
    assert narrowed["harness_sha256"] != product.digest(
        contract.REPO, contract.HARNESS_SURFACE
    )


def _span_ordered(row: dict[str, Any]) -> None:
    assert _is_utc_instant(row.get("started_at")), row
    assert _is_utc_instant(row.get("ended_at")), row
    assert row["started_at"] <= row["ended_at"], row


def _stamped(row: dict[str, Any], stamp: dict[str, Any]) -> None:
    for field, keys in sys.modules["serving_contract"].PROVENANCE_DISPOSITION.items():
        for key in keys:
            assert key in row, f"{key} is not on the row"
            assert row[key] == stamp[field]


def _drive_sleep(
    calibrate: Any, claimed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sleep_run`'s seams, with the real `emit` left in place."""
    cards = iter([11109, 189, 11000] * 4)
    backends = {"vllm": _SleepVllm(claimed), "ollama": _SleepOllama()}
    monkeypatch.setattr(calibrate.contract, "load_backend", lambda n: backends[n])
    monkeypatch.setattr(
        calibrate.contract, "get_json", lambda *a, **k: {"is_sleeping": True}
    )
    monkeypatch.setattr(calibrate, "_awq", lambda host, vllm: "m")
    monkeypatch.setattr(calibrate, "_card_mib", lambda host: next(cards))
    monkeypatch.setattr(calibrate, "_post", lambda *a, **k: {"status": 200})
    monkeypatch.setattr(calibrate.time, "sleep", lambda s: None)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_stamp_reaches_the_ramp_launch_sleep_and_survey_rows_and_every_claim_attempt(  # noqa: E501
    calibrate: Any,
    contract: Any,
    claimed: dict[str, Any],
    ollama_attempt: dict[str, Any],
    produced: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Through the real sinks, to real files, read back."""
    monkeypatch.setattr(calibrate, "STAMP", dict(FAKE_STAMP))
    monkeypatch.setattr(contract, "ramp", lambda *a, **k: produced)
    # `identify` reads the card over contract.ssh, which is the door's
    # transport and refuses outside a door run; the identity block is not
    # this test's subject, so the read answers nothing (an unread card).
    monkeypatch.setattr(contract, "ssh", lambda *a, **k: None)
    out = tmp_path / "calibrate.jsonl"
    calibrate._one_ramp(out, "http://s", "m", "h", "vllm", 4, 475, declared={})
    calibrate.emit(out, calibrate._launch_row("h", "m", 4, claimed))
    _drive_sleep(calibrate, claimed, monkeypatch)
    calibrate.sleep_state(out, ["h"])
    rows = _rows(out)
    assert [r.get("metric") for r in rows] == ["ramp", "launch", "sleep", "sleep"]
    for row in rows:
        _stamped(row, FAKE_STAMP)
        _span_ordered(row)
    launch = rows[1]
    assert (
        launch["started_at"]
        == launch["claim_started_at"]
        == claimed["checks"]["started_at"]
    )
    assert (
        launch["ended_at"] == launch["claim_ended_at"] == claimed["checks"]["ended_at"]
    )
    # The sleep arm's unit is wider than its claim, and holds both spans. The
    # stubbed claim's span is the fixture's, so only its carriage is checked.
    assert rows[2]["claim_started_at"] == claimed["checks"]["started_at"]
    assert rows[2]["claim_ended_at"] == claimed["checks"]["ended_at"]

    # The survey: every row the sink writes, including the phase row.
    journal = tmp_path / "survey.jsonl"
    runner: Any = _by_path("serving_run_stamp", RUN)
    monkeypatch.setattr(runner.contract, "provenance", lambda *a, **k: dict(FAKE_STAMP))
    _survey_row(["n"], journal=journal)
    survey = _rows(journal)
    assert len(survey) == 2
    for row in survey:
        _stamped(row, FAKE_STAMP)
        _span_ordered(row)

    # Every claim attempt, from the claim that built it.
    for attempt in ollama_attempt["attempts"]:
        _span_ordered(attempt)
    _span_ordered(claimed["checks"])
    load = calibrate._load_row("h", "m", 0, 1.0, True, None, ollama_attempt)
    assert load["attempt_started_at"] == ollama_attempt["attempts"][-1]["started_at"]


def test_the_phase_duration_is_a_row_with_a_clock_not_a_print(
    calibrate: Any, contract: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One phase row per invocation; a `--resume`d journal holds two."""
    monkeypatch.setattr(contract, "provenance", lambda *a, **k: dict(FAKE_STAMP))
    monkeypatch.setattr(calibrate, "ramp", lambda *a, **k: None)
    out = tmp_path / "ramp.jsonl"
    argv = ["--phase", "ramp", "--out", str(out), "--hosts", "h", "--resume"]
    assert calibrate.main(argv) == 0
    assert calibrate.main(argv) == 0
    rows = _rows(out)
    assert [r["metric"] for r in rows] == ["phase", "phase"]
    for row in rows:
        assert row["phase"] == "ramp"
        _span_ordered(row)
        _stamped(row, FAKE_STAMP)
        assert row["seconds"] == contract.seconds_between(
            row["started_at"], row["ended_at"]
        )
        assert row["started_at"] == FAKE_STAMP["run_started_at"]

    runner: Any = _by_path("serving_run_phase", RUN)
    monkeypatch.setattr(runner.contract, "provenance", lambda *a, **k: dict(FAKE_STAMP))
    journal = tmp_path / "survey.jsonl"
    _survey_row(["n"], journal=journal)
    _survey_row(["n"], journal=journal)
    phases = [r for r in _rows(journal) if r.get("metric") == "phase"]
    assert len(phases) == 2 and all(r["phase"] == "survey" for r in phases)
    # And the document carries the same four, beside the stamp.
    monkeypatch.setattr(
        runner.contract, "load_backend", lambda name: _SurveyBackend([])
    )
    document = runner.run(
        {"hosts": [], "backends": ["alpha"], "models": []}, journal=None
    )
    assert set(document["run"]) == set(FAKE_STAMP) | {
        "metric",
        "started_at",
        "ended_at",
        "seconds",
    }
    assert document["run"]["metric"] == "phase"


def test_a_phase_row_is_not_a_cell_for_resume(calibrate: Any, tmp_path: Path) -> None:
    """ "resuming: N samples" counts cells; the phase row is not one."""
    cell = {
        "phase": "ramp",
        "host": "h",
        "engine": "vllm",
        "model": "m",
        "configured_width": 4,
        "tokens": 475,
        "metric": "ramp",
    }
    span = {"phase": "ramp", "metric": "phase", "started_at": "x", "ended_at": "y"}
    journal = tmp_path / "ramp.jsonl"
    journal.write_text(json.dumps(cell) + "\n" + json.dumps(span) + "\n")
    assert calibrate.completed(journal) == {calibrate.key(cell)}
    assert calibrate.completed(journal, retry_failed=True) == {calibrate.key(cell)}

    runner: Any = _by_path("serving_run_resume_phase", RUN)
    survey = tmp_path / "survey.jsonl"
    survey.write_text(
        json.dumps({"host": "h", "label": "one", "outcome": "ok"})
        + "\n"
        + json.dumps({"phase": "survey", **span})
        + "\n"
        # Belt and braces: a phase row that somehow carried a host and label.
        + json.dumps({"host": "h", "label": "two", **span})
        + "\n"
    )
    assert set(runner.completed(survey)) == {"h\x00one"}


class _FakeClock:
    """Advances only where a seam says it does."""

    def __init__(self, contract: Any) -> None:
        self.t = 1_000_000.0
        self.contract = contract
        self.inside: dict[str, float] = {}

    def now(self) -> str:
        return str(self.contract.stamp(self.t))

    def spend(self, term: str, seconds: float) -> None:
        self.t += seconds
        self.inside[term] = self.inside.get(term, 0.0) + seconds


def test_the_ramp_phase_remainder_is_a_sum_of_named_terms(
    calibrate: Any, contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """phase span - sum(launch + ramp row spans) == the clock spent inside the
    seams that write no row. On 2026-08-20 that remainder was 8,185.3 s and
    no file held its split; here every second of it has a name.

    The seams: `release` (both engines), `ollama.slots_now`,
    `vllm.declared_slots` -- and `ollama.claim` in the ramp phase, which loads
    a model and writes no row (the load phase's claim does; #326/#327 own
    whether the ramp's should).
    """
    clock = _FakeClock(contract)
    monkeypatch.setattr(contract, "now", clock.now)
    monkeypatch.setattr(calibrate, "STAMP", dict(FAKE_STAMP))
    monkeypatch.setattr(calibrate, "WIDTHS", (1, 2))
    monkeypatch.setattr(calibrate, "TOKEN_COUNTS", (475,))

    def ramp(*a: Any, **k: Any) -> dict[str, Any]:
        clock.spend("contract.ramp", 100.0)
        return {
            "levels": [{"n": 1, "wall_s": 40.0}, {"n": 2, "wall_s": 40.0}],
            "repeats": 2,
            "saturation": {"n": 2},
            "readings": {},
        }

    class Vllm:
        NAME, PORT = "vllm", 8000

        def release(self, host: str) -> None:
            clock.spend("release", 7.0)

        def claim(self, *a: Any, **k: Any) -> dict[str, Any]:
            started_at = contract.now()
            clock.spend("vllm.claim", 60.0)
            return {
                "backend": "vllm",
                "verified": True,
                "checks": {"started_at": started_at, "ended_at": contract.now()},
            }

        def declared_slots(self, serve: Any, host: str) -> dict[str, Any]:
            clock.spend("vllm.declared_slots", 9.0)
            return {"value": serve["max_num_seqs"], "provenance": "observed"}

        def serving_config(self, base: str) -> dict[str, Any]:
            return {"refused": "stub"}

        def resolved_serving(
            self, host: str, base: str, serve: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            return {"serving_resolved_sha256": None, "refused": "stub: no host log"}

    class Ollama:
        def probe(self, host: str) -> str:
            return "http://h:11434"

        def inventory(self, host: str, base: str) -> list[str]:
            return ["m"]

        def release(self, host: str) -> None:
            clock.spend("release", 3.0)

        def slots_now(self, host: str) -> dict[str, Any]:
            clock.spend("ollama.slots_now", 5.0)
            return {"value": 2, "provenance": "observed"}

        def claim(self, *a: Any, **k: Any) -> dict[str, Any]:
            clock.spend("ollama.claim", 11.0)
            return {}

    backends: dict[str, Any] = {"vllm": Vllm(), "ollama": Ollama()}
    monkeypatch.setattr(contract, "load_backend", lambda n: backends[n])
    monkeypatch.setattr(contract, "ramp", ramp)
    monkeypatch.setattr(calibrate, "_awq", lambda host, vllm: "m")
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(calibrate, "emit", lambda _out, row: rows.append(row))

    phase_started = contract.now()
    calibrate.ramp(Path("unused.jsonl"), ["h"])
    phase_ended = contract.now()
    phase = contract.seconds_between(phase_started, phase_ended)

    assert [r["metric"] for r in rows] == ["ramp", "launch", "ramp", "launch", "ramp"]
    spans = 0.0
    previous = phase_started
    for row in rows:
        _span_ordered(row)
        assert phase_started <= row["started_at"] and row["ended_at"] <= phase_ended
        assert previous <= row["started_at"], "rows overlap"
        previous = row["ended_at"]
        span = contract.seconds_between(row["started_at"], row["ended_at"])
        spans += span
        if row["metric"] == "ramp":
            assert sum(lv["wall_s"] for lv in row["levels"]) <= span, (
                "both repeats of every level lie inside the ramp row"
            )
            assert span == clock.inside["contract.ramp"] / 3
        else:
            assert span == 60.0
    unattributed = {
        k: v
        for k, v in clock.inside.items()
        if k not in ("contract.ramp", "vllm.claim")
    }
    assert round(phase - spans, 3) == round(sum(unattributed.values()), 3)
    assert set(unattributed) == {
        "release",
        "ollama.slots_now",
        "ollama.claim",
        "vllm.declared_slots",
    }
    # vllm.release at the host's top and in `finally` (DE-9); ollama's per width.
    assert unattributed["release"] == 7.0 * 2 + 3.0 * 2


# --- #326: identity on every row -----------------------------------------------
#
# The campaign's 16 ramp and sleep rows named the machine by `host` alone.
# `weights_sha256`, `serving_semantic_sha256`, `serving_build`, the driver and
# the compute capability were on 0 of 16, the vLLM claim was unpinned and
# discarded, and a refused load left no attempt trail in either sink.

IDENTITY_FIELDS = (
    "gpu_name",
    "gpu_total_mib",
    "driver_version",
    "compute_capability",
    "engine",
    "serving_build",
)

#: The ten row shapes `calibrate.emit` writes, by (phase, metric). Hand-listed
#: until the discovery census child replaces it.
ROW_SHAPES = {
    ("ramp", "ramp"),
    ("ramp", "launch"),
    ("sleep", "sleep"),
    ("fast", "idle_gpu_mib"),
    ("fast", "ssh_step_seconds"),
    ("fast", "discovery_seconds"),
    ("fast", "capture_show_seconds"),
    ("fast", "array_length"),
    ("load", "load_seconds"),
    ("load", "vram_fraction"),
}


class _Host:
    """One stubbed rig: counts every identity read so 'once' is checkable."""

    def __init__(self, answers: bool = True) -> None:
        self.hardware_reads = 0
        self.build_reads: Counter[str] = Counter()
        self.answers = answers

    def ssh(self, host: str, command: str, timeout: float | None = None) -> str | None:
        if "compute_cap" in command:
            self.hardware_reads += 1
            return (
                "NVIDIA GeForce RTX 3090, 24576 MiB, 550.54.15, 8.6"
                if self.answers
                else None
            )
        if "ollama --version" in command:
            self.build_reads["ollama"] += 1
            return "ollama version is 0.32.5" if self.answers else None
        if "vllm --version" in command:
            self.build_reads["vllm"] += 1
            return "0.26.0" if self.answers else None
        return "1 MiB"


@pytest.fixture
def rig(calibrate: Any, contract: Any, monkeypatch: pytest.MonkeyPatch) -> _Host:
    host = _Host()
    monkeypatch.setattr(contract, "ssh", host.ssh)
    monkeypatch.setattr(contract, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(calibrate, "IDENTITY", {})
    monkeypatch.setattr(calibrate, "STAMP", dict(FAKE_STAMP))
    return host


def _drive_every_shape(
    calibrate: Any,
    contract: Any,
    claimed: dict[str, Any],
    ollama_attempt: dict[str, Any],
    produced: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    out: Path,
) -> list[dict[str, Any]]:
    """Every phase, every seam stubbed, the real `emit` writing to ``out``."""
    ollama: Any = _by_path(
        "serving_ollama_identity", SERVING / "backends" / "ollama.py"
    )
    vllm: Any = _by_path("serving_vllm_identity", SERVING / "backends" / "vllm.py")
    for module in (ollama, vllm):
        monkeypatch.setattr(module, "release", lambda host: {"card_idle": True})
    monkeypatch.setattr(ollama, "probe", lambda host: "http://h:11434")
    monkeypatch.setattr(ollama, "inventory", lambda host, base: ["m"])
    monkeypatch.setattr(ollama, "claim", lambda *a, **k: dict(ollama_attempt))
    monkeypatch.setattr(ollama, "slots_now", lambda host: {"value": 2})
    monkeypatch.setattr(vllm, "claim", lambda *a, **k: dict(claimed))
    monkeypatch.setattr(vllm, "declared_slots", lambda serve, host: {"value": 1})
    monkeypatch.setattr(vllm, "serving_config", lambda base: {"refused": "stub"})
    backends = {"ollama": ollama, "vllm": vllm}
    monkeypatch.setattr(contract, "load_backend", lambda n: backends[n])
    monkeypatch.setattr(contract, "ramp", lambda *a, **k: produced)
    monkeypatch.setattr(calibrate, "_show", lambda base, model: {"tensors": [1, 2]})
    monkeypatch.setattr(calibrate, "_awq", lambda host, vllm: "m")
    monkeypatch.setattr(calibrate, "_card_mib", lambda host: 100)
    monkeypatch.setattr(calibrate, "_post", lambda *a, **k: {"status": 200})
    monkeypatch.setattr(calibrate, "WIDTHS", (1,))
    monkeypatch.setattr(calibrate, "TOKEN_COUNTS", (475,))
    monkeypatch.setattr(calibrate.time, "sleep", lambda s: None)
    calibrate.fast(out, ["h"], repeats=1)
    calibrate.load(out, ["h"], repeats=1)
    calibrate.ramp(out, ["h"])
    calibrate.sleep_state(out, ["h"])
    return _rows(out)


def test_every_emitted_row_carries_the_identity_block(
    calibrate: Any,
    contract: Any,
    claimed: dict[str, Any],
    ollama_attempt: dict[str, Any],
    produced: dict[str, Any],
    rig: _Host,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows = _drive_every_shape(
        calibrate,
        contract,
        claimed,
        ollama_attempt,
        produced,
        monkeypatch,
        tmp_path / "all.jsonl",
    )
    shapes = {(r.get("phase"), r.get("metric")) for r in rows}
    assert shapes == ROW_SHAPES, shapes ^ ROW_SHAPES
    for row in rows:
        block = row["identity"]
        assert set(IDENTITY_FIELDS) <= set(block), (row["metric"], sorted(block))
        assert block["gpu_name"] == "NVIDIA GeForce RTX 3090"
        assert block["gpu_total_mib"] == 24576
        assert block["driver_version"] == "550.54.15"
        assert block["compute_capability"] == "8.6"
        if row.get("engine"):
            assert block["engine"] == row["engine"]
            assert (
                block["serving_build"]
                # #358: the vLLM build names its launcher. Two hosts of the same
                # release through different launchers are two instruments, and
                # the version string alone said they were one.
                == {"ollama": "ollama 0.32.5", "vllm": "vllm 0.26.0 via pip"}[
                    row["engine"]
                ]
            )
        else:
            assert block["engine"] is None and block["serving_build"] is None
            assert "serving_build" in row["identity_refusals"]
    # Read once per host; once per (host, engine).
    assert rig.hardware_reads == 1
    assert rig.build_reads == {"ollama": 1, "vllm": 1}


def test_an_identity_field_the_host_did_not_answer_is_null_with_the_command_it_ran(
    calibrate: Any, contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0027 D2: null plus the read, never a blank, never a number from prose."""
    host = _Host(answers=False)
    monkeypatch.setattr(contract, "ssh", host.ssh)
    monkeypatch.setattr(contract, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(calibrate, "IDENTITY", {})
    block = calibrate.identify("h", "ollama")
    identity, refusals = block["identity"], block["identity_refusals"]
    for field in ("gpu_name", "gpu_total_mib", "driver_version", "compute_capability"):
        assert identity[field] is None
        assert refusals[field] == contract.HARDWARE_COMMAND
    assert identity["serving_build"] is None
    assert "ollama --version" in refusals["serving_build"]
    # Bandwidth: refused today with the reason, on every row, answered by none.
    assert identity["memory_bandwidth_gb_s"] is None
    why = refusals["memory_bandwidth_gb_s"]
    assert "step0-gaps.md:202" in why and "ADR-0024:40" in why
    assert "21.8" in why, "the prose figure is named as NOT the value"
    assert "" not in identity.values(), "a blank is not a refusal"


def test_a_vllm_row_names_the_weights_it_ran_on(
    calibrate: Any,
    contract: Any,
    claimed: dict[str, Any],
    ollama_attempt: dict[str, Any],
    produced: dict[str, Any],
    rig: _Host,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows = _drive_every_shape(
        calibrate,
        contract,
        claimed,
        ollama_attempt,
        produced,
        monkeypatch,
        tmp_path / "w.jsonl",
    )
    vllm_rows = [
        r for r in rows if r.get("engine") == "vllm" or r.get("phase") == "sleep"
    ]
    assert len(vllm_rows) == 4, [(r["phase"], r["metric"]) for r in vllm_rows]
    digest = claimed["checks"]["weights"]["weights_sha256"]
    launches = {r["configured_width"]: r for r in vllm_rows if r["metric"] == "launch"}
    for row in vllm_rows:
        assert row["weights_sha256"] == digest
        assert "serving_semantic_sha256" in row
        assert row["serving_semantic_sha256"] or row["serving_semantic_refused"]
        if row["metric"] == "ramp":
            assert (
                row["weights_sha256"]
                == launches[row["configured_width"]]["weights_sha256"]
            )
    ollama_ramp = [
        r for r in rows if r.get("engine") == "ollama" and r["metric"] == "ramp"
    ]
    assert (
        ollama_ramp[0]["model_sha256"] == ollama_attempt["attempts"][-1]["model_sha256"]
    )


def test_the_sleep_row_keeps_the_claim_it_paid_for(
    claimed: dict[str, Any], sleep_run: _SleepRun
) -> None:
    for row in sleep_run.rows:
        assert row["engine"] == "vllm"
        assert row["weights_sha256"] == claimed["checks"]["weights"]["weights_sha256"]
        assert row["start_seconds"] == claimed["checks"]["started"]["start_seconds"]
        assert row["digest_seconds"] == claimed["checks"]["weights"]["digest_seconds"]
        assert (
            row["weights_sha256_expected"]
            == claimed["checks"]["weights_sha256_expected"]
        )


def test_the_calibration_claim_is_pinned_when_the_model_has_a_pin(
    calibrate: Any,
    contract: Any,
    claimed: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    awq = "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"
    pin = calibrate._expected_weights(awq)
    assert pin and pin["weights_sha256"].startswith("047d5b14")
    assert calibrate._expected_weights("nobody/pins-this") is None

    received: list[Any] = []

    class Vllm:
        NAME, PORT = "vllm", 8000

        def claim(
            self,
            host: str,
            base: str,
            model: str,
            serve: Any = None,
            expect: Any = None,
            **k: Any,
        ) -> dict[str, Any]:
            received.append(expect)
            if expect and expect.get("weights_sha256") != "abc123":
                raise contract.NotCleanError("not the pinned weights")
            return dict(claimed)

        def release(self, host: str) -> None:
            pass

        def declared_slots(self, serve: Any, host: str) -> dict[str, Any]:
            return {"value": 1}

        def serving_config(self, base: str) -> dict[str, Any]:
            return {"refused": "stub"}

        def resolved_serving(
            self, host: str, base: str, serve: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            return {"serving_resolved_sha256": None, "refused": "stub: no host log"}

    class Ollama:
        def release(self, host: str) -> None:
            pass

    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(calibrate, "emit", lambda _o, row: rows.append(row))
    monkeypatch.setattr(contract, "ramp", lambda *a, **k: {"levels": []})
    monkeypatch.setattr(calibrate, "WIDTHS", (1,))
    monkeypatch.setattr(calibrate, "TOKEN_COUNTS", (475,))
    # The pinned model: the stub receives the pin, mismatches, refuses; the
    # refusal row says what it was judged against.
    calibrate._widths(Path("unused"), awq, "h", Vllm(), Ollama(), set())
    assert received == [{"weights_sha256": pin["weights_sha256"]}]
    assert (
        rows[-1]["error"]
        and rows[-1]["weights_sha256_expected"] == pin["weights_sha256"]
    )
    # An unpinned model: None is passed and the row records null.
    rows.clear()
    calibrate._widths(Path("unused"), "nobody/pins-this", "h", Vllm(), Ollama(), set())
    assert received[-1] is None
    assert (
        rows[0]["metric"] == "launch"
        and rows[0]["weights_sha256_expected"]
        == claimed["checks"]["weights_sha256_expected"]
    )
    # The sleep arm passes it too.
    monkeypatch.setattr(
        contract, "load_backend", lambda n: {"vllm": Vllm(), "ollama": Ollama()}[n]
    )
    monkeypatch.setattr(calibrate, "_awq", lambda host, vllm: awq)
    monkeypatch.setattr(calibrate, "_card_mib", lambda host: 100)
    rows.clear()
    calibrate.sleep_state(Path("unused"), ["h"])
    assert received[-1] == {"weights_sha256": pin["weights_sha256"]}
    assert all(
        r["refused"] and r["weights_sha256_expected"] == pin["weights_sha256"]
        for r in rows
    )


def test_every_nested_key_of_checks_has_a_disposition(
    calibrate: Any, claimed: dict[str, Any]
) -> None:
    """`checks` and `checks.weights` are dicts; their keys are disposed too."""
    checks = claimed["checks"]
    _disposition_matches_producer(
        calibrate.LAUNCH_CHECKS_DISPOSITION, set(checks), "LAUNCH_CHECKS_DISPOSITION"
    )
    _dropped_state_why(
        calibrate.LAUNCH_CHECKS_DISPOSITION,
        calibrate.LAUNCH_CHECKS_DROPPED,
        "LAUNCH_CHECKS_DISPOSITION",
    )
    weights = checks["weights"]
    # The producer's real key set: `weights_sha256` ran its own body over the
    # digest script's output. `error` is the failure path's key.
    assert set(weights) >= {
        "weights_sha256",
        "snapshot",
        "shards",
        "tensors",
        "bytes",
        "mtime",
        "digest_seconds",
        "method",
    }
    _disposition_matches_producer(
        calibrate.LAUNCH_WEIGHTS_DISPOSITION,
        set(weights) | {"error"},
        "LAUNCH_WEIGHTS_DISPOSITION",
    )
    _dropped_state_why(
        calibrate.LAUNCH_WEIGHTS_DISPOSITION,
        calibrate.LAUNCH_WEIGHTS_DROPPED,
        "LAUNCH_WEIGHTS_DISPOSITION",
    )
    row = calibrate._launch_row("h", "m", 1, claimed)
    _carried_are_in_row(
        calibrate.LAUNCH_CHECKS_DISPOSITION, row, "LAUNCH_CHECKS_DISPOSITION"
    )
    _carried_are_in_row(
        calibrate.LAUNCH_WEIGHTS_DISPOSITION, row, "LAUNCH_WEIGHTS_DISPOSITION"
    )
    # And the flat `checks` tuple on LAUNCH_ROW_DISPOSITION is the union.
    carried = {
        k
        for table in (
            calibrate.LAUNCH_CHECKS_DISPOSITION,
            calibrate.LAUNCH_WEIGHTS_DISPOSITION,
        )
        for keys in table.values()
        if keys
        for k in keys
    }
    assert set(calibrate.LAUNCH_ROW_DISPOSITION["checks"]) == carried
    assert row["engine_config"] == checks["engine_config"]


def test_the_digest_duration_arrives_with_the_bytes_it_hashed(
    calibrate: Any, claimed: dict[str, Any]
) -> None:
    row = calibrate._launch_row("h", "m", 1, claimed)
    weights = claimed["checks"]["weights"]
    assert row["digest_bytes"] == weights["bytes"] == DIGEST_OUTPUT["bytes"]
    assert row["digest_tensors"] == weights["tensors"]
    assert row["digest_seconds"] == weights["digest_seconds"]
    assert row["digest_error"] is None


def test_a_digest_that_ran_out_of_time_is_a_recorded_point_not_a_blank(
    calibrate: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    vllm: Any = _by_path(
        "serving_vllm_digest_timeout", SERVING / "backends" / "vllm.py"
    )
    vllm._DIGEST_CACHE.clear()
    ticks = iter([0.0, vllm.DIGEST_TIMEOUT_S + 0.5])
    monkeypatch.setattr(vllm.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(vllm, "launcher", lambda host: "pip")
    monkeypatch.setattr(vllm.contract, "ssh", lambda *a, **k: None)
    result = vllm.weights_sha256("h", "m")
    assert "DIGEST_TIMEOUT_S" in result["error"] and "1800" in result["error"]
    assert result["digest_seconds"] >= vllm.DIGEST_TIMEOUT_S
    assert ("h", "m") not in vllm._DIGEST_CACHE, "a failure is never cached"
    row = calibrate._launch_row(
        "h", "m", 1, {"backend": "vllm", "checks": {"weights": result}}
    )
    assert row["digest_error"] == result["error"]
    assert row["digest_seconds"] == result["digest_seconds"]
    # The other failure is still told apart from a timeout.
    ticks = iter([0.0, 3.0])
    monkeypatch.setattr(vllm.time, "monotonic", lambda: next(ticks))
    quick = vllm.weights_sha256("h", "m")
    assert "DIGEST_TIMEOUT_S" not in quick["error"]
