"""The shipped programs run on the oldest Python a rig has: macOS's own 3.9.

A non-login ssh shell on a Mac finds ``/usr/bin/python3`` first, the Command
Line Tools' Python 3.9, so every program the door ships (the reader, the lease,
the fetcher, the native launcher) is assembled to run there
(``shipped.FLOOR``), and refuses a Python older still with a sentence instead
of a traceback. Here each runs on a Python 3.9 when this machine has one (``uv
python find 3.9``; the test is skipped without it), over invented machines,
and reads what it reads on the newest Python too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib, shipped
from tests.machine_shapes import host_shape, host_shapes, shape
from tests.machinereader import run, stage, stage_host


def _python39() -> str | None:
    found = shutil.which("python3.9")
    if found:
        return found
    uv = shutil.which("uv")
    if uv is None:
        return None
    done = subprocess.run(
        [uv, "python", "find", "--no-project", "3.9"],
        capture_output=True,
        text=True,
        check=False,
    )
    path = done.stdout.strip()
    return path if done.returncode == 0 and path else None


PYTHON39 = _python39()
needs39 = pytest.mark.skipif(PYTHON39 is None, reason="no Python 3.9 on this machine")


def test_the_floor_is_macos_own_python() -> None:
    assert shipped.FLOOR == (3, 9)


def test_a_python_older_than_the_floor_is_refused_with_a_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shipped, "FLOOR", (sys.version_info[0], sys.version_info[1] + 1)
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-"],
        input=shipped.packed(shipped.lease()),
        capture_output=True,
        check=False,
    )
    assert done.returncode == 127
    assert b"needs Python" in done.stderr
    assert b"Traceback" not in done.stderr


@needs39
@pytest.mark.parametrize(
    "label",
    ["one-card", *(m.label for m in host_shapes())],
)
def test_the_reader_reads_on_3_9_as_on_this_python(tmp_path: Path, label: str) -> None:
    assert PYTHON39 is not None
    staged = (
        stage(shape(label)) if label == "one-card" else stage_host(host_shape(label))
    )
    old = run(staged, tmp_path / "old", command=(PYTHON39, "-I", "-B", "-", "--cards"))
    new = run(staged, tmp_path / "new")
    assert old.returncode == 0, old.stderr
    assert json.loads(old.stdout) == json.loads(new.stdout)


@needs39
def test_the_lease_takes_reads_stamps_and_releases_on_3_9(tmp_path: Path) -> None:
    assert PYTHON39 is not None
    lease = gatelib.new_lease("up", 4242)
    program = shipped.packed(shipped.lease())

    def op(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [PYTHON39, "-I", "-B", "-", *args],
            input=program,
            capture_output=True,
            env={"HOME": str(tmp_path)},
            check=False,
        )

    assert op("take_free", gatelib.LEASE_DIR, f"line={lease.line()}").returncode == 0
    assert op("take_free", gatelib.LEASE_DIR, f"line={lease.line()}").returncode == 1
    read = op("read", gatelib.LEASE_DIR)
    assert read.stdout.decode() == lease.line() + "\n"
    stamped = f"line={lease.line()}x"
    assert (
        op("stamp", gatelib.LEASE_DIR, f"held={lease.lease_id}", stamped).returncode
        == 0
    )
    assert op("release", gatelib.LEASE_DIR, f"held={lease.lease_id}").returncode == 0
    assert not (tmp_path / ".mcgyvr" / "lease").exists()


@needs39
def test_the_fetcher_runs_on_3_9_and_reports_its_job(tmp_path: Path) -> None:
    assert PYTHON39 is not None
    job = json.dumps({"files": [], "token_env": "HF_TOKEN", "token": ""})
    done = subprocess.run(
        [PYTHON39, "-I", "-B", "-", "mcgyvr-fetch"],
        input=shipped.fetcher(job),
        capture_output=True,
        text=False,
        env={"HOME": str(tmp_path), "MCGYVR_WEIGHTS": str(tmp_path / "w")},
        check=False,
    )
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout.decode().strip().splitlines()[-1])
    assert said["files"] == []


@needs39
def test_the_native_launcher_answers_its_verbs_on_3_9(tmp_path: Path) -> None:
    assert PYTHON39 is not None
    program = shipped.packed(shipped.native())
    for args in (["units"], ["status"], ["down", "mcgyvr-box1-m-8080"]):
        done = subprocess.run(
            [PYTHON39, "-I", "-B", "-", *args],
            input=program,
            capture_output=True,
            env={"HOME": str(tmp_path), "PATH": str(tmp_path)},
            check=False,
        )
        assert done.returncode == 0, (args, done.stderr)
