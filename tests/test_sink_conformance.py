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
import importlib.util
import json
import sys
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
    vllm._running_config = lambda *a, **k: None
    vllm._start = lambda *a, **k: dict(STARTED)
    vllm.inventory = lambda *a, **k: [model]
    vllm.weights_sha256 = lambda *a, **k: {
        "weights_sha256": "abc123",
        "digest_seconds": 34.2,
    }
    vllm.contract.ssh = lambda *a, **k: "4916 MiB"
    vllm.contract.first_int = lambda *a, **k: 4916
    result: dict[str, Any] = vllm.claim("srv2", "http://srv2:8000", model, {})
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
    assert row["digest_seconds"] == 34.2, (
        "digest_seconds is DIGEST_TIMEOUT_S's only calibration point and it "
        "must survive to the row for the same reason."
    )


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
    "calibrate.py::_widths::_launch_row": "LAUNCH_ROW_DISPOSITION",
    "calibrate.py::_one_ramp::ramp/ramp": "RAMP_ROW_DISPOSITION",
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
        "literal row: ollama.claim raised; the exception text is carried, the "
        "partial attempt trail the exception may hold is discarded (#326 "
        "owns the refusal's attempt trail)"
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
        "literal refusal row: claim raised; the exception's `reasons` and "
        "text are carried, its attempt trail is not (#326 owns that)"
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
        if name == "emit" and len(node.args) >= 2:
            row = node.args[1]
        elif name == "record" and len(node.args) >= 1:
            row = node.args[0]
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
        'emit(None, {"phase": "p", "metric": "at_module_level"})\n',
        encoding="utf-8",
    )
    assert set(_sinks(hidden)) == {
        "hidden.py::write::p/in_a_method",
        "hidden.py::inner::p/in_a_nested_def",
        "hidden.py::phase::p/via_attribute",
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
    ollama.contract.ssh = lambda *a, **k: "200"
    ollama.contract.drop_page_cache = lambda host: None
    ollama.contract.first_int = lambda *a, **k: ollama.IDLE_BEFORE_LOAD_MIB + 4000
    ollama._resident = lambda host: [{"name": model, "size": 1000, "size_vram": 1000}]
    ollama._digest = lambda base, m: "sha256:abc"
    ollama._server = lambda host: {"instances": [{"pid": 1}]}
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
    assert row["digest_seconds"] == 34.2
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


def _survey_row(
    resident: list[str] | Exception,
) -> tuple[dict[str, Any], _SurveyBackend, dict[str, Any]]:
    runner: Any = _by_path("serving_run_survey_sink", RUN)
    backend = _SurveyBackend(resident)
    ramp = {"saturation": {"n": 4}, "levels": [1], "repeats": 2}
    runner.contract.load_backend = lambda name: backend
    runner.contract.snapshot = lambda host: {}
    runner.contract.ramp = lambda *a, **k: dict(ramp)
    rows: list[dict[str, Any]] = []
    runner._journal = lambda path: rows.append
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
        journal=Path("unused.jsonl"),
    )
    assert len(rows) == 1
    return rows[0], backend, ramp


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


def test_the_survey_sink_records_a_residency_read_that_raised() -> None:
    row, _, _ = _survey_row(RuntimeError("ssh died"))
    assert row["coresidency_after_error"] == "ssh died"
    assert row["coresidency_after"]["resident"] == []
    assert row["outcome"] == "ramp_failed"
