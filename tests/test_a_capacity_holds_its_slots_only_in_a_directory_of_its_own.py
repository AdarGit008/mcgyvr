"""A capacity holds its slots only in a directory this user owns outright.

Slot files live under the temporary directory, which every local user shares.
A directory another user made first, or a symlink, would let somebody else
hold this user's slots or plant one, so such a directory is refused by name
rather than used, and a missing one is made 0700. A directory of this user's
own that others may write into (an older mcgyvr made it under the umask) is
narrowed to 0700. Each slot file is made 0600, is never opened through a
symlink, and one another user owns is refused, so no other user can hold a
slot.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, CapacityError, SlotUnavailableError
from mcgyvr.local_pool import Endpoint, Protocol

UNIT = Endpoint(
    source="local",
    base_url="http://localhost/local",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def test_a_missing_directory_is_made_private_and_its_slots_are_private(
    tmp_path: Path,
) -> None:
    where = tmp_path / "capacity-locks"
    capacity = Capacity({"local": 1}, lock_dir=where)
    with capacity.hold(UNIT):
        pass
    assert _mode(where) == 0o700
    slots = sorted(where.glob("*.slot"))
    assert slots, "the hold took no slot file"
    assert all(_mode(slot) == 0o600 for slot in slots)


def test_a_directory_another_user_owns_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = tmp_path / "capacity-locks"
    where.mkdir(mode=0o700)
    someone_else = os.getuid() + 1
    monkeypatch.setattr(os, "getuid", lambda: someone_else)
    capacity = Capacity({"local": 1}, lock_dir=where)
    with pytest.raises(CapacityError) as refused, capacity.hold(UNIT):
        pass
    assert not isinstance(refused.value, SlotUnavailableError)
    assert str(where) in str(refused.value)
    assert "Remove it" in str(refused.value)
    assert not list(where.iterdir()), "a slot file was made in a refused directory"
    assert _mode(where) == 0o700, "another user's directory had its mode changed"


@pytest.mark.parametrize("mode", [0o775, 0o777])
def test_a_directory_of_this_users_own_that_others_may_write_into_is_narrowed(
    tmp_path: Path, mode: int
) -> None:
    where = tmp_path / "capacity-locks"
    where.mkdir()
    where.chmod(mode)
    capacity = Capacity({"local": 1}, lock_dir=where)
    with capacity.hold(UNIT):
        assert capacity.in_flight("local") == 1
    assert _mode(where) == 0o700


def test_a_slot_file_another_user_owns_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = tmp_path / "capacity-locks"
    capacity = Capacity({"local": 1}, lock_dir=where)
    with capacity.hold(UNIT):
        pass
    (slot,) = where.glob("*.slot")
    real_fstat = os.fstat
    owner = os.getuid() + 1

    def fstat(fd: int) -> os.stat_result:
        found = real_fstat(fd)
        if stat.S_ISREG(found.st_mode):
            fields = list(found)
            fields[stat.ST_UID] = owner
            return os.stat_result(fields)
        return found

    monkeypatch.setattr(os, "fstat", fstat)
    with pytest.raises(CapacityError) as refused, capacity.hold(UNIT):
        pass
    assert str(slot) in str(refused.value)


def test_a_symlinked_directory_is_refused_by_name(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere"
    real.mkdir(mode=0o700)
    where = tmp_path / "capacity-locks"
    where.symlink_to(real)
    capacity = Capacity({"local": 1}, lock_dir=where)
    with pytest.raises(CapacityError) as refused, capacity.hold(UNIT):
        pass
    assert str(where) in str(refused.value)
    assert not list(real.iterdir())


def test_a_slot_file_planted_as_a_symlink_is_not_followed(tmp_path: Path) -> None:
    where = tmp_path / "capacity-locks"
    capacity = Capacity({"local": 1}, lock_dir=where)
    with capacity.hold(UNIT):
        pass
    (slot,) = where.glob("*.slot")
    slot.unlink()
    target = tmp_path / "chosen-by-somebody-else"
    slot.symlink_to(target)
    with pytest.raises(CapacityError) as refused, capacity.hold(UNIT):
        pass
    assert str(slot) in str(refused.value)
    assert not target.exists(), "the slot was opened through the planted symlink"


def test_a_directory_of_this_users_own_made_by_an_older_version_still_serves(
    tmp_path: Path,
) -> None:
    """An existing 0755 directory of this user's own passes: nobody else can
    write into it, so nothing about the upgrade stops a run."""
    where = tmp_path / "capacity-locks"
    where.mkdir()
    where.chmod(0o755)
    capacity = Capacity({"local": 1}, lock_dir=where)
    with capacity.hold(UNIT):
        assert capacity.in_flight("local") == 1
