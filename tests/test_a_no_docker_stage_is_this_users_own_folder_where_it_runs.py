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
