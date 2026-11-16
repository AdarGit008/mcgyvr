"""The no-docker stage is this user's own folder, resolved where the launcher runs.

With ``MCGYVR_NATIVE_STAGE`` on, the build and the launcher copy go to
``<tmp>/mcgyvr-native-<uid>`` (:func:`mcgyvr.userdir.user_tempdir`), one folder
per user. The temp root is shared by every local user, so the folder is used
only once it is this user's alone: another user's folder, a link, or one others
may write into is refused before anything is read, fetched into or run from it,
a build planted there that looks current included. The variable is a flag: any
value but ``1`` leaves the mcgyvr home in place, a path among them.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

import pytest

from mcgyvr import hostos, userdir
from mcgyvr.serving import llamacpp, native, release

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="owners and modes are POSIX's to check"
)


@pytest.fixture
def tmp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temp root the stage is made under, and the mcgyvr home beside it."""
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    return root


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The archives a build install fetched; none is served."""
    asked: list[str] = []

    def fetch(_release: object, asset: release.Asset, _downloads: Path) -> Path:
        asked.append(asset.name)
        raise release.ReleaseError("no archive is served here")

    monkeypatch.setattr(release, "_fetch", fetch)
    return asked


def _build() -> llamacpp.Build:
    return next(b for b in llamacpp.BUILDS if b.backend == llamacpp.CPU)


def test_two_users_get_two_stage_folders(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folders = []
    for uid in ("1000", "1001"):
        monkeypatch.setattr(hostos, "current_user_id", lambda uid=uid: uid)
        assert native.stage_dir() == userdir.user_tempdir(native.STAGE_PURPOSE)
        folders.append(native.stage_dir())
    assert folders == [tmp_root / "mcgyvr-native-1000", tmp_root / "mcgyvr-native-1001"]


@posix_only
def test_the_stage_is_made_this_users_alone_before_a_build_is_looked_for(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch, fetched: list[str]
) -> None:
    monkeypatch.setenv(native.STAGE_ENV, native.STAGE_ON)
    with pytest.raises(native.NativeError, match="no archive is served"):
        native.binaries(_build())
    stage = native.stage_dir()
    assert userdir.owned_outright(stage)
    assert os.stat(stage).st_mode & 0o077 == 0
    assert fetched == [_build().assets[0]]
    assert native.bin_root() == stage / native.BIN / llamacpp.TAG


def _another_users(stage: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage.mkdir(mode=0o700)
    mine = hostos.owned_by_current_user
    monkeypatch.setattr(
        hostos,
        "owned_by_current_user",
        lambda found: mine(found) and found.st_ino != os.lstat(stage).st_ino,
    )


def _a_link(stage: Path, _monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = stage.parent / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    stage.symlink_to(elsewhere, target_is_directory=True)


def _open_to_others(stage: Path, _monkeypatch: pytest.MonkeyPatch) -> None:
    stage.mkdir()
    stage.chmod(0o777)


@posix_only
@pytest.mark.parametrize("taken", [_another_users, _a_link, _open_to_others])
def test_a_stage_not_this_users_alone_is_refused_before_anything_is_fetched(
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    fetched: list[str],
    taken: object,
) -> None:
    taken(native.stage_dir(), monkeypatch)  # type: ignore[operator]
    monkeypatch.setenv(native.STAGE_ENV, native.STAGE_ON)
    with pytest.raises(native.NativeError, match="not this user's own folder"):
        native.binaries(_build())
    with pytest.raises(native.NativeError, match="not this user's own folder"):
        native._settle(b"print('launcher')\n")
    assert fetched == []
    assert not (native.stage_dir() / native.BIN).exists()


@posix_only
def test_a_build_planted_in_a_stage_others_may_write_is_refused_not_used(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch, fetched: list[str]
) -> None:
    stage = native.stage_dir()
    _open_to_others(stage, monkeypatch)
    build = _build()
    folder = stage / native.BIN / llamacpp.TAG / build.name
    folder.mkdir(parents=True)
    recorded = {}
    for program in llamacpp.EXECUTABLES:
        path = folder / hostos.exe(program)
        path.write_bytes(b"#!/bin/sh\necho planted\n")
        recorded[program] = hashlib.sha256(path.read_bytes()).hexdigest()
    wanted = [llamacpp.RELEASE.asset(name) for name in build.assets]
    (folder / release.RECORD).write_text(
        json.dumps(
            {
                "repo": llamacpp.RELEASE.repo,
                "tag": llamacpp.RELEASE.tag,
                "assets": {a.name: a.sha256 for a in wanted},
                "executables": recorded,
            }
        ),
        encoding="utf-8",
    )
    # It looks current: the install by itself would hand it back unfetched.
    assert (
        release.install(
            llamacpp.RELEASE,
            build.assets,
            folder,
            executables=llamacpp.EXECUTABLES,
        )
        == folder
    )
    monkeypatch.setenv(native.STAGE_ENV, native.STAGE_ON)
    with pytest.raises(native.NativeError, match="not this user's own folder"):
        native.binaries(build)
    assert fetched == []


@pytest.mark.parametrize(
    "value", [None, "", "0", "/var/folders/zz/abc/T/mcgyvr-native"]
)
def test_any_value_but_on_keeps_the_mcgyvr_home(
    tmp_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(native.STAGE_ENV, raising=False)
    else:
        monkeypatch.setenv(native.STAGE_ENV, value)
    assert not native.staged()
    assert native.bin_root() == tmp_path / "home" / native.BIN / llamacpp.TAG
    assert list(tmp_root.iterdir()) == []


def _supervised(program: Path, unit: str) -> tuple[Path, Path]:
    """A spec for `program` that restarts once, quickly; its spec and log."""
    native._private(native.state_dir())
    log = native.log_path(unit)
    native._private(log.parent)
    spec = {
        "unit": unit,
        "program": str(program),
        "argv": [],
        "env": {},
        "port": 18999,
        "backend": llamacpp.CPU,
        "build": "x",
        "tag": llamacpp.TAG,
        "log": str(log),
        "max_restarts": 1,
        "backoff_s": 0.05,
        "backoff_max_s": 0.05,
        "reset_after_s": 60.0,
    }
    spec_file = native.state_dir() / f"{unit}.spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    return spec_file, log


def _staged_program(monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    monkeypatch.setenv(native.STAGE_ENV, native.STAGE_ON)
    monkeypatch.setattr(signal, "signal", lambda *_: None)
    folder = native._private(native._private(native.bin_root()) / "x")
    program = folder / "llama-server"
    program.write_text(body, encoding="utf-8")
    program.chmod(0o700)
    return program


@posix_only
def test_a_restart_from_a_stage_no_longer_this_users_alone_is_refused(
    tmp_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first run stands for a /tmp cleaned by age and the folder made
    # again by somebody else: the stage opens to others, the program is swapped.
    marker = tmp_path / "planted-ran"
    program = _staged_program(monkeypatch, "")
    stage = native.stage_dir()
    program.write_text(
        "#!/bin/sh\n"
        f"chmod 0777 '{stage}'\n"
        f"printf '#!/bin/sh\\ntouch {marker}\\nexit 1\\n' > '{program}.new'\n"
        f"chmod +x '{program}.new'; mv '{program}.new' '{program}'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    spec_file, log = _supervised(program, "mcgyvr-swap")
    assert native.supervise(spec_file) == 1
    assert not marker.exists()
    record = json.loads((native.state_dir() / "mcgyvr-swap.json").read_text())
    assert record["state"] == native.FAILED
    assert "not this user's own folder" in record["why"]
    assert "not started" in log.read_text()


@posix_only
def test_a_restart_of_a_program_turned_into_a_link_is_refused(
    tmp_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    elsewhere.chmod(0o700)
    program = _staged_program(monkeypatch, "")
    program.write_text(
        f"#!/bin/sh\nrm '{program}'; ln -s '{elsewhere}' '{program}'\nexit 1\n",
        encoding="utf-8",
    )
    spec_file, _log = _supervised(program, "mcgyvr-link")
    assert native.supervise(spec_file) == 1
    record = json.loads((native.state_dir() / "mcgyvr-link.json").read_text())
    assert record["state"] == native.FAILED
    assert "a link" in record["why"]


@posix_only
def test_the_stage_is_held_with_a_shared_lock_while_its_server_runs(
    tmp_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # What a /tmp cleaned by age (systemd-tmpfiles) does before it removes a
    # folder: an exclusive lock, not waited for. Another supervisor's shared
    # lock is still had.
    said = tmp_path / "said"
    probe = (
        "import fcntl, os, sys\n"
        "fd = os.open(sys.argv[1], os.O_RDONLY)\n"
        "out = []\n"
        "for name, how in (('exclusive', fcntl.LOCK_EX), ('shared', fcntl.LOCK_SH)):\n"
        "    try:\n"
        "        fcntl.flock(fd, how | fcntl.LOCK_NB)\n"
        "        out.append(name + ' had')\n"
        "        fcntl.flock(fd, fcntl.LOCK_UN)\n"
        "    except BlockingIOError:\n"
        "        out.append(name + ' refused')\n"
        "open(sys.argv[2], 'a').write(', '.join(out) + '\\n')\n"
    )
    script = tmp_path / "probe.py"
    script.write_text(probe, encoding="utf-8")
    stage = native.stage_dir()
    program = _staged_program(
        monkeypatch,
        f"#!/bin/sh\n'{sys.executable}' '{script}' '{stage}' '{said}'\nexit 1\n",
    )
    spec_file, log = _supervised(program, "mcgyvr-held")
    assert native.supervise(spec_file) == 1
    assert said.exists(), log.read_text()
    assert said.read_text().splitlines() == ["exclusive refused, shared had"] * 2
    record = json.loads((native.state_dir() / "mcgyvr-held.json").read_text())
    assert record["state"] == native.GAVE_UP
