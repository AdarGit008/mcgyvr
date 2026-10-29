"""hostos keeps a user's files to that user, by what each system can tell.

POSIX tells a file's owner by uid and who else may read it by its mode, and
refuses a link with ``O_NOFOLLOW``. Windows' ``st_uid`` is always 0 and its
mode says only read-only, so ownership and privacy are the profile ACL's and
these answers say so; a link is refused there by checking the file once open.
"""

from __future__ import annotations

import errno
import getpass
import os
import stat
import sys
from pathlib import Path
from typing import cast

import pytest

from mcgyvr import hostos
from tests.hostos_fakes import as_system

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX ids and modes")
links = pytest.mark.skipif(sys.platform == "win32", reason="needs a symlink")


def _facts(uid: int, mode: int) -> os.stat_result:
    return os.stat_result((stat.S_IFREG | mode, 1, 1, 1, uid, 0, 0, 0, 0, 0))


@posix
def test_a_posix_user_is_its_uid() -> None:
    assert hostos.current_user_id() == str(os.getuid())
    assert hostos.posix_ids() == (os.getuid(), os.getgid())


@pytest.mark.parametrize(
    ("login", "named"),
    [("Ada Lovelace", "ada_lovelace"), ("dev\\ada", "dev_ada"), ("", "user")],
)
def test_a_windows_user_is_its_login_name_safe_for_a_folder(
    login: str, named: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    monkeypatch.setattr(getpass, "getuser", lambda: login)
    assert hostos.current_user_id() == named
    assert hostos.posix_ids() is None


def test_a_windows_user_with_no_readable_name_is_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "windows")

    def unreadable() -> str:
        raise OSError("no login name")

    monkeypatch.setattr(getpass, "getuser", unreadable)
    assert hostos.current_user_id() == "user"


@posix
def test_posix_owns_by_uid_and_counts_group_and_other_bits(tmp_path: Path) -> None:
    mine = tmp_path / "mine"
    mine.write_text("x")
    os.chmod(mine, 0o640)
    assert hostos.owned_by_current_user(os.stat(mine))
    assert not hostos.owned_by_current_user(_facts(os.getuid() + 1, 0o600))
    assert hostos.others_mode_bits(os.stat(mine)) == 0o040
    assert hostos.others_mode_bits(_facts(0, 0o666), stat.S_IWGRP | stat.S_IWOTH) == (
        0o022
    )


def test_windows_leaves_owner_and_privacy_to_the_profile_acl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "windows")
    assert hostos.owned_by_current_user(_facts(12345, 0o666))
    assert hostos.others_mode_bits(_facts(0, 0o777)) == 0


@posix
def test_posix_narrows_a_file_a_descriptor_and_a_folder_to_the_owner(
    tmp_path: Path,
) -> None:
    by_path, by_fd, folder = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    by_path.write_text("x")
    by_fd.write_text("x")
    folder.mkdir()
    for made in (by_path, by_fd, folder):
        os.chmod(made, 0o777)
    hostos.chmod_private(by_path)
    fd = os.open(by_fd, os.O_RDONLY)
    try:
        hostos.chmod_private(fd)
    finally:
        os.close(fd)
    hostos.chmod_private(folder, directory=True)
    assert stat.S_IMODE(by_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(by_fd.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


@posix
def test_windows_changes_no_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kept = tmp_path / "kept"
    kept.write_text("x")
    os.chmod(kept, 0o644)
    as_system(monkeypatch, "windows")
    hostos.chmod_private(kept)
    assert stat.S_IMODE(kept.stat().st_mode) == 0o644


def test_the_open_flags_are_the_systems_own_or_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hostos.open_flags_nofollow() == getattr(os, "O_NOFOLLOW", 0)
    assert hostos.open_flags_nonblock() == getattr(os, "O_NONBLOCK", 0)
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    monkeypatch.delattr(os, "O_NONBLOCK", raising=False)
    assert hostos.open_flags_nofollow() == 0
    assert hostos.open_flags_nonblock() == 0


@pytest.fixture(params=["kernel", "checked"])
def nofollow(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Both ways a link is refused: by O_NOFOLLOW, and by the check once open."""
    if request.param == "checked":
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    elif not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("this system has no O_NOFOLLOW")
    return str(request.param)


@links
def test_a_link_is_refused_and_nothing_is_left_open(
    nofollow: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_text("secret")
    link = tmp_path / "link"
    link.symlink_to(target)
    closed: list[int] = []
    real_close = os.close

    def close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "close", close)
    with pytest.raises(OSError) as raised:
        hostos.open_nofollow(link, os.O_RDONLY)
    assert raised.value.errno == errno.ELOOP
    if nofollow == "checked":
        assert len(closed) == 1


def test_a_plain_file_opens_and_is_created_as_asked(
    nofollow: str, tmp_path: Path
) -> None:
    plain = tmp_path / "plain"
    plain.write_text("kept")
    fd = hostos.open_nofollow(plain, os.O_RDONLY)
    try:
        assert os.read(fd, 4) == b"kept"
    finally:
        os.close(fd)
    made = tmp_path / "made"
    fd = hostos.open_nofollow(made, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    assert made.is_file()


@links
def test_a_path_naming_another_file_once_open_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    plain = tmp_path / "plain"
    plain.write_text("kept")
    other = tmp_path / "other"
    other.write_text("other")
    real_open = os.open

    def open_then_swap(
        path: str | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        fd = real_open(path, flags, mode)
        os.replace(other, plain)
        return fd

    monkeypatch.setattr(os, "open", open_then_swap)
    with pytest.raises(OSError) as raised:
        hostos.open_nofollow(plain, os.O_RDONLY)
    assert raised.value.errno == errno.ELOOP


class _Seen:
    """What ``lstat`` gives on Windows for a folder that may be a junction."""

    def __init__(self, tag: int) -> None:
        self.st_mode = stat.S_IFDIR | 0o777
        self.st_uid = 0
        self.st_reparse_tag = tag


@pytest.mark.parametrize(
    ("tag", "link"),
    [(0, False), (0xA000_0003, True), (0xA000_000C, True), (0x9000_601A, False)],
)
def test_windows_counts_a_junction_as_a_link_and_a_cloud_file_as_none(
    tag: int, link: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import userdir

    as_system(monkeypatch, "windows")
    seen = cast(os.stat_result, _Seen(tag))
    assert hostos.is_link(seen) is link
    monkeypatch.setattr(os, "lstat", lambda _path: seen)
    assert userdir.owned_outright(tmp_path) is not link


def test_posix_counts_no_reparse_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    as_system(monkeypatch, "linux")
    assert not hostos.is_link(cast(os.stat_result, _Seen(0xA000_0003)))


def test_a_file_opened_where_there_is_o_binary_is_opened_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert hostos.open_flags_binary() == getattr(os, "O_BINARY", 0)
    monkeypatch.setattr(os, "O_BINARY", 0x8000, raising=False)
    asked: list[int] = []
    real_open = os.open

    def recording(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        asked.append(flags)
        return real_open(path, flags & ~0x8000, mode)

    monkeypatch.setattr(os, "open", recording)
    plain = tmp_path / "plain"
    plain.write_text("kept")
    os.close(hostos.open_nofollow(plain, os.O_RDONLY))
    assert asked and asked[0] & 0x8000
