"""A load runs at most thirty seconds, then gives its verdict.

Owner ruling NB5, 2026-09-15: "measure pace for 30 seconds then verdict - if
breaks in longer contexts we will know from logs - no 900s no 3600s". It holds
for every load, 8x4096 included.

* **Each request still asks to fill the whole window**: its prompt fills N - 64
  tokens and it generates the rest.
* **The load runs at most 30 s from when its requests start**, and ends sooner
  when they all finish sooner. At 30 s every unfinished request's connection is
  closed, the unit's status page is read once more, and ``idle_after`` files
  whether it shows nothing in flight.
* **While it runs**, the card is sampled every 0.5 s as before, and PACE, the
  prompt tokens per second over the load, is taken from the unit's own counter
  read at the start and at the end. vLLM's is ``vllm:prompt_tokens_total`` on
  ``/metrics``. A llama.cpp unit publishes no counter it can be taken from, so
  its pace is null with the reason, never a client-side guess.
* **No fixed timeout holds a load.** The load's requests carry no 900 s and its
  model list and tokenize calls no 10 s; the 30 s is the only limit. The probes
  keep theirs.
* **The verdict is the card peak, judged against ``room_mib`` as before.** Pace
  and completion counts are filed, not judged. A load cut at the limit with
  requests unfinished is judged; only an error other than that close, or no
  sample of the container, leaves a load unjudged.
* **The row** keeps every field, plus ``limit_s``, ``pace_prompt_tok_s``,
  ``pace_source``, ``completed``, ``closed_unfinished`` and ``idle_after``.

Owner ruling NBc, 2026-09-15: after the close, the load keeps reading the unit's
own status page until it reads idle, with no time limit on that wait. It files
``idle_after_close``, whether the first reading right after the close was
already idle (true when nothing was left to close), and ``idle_after_s``, the
seconds from the close (or the finish) to the first idle reading; ``idle_after``
stays the final reading. A status page that cannot be read at all is filed as
``idle_error`` and ends the wait.

Owner ruling, 2026-09-15: "Sample the card until idle". Closing a request at
30 s did not stop llama.cpp b10644: ``rig-id-relock``'s srv1-01 read idle 104.3 s
after the close, and all 58 of its card samples were taken before it. So after
the close the card is sampled beside every status reading, up to and including
the first idle one. ``samples`` holds every sample, ``samples_before_close`` is
how many came before the close, and ``sampled_until_idle`` says whether they run
through to an idle reading; an unreadable status page still ends the wait, short
of idle. The verdict is the peak over every sample, and the peak of the samples
before the close is filed beside it as ``peak_before_close_mib``.

So nothing outside the load holds it either (R1, under NB5 and NBc): the door's
ssh that runs a load's harness on the rig carries no timeout, while a probe's
keeps ``PROBE_TIMEOUT_S`` and the rig reading keeps ``READ_TIMEOUT_S``.

The clock, the sleep, the requests, the pages and the poll are fakes: nothing
sleeps and no rig is reached.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest

from tests.test_a_read_measures_before_it_judges_and_loads_a_unit import (
    Rig,
    _load_rows,
    rig_text,
)
from tests.test_a_rig_is_read_through_the_door_without_leasing_it import (
    C_3B,
    C_7B,
    RUN_ID,
    go_live,
    metrics,
)

COUNTER = "vllm:prompt_tokens_total"
WIDTH, WINDOW = 8, 4096


def counter_page(total: float, running: int = 0) -> str:
    return (
        f"# HELP {COUNTER} Number of prefill tokens processed.\n"
        f"# TYPE {COUNTER} counter\n"
        f'{COUNTER}{{engine="0",model_name="m"}} {total}\n' + metrics(running)
    )


class Clock:
    """A clock only the load's own sleep moves."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Batch:
    """W requests that finish together after ``finish_after`` seconds, or never."""

    def __init__(
        self, clock: Clock, width: int, finish_after: float | None, failing: int
    ) -> None:
        self.clock = clock
        self.width = width
        self.finish_after = finish_after
        self.failing = failing
        self.started = clock()
        self.closed_after: float | None = None

    def done(self) -> bool:
        if self.closed_after is not None:
            return True
        return (
            self.finish_after is not None
            and self.clock() - self.started >= self.finish_after
        )

    def completed(self) -> int:
        finished = self.finish_after is not None and self.closed_after is None
        return self.width - self.failing if finished and self.done() else 0

    def errors(self) -> list[str]:
        return ["ConnectionResetError: reset by peer"] * self.failing

    def close(self) -> int:
        self.closed_after = self.clock() - self.started
        return self.width


class Starter:
    def __init__(
        self, clock: Clock, finish_after: float | None = None, failing: int = 0
    ) -> None:
        self.clock = clock
        self.finish_after = finish_after
        self.failing = failing
        self.url = ""
        self.payloads: list[Mapping[str, Any]] = []
        self.batch: Batch | None = None

    def __call__(self, url: str, payloads: Sequence[Mapping[str, Any]]) -> Batch:
        self.url = url
        self.payloads = list(payloads)
        self.batch = Batch(self.clock, len(payloads), self.finish_after, self.failing)
        return self.batch


class Unit:
    """The unit's JSON face: its model list, and a tokenizer that counts words."""

    def __init__(self) -> None:
        self.timeouts: list[tuple[str, float | None]] = []

    def get(self, url: str, timeout: float | None) -> Any:
        self.timeouts.append((url, timeout))
        return {"data": [{"id": "m"}]}

    def post(self, url: str, payload: dict[str, Any], timeout: float | None) -> Any:
        self.timeouts.append((url, timeout))
        text = str(payload.get("prompt") or payload.get("content") or "")
        if url.endswith("/tokenize"):
            words = len(text.split())
            return {"count": words, "tokens": list(range(words))}
        raise AssertionError(f"a load's requests go through its batch, not {url}")


class Pages:
    """The counter page at the start and the end, then the status readings after.

    ``statuses`` is what the status page shows in flight at each reading after
    the load, in order; ``None`` is a page that cannot be read. Asked for a page
    past the last one, it fails the test: a wait that should have stopped did not.
    """

    def __init__(
        self, start: float, end: float, statuses: Sequence[int | None] = (0,)
    ) -> None:
        self.pages: list[str | None] = [counter_page(start), counter_page(end)]
        self.pages += [None if n is None else metrics(n) for n in statuses]
        self.urls: list[str] = []

    def __call__(self, url: str) -> str | None:
        self.urls.append(url)
        assert self.pages, f"the load read {url} after its last reading"
        return self.pages.pop(0)


def poll(*args: str) -> str:
    if args[0] == "--card-holders":
        return f"gpu_app=4242,3500,{C_3B},python3\n"
    return "0\n"


def spec(pace_path: str | None = "/metrics", engine: str = "vllm") -> dict[str, Any]:
    return {
        "mode": "load",
        "engine": engine,
        "port": 8001,
        "width": WIDTH,
        "window": WINDOW,
        "container": C_3B,
        "poll": "unused: the poll is a fake",
        "pace_path": pace_path,
    }


class RisingCard:
    """The card as the rig reads it, the container holding more once the close
    has not stopped the unit's work: ``before`` MiB for the first ``closed_at``
    readings, ``after`` MiB from then on."""

    def __init__(self, before: int, after: int, closed_at: int) -> None:
        self.mibs = (before, after)
        self.closed_at = closed_at
        self.readings = 0

    def __call__(self, *args: str) -> str:
        if args[0] != "--card-holders":
            return "0\n"
        self.readings += 1
        mib = self.mibs[self.readings > self.closed_at]
        return f"gpu_app=4242,{mib},{C_3B},python3\n"


def run_load(
    clock: Clock,
    starter: Starter,
    pages: Pages,
    unit: Unit | None = None,
    card: Callable[..., str] | None = None,
    **more: Any,
) -> dict[str, Any]:
    from mcgyvr.fleet import harness

    answer = harness.load(
        spec(**more),
        transport=unit or Unit(),
        fetch=pages,
        poll=card or poll,
        start=starter,
        clock=clock,
        sleep=clock.sleep,
    )
    return dict(answer["load"])


# --- the harness on the rig ------------------------------------------------------


def test_a_load_still_running_at_thirty_seconds_is_closed_there() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=None)

    body = run_load(clock, starter, Pages(182901.0, 302901.0))

    assert starter.batch is not None and starter.batch.closed_after == 30.0
    assert body["limit_s"] == 30
    assert (body["completed"], body["closed_unfinished"]) == (0, WIDTH)
    assert body["errors"] == []
    assert body["samples_before_close"] == 61, "every 0.5 s over 30 s, both ends"
    assert len(body["samples"]) == 62, "and one beside the idle reading after"
    assert body["sampled_until_idle"] is True
    assert body["pace_seconds"] == 30.0
    assert COUNTER in body["pace_start_page"] and "182901.0" in body["pace_start_page"]
    assert "302901.0" in body["pace_end_page"]
    assert "vllm:num_requests_running" in body["after_page"]


def test_a_load_whose_requests_finish_sooner_ends_when_they_finish() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=12.0)

    body = run_load(clock, starter, Pages(182901.0, 230901.0))

    assert starter.batch is not None and starter.batch.closed_after is None
    assert (body["completed"], body["closed_unfinished"]) == (WIDTH, 0)
    assert body["samples_before_close"] == 25
    assert len(body["samples"]) == 26
    assert body["pace_seconds"] == 12.0


def test_every_request_still_fills_the_window_and_no_fixed_timeout_holds_a_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.fleet import harness

    clock = Clock()
    starter = Starter(clock, finish_after=1.0)
    unit = Unit()

    run_load(clock, starter, Pages(0.0, 1.0), unit)

    assert len(starter.payloads) == WIDTH and starter.url.endswith("/v1/completions")
    for payload in starter.payloads:
        assert len(str(payload["prompt"]).split()) + payload["max_tokens"] == WINDOW
        assert payload["max_tokens"] >= harness.LOAD_OUTPUT_TOKENS
    assert unit.timeouts and all(timeout is None for _, timeout in unit.timeouts)
    assert (harness.REQUEST_TIMEOUT_S, harness.MODELS_TIMEOUT_S) == (900.0, 10.0)

    seen: dict[str, Any] = {}

    def run(argv: list[str], **kwargs: Any) -> Any:
        seen.update(kwargs)
        raise OSError("no bash in this test")

    monkeypatch.setattr(subprocess, "run", run)
    harness._poll("echo", "--card-holders")
    assert "timeout" not in seen, "the load's poll is held to no number"


def test_a_load_with_no_pace_counter_reads_only_the_status_page_after() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=2.0)
    pages = Pages(0.0, 0.0)
    pages.pages = ['[{"id":0,"n_ctx":8192,"speculative":false,"is_processing":false}]']

    body = run_load(clock, starter, pages, pace_path=None, engine="llama.cpp")

    assert pages.urls == ["http://127.0.0.1:8001/slots"]
    assert body["pace_start_page"] is None and body["pace_end_page"] is None
    assert starter.url.endswith("/completion")


def test_after_the_close_the_load_reads_until_the_unit_is_idle_and_files_how_long() -> (
    None
):
    from mcgyvr.fleet import harness

    clock = Clock()
    starter = Starter(clock, finish_after=None)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(2, 1, 0)))

    assert starter.batch is not None and starter.batch.closed_after == 30.0
    assert body["idle_after_close"] is False, "the close did not stop the work at once"
    assert body["idle_after_s"] == 2 * harness.LOAD_SAMPLE_S
    assert body["status_readings"] == 3
    assert body["idle_error"] is None
    assert "vllm:num_requests_running" in body["after_page"]


def test_the_wait_for_idle_has_no_time_limit() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=None)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(1,) * 200 + (0,)))

    assert body["idle_after_s"] == 100.0
    assert body["status_readings"] == 201


def test_a_unit_idle_at_the_first_reading_after_the_close_files_zero_seconds() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=None)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(0,)))

    assert body["idle_after_close"] is True
    assert body["idle_after_s"] == 0.0
    assert body["status_readings"] == 1


def test_with_nothing_left_to_close_the_wait_counts_from_the_finish() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=12.0)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(1, 0)))

    assert body["closed_unfinished"] == 0
    assert body["idle_after_close"] is True, "nothing was closed"
    assert body["idle_after_s"] == 0.5


def test_an_unreadable_status_page_is_filed_and_ends_the_wait() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=None)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(None,)))

    assert body["idle_error"] and "/metrics" in body["idle_error"]
    assert body["status_readings"] == 1
    assert body["idle_after_close"] is None and body["idle_after_s"] is None


def test_after_the_close_the_card_is_sampled_until_the_first_idle_reading() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=None)
    card = RisingCard(3500, 3900, closed_at=61)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(2, 1, 0)), card=card)

    assert body["samples_before_close"] == 61
    assert len(body["samples"]) == 61 + 3, "one beside each status reading, idle too"
    assert body["sampled_until_idle"] is True
    assert all(",3500," in sample for sample in body["samples"][:61])
    assert all(",3900," in sample for sample in body["samples"][61:])
    assert (body["idle_after_close"], body["idle_after_s"]) == (False, 1.0)
    assert (body["closed_unfinished"], body["completed"]) == (WIDTH, 0)
    assert body["status_readings"] == 3 and body["idle_error"] is None


def test_an_unreadable_status_page_keeps_the_samples_taken_short_of_idle() -> None:
    clock = Clock()
    starter = Starter(clock, finish_after=None)

    body = run_load(clock, starter, Pages(0.0, 1.0, statuses=(1, None)))

    assert body["idle_error"] and body["sampled_until_idle"] is False
    assert (body["samples_before_close"], len(body["samples"])) == (61, 63)


class _Holding(BaseHTTPRequestHandler):
    """A unit that takes a request and never answers it."""

    arrived: ClassVar[threading.Semaphore] = threading.Semaphore(0)
    release: ClassVar[threading.Event] = threading.Event()

    def log_message(self, *_: Any) -> None:
        return

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _Holding.arrived.release()
        _Holding.release.wait()


def test_the_real_requests_close_their_connections_mid_request() -> None:
    from mcgyvr.fleet import harness

    _Holding.arrived = threading.Semaphore(0)
    _Holding.release = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Holding)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/v1/completions"
        requests = harness.Requests(url, [{"prompt": "a"}, {"prompt": "b"}])
        for _ in range(2):
            assert _Holding.arrived.acquire(timeout=30), "a request never arrived"
        assert not requests.done()

        closed = requests.close()

        assert closed == 2
        assert requests.done()
        assert (requests.completed(), requests.errors()) == (0, [])
    finally:
        _Holding.release.set()
        server.shutdown()


# --- the door's row -------------------------------------------------------------------


def load_answer(
    *,
    mib: int = 3500,
    completed: int = 0,
    closed: int = WIDTH,
    errors: Sequence[str] = (),
    start: float = 182901.0,
    end: float = 302901.0,
    seconds: float = 30.0,
    running_after: int = 0,
    idle_after_close: bool | None = True,
    idle_after_s: float | None = 0.0,
    idle_error: str | None = None,
    samples: Sequence[str] | None = None,
    samples_before_close: int = 1,
    sampled_until_idle: bool = True,
) -> dict[str, Any]:
    return {
        "prompt_tokens": 4032,
        "max_tokens": 64,
        "limit_s": 30,
        "completed": completed,
        "closed_unfinished": closed,
        "errors": list(errors),
        "started_at": "2026-09-15T12:00:05",
        "finished_at": "2026-09-15T12:00:35",
        "samples": list(samples)
        if samples is not None
        else [f"gpu_app=4242,{mib},{C_3B},python3\ngpu_app=4343,7800,{C_7B},python3\n"],
        "samples_before_close": samples_before_close,
        "sampled_until_idle": sampled_until_idle,
        "restarts_before": "0",
        "restarts_after": "0",
        "pace_path": "/metrics",
        "pace_start_page": counter_page(start),
        "pace_end_page": counter_page(end),
        "pace_seconds": seconds,
        "after_page": None if idle_error else metrics(running_after),
        "idle_after_close": idle_after_close,
        "idle_after_s": idle_after_s,
        "idle_error": idle_error,
        "status_readings": 1,
    }


class LoadRig(Rig):
    def __init__(self, **answer: Any) -> None:
        super().__init__()
        self.answer = load_answer(**answer)

    def __call__(self, unit: str, asked: str) -> str:
        if json.loads(asked).get("mode") == "load":
            self.specs.append(json.loads(asked))
            return json.dumps({"load": self.answer})
        return super().__call__(unit, asked)


def read_srv2(rig: Rig) -> Any:
    from mcgyvr.fleet import read

    return read.record(
        "srv2",
        rig_text(),
        run_id=RUN_ID,
        profile="live",
        probe=("srv2_3b",),
        measure=rig,
        load=f"{WIDTH}x{WINDOW}",
    )


def test_a_load_files_its_limit_pace_closed_count_and_the_idle_reading_after(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)
    rig = LoadRig()

    read_srv2(rig)

    (asked,) = [s for s in rig.specs if s.get("mode") == "load"]
    assert asked["pace_path"] == "/metrics"
    (row,) = _load_rows(journal)
    assert row["limit_s"] == 30
    assert row["pace_prompt_tok_s"] == 4000.0, "120000 prompt tokens over 30 s"
    assert COUNTER in row["pace_source"]
    assert (row["completed"], row["closed_unfinished"]) == (0, WIDTH)
    assert row["idle_after"] is True and row["in_flight_after"] == 0
    assert row["idle_after_close"] is True and row["idle_after_s"] == 0.0
    assert row["peak_mib"] == 3500 and row["spec"] == f"{WIDTH}x{WINDOW}"
    assert row["alert"] is False, "cut at the limit, and still judged"


def test_a_load_cut_at_the_limit_is_judged_and_one_with_a_real_error_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = go_live(tmp_path)
    read_srv2(LoadRig(mib=3600))
    (cut,) = _load_rows(journal)
    assert cut["alert"] is True, "3600 MiB is over the 3573 MiB room"

    later = tmp_path / "errored"
    later.mkdir()
    journal = go_live_again(later, monkeypatch)
    read_srv2(LoadRig(mib=3600, errors=["ConnectionResetError: reset by peer"]))
    (errored,) = _load_rows(journal)
    assert "alert" not in errored


def go_live_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A second live fleet in a fresh HOME, for a second read in one test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return go_live(tmp_path)


def test_a_unit_still_busy_after_the_close_files_how_long_it_took_to_read_idle(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)

    read_srv2(LoadRig(idle_after_close=False, idle_after_s=4.5))

    (row,) = _load_rows(journal)
    assert row["idle_after_close"] is False
    assert row["idle_after_s"] == 4.5
    assert row["idle_after"] is True and row["in_flight_after"] == 0


def test_the_verdict_is_the_peak_over_every_sample_up_to_idle(tmp_path: Path) -> None:
    journal = go_live(tmp_path)
    before = f"gpu_app=4242,3500,{C_3B},python3\n"
    after = f"gpu_app=4242,3600,{C_3B},python3\n"

    read_srv2(LoadRig(samples=[before, before, after], samples_before_close=2))

    (row,) = _load_rows(journal)
    assert row["peak_mib"] == row["observed"] == 3600
    assert row["peak_before_close_mib"] == 3500
    assert (row["samples_before_close"], row["sampled_until_idle"]) == (2, True)
    assert row["alert"] is True, "3600 MiB after the close is over the 3573 MiB room"


def test_a_load_filed_before_sampling_until_idle_says_so(tmp_path: Path) -> None:
    journal = go_live(tmp_path)
    rig = LoadRig()
    del rig.answer["samples_before_close"], rig.answer["sampled_until_idle"]

    read_srv2(rig)

    (row,) = _load_rows(journal)
    assert row["sampled_until_idle"] is False
    assert row["peak_before_close_mib"] == row["peak_mib"] == 3500


def test_an_unreadable_status_page_after_a_load_is_filed_and_the_verdict_stands(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)
    why = "http://127.0.0.1:8001/metrics could not be read as a status page"

    read_srv2(LoadRig(idle_after_close=None, idle_after_s=None, idle_error=why))

    (row,) = _load_rows(journal)
    assert row["idle_error"] == why
    assert row["idle_after"] is None and row["idle_after_s"] is None
    assert row["alert"] is False, "the card verdict does not depend on the wait"


def test_a_pace_counter_that_went_backwards_is_null_with_why(tmp_path: Path) -> None:
    journal = go_live(tmp_path)

    read_srv2(LoadRig(start=302901.0, end=1000.0))

    (row,) = _load_rows(journal)
    assert row["pace_prompt_tok_s"] is None
    assert "backwards" in row["pace_source"]


def test_a_llamacpp_load_files_pace_null_with_the_reason(tmp_path: Path) -> None:
    from mcgyvr.fleet import read
    from tests import test_a_live_run_is_admitted_only_by_a_read_of_its_rigs as two

    two.go_live(tmp_path)
    journal = tmp_path / "journal" / "fleet"
    slots = '[{"id":0,"n_ctx":8192,"speculative":false,"is_processing":false}]'
    text = two.matching("srv1") + (
        f"status=18080,{base64.b64encode(slots.encode()).decode()}\n"
    )
    specs: list[dict[str, Any]] = []

    def measure(unit: str, asked: str) -> str:
        specs.append(json.loads(asked))
        if specs[-1].get("mode") == "load":
            answer = load_answer(mib=5200) | {
                "pace_path": None,
                "pace_start_page": None,
                "pace_end_page": None,
                "after_page": slots,
                "samples": [f"gpu_app=4343,5200,{two.C_SECOND},llama-server\n"],
            }
            return json.dumps({"load": answer})
        figures = {"warm_decode_tok_s": 32.56, "prefill_tok_s": 307.11}
        return json.dumps({"figures": figures, "after_page": slots})

    read.record(
        "srv1",
        text,
        run_id=RUN_ID,
        profile="live",
        probe=("srv1_deepseek",),
        measure=measure,
        load="2x8192",
    )

    (asked,) = [s for s in specs if s.get("mode") == "load"]
    assert asked["pace_path"] is None
    (row,) = _load_rows(journal)
    assert row["pace_prompt_tok_s"] is None
    assert "--metrics" in row["pace_source"] and "/slots" in row["pace_source"]
    assert row["idle_after"] is True


# --- the door's ssh to the rig --------------------------------------------------

READ_02_RIG = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "mcgyvr"
    / "serving"
    / "gate-scripts"
    / "read-02-rig.py"
)


def read_02_rig() -> ModuleType:
    spec = importlib.util.spec_from_file_location("read_02_rig", READ_02_RIG)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_doors_ssh_gives_a_load_no_timeout_and_a_probe_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.fleet import harness

    gate = read_02_rig()
    asked: list[tuple[str, str, float | None, str | None]] = []

    def ssh(
        host: str,
        command: str,
        timeout: float | None = 120.0,
        *,
        input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        asked.append((host, command, timeout, input))
        return subprocess.CompletedProcess([], 0, stdout='{"load": {}}', stderr="")

    monkeypatch.setattr(gate, "ssh", ssh)
    load = json.dumps({"mode": "load", "engine": "vllm", "port": 8001, "width": 8})
    probe = json.dumps({"mode": "probe", "engine": "vllm", "port": 8001})

    assert gate.harness_on_rig("srv2", load, "SOURCE") == '{"load": {}}'
    assert gate.harness_on_rig("srv2", probe, "SOURCE") == '{"load": {}}'

    (on_load, on_probe) = asked
    assert on_load[0] == "srv2" and harness.HARNESS_WORD in on_load[1]
    assert on_load[3] == "SOURCE"
    assert on_load[2] is None
    assert on_probe[2] == gate.PROBE_TIMEOUT_S == 1800
    assert gate.READ_TIMEOUT_S == 180


def test_a_probe_that_outlasts_its_timeout_is_still_no_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = read_02_rig()

    def ssh(
        host: str,
        command: str,
        timeout: float | None = 120.0,
        *,
        input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout or 0.0)

    monkeypatch.setattr(gate, "ssh", ssh)
    probe = json.dumps({"mode": "probe", "engine": "vllm", "port": 8001})

    assert gate.harness_on_rig("srv2", probe, "SOURCE") is None
