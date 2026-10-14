"""A file written through ``atomic.write`` is whole or untouched, and leaves no litter.

Every file mcgyvr keeps for a later reader goes through this one routine, so
these pin what each of them relied on: the old file survives a failed write,
no staging file outlives the call, a private file is never wider than its
owner, and bytes land exactly as given.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from mcgyvr import atomic


def test_the_target_holds_the_new_text_after_the_write(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("old\n", encoding="utf-8")

    atomic.write(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_text_is_written_as_utf_8_and_bytes_as_given(tmp_path: Path) -> None:
    text = tmp_path / "text"
    raw = tmp_path / "raw"

    atomic.write(text, "café\r\nline\n")
    atomic.write(raw, b"\x00\xff\r\n")

    assert text.read_bytes() == "café\r\nline\n".encode()
    assert raw.read_bytes() == b"\x00\xff\r\n"


def test_a_failed_replace_leaves_no_staging_file_and_raises(tmp_path: Path) -> None:
    taken = tmp_path / "taken"
    taken.mkdir()

    with pytest.raises(OSError):
        atomic.write(taken, "x")

    assert [p.name for p in tmp_path.iterdir()] == ["taken"]


def test_an_interrupted_write_keeps_the_old_file_and_leaves_no_staging_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "kept"
    target.write_text("old", encoding="utf-8")

    def interrupted(fd: int, data: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "write", interrupted)
    with pytest.raises(KeyboardInterrupt):
        atomic.write(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["kept"]


def test_a_private_file_is_readable_by_its_owner_alone(tmp_path: Path) -> None:
    previous = os.umask(0)
    try:
        target = tmp_path / "credentials.json"
        atomic.write(target, "secret\n", private=True, fsync=True)
    finally:
        os.umask(previous)

    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR


def test_an_ordinary_file_follows_the_umask(tmp_path: Path) -> None:
    previous = os.umask(0o022)
    try:
        target = tmp_path / "plain"
        atomic.write(target, "x")
    finally:
        os.umask(previous)

    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_a_stale_staging_file_at_a_named_staging_path_is_replaced(
    tmp_path: Path,
) -> None:
    target = tmp_path / "board.json"
    staging = tmp_path / "board.json.1.1.tmp"
    staging.write_text("left by a dead writer", encoding="utf-8")

    atomic.write(target, "fresh", staging=staging)

    assert target.read_text(encoding="utf-8") == "fresh"
    assert not staging.exists()


def test_a_link_at_the_staging_path_is_not_followed(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("untouched", encoding="utf-8")
    staging = tmp_path / ".part"
    staging.symlink_to(elsewhere)
    target = tmp_path / "target"

    atomic.write(target, "new", private=True, staging=staging)

    assert elsewhere.read_text(encoding="utf-8") == "untouched"
    assert target.read_text(encoding="utf-8") == "new"
