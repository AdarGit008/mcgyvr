"""A native unit's lock, record and spec carry the unit's whole name.

A unit is named after its model, and a model id may hold dots
(``Org/Model2.5-0.5B``): none of them ends the name. Each file is the whole
name and its own end, so the name read back from a record is the unit's, the
unit counts as running once started, and two units of one model on two ports
keep a lock each. A name with no dot names the same files as before.

An earlier mcgyvr cut a dotted name at its last dot (``Path.with_suffix``). A
supervisor it started still holds the cut lock: it is listed under the cut
name, ``down`` stops it, and ``up`` stops it before it starts the unit again,
so one server holds the port. A cut record is the unit's only while it names
the unit itself.
"""

from __future__ import annotations

import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from mcgyvr import hostos
from mcgyvr.serving import CARDS_KEY, LAUNCHER_KEY, PROGRAM_KEY, llamacpp, native

FAKE = Path(__file__).with_name("fake_llama_server.py")
DOTTED = "mcgyvr-box1-Org-Model2.5-0.5B-Instruct-8080"
#: What an earlier mcgyvr named DOTTED's files after: its cut at the last dot.
CUT = "mcgyvr-box1-Org-Model2.5-0"
BUILD = llamacpp.Build("linux", "x86_64", "cpu", "ubuntu-x64", ("x",))

#: A supervisor as an earlier mcgyvr ran it: its files named by `with_suffix`.
OLD_SUPERVISOR = """
import sys
from pathlib import Path
from mcgyvr.serving import native

def cut(unit):
    base = native.state_dir() / native._checked(unit)
    return (
        base.with_suffix(".lock"),
        base.with_suffix(".json"),
        base.with_suffix(".spec.json"),
    )

native._paths = cut
sys.exit(native.main())
"""

needs_posix = pytest.mark.skipif(
    sys.platform == "win32", reason="the stand-in server is a script with a shebang"
)


def _old_paths(unit: str) -> tuple[Path, Path, Path]:
    base = native.state_dir() / unit
    return (
        base.with_suffix(".lock"),
        base.with_suffix(".json"),
        base.with_suffix(".spec.json"),
    )


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


def _spec(tmp_path: Path, unit: str, port: int) -> Path:
    service = {
        LAUNCHER_KEY: "native",
        PROGRAM_KEY: "llama-server",
        "container_name": unit,
        "command": ["--model", "/w/x.gguf", "--port", str(port), "--host", "127.0.0.1"],
        CARDS_KEY: [0],
    }
    path = tmp_path / "compose.box1.yml"
    path.write_text(yaml.safe_dump({"services": {"model": service}}))
    return path


def _until(check: object, budget: float = 20.0) -> bool:
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if check():  # type: ignore[operator]
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def stopped_after() -> Iterator[None]:
    yield
    native.stop(DOTTED)


def test_a_dotted_name_keeps_three_files_of_its_whole_name() -> None:
    lock, record, spec = native._paths(DOTTED)
    assert len({lock, record, spec}) == 3
    assert {lock.parent, record.parent, spec.parent} == {native.state_dir()}
    assert lock.name == f"{DOTTED}.lock"
    assert record.name == f"{DOTTED}.json"
    assert spec.name == f"{DOTTED}.spec.json"


def test_a_unit_read_back_from_its_record_is_its_whole_name() -> None:
    record = native._paths(DOTTED)[1]
    native._private(record.parent)
    record.write_text("{}")
    native._paths(DOTTED)[2].write_text("{}")
    assert native.units() == [DOTTED]


def test_two_units_of_one_model_on_two_ports_hold_a_lock_each() -> None:
    other = DOTTED[: -len("8080")] + "8081"
    assert native._paths(DOTTED)[0] != native._paths(other)[0]
    assert native._paths(DOTTED)[1] != native._paths(other)[1]


def test_a_name_with_no_dot_names_the_files_it_named_before() -> None:
    plain = "mcgyvr-box1-m-8080"
    assert native._paths(plain) == _old_paths(plain)
    assert native._cut(plain) is None


def test_a_cut_record_is_a_units_only_while_it_names_that_unit() -> None:
    lock, record, _spec = _old_paths(DOTTED)
    native._private(record.parent)
    record.write_text(f'{{"unit": "{DOTTED}"}}')
    assert native._cut(DOTTED) == (lock, record)
    other = DOTTED[: -len("8080")] + "8081"
    assert native._cut(other) is None


@needs_posix
def test_a_started_dotted_unit_counts_as_running_until_down(
    tmp_path: Path, stopped_after: None
) -> None:
    port = _port()
    programs = _programs(tmp_path)
    done = native.up(
        _spec(tmp_path, DOTTED, port), folder=lambda b: programs, build=lambda: BUILD
    )
    assert done.returncode == 0, done.stderr
    assert native.wait_answers(port, 20)
    # The door's gate 7 compares the declared units with these names.
    assert list(native.running().values()) == [DOTTED]
    (row,) = native.status()
    assert (row["unit"], row["state"], row["port"]) == (DOTTED, native.RUNNING, port)

    gone = native.down([DOTTED])
    assert gone.returncode == 0, gone.stderr
    assert native.running() == {}
    assert not native.answers(port)


def _old_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, port: int
) -> dict[str, object]:
    """Start DOTTED as an earlier mcgyvr did; its record."""
    programs = _programs(tmp_path)
    (unit,) = native.parse(_spec(tmp_path, DOTTED, port))
    with monkeypatch.context() as patched:
        patched.setattr(native, "_paths", _old_paths)
        said = native.start(
            unit,
            BUILD,
            programs,
            supervisor=(sys.executable, "-c", OLD_SUPERVISOR),
        )
    assert said is None, said
    assert native.wait_answers(port, 20)
    assert not native._paths(DOTTED)[1].exists()
    lock, record_file, _old_spec = _old_paths(DOTTED)
    assert native._held(lock)
    return native._record(record_file) or {}


@needs_posix
def test_an_old_supervisor_is_seen_and_stopped_by_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped_after: None
) -> None:
    port = _port()
    old = _old_start(tmp_path, monkeypatch, port)
    assert list(native.running().values()) == [CUT]
    assert [(r["unit"], r["state"]) for r in native.status()] == [(CUT, native.RUNNING)]

    gone = native.down([DOTTED])
    assert gone.returncode == 0, gone.stderr
    # The old supervisor is this test's child: its lock, not its pid, is asked.
    assert not native._held(_old_paths(DOTTED)[0])
    assert native.matches(old["server"]) is None
    assert not native.answers(port)
    assert native.running() == {}


@needs_posix
def test_up_stops_an_old_supervisor_before_it_starts_the_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped_after: None
) -> None:
    port = _port()
    old = _old_start(tmp_path, monkeypatch, port)
    done = native.up(
        _spec(tmp_path, DOTTED, port),
        folder=lambda b: tmp_path / "build",
        build=lambda: BUILD,
    )
    assert done.returncode == 0, done.stderr
    assert native.matches(old["server"]) is None
    assert not native._held(_old_paths(DOTTED)[0])
    assert native.wait_answers(port, 20)
    assert list(native.running().values()) == [DOTTED]
    record = native.read_record(DOTTED) or {}
    assert record["server"]["pid"] != old["server"]["pid"]  # type: ignore[index]
    assert record["server"]["start"] == hostos.process_start_time(
        record["server"]["pid"]
    )
