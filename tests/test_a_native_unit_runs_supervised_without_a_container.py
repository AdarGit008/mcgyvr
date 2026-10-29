"""A native unit runs as a supervised process: up, answering, recorded, down.

A stand-in llama-server (``tests/fake_llama_server.py``, written out as the
build's ``llama-server``) is started from a launch spec whose service is
native. Its supervisor holds the unit's lock, records both pids with their
start times and programs, logs the server's output, files the Metal working
set the server's start-up log states as a reading, and answers ``down`` by
stopping it. A server that crashes is restarted after a pause, and one that
keeps crashing is given up on once the restarts allowed are spent.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from mcgyvr import hostos
from mcgyvr.serving import CARDS_KEY, LAUNCHER_KEY, PROGRAM_KEY, llamacpp, native

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the stand-in server is a script with a shebang"
)

FAKE = Path(__file__).with_name("fake_llama_server.py")
UNIT = "mcgyvr-localhost-fake-model"


def _port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _programs(tmp_path: Path) -> Path:
    folder = tmp_path / "build"
    folder.mkdir()
    server = folder / "llama-server"
    server.write_text(
        f"#!{sys.executable}\n" + FAKE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    server.chmod(0o700)
    return folder


def _spec(tmp_path: Path, port: int, env: dict[str, str] | None = None) -> Path:
    service: dict[str, object] = {
        LAUNCHER_KEY: "native",
        PROGRAM_KEY: "llama-server",
        "container_name": UNIT,
        "command": ["--model", "/w/x.gguf", "--port", str(port), "--host", "127.0.0.1"],
        CARDS_KEY: [0],
    }
    if env:
        service["environment"] = env
    path = tmp_path / "compose.localhost.yml"
    path.write_text(yaml.safe_dump({"services": {"fake-model": service}}))
    return path


METAL_BUILD = llamacpp.Build("darwin", "arm64", "metal", "macos-arm64", ("x",))


@pytest.fixture
def stopped_after() -> Iterator[None]:
    yield
    native.stop(UNIT)


def _until(check: object, budget: float = 20.0) -> bool:
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if check():  # type: ignore[operator]
            return True
        time.sleep(0.1)
    return False


def test_a_native_unit_comes_up_answers_and_goes_down(
    tmp_path: Path, stopped_after: None
) -> None:
    port = _port()
    programs = _programs(tmp_path)
    done = native.up(
        _spec(tmp_path, port), folder=lambda build: programs, build=lambda: METAL_BUILD
    )
    assert done.returncode == 0, done.stderr
    assert native.wait_answers(port, 20)
    assert native.answers(port, "/health")
    assert native.supervised(UNIT)
    assert list(native.running().values()) == [UNIT]

    record = native.read_record(UNIT) or {}
    assert record["state"] == native.RUNNING
    assert record["server"]["program"] == str(programs / "llama-server")
    assert record["server"]["start"] == hostos.process_start_time(
        record["server"]["pid"]
    )
    assert record["supervisor"]["start"] == hostos.process_start_time(
        record["supervisor"]["pid"]
    )
    assert record["port"] == port

    assert _until(lambda: native.metal_working_set() is not None)
    reading = native.metal_working_set() or {}
    assert reading["bytes"] == 22_906_500_000
    assert reading["figure"] == "reading"

    log = native.log_path(UNIT).read_text(encoding="utf-8")
    assert "recommendedMaxWorkingSetSize" in log

    # A second `up` of the same spec leaves the running unit as it is.
    again = native.up(
        _spec(tmp_path, port), folder=lambda build: programs, build=lambda: METAL_BUILD
    )
    assert again.returncode == 0
    assert (native.read_record(UNIT) or {})["server"] == record["server"]

    gone = native.down([UNIT])
    assert gone.returncode == 0, gone.stderr
    assert not native.supervised(UNIT)
    assert not native.answers(port)
    assert native.running() == {}
    assert [row["state"] for row in native.status()] == [native.STOPPED]


def test_a_crashed_server_is_restarted_once_and_then_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped_after: None
) -> None:
    monkeypatch.setattr(
        native, "RESTART", {**native.RESTART, "backoff_s": 0.05, "max_restarts": 3}
    )
    port = _port()
    marker = tmp_path / "crashed-once"
    env = {"FAKE_MODE": "crash-once", "FAKE_MARKER": str(marker)}
    programs = _programs(tmp_path)
    native.up(
        _spec(tmp_path, port, env), folder=lambda b: programs, build=lambda: METAL_BUILD
    )
    assert native.wait_answers(port, 20)
    record = native.read_record(UNIT) or {}
    assert record["state"] == native.RUNNING
    assert record["restarts"] == 1
    assert native.log_path(UNIT).read_text().count("starts at") == 2


def test_a_server_that_keeps_crashing_is_given_up_on_after_n_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped_after: None
) -> None:
    monkeypatch.setattr(
        native, "RESTART", {**native.RESTART, "backoff_s": 0.05, "max_restarts": 2}
    )
    port = _port()
    programs = _programs(tmp_path)
    native.up(
        _spec(tmp_path, port, {"FAKE_MODE": "crash"}),
        folder=lambda b: programs,
        build=lambda: METAL_BUILD,
    )
    assert _until(lambda: (native.read_record(UNIT) or {}).get("state") == "gave_up")
    record = native.read_record(UNIT) or {}
    assert record["restarts"] == 2
    assert record["exit"] == 3
    log = native.log_path(UNIT).read_text()
    assert log.count("starts at") == 3
    assert "given up after 2 restarts" in log
    assert _until(lambda: not native.supervised(UNIT))
    assert [row["state"] for row in native.status()] == ["gave_up"]


def test_an_engine_told_never_to_restart_is_given_up_on_at_its_first_exit(
    tmp_path: Path, stopped_after: None
) -> None:
    port = _port()
    programs = _programs(tmp_path)
    native.up(
        _spec(tmp_path, port, {"FAKE_MODE": "crash"}),
        folder=lambda b: programs,
        build=lambda: METAL_BUILD,
        restart={"max_restarts": 0},
    )
    assert _until(lambda: (native.read_record(UNIT) or {}).get("state") == "gave_up")
    assert native.log_path(UNIT).read_text().count("starts at") == 1


def test_the_door_vocabulary_stays_with_the_door(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped_after: None
) -> None:
    monkeypatch.setenv("RUN_DOOR_PROOF", "a" * 64)
    port = _port()
    programs = _programs(tmp_path)
    marker = tmp_path / "env"
    native.up(
        _spec(tmp_path, port, {"FAKE_ENV_NAMES": str(marker)}),
        folder=lambda b: programs,
        build=lambda: METAL_BUILD,
    )
    assert _until(marker.exists)
    assert not [n for n in marker.read_text().split() if n.startswith("RUN_")]


def test_a_server_left_by_a_killed_supervisor_is_ended_before_a_new_start(
    tmp_path: Path, stopped_after: None
) -> None:
    port = _port()
    programs = _programs(tmp_path)
    spec = _spec(tmp_path, port)
    native.up(spec, folder=lambda b: programs, build=lambda: METAL_BUILD)
    first = native.read_record(UNIT) or {}
    hostos.end_pid(first["supervisor"]["pid"], force=True)
    assert _until(lambda: not native.supervised(UNIT))
    assert native.matches(first["server"]) is not None, "the server went too"
    again = native.up(spec, folder=lambda b: programs, build=lambda: METAL_BUILD)
    assert again.returncode == 0, again.stderr
    assert _until(lambda: native.matches(first["server"]) is None)
    assert (native.read_record(UNIT) or {})["server"]["pid"] != first["server"]["pid"]
    assert native.wait_answers(port, 20)


def test_the_pauses_between_restarts_double_up_to_their_cap() -> None:
    spec = {**native.RESTART, "backoff_s": 1.0, "backoff_max_s": 30.0}
    pauses = [
        min(spec["backoff_s"] * 2 ** (n - 1), spec["backoff_max_s"])
        for n in range(1, 8)
    ]
    assert pauses == [1, 2, 4, 8, 16, 30, 30]
    assert native.RESTART["max_restarts"] >= 1


def test_a_unit_name_that_would_leave_its_folder_is_refused() -> None:
    with pytest.raises(native.NativeError):
        native.log_path("../escape")


def test_the_cards_reach_the_server_as_its_backend_reads_them() -> None:
    assert native.device_env("cuda", (1, 0)) == {
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES": "1,0",
    }
    # Vulkan numbers devices its own way: a card's index is not passed on.
    assert native.device_env("vulkan", (0,)) == {}
    assert native.device_env("metal", (0,)) == {}


def test_the_metal_line_is_read_as_llama_cpp_prints_it() -> None:
    line = b"ggml_metal_device_init: recommendedMaxWorkingSetSize  = 11453.25 MB\n"
    assert native.metal_reading(line) == 11_453_250_000
    assert native.metal_reading(b"no such line") is None


def test_status_is_one_json_row_per_unit(capsys: pytest.CaptureFixture[str]) -> None:
    assert native.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out) == []
