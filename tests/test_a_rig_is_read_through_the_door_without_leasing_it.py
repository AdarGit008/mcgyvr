"""A rig is read through the door without being leased, and the read is filed.

Owner, 2026-09-15 (D2): ``python -m mcgyvr.serving.run read --host H [--probe
UNIT...]`` is the door's third fixed sequence, beside the campaign run and
``serve``. Neither of those can read a serving rig: gate 2 takes the rig's
lease, a live run tears down what it displaced, and a busy rig is refused
unless the run is ``serve down``. ``read`` changes nothing on the rig:

* **The profile is settled**, and no round is appended to
  ``tools/bench/rounds.json``.
* **The rig is compared with its declaration and nothing else.** No lease, no
  teardown of a displaced run, no refusal of a busy rig. A rig that is not its
  declaration is refused, and nothing is filed.
* **One reader is shipped to the rig**: its facts and ``os_machine_id`` (so its
  rig id, :func:`mcgyvr.fleet.ids.rig_id`), every container with its restart
  count ("not read" is never 0), every card holder by pid, container and MiB
  (``/proc/<pid>/cgroup`` on the rig), and each vLLM unit's ``/is_sleeping``.
* **With ``--probe``**, the lock's own harness runs on the rig at 127.0.0.1, on
  an idle unit only, and its figures are judged.
* **Rows go to ``<journal.dir>/fleet``** with the usual stamps: the live fleet,
  the rig, its locked rig id, the combination and the unit. Card MiB is judged
  against the unit's ``room_mib`` and restarts against 0. No envelope is made.

The door runs from a fixture tree against stub ``ssh`` and ``docker``
(:mod:`tests.onedoor`); no rig is reached.
"""

from __future__ import annotations

import ast
import base64
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from mcgyvr.serving import run
from tests import onedoor

REPO = Path(__file__).resolve().parent.parent
GATE_SCRIPTS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts"
HARNESS_PY = REPO / "src" / "mcgyvr" / "fleet" / "harness.py"

#: srv2 as it is locked, and what its snapshot must print to reproduce it
#: (``fleet-setup/digests-srv2.json``).
LOCKED_SRV2 = "rig-cbe770b55841d616363165e38553a1c7c3768250df01ead1a255f0cbdef98455"
SRV2_SYSTEM = {"os_machine_id": "6d5d8f1f2bfa5f96", "kernel": "7.0.0-31-generic"}

UNIT_3B = "unt-" + "5" * 64
UNIT_7B = "unt-" + "7" * 64
C_3B = "3b" * 32
C_7B = "7b" * 32
C_STRAY = "5a" * 32
C_OTHER = "0e" * 32
RUN_ID = "run-20260915T120000-0a1b2c3d"
FLEET_NAME = "b-small"


def _vllm(port: int, container: str, room: int, kv: int) -> dict[str, Any]:
    return {
        "rig": "srv2",
        "engine": "vllm",
        "address": f"http://srv2:{port}",
        "model": f"Qwen/unit-{port}",
        "container": container,
        "width": 8,
        "window": 4096,
        "output_tokens": 2048,
        "request_timeout_s": 180,
        "room_mib": room,
        "kv_cache_memory_bytes": kv,
        "attention_backend": "FLASH_ATTN",
    }


FLEET: dict[str, Any] = {
    "profile": "live",
    "units": {
        "srv2_3b": {
            **_vllm(8001, "mcgyvr-srv2-3b", 3573, 1207959552),
            "unit_id": UNIT_3B,
        },
        "srv2_7b": {
            **_vllm(8002, "mcgyvr-srv2-7b", 8099, 1879048192),
            "unit_id": UNIT_7B,
        },
    },
    "rigs": {"srv2": {"rig_id": LOCKED_SRV2}},
    "fleets": {
        FLEET_NAME: {
            "layout": {"srv2": [["srv2_3b", "awake"], ["srv2_7b", "awake"]]},
            "next": [],
        }
    },
}
EVIDENCE: dict[str, Any] = {
    "rigs": {"srv2": {"card_mib": 12288}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
            "passed": True,
            "overhead_mib": 610.5,
            "restarts": {"srv2_3b": 0, "srv2_7b": 0},
            "warm_decode_tok_s": {"srv2_3b": 126.7, "srv2_7b": 68.3},
            "prefill_tok_s": {"srv2_3b": 11500.0, "srv2_7b": 12059.0},
            "attention_backend": {"srv2_3b": "FLASH_ATTN", "srv2_7b": "FLASH_ATTN"},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv2",
        }
    ],
    "moves": [],
}
TOLERANCES = {
    "warm_decode_class_pct": {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}
}


def go_live(tmp_path: Path) -> Path:
    """Promote the fleet into this test's HOME, name it live, return its journal."""
    from mcgyvr.fleet import lock

    home = Path(os.environ["HOME"])
    folder = home / ".mcgyvr" / "fleets" / FLEET_NAME
    folder.mkdir(parents=True)
    (folder / "fleet.yaml").write_text(yaml.safe_dump(FLEET), encoding="utf-8")
    journal = tmp_path / "journal"
    policy = {"ladder": ["srv2_3b", "srv2_7b"], "journal": {"dir": str(journal)}}
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(folder, FLEET, EVIDENCE, tolerances=TOLERANCES)
    (home / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": FLEET_NAME}), encoding="utf-8"
    )
    return journal / "fleet"


def metrics(running: int) -> str:
    return (
        f'vllm:num_requests_running{{model_name="m"}} {running}.0\n'
        'vllm:num_requests_waiting{model_name="m"} 0.0\n'
    )


def page(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def reading(
    root: Path,
    *,
    snapshot: dict[str, str] | None = None,
    containers: tuple[str, ...] | None = None,
    gpu: tuple[str, ...] | None = None,
    sleeping: tuple[str, ...] = ("8001,false", "8002,unknown"),
    status: tuple[str, ...] = (),
) -> None:
    """What the stub rig answers the reader with: its snapshot and the rest."""
    lines = onedoor.snapshot_lines("srv2", **(SRV2_SYSTEM | (snapshot or {})))
    for row in (
        containers
        if containers is not None
        else (
            f"mcgyvr-srv2-3b,{C_3B},mcgyvr,0",
            f"mcgyvr-srv2-7b,{C_7B},mcgyvr,unread",
            f"mcgyvr-srv2-stray,{C_STRAY},mcgyvr,0",
            f"someone-elses,{C_OTHER},-,0",
        )
    ):
        lines += f"container={row}\n"
    for row in (
        gpu
        if gpu is not None
        else (
            f"4242,3400,{C_3B},python3",
            f"4343,7800,{C_7B},python3",
            "5555,1024,none,python3_train.py",
        )
    ):
        lines += f"gpu_app={row}\n"
    for row in sleeping:
        lines += f"sleeping={row}\n"
    for row in status:
        lines += f"status={row}\n"
    (onedoor.stubs_dir(root) / "snapshot.txt").write_text(lines, encoding="utf-8")


def read_door(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(root / onedoor.DOOR_REL), "read", "--host", "srv2"]
    argv += ["--run-id", RUN_ID, *args]
    return subprocess.run(
        argv,
        cwd=root,
        env=onedoor.door_env(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def rows(journal: Path) -> list[dict[str, Any]]:
    if not journal.is_dir():
        return []
    return [
        json.loads(line)
        for path in sorted(journal.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def unit_rows(journal: Path, unit_id: str) -> dict[str, dict[str, Any]]:
    return {
        r["field"]: r
        for r in rows(journal)
        if r.get("unit_id") == unit_id and "field" in r
    }


def rig_row(journal: Path) -> dict[str, Any]:
    found = [r for r in rows(journal) if "observed_rig_id" in r]
    assert len(found) == 1, rows(journal)
    return found[0]


@pytest.fixture
def srv2(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    root = onedoor.fixture_repo(tmp_path, host="srv2")
    journal = go_live(tmp_path)
    reading(root)
    yield root, journal


# --- the shape ------------------------------------------------------------------


def test_read_is_a_fixed_sequence_with_one_reader_on_the_manifest() -> None:
    assert [entry.script for entry in run.READ_SEQUENCE] == [
        "read-01-profile.py",
        "read-02-rig.py",
    ]
    for entry in run.READ_SEQUENCE:
        assert (GATE_SCRIPTS / entry.script).is_file(), entry.script
    assert "rig-units.sh" in [path.name for path in run.READERS]


def test_read_help_offers_no_way_past_a_gate(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(root / onedoor.DOOR_REL), "read", "--help"],
        cwd=root,
        env=onedoor.door_env(root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--probe" in result.stdout
    for forbidden in ("--skip", "--no-gate", "--force", "--model", "--compose"):
        assert forbidden not in result.stdout, forbidden


# --- what a read leaves -----------------------------------------------------------


def test_a_read_leases_nothing_tears_nothing_down_appends_no_round_files_no_envelope(
    srv2: tuple[Path, Path],
) -> None:
    from mcgyvr.serving import gatelib

    root, _ = srv2
    held = gatelib.new_lease("dev", "a-dev-campaign", "step", 1).line()
    onedoor.plant_lease(root, held)
    onedoor.unpin(root)
    rounds = (root / "tools" / "bench" / "rounds.json").read_bytes()

    result = read_door(root)

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    assert (onedoor.read_lease(root) or "").strip() == held.strip()
    assert not [line for line in onedoor.docker_log(root) if line.startswith("rm")]
    assert (root / "tools" / "bench" / "rounds.json").read_bytes() == rounds
    assert not (root / "records" / "evidence").exists()


def test_a_rig_that_is_not_its_declaration_is_refused_and_nothing_is_filed(
    srv2: tuple[Path, Path],
) -> None:
    root, journal = srv2
    reading(root, snapshot={"gpu_vram_mib": "8192"})

    result = read_door(root)

    assert result.returncode == 2, (result.stdout, result.stderr[-2000:])
    assert "gpu_vram_mib" in result.stderr and "declar" in result.stderr
    assert rows(journal) == []


# --- what a read files --------------------------------------------------------------


def test_a_read_files_its_rig_id_units_and_what_else_holds_the_card(
    srv2: tuple[Path, Path],
) -> None:
    root, journal = srv2

    result = read_door(root)

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    rig = rig_row(journal)
    assert rig["observed_rig_id"] == LOCKED_SRV2
    assert rig["fleet"] == FLEET_NAME and rig["rig"] == "srv2"
    assert rig["rig_id"] == LOCKED_SRV2
    assert rig["combination_id"].startswith("cmb-")
    assert rig["run_id"] == RUN_ID
    assert rig["units"] == {
        UNIT_3B: "awake",
        UNIT_7B: "awake",
        "mcgyvr-srv2-stray": "awake",
    }
    assert len(rig["foreign"]) == 1, rig["foreign"]
    assert "5555" in rig["foreign"][0] and "train" in rig["foreign"][0]

    three = unit_rows(journal, UNIT_3B)
    assert three["card_mib"]["observed"] == 3400 and three["card_mib"]["alert"] is False
    assert three["restarts"]["observed"] == 0 and three["restarts"]["alert"] is False
    for row in three.values():
        assert row["fleet"] == FLEET_NAME and row["rig_id"] == LOCKED_SRV2
        assert row["combination_id"] == rig["combination_id"]
        assert row["run_id"] == RUN_ID

    seven = unit_rows(journal, UNIT_7B)
    assert seven["card_mib"]["observed"] == 7800
    assert seven["restarts"]["observed"] is None
    assert seven["restarts"]["read"] is False
    assert "alert" not in seven["restarts"], "a count not read is not judged as 0"


def test_card_over_room_and_a_restart_alert_on_a_live_read(
    srv2: tuple[Path, Path],
) -> None:
    root, journal = srv2
    reading(
        root,
        containers=(
            f"mcgyvr-srv2-3b,{C_3B},mcgyvr,1",
            f"mcgyvr-srv2-7b,{C_7B},mcgyvr,0",
        ),
        gpu=(f"4242,3600,{C_3B},python3", f"4343,7800,{C_7B},python3"),
    )

    result = read_door(root)

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    three = unit_rows(journal, UNIT_3B)
    assert three["card_mib"]["alert"] is True, "3600 MiB is over its 3573 MiB room"
    assert three["restarts"]["alert"] is True
    seven = unit_rows(journal, UNIT_7B)
    assert seven["card_mib"]["alert"] is False and seven["restarts"]["alert"] is False
    assert rig_row(journal)["foreign"] == []


def test_a_unit_that_says_it_is_asleep_reads_asleep(srv2: tuple[Path, Path]) -> None:
    root, journal = srv2
    reading(root, sleeping=("8001,true", "8002,false"))

    assert read_door(root).returncode == 0
    assert rig_row(journal)["units"][UNIT_3B] == "asleep"


# --- read --probe -----------------------------------------------------------------


def test_read_probe_runs_the_locks_harness_on_the_rig_and_its_figures_are_judged(
    srv2: tuple[Path, Path],
) -> None:
    """125.0 is 1.3% under 126.7: past vLLM's 1%, timed on the rig."""
    root, journal = srv2
    reading(root, status=(f"8001,{page(metrics(0))}",))
    measured = {
        "figures": {"warm_decode_tok_s": 125.0, "prefill_tok_s": 11500.0},
        "after_page": metrics(0),
    }
    (onedoor.stubs_dir(root) / "harness.json").write_text(
        json.dumps(measured), encoding="utf-8"
    )

    result = read_door(root, "--probe", "srv2_3b")

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    assert [line for line in onedoor.ssh_log(root) if "mcgyvr-harness" in line]
    three = unit_rows(journal, UNIT_3B)
    assert three["warm_decode_tok_s"]["observed"] == 125.0
    assert three["warm_decode_tok_s"]["alert"] is True
    assert three["prefill_tok_s"]["alert"] is False
    assert three["warm_decode_tok_s"]["lease_id"].startswith("read-")
    assert "off_the_rig" not in three["warm_decode_tok_s"]
    assert "warm_decode_tok_s" not in unit_rows(journal, UNIT_7B)


def test_read_probe_does_not_probe_a_unit_with_work_in_flight(
    srv2: tuple[Path, Path],
) -> None:
    root, journal = srv2
    reading(root, status=(f"8001,{page(metrics(2))}",))

    result = read_door(root, "--probe", "srv2_3b")

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    assert not [line for line in onedoor.ssh_log(root) if "mcgyvr-harness" in line]
    assert "warm_decode_tok_s" not in unit_rows(journal, UNIT_3B)
    assert "busy" in result.stdout and "srv2_3b" in result.stdout


def test_read_probe_of_a_unit_not_awake_on_this_rig_is_refused_before_the_rig(
    srv2: tuple[Path, Path],
) -> None:
    root, journal = srv2

    result = read_door(root, "--probe", "srv1_deepseek")

    assert result.returncode == 2, (result.stdout, result.stderr[-2000:])
    assert "srv1_deepseek" in result.stderr
    assert onedoor.ssh_log(root) == []
    assert rows(journal) == []


# --- the reader and the harness, as shipped ----------------------------------------


def _stub(where: Path, name: str, body: str) -> None:
    onedoor.executable(where / name, "#!/usr/bin/env bash\n" + body)


def test_the_units_reader_prints_containers_card_holders_and_sleep(
    tmp_path: Path,
) -> None:
    """``rig-units.sh`` run here, against stub ``docker``, ``nvidia-smi`` and
    ``curl``: one pid is this test's own, which is in no container of ours."""
    stubs = tmp_path / "bin"
    mine = os.getpid()
    _stub(
        stubs,
        "docker",
        'case "$1" in\n'
        f"  ps) printf '%s|%s|%s\\n' {C_3B} mcgyvr-srv2-3b mcgyvr ;;\n"
        "  inspect) echo 3 ;;\n"
        "esac\n",
    )
    _stub(
        stubs,
        "nvidia-smi",
        f'case "$*" in *query-compute-apps*) echo "{mine}, 1024, python3" ;; esac\n',
    )
    _stub(
        stubs,
        "curl",
        'case "$*" in\n'
        "  *is_sleeping*) echo '{\"is_sleeping\": false}' ;;\n"
        "  *metrics*) printf 'vllm:num_requests_running 0\\n' ;;\n"
        "  *) exit 7 ;;\n"
        "esac\n",
    )
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(
        ["bash", str(GATE_SCRIPTS / "rig-units.sh"), "vllm:8001"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert f"container=mcgyvr-srv2-3b,{C_3B},mcgyvr,3" in lines, lines
    assert f"gpu_app={mine},1024,none,python3" in lines, lines
    assert "sleeping=8001,false" in lines, lines
    status = [line for line in lines if line.startswith("status=8001,")]
    assert len(status) == 1, lines
    decoded = base64.b64decode(status[0].split(",", 1)[1]).decode("utf-8")
    assert "vllm:num_requests_running 0" in decoded
    assert all(" " not in line for line in lines), lines


class _Unit(BaseHTTPRequestHandler):
    seen: ClassVar[list[str]] = []

    def log_message(self, *_: Any) -> None:
        return

    def _send(self, body: str, kind: str = "application/json") -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self.seen.append(f"GET {self.path}")
        if self.path == "/v1/models":
            self._send(json.dumps({"data": [{"id": "m"}]}))
        else:
            self._send(metrics(0), "text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length))
        self.seen.append(f"POST {self.path} {payload['max_tokens']}")
        prompt = 1960 if payload["max_tokens"] == 16 else 20
        self._send(
            json.dumps(
                {
                    "usage": {
                        "completion_tokens": payload["max_tokens"],
                        "prompt_tokens": prompt,
                    }
                }
            )
        )


def test_the_harness_shipped_to_the_rig_asks_the_locks_requests_at_127_0_0_1() -> None:
    """``harness.py`` run as the rig runs it: ``python3 -``, isolated, no mcgyvr."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Unit)
    _Unit.seen = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec = json.dumps({"engine": "vllm", "port": server.server_address[1]})
        done = subprocess.run(
            [sys.executable, "-I", "-", "mcgyvr-harness", spec],
            input=HARNESS_PY.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert set(out["figures"]) == {"warm_decode_tok_s", "prefill_tok_s"}
    assert "vllm:num_requests_running" in out["after_page"]
    posts = [line.split()[-1] for line in _Unit.seen if line.startswith("POST")]
    assert posts == ["64"] + ["256"] * 5 + ["16"] * 3, _Unit.seen


def test_the_probe_and_the_harness_are_one_method() -> None:
    """``mcgyvr fleet probe`` and the harness on the rig ask the same requests."""
    from mcgyvr.fleet import harness, probe

    assert probe.measure_vllm is harness.measure_vllm
    assert probe.measure_llamacpp is harness.measure_llamacpp
    assert probe.VLLM_LONG == harness.VLLM_LONG
    tree = ast.parse(HARNESS_PY.read_text(encoding="utf-8"))
    imported = {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "mcgyvr" not in imported, "the rig has no mcgyvr to import"
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
