"""A pinned release is installed only as pinned, and held inside its folder.

An archive whose bytes do not hash to the committed sha256 is refused and
nothing is installed; a member that would land outside the folder is refused;
the programs are marked executable, and a second install with nothing changed
fetches nothing. On macOS the quarantine flag is removed from the folder with
``xattr -dr``; no other system is asked to.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import release
from tests.hostos_fakes import as_system
from tests.release_fakes import release_of, serving, tar_gz, zip_of

PROGRAMS = {"tool-server": b"#!/bin/sh\necho serving\n", "libtool.so": b"\x7fELF"}


def test_an_archive_whose_sha256_differs_is_refused_and_nothing_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"tool.tar.gz": tar_gz(PROGRAMS)}
    with serving(files) as port:
        pinned = release_of(monkeypatch, port, files, pinned={"tool.tar.gz": "0" * 64})
        with pytest.raises(release.ReleaseError, match="sha256"):
            release.install(
                pinned,
                ["tool.tar.gz"],
                tmp_path / "bin" / "v1",
                executables=["tool-server"],
            )
    assert not (tmp_path / "bin" / "v1").exists()
    assert not (tmp_path / "bin" / "v1.staging").exists()
    assert not (tmp_path / "bin" / release.DOWNLOADS / "tool.tar.gz").exists()


def test_a_name_not_pinned_is_never_fetched(tmp_path: Path) -> None:
    pinned = release.Release("example/tool", "v1", ())
    with pytest.raises(release.ReleaseError, match="not an archive pinned"):
        release.install(pinned, ["other.zip"], tmp_path / "v1", executables=[])


def test_a_pinned_archive_is_unpacked_flat_and_its_program_runnable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "tool.tar.gz": tar_gz(PROGRAMS),
        "runtime.zip": zip_of({"runtime/libcudart.so": b"rt"}),
    }
    folder = tmp_path / "bin" / "v1"
    with serving(files) as port:
        pinned = release_of(monkeypatch, port, files)
        got = release.install(
            pinned, ["tool.tar.gz", "runtime.zip"], folder, executables=["tool-server"]
        )
    assert got == folder
    assert (folder / "tool-server").read_bytes() == PROGRAMS["tool-server"]
    assert (folder / "libcudart.so").read_bytes() == b"rt"
    if sys.platform != "win32":
        assert os.stat(folder / "tool-server").st_mode & 0o100
        assert not os.stat(folder / "tool-server").st_mode & 0o022
        assert os.stat(folder.parent).st_mode & 0o077 == 0
    # The archives are gone once installed; a second install fetches nothing.
    assert not (folder.parent / release.DOWNLOADS / "tool.tar.gz").exists()
    monkeypatch.setattr(release, "_fetch", _no_fetch)
    assert (
        release.install(
            pinned, ["tool.tar.gz", "runtime.zip"], folder, executables=["tool-server"]
        )
        == folder
    )


def test_an_archive_with_its_folders_own_entry_is_unpacked_flat(
    tmp_path: Path,
) -> None:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        folder = tarfile.TarInfo("llama-b0")
        folder.type = tarfile.DIRTYPE
        tar.addfile(folder)
        server = tarfile.TarInfo("llama-b0/tool-server")
        server.size = 2
        tar.addfile(server, io.BytesIO(b"ok"))
    path = tmp_path / "tool.tar.gz"
    path.write_bytes(out.getvalue())
    into = tmp_path / "into"
    into.mkdir()
    release.unpack(path, into)
    assert (into / "tool-server").read_bytes() == b"ok"


def test_a_program_changed_after_install_is_installed_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"tool.tar.gz": tar_gz(PROGRAMS)}
    folder = tmp_path / "v1"
    with serving(files) as port:
        pinned = release_of(monkeypatch, port, files)
        release.install(pinned, ["tool.tar.gz"], folder, executables=["tool-server"])
        (folder / "tool-server").write_bytes(b"changed")
        release.install(pinned, ["tool.tar.gz"], folder, executables=["tool-server"])
    assert (folder / "tool-server").read_bytes() == PROGRAMS["tool-server"]


def test_an_archive_lacking_a_program_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"tool.tar.gz": tar_gz({"README": b"x"})}
    with serving(files) as port:
        pinned = release_of(monkeypatch, port, files)
        with pytest.raises(release.ReleaseError, match="holds no tool-server"):
            release.install(
                pinned, ["tool.tar.gz"], tmp_path / "v1", executables=["tool-server"]
            )
    assert not (tmp_path / "v1").exists()


def _evil_tar(name: str, *, link: str | None = None) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        if link is None:
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        else:
            info.type = tarfile.SYMTYPE
            info.linkname = link
            tar.addfile(info)
    return out.getvalue()


EVIL = {
    "climbs": ("../escaped", None),
    "absolute": ("/etc/escaped", None),
    "links-up": ("top/lib.so", "../../outside"),
    "links-absolute": ("top/lib.so", "/etc/passwd"),
}


@pytest.mark.parametrize("shape", sorted(EVIL))
def test_a_member_that_would_land_outside_the_folder_is_refused(
    tmp_path: Path, shape: str
) -> None:
    name, link = EVIL[shape]
    path = tmp_path / "evil.tar.gz"
    path.write_bytes(_evil_tar(name, link=link))
    into = tmp_path / "into"
    into.mkdir()
    with pytest.raises(release.ReleaseError):
        release.unpack(path, into)
    assert not (tmp_path / "escaped").exists()


def test_a_zip_member_climbing_out_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    path.write_bytes(zip_of({"../escaped": b"x"}))
    into = tmp_path / "into"
    into.mkdir()
    with pytest.raises(release.ReleaseError, match="climbs out"):
        release.unpack(path, into)
    assert not (tmp_path / "escaped").exists()


class _Ran:
    def __init__(self) -> None:
        self.argv: list[list[str]] = []

    def __call__(self, argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        self.argv.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_the_quarantine_flag_is_removed_on_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = _Ran()
    monkeypatch.setattr(subprocess, "run", ran)
    as_system(monkeypatch, "darwin")
    assert release.strip_quarantine(tmp_path) is True
    assert ran.argv == [
        ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(tmp_path)]
    ]


@pytest.mark.parametrize("system", ["linux", "windows"])
def test_no_other_system_is_asked_to_remove_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str
) -> None:
    ran = _Ran()
    monkeypatch.setattr(subprocess, "run", ran)
    as_system(monkeypatch, system)
    assert release.strip_quarantine(tmp_path) is None
    assert ran.argv == []


def test_an_install_on_macos_strips_the_flag_before_the_folder_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"tool.tar.gz": tar_gz(PROGRAMS)}
    stripped: list[Path] = []
    monkeypatch.setattr(release, "strip_quarantine", lambda f: stripped.append(f))
    with serving(files) as port:
        pinned = release_of(monkeypatch, port, files)
        folder = release.install(
            pinned, ["tool.tar.gz"], tmp_path / "v1", executables=["tool-server"]
        )
    assert stripped == [tmp_path / "v1.staging"]
    assert hashlib.sha256((folder / "tool-server").read_bytes()).hexdigest()


def _no_fetch(*_a: Any, **_k: Any) -> Path:
    raise AssertionError("an installed folder fetched again")
