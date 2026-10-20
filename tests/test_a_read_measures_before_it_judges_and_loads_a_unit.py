"""A read measures and files everything before it judges, and can load a unit.

What ``python -m mcgyvr.serving.run read`` does:

* **Probe first, judge after.** :func:`mcgyvr.fleet.read.record`
  measures first (the probes, then the loads), files every row (units, probes,
  loads), and judges after, so a unit one MiB over its room is still measured
  whole. An alert warns and stops nothing.
* **A load mode.** ``read --host H --probe UNIT --load WxN``
  runs W concurrent requests on the rig at 127.0.0.1, each filling the unit's
  N-token window (its prompt plus ``max_tokens``). While they run it samples the
  unit's container card MiB with the same pid -> container poll the read uses,
  and files one load row: the unit, the spec, ``peak_mib``, the samples, the
  container, when it started and finished, and the restart counts before and
  after. The peak is judged like the card: at most ``room_mib``.
  ``room_mib`` is the process's measured card peak, context included. An
  idle unit only, no lease, and the harness imports only the standard library.
* **Read saves both.** For each vLLM unit, the attention backend its
  container's log names is filed in that unit's row as ``attention_backend``,
  or null when the log names none; nothing is guessed. The whole
  log is searched for the token, as the lock's ``measure_vllm.py`` does, and the
  line the reader matched is filed beside it
  (``tests/test_a_vllm_backend_read_searches_the_whole_log_and_records_its_line.py``).
  The rig row files the reading's snapshot beside ``observed_rig_id``, the
  rig id the machine's reading names, which a sample's evidence hands the lock.

No rig is reached: the reading is canned text, the rig's harness a stand-in,
and the door runs against :mod:`tests.onedoor`'s stubs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests import onedoor
from tests.reads import (
    C_3B,
    GATE_SCRIPTS,
    HARNESS_PY,
    LOAD,
    LOCKED_BOX2,
    RUN_ID,
    UNIT_3B,
    UNIT_7B,
    Rig,
    _load_rows,
    go_live,
    metrics,
    page,
    read_door,
    reading,
    record,
    rig_row,
    rig_text,
    unit_rows,
)

# --- B2: probe first, judge after ------------------------------------------------


def test_a_read_over_room_still_probes_and_files_what_it_measured(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)
    rig = Rig()

    done = record(rig_text(card_3b=3574), rig)

    assert {(a["unit_id"], a["field"]) for a in done.alerts} == {(UNIT_3B, "card_mib")}

    assert [spec.get("mode", "probe") for spec in rig.specs] == ["probe"], rig.specs
    three = unit_rows(journal, UNIT_3B)
    assert three["warm_decode_tok_s"]["observed"] == 126.7
    assert three["prefill_tok_s"]["observed"] == 11500.0
    assert three["card_mib"]["observed"] == 3574 and three["card_mib"]["alert"] is True


def test_a_read_files_every_units_rows_whatever_alerted(tmp_path: Path) -> None:
    journal = go_live(tmp_path)

    record(rig_text(card_3b=3574, restarts_7b="1"), Rig())

    three = unit_rows(journal, UNIT_3B)
    seven = unit_rows(journal, UNIT_7B)
    assert three["card_mib"]["alert"] is True and three["restarts"]["alert"] is False
    assert seven["card_mib"]["alert"] is False and seven["restarts"]["alert"] is True


# --- B1: a load of the unit --------------------------------------------------------


def test_a_load_files_one_row_with_its_peak_samples_container_times_and_restarts(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)

    record(rig_text(), Rig(), load=LOAD)

    (row,) = _load_rows(journal)
    assert row["unit_id"] == UNIT_3B and row["unit"] == "box2_3b"
    assert row["spec"] == LOAD
    assert row["peak_mib"] == 3500 and row["observed"] == 3500
    assert row["samples"] == 3
    assert row["container"] == C_3B
    assert row["started_at"] == "2026-09-15T12:00:05"
    assert row["finished_at"] == "2026-09-15T12:00:41"
    assert (row["restarts_before"], row["restarts_after"]) == (0, 0)
    assert row["alert"] is False, "3500 MiB is inside a 3573 MiB room"
    assert row["run_id"] == RUN_ID and row["rig_id"] == LOCKED_BOX2


def test_a_load_peak_over_room_alerts_like_the_card(tmp_path: Path) -> None:
    journal = go_live(tmp_path)
    done = record(rig_text(), Rig(load_mib=(3100, 3600)), load=LOAD)
    assert _load_rows(journal)[0]["alert"] is True
    assert "load_peak_mib" in {alert["field"] for alert in done.alerts}


def test_the_load_asked_of_the_rig_is_w_requests_filling_the_units_window(
    tmp_path: Path,
) -> None:
    go_live(tmp_path)
    rig = Rig()

    record(rig_text(), rig, load=LOAD)

    (load,) = [spec for spec in rig.specs if spec.get("mode") == "load"]
    assert (load["width"], load["window"]) == (8, 4096)
    assert (load["engine"], load["port"], load["container"]) == ("vllm", 8001, C_3B)
    assert "--card-holders" in load["poll"], "the read's own pid -> container poll"


def test_a_unit_with_work_in_flight_is_neither_probed_nor_loaded(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)
    rig = Rig()

    done = record(rig_text(status=(f"8001,{page(metrics(2))}",)), rig, load=LOAD)

    assert rig.specs == []
    assert done.busy == {"box2_3b": 2}
    assert _load_rows(journal) == []


def test_a_load_that_did_not_complete_every_request_is_still_judged(
    tmp_path: Path,
) -> None:
    """A load that reached its limit with requests unfinished is
    judged on its peak. Only an error other than that close, or no sample of the
    container, leaves a load unjudged
    (``tests/test_a_load_runs_thirty_seconds_then_gives_its_verdict.py``)."""
    journal = go_live(tmp_path)

    record(rig_text(), Rig(load_mib=(3600,), completed=5), load=LOAD)

    (row,) = _load_rows(journal)
    assert row["completed"] == 5 and row["peak_mib"] == 3600
    assert row["alert"] is True, "3600 MiB is over the 3573 MiB room"


def test_read_load_is_a_door_flag_that_needs_a_probe_and_a_w_x_n_spec(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path, host="box2")
    go_live(tmp_path)
    reading(root)
    shown = subprocess.run(
        [sys.executable, str(root / onedoor.DOOR_REL), "read", "--help"],
        cwd=root,
        env=onedoor.door_env(root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert "--load" in shown.stdout, shown.stdout

    alone = read_door(root, "--load", LOAD)
    assert alone.returncode == 2 and "--load needs --probe" in alone.stderr, alone
    malformed = read_door(root, "--probe", "box2_3b", "--load", "8by4096")
    assert malformed.returncode == 2 and "WxN" in malformed.stderr, malformed
    assert onedoor.ssh_log(root) == [], "refused before the rig was read"


def test_a_door_read_with_a_load_ships_it_to_the_rig_and_files_its_row(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path, host="box2")
    journal = go_live(tmp_path)
    reading(root, status=(f"8001,{page(metrics(0))}",))
    loaded = json.loads(Rig()("box2_3b", json.dumps({"mode": "load"})))
    probed = json.loads(Rig()("box2_3b", json.dumps({})))
    (onedoor.stubs_dir(root) / "harness.json").write_text(
        json.dumps(probed | loaded), encoding="utf-8"
    )

    result = read_door(root, "--probe", "box2_3b", "--load", LOAD)

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    shipped = [line for line in onedoor.ssh_log(root) if "mcgyvr-harness" in line]
    assert len(shipped) == 2, shipped
    (row,) = _load_rows(journal)
    assert row["spec"] == LOAD and row["peak_mib"] == 3500


class _Unit(BaseHTTPRequestHandler):
    """A vLLM face that tokenizes by words and remembers every completion."""

    asked: ClassVar[list[tuple[int, int]]] = []

    def log_message(self, *_: Any) -> None:
        return

    def _send(self, body: Any) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send({"data": [{"id": "m"}]})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length))
        words = len(str(payload.get("prompt", "")).split())
        if self.path == "/tokenize":
            self._send({"count": words})
            return
        self.asked.append((words, int(payload["max_tokens"])))
        threading.Event().wait(0.4)
        self._send({"usage": {"prompt_tokens": words, "completion_tokens": 1}})


POLL = """\
case "$1" in
  --card-holders) echo "gpu_app=1,3210,cafe,python3" ;;
  --restarts) echo 2 ;;
esac
"""


def test_the_harness_loads_a_unit_at_127_0_0_1_and_samples_its_container() -> None:
    """``harness.py`` as the rig runs it: ``python3 -``, isolated, no mcgyvr."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Unit)
    _Unit.asked = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec = {
            "mode": "load",
            "engine": "vllm",
            "port": server.server_address[1],
            "width": 3,
            "window": 512,
            "container": "cafe",
            "poll": POLL,
        }
        done = subprocess.run(
            [sys.executable, "-I", "-", "mcgyvr-harness", json.dumps(spec)],
            input=HARNESS_PY.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
    assert done.returncode == 0, (done.stdout, done.stderr)
    load = json.loads(done.stdout)["load"]
    assert load["completed"] == 3 and load["errors"] == []
    assert len(_Unit.asked) == 3
    assert all(prompt + most == 512 and most >= 1 for prompt, most in _Unit.asked)
    assert load["samples"] and all("gpu_app=1,3210,cafe" in s for s in load["samples"])
    assert (load["restarts_before"].strip(), load["restarts_after"].strip()) == (
        "2",
        "2",
    )


# --- B4: the attention backend and the snapshot -------------------------------------


def test_a_vllm_units_attention_backend_is_filed_and_null_when_its_log_names_none(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)

    record(rig_text(backend=("8001,FLASH_ATTN", "8002,none")), Rig())

    three = unit_rows(journal, UNIT_3B)["attention_backend"]
    seven = unit_rows(journal, UNIT_7B)["attention_backend"]
    assert (
        three["observed"] == "FLASH_ATTN" and three["attention_backend"] == "FLASH_ATTN"
    )
    assert seven["observed"] is None and seven["attention_backend"] is None
    assert "alert" not in three and "alert" not in seven


def test_the_rig_row_files_the_snapshot_beside_the_rig_id_its_reading_names(
    tmp_path: Path,
) -> None:
    journal = go_live(tmp_path)

    record(rig_text(), Rig())

    row = rig_row(journal)
    assert row["observed_rig_id"] == onedoor.rig_id_of_text(rig_text())
    assert row["snapshot"] == onedoor.split_reading(rig_text())[0]["snapshot"]
    assert "container" not in row["snapshot"] and "gpu_app" not in row["snapshot"]


def _units_reader(tmp_path: Path, log: str) -> list[str]:
    stubs = tmp_path / "bin"
    onedoor.executable(
        stubs / "docker",
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        f"  ps) printf '%s|%s|%s\\n' {C_3B} mcgyvr-box2-3b mcgyvr ;;\n"
        "  inspect) echo 0 ;;\n"
        f"  logs) printf '%s' {json.dumps(log)} ;;\n"
        "esac\n",
    )
    onedoor.executable(stubs / "nvidia-smi", "#!/usr/bin/env bash\nexit 0\n")
    onedoor.executable(
        stubs / "curl",
        "#!/usr/bin/env bash\n"
        'case "$*" in *is_sleeping*) echo \'{"is_sleeping": false}\' ;;\n'
        "  *) exit 7 ;; esac\n",
    )
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(
        ["bash", str(GATE_SCRIPTS / "rig-units.sh"), "vllm:8001:mcgyvr-box2-3b"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


def test_the_units_reader_names_the_backend_its_whole_log_carries(
    tmp_path: Path,
) -> None:
    """The token is looked for in the whole log, as the lock's
    ``measure_vllm.py`` does, and a log naming none anywhere is still ``none``."""
    started = (
        "INFO 09-13 21:40:02 loader.py:12] Loading weights\n"
        "INFO 09-13 21:40:05 cuda.py:40] Using attention backend: FLASH_ATTN\n"
    )
    assert "backend=8001,FLASH_ATTN" in _units_reader(tmp_path / "said", started)
    elsewhere = "INFO 09-13 21:40:02 loader.py:12] FLASHINFER is available\n"
    assert "backend=8001,FLASHINFER" in _units_reader(tmp_path / "later", elsewhere)
    silent = "INFO 09-13 21:40:02 loader.py:12] Loading weights\n"
    assert "backend=8001,none" in _units_reader(tmp_path / "silent", silent)


def test_a_backend_row_is_decoded_from_a_reader_line() -> None:
    from mcgyvr.fleet import read

    parsed = read.parse("backend=8001,FLASH_ATTN\nbackend=8002,none\n")
    assert parsed.backend == {8001: "FLASH_ATTN", 8002: None}
    # A row the runtime reader does not print is refused, never filed.
    with pytest.raises(read.ReadError):
        read.parse("kernel=7.0.0\n")
