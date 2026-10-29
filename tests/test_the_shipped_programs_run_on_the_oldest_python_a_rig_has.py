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


@needs39
def test_the_native_build_is_hashed_and_unpacked_on_3_9(tmp_path: Path) -> None:
    import hashlib
    import io
    import tarfile

    assert PYTHON39 is not None
    archive = tmp_path / "build.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        body = b"#!/bin/sh\n"
        info = tarfile.TarInfo("llama-b1-bin/llama-server")
        info.size, info.mode = len(body), 0o755
        tar.addfile(info, io.BytesIO(body))
    tail = (
        "import sys\nfrom pathlib import Path\n"
        f"print(sha256_of(Path({str(archive)!r})))\n"
        f"_unpack_tar(Path({str(archive)!r}), Path({str(tmp_path / 'out')!r}))\n"
    )
    program = shipped.program(
        "mcgyvr.serving.release",
        modules=("mcgyvr.hostos", "mcgyvr.userdir", "mcgyvr.serving.fetcher"),
        tail=tail,
    )
    (tmp_path / "out").mkdir()
    done = subprocess.run(
        [PYTHON39, "-I", "-B", "-"],
        input=program,
        capture_output=True,
        env={"HOME": str(tmp_path)},
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert (
        done.stdout.decode().strip() == hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    assert (tmp_path / "out" / "llama-server").read_bytes() == b"#!/bin/sh\n"


def test_a_python_without_the_tar_data_filter_unpacks_files_and_refuses_devices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import io
    import tarfile

    from mcgyvr.serving import release

    monkeypatch.delattr(tarfile, "data_filter")  # macOS's own 3.9.6 has none
    archive = tmp_path / "build.tar"
    with tarfile.open(archive, "w") as tar:
        body = b"#!/bin/sh\n"
        info = tarfile.TarInfo("top/llama-server")
        info.size, info.mode = len(body), 0o4755
        tar.addfile(info, io.BytesIO(body))
    (tmp_path / "out").mkdir()
    release._unpack_tar(archive, tmp_path / "out")
    unpacked = tmp_path / "out" / "llama-server"
    assert unpacked.read_bytes() == b"#!/bin/sh\n"
    assert not unpacked.stat().st_mode & 0o4000  # no set-user-id carried
    device = tmp_path / "device.tar"
    with tarfile.open(device, "w") as tar:
        info = tarfile.TarInfo("top/disk")
        info.type = tarfile.CHRTYPE
        tar.addfile(info)
    with pytest.raises(release.ReleaseError, match="not a file, a folder or a link"):
        release._unpack_tar(device, tmp_path / "out")


@needs39
@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in server has a shebang")
def test_up_starts_a_supervised_unit_on_3_9_and_down_stops_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import socket

    from mcgyvr import hostos
    from mcgyvr.serving import llamacpp, native, release

    assert PYTHON39 is not None
    env = {
        "HOME": str(tmp_path),
        "MCGYVR_HOME": str(tmp_path / "home"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        native.BACKEND_ENV: llamacpp.CPU,
        "PATH": str(tmp_path / "no-tools"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # The pinned CPU build of this machine, already in place (as a first `up`
    # leaves it), so nothing is fetched: a stand-in server, recorded as the
    # release's own unpacking records it.
    build = llamacpp.build_for(
        hostos.os_name(), native.machine_arch(), llamacpp.CPU, nvidia_driver=None
    )
    folder = native.bin_root() / build.name
    folder.mkdir(parents=True)
    fake = Path(__file__).with_name("fake_llama_server.py").read_text("utf-8")
    for program in llamacpp.EXECUTABLES:
        (folder / program).write_text(f"#!{sys.executable}\n{fake}", "utf-8")
        (folder / program).chmod(0o755)
    record = {
        "repo": llamacpp.RELEASE.repo,
        "tag": llamacpp.RELEASE.tag,
        "assets": {a: llamacpp.RELEASE.asset(a).sha256 for a in build.assets},
        "executables": {
            p: hashlib.sha256((folder / p).read_bytes()).hexdigest()
            for p in llamacpp.EXECUTABLES
        },
    }
    (folder / release.RECORD).write_text(json.dumps(record), "utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    unit = native.NativeUnit(
        name="m",
        container="mcgyvr-box1-m",
        program=llamacpp.SERVER,
        argv=("--model", "/w/x.gguf", "--port", str(port), "--host", "127.0.0.1"),
        env={},
        port=port,
        cards=(),
        depends_on=(),
        asleep=False,
    )
    launcher = shipped.packed(shipped.native())

    def verb(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [PYTHON39, "-I", "-B", "-", *args],
            input=launcher,
            capture_output=True,
            env=env,
            timeout=120,
            check=False,
        )

    try:
        up = verb("up", native.units_text([unit]))
        assert up.returncode == 0, up.stderr
        found = native.read_record(unit.container) or {}
        assert found["state"] == native.RUNNING
        # The supervisor is the copy the launcher left, on 3.9.
        (copy,) = (tmp_path / "home" / native.SHIPPED).iterdir()
        assert native.supervised(unit.container)
        assert found["supervisor"]["program"] == PYTHON39
        assert native.wait_answers(port, 30)
        assert copy.name.startswith("native-")
    finally:
        down = verb("down", unit.container)
    assert down.returncode == 0, down.stderr
    assert not native.supervised(unit.container)
