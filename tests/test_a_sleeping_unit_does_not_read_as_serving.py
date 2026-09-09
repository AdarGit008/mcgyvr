"""A sleeping unit answers ``/v1/models`` with 200, and must still not read as up.

RED. Every test here fails today, and it fails for one reason: the door's health
probe asks a single question — ``GET /v1/models`` — and a sleeping vLLM unit
answers it. ``servelib.models_served`` returns the ids, ``servelib.wait_for``
calls the unit ``healthy: True``, ``serve-up.py`` prints ``up`` and exits 0, and
gate 7 finds every declared container running and calls the run green. The rig is
not serving anything.

**The measurement.** ``records/measurements/vllm-sleep-2026-09-09/README.md``,
section "A sleeping unit passes a health check and then hangs", put three probes
to a vLLM unit slept at level 2:

===========================  ==========================
``GET /v1/models``           **200**
``GET /is_sleeping``         ``{"is_sleeping": true}``
``POST /v1/chat/completions``  **hangs — nothing in 60 s**
===========================  ==========================

So the existing probe is not merely incomplete, it is *wrong*, and it is wrong
silently: a contract dispatched to a rig the door has just declared healthy does
not fail, it hangs until ``budgets.request_timeout_s``. That is the failure this
file exists to prevent, and it is the one the 2026-09-09 handoff ranks as the
precondition for any runtime sleep/wake (``records/plans/handoff.md``, open item
2): until the door can tell a slept rig from a live one, D3's "a wake is a
``serve up`` through the door" (``records/plans/sleep-wake.md`` §5) cannot report
whether the wake worked.

**Why the second probe cannot simply be required.** ``/is_sleeping`` is a vLLM
endpoint and only exists on a unit launched ``--enable-sleep-mode`` with
``VLLM_SERVER_DEV_MODE=1``. Without those flags it is 404 — *and that is how the
live ladder runs*: the handoff's "Live state, as left" records srv2's vLLM pair
serving with sleep mode off, ``/is_sleeping`` 404. llama.cpp, which is the whole
of srv1, has no such endpoint at any launch. So a probe that treated a 404 as an
error, or as an answer of "asleep", would take down every rig in the fleet the
day it landed. **A 404 means "this engine cannot tell me", and a unit that cannot
tell is awake** — which is true, because an engine with no sleep endpoint has no
way to be asleep.

The asymmetry is the point and is pinned below in both directions: only an
explicit ``{"is_sleeping": true}`` may take a unit out of service, and everything
else — 404, a connection that fails, a body that does not parse, a body of the
wrong shape — leaves it in.

**The seam** is ``mcgyvr.serving.servelib.ssh``, the one call in the probe path
that reaches a rig; ``gatelib.ssh`` refuses outright unless it descends from the
door (``src/mcgyvr/serving/gatelib.py:213``), so these tests substitute it and
touch no machine. The polling constants are cut down the same way, because the
real budget is 120 polls at 3.0 s and this file must not spend six minutes
proving that a sleeper is never called healthy.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from mcgyvr.serving import servelib

#: A unit that has loaded its weights, as both engines answer ``/v1/models``.
MODELS = '{"data": [{"id": "qwen2.5-coder-3b"}]}'
#: srv2's 3B after ``POST /sleep {"level": 2}``, 2026-09-09: 0.25 s to this.
ASLEEP = '{"is_sleeping": true}'
#: The same unit after ``POST /wake_up``, 0.24 s later.
AWAKE = '{"is_sleeping": false}'

#: srv1's card, the one the ladder actually runs on: one llama.cpp unit.
UNIT = servelib.Service(name="svc0", container="mcgyvr-srv1-a-8080", port=8080)
HOST = "srv1"


#: The attribute :func:`probe` substitutes, spelled once and away from a comma.
#: ``tests/test_one_door.py`` scans every line of ``tests/`` for something that
#: looks like a spawn, and a bare ``"ssh",`` in an argument list looks exactly
#: like one. Nothing here reaches a machine — that is the point of substituting
#: it — so the name is bound to a constant rather than argued into that file's
#: ALLOWED, which is the list of places that really do touch a rig.
SEAM = "ssh"


def reply(stdout: str = "", *, code: int = 0) -> subprocess.CompletedProcess[str]:
    """One answer from the rig, shaped as :func:`gatelib.ssh` returns them."""
    return subprocess.CompletedProcess(
        args=[SEAM, HOST], returncode=code, stdout=stdout, stderr=""
    )


#: What ``curl -sf`` — the flags the probe uses — gives for a route the engine
#: does not serve: exit 22, nothing on stdout. This is srv2's vLLM pair as the
#: live ladder launches it, and srv1's llama.cpp at every launch there is.
NO_ROUTE = reply(code=22)


class Rig:
    """A rig that answers the probe's two questions from a script, and logs them.

    Each argument is either one answer, given to every ask, or a list of
    answers given in order — which is how a unit that wakes *during* the poll
    is spelled. Anything the probe asks that is not one of the two endpoints is
    an error rather than a default, so a probe that grew a third question would
    be seen here rather than silently answered.
    """

    def __init__(
        self,
        models: subprocess.CompletedProcess[str]
        | list[subprocess.CompletedProcess[str]],
        is_sleeping: subprocess.CompletedProcess[str]
        | list[subprocess.CompletedProcess[str]],
    ) -> None:
        self.models = models
        self.is_sleeping = is_sleeping
        self.asked: list[str] = []

    def _next(
        self,
        scripted: subprocess.CompletedProcess[str]
        | list[subprocess.CompletedProcess[str]],
        which: str,
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(scripted, subprocess.CompletedProcess):
            return scripted
        if not scripted:
            raise AssertionError(f"the probe asked {which} more times than scripted")
        return scripted.pop(0)

    def __call__(
        self, host: str, command: str, timeout: float = 120.0, **_: Any
    ) -> subprocess.CompletedProcess[str]:
        self.asked.append(command)
        if "/is_sleeping" in command:
            return self._next(self.is_sleeping, "/is_sleeping")
        if "/v1/models" in command:
            return self._next(self.models, "/v1/models")
        raise AssertionError(f"the probe asked a rig something else: {command!r}")

    @property
    def sleep_asks(self) -> int:
        return sum(1 for c in self.asked if "/is_sleeping" in c)


@pytest.fixture
def brief(monkeypatch: pytest.MonkeyPatch) -> None:
    """Four polls with no wait between them, in place of six real minutes.

    ``HEALTH_POLLS``/``HEALTH_INTERVAL_S`` are read out of the module on every
    call, and the wake-budget RED file — ``tests/test_a_wake_is_asked_for_in_
    the_config_and_bounded_by_its_own_budget.py`` — reads the same two to derive
    a caller's budget, on the ground that the two numbers must not be able to
    drift apart. So they are cut here rather than lowered in the source.
    """
    monkeypatch.setattr(servelib, "HEALTH_POLLS", 4)
    monkeypatch.setattr(servelib, "HEALTH_INTERVAL_S", 0.0)


def probe(monkeypatch: pytest.MonkeyPatch, rig: Rig) -> dict[str, object]:
    """``wait_for`` against ``rig``, with the one rig-reaching call substituted."""
    monkeypatch.setattr(servelib, SEAM, rig)
    return servelib.wait_for(HOST, UNIT)


# --- the trap ------------------------------------------------------------------


def test_a_unit_that_lists_its_models_while_asleep_does_not_read_as_serving(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """The measured trap, in one assertion: 200 on ``/v1/models``, and asleep.

    This is the whole failure. The unit is up, its process is alive, its CUDA
    context is alive (503 MiB of card for srv2's two sleepers), and it will hang
    on the first real request. ``healthy`` is what ``serve-up.py`` turns into
    exit 0 and gate 7 turns into a green run, so ``healthy`` is what must be
    false.
    """
    rig = Rig(models=reply(MODELS), is_sleeping=reply(ASLEEP))
    row = probe(monkeypatch, rig)

    assert row["healthy"] is False, (
        "a unit that answers /v1/models while /is_sleeping says it is asleep "
        "read as serving. This is the 2026-09-09 trap exactly: the door calls "
        "the rig healthy, gate 7 calls the run green, and the first contract "
        "dispatched to it hangs until budgets.request_timeout_s"
    )


def test_the_row_says_the_unit_was_asleep_rather_than_that_it_never_answered(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """Two different failures must not print as one.

    ``serve-up.json`` is the envelope an operator reads afterwards, and D3's
    first accepted consequence is that every wake leaves one
    (``records/plans/sleep-wake.md`` §5). A unit that never came up wants a
    container log read; a unit that is asleep wants a ``POST /wake_up`` and
    nothing else. A row that spelled both as ``NOT ANSWERING, models=[]`` would
    send the operator to the wrong one — and the sleeper's log is *clean*, which
    is the worst possible thing for it to be.
    """
    rig = Rig(models=reply(MODELS), is_sleeping=reply(ASLEEP))
    row = probe(monkeypatch, rig)

    assert row["sleeping"] is True, (
        "the row does not record that the unit said it was asleep, so the "
        "envelope cannot tell a sleeper from a unit that never started"
    )
    assert row["models"] == ["qwen2.5-coder-3b"], (
        "the row dropped the model list the sleeping unit did in fact return; "
        "the envelope should say what was seen, not less"
    )


# --- the live ladder, which must not break -------------------------------------


def test_a_unit_whose_is_sleeping_is_404_reads_as_serving(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """srv2 as it is launched today: vLLM without ``--enable-sleep-mode``.

    ``records/measurements/vllm-sleep-2026-09-09/README.md``: without the flag
    (and ``VLLM_SERVER_DEV_MODE=1``) ``/sleep``, ``/wake_up`` and
    ``/is_sleeping`` are all 404, "which is how the live ladder runs today". The
    handoff's closing state says the same of srv2 as left. A probe that read
    that 404 as an error, or as an answer, would take the whole fleet out of
    service on the day it landed.
    """
    rig = Rig(models=reply(MODELS), is_sleeping=NO_ROUTE)
    row = probe(monkeypatch, rig)

    assert row["healthy"] is True, (
        "a unit whose /is_sleeping is 404 stopped reading as serving. That is "
        "every unit on the live ladder: a 404 means the engine cannot answer "
        "the question, not that the answer is yes"
    )
    assert row["sleeping"] is None, (
        "an engine that cannot answer was recorded as having answered; None "
        "and False are different readings and the envelope should keep them apart"
    )


def test_a_llamacpp_unit_that_has_no_such_endpoint_at_all_reads_as_serving(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """srv1, and every llama.cpp unit at every launch there will ever be.

    Wire-identical to the flagless vLLM case above and pinned separately anyway,
    because the two are different *reasons*: vLLM's 404 is a flag that could be
    turned on, llama.cpp's is an engine that has no sleep to report. A later fix
    that decided the probe by engine — and the handoff's ruling 4 of 2026-09-08
    is that there is no engine scope — would have to keep both.
    """
    rig = Rig(models=reply(MODELS), is_sleeping=NO_ROUTE)
    row = probe(monkeypatch, rig)

    assert row["healthy"] is True and row["sleeping"] is None


def test_an_engine_that_answers_the_question_with_nonsense_reads_as_serving(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """A 200 that is not an answer is not an answer, and not a refusal either.

    A catch-all route, a proxy's error page, a future engine that spells the
    field differently: none of these say a unit is asleep, and the rule is that
    only ``{"is_sleeping": true}`` takes a unit out of service. The alternative —
    treating an unreadable body as suspicious — makes the probe fail closed on
    every engine nobody has taught it about yet, which on a fleet whose rigs are
    both currently 404 is the same as refusing to serve.
    """
    for body in ("<html>404 page not found</html>", "{}", '{"is_sleeping": "yes"}'):
        rig = Rig(models=reply(MODELS), is_sleeping=reply(body))
        row = probe(monkeypatch, rig)
        assert row["healthy"] is True and row["sleeping"] is None, body


def test_an_awake_vllm_unit_says_so_and_reads_as_serving(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """The case the flag exists for, and the only one that records ``False``.

    ``sleeping: False`` is a positive reading — the engine was asked and said no
    — where ``None`` is "nobody could be asked". Once ``--enable-sleep-mode`` is
    on the live ladder, this is what a healthy row looks like, and the
    difference is how an operator tells a rig that can be slept from one that
    cannot.
    """
    rig = Rig(models=reply(MODELS), is_sleeping=reply(AWAKE))
    row = probe(monkeypatch, rig)

    assert row["healthy"] is True
    assert row["sleeping"] is False


# --- how the probe spends its budget -------------------------------------------


def test_a_unit_woken_while_the_door_is_polling_reads_as_serving(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """Asleep is "not yet", not "no": the poll keeps its budget and waits it out.

    A wake is measured at 0.24-0.82 s for a vLLM unit
    (``records/measurements/vllm-sleep-2026-09-09/README.md``), well inside one
    3.0 s poll interval, so a probe that gave up the first time it saw
    ``is_sleeping: true`` would fail a wake that was about to succeed. The unit
    is asleep for two polls here and awake on the third.
    """
    rig = Rig(
        models=reply(MODELS),
        is_sleeping=[reply(ASLEEP), reply(ASLEEP), reply(AWAKE)],
    )
    row = probe(monkeypatch, rig)

    assert row["healthy"] is True, (
        "a unit that woke during the poll was written off; the sleep reading "
        "must be a reason to keep waiting, the same as a unit still loading"
    )
    assert row["sleeping"] is False


def test_the_sleep_question_is_not_put_to_a_unit_that_is_not_answering_yet(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """One ssh per poll while a unit is still loading, as before this change.

    ``/v1/models`` is the gate: an engine that has not finished reading its
    weights cannot answer either question, and srv1 spends 50-129 s there
    (``servelib`` header, 2026-09-05). Asking twice per poll for two minutes
    buys nothing and doubles the traffic on a rig that is busy loading. The unit
    here answers on the third poll and must have been asked about sleep exactly
    once.
    """
    rig = Rig(
        models=[NO_ROUTE, NO_ROUTE, reply(MODELS)],
        is_sleeping=reply(AWAKE),
    )
    row = probe(monkeypatch, rig)

    assert row["healthy"] is True
    assert rig.sleep_asks == 1, (
        f"the probe asked /is_sleeping {rig.sleep_asks} times for a unit that "
        "answered /v1/models once; a unit that is not answering has nothing to "
        "say about being asleep"
    )


def test_a_unit_that_never_answers_at_all_is_still_the_silent_failure_it_was(
    monkeypatch: pytest.MonkeyPatch, brief: None
) -> None:
    """The pre-existing reading is unchanged: not healthy, and no sleep claimed.

    ``sleeping`` is ``None`` and not ``False`` because nothing was ever asked —
    the same distinction the 404 case draws. Pinned so that a probe which
    defaulted the field to ``False`` could not make a dead unit look like one
    that had been checked and found awake.
    """
    rig = Rig(models=NO_ROUTE, is_sleeping=reply(ASLEEP))
    row = probe(monkeypatch, rig)

    assert row["healthy"] is False
    assert row["models"] == []
    assert row["sleeping"] is None
    assert rig.sleep_asks == 0
