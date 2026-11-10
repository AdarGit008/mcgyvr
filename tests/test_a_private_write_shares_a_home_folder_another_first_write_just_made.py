"""Two first writes at once share the home folder one of them makes.

``rig join`` and a service's ``rig run`` can both make the first file in a
home folder that does not exist yet. Both see no folder; the one that calls
``mkdir`` second used to fail with ``FileExistsError`` and lose its write
(``tests/test_a_rig_signs_each_sessions_tunnel_key_and_pins_the_identity_of_each_peer_it_meets.py``
caught it, now and then, as two identity keys). Here the race is made certain:
the folder appears between the check and the ``mkdir``, and the write lands.
Both copies of the private write are held, the shared one and the rig token's.
"""

from __future__ import annotations

import stat
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import atomic
from mcgyvr.rig import credentials

WRITES: list[Callable[[Path, str], Path]] = [
    atomic.write_private,
    credentials.write_private,
]


@pytest.mark.parametrize("write", WRITES, ids=["atomic", "credentials"])
def test_the_folder_made_between_the_check_and_the_mkdir_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write: Callable[[Path, str], Path]
) -> None:
    folder = tmp_path / "mcgyvr-home"
    target = folder / "identity.json"
    real_exists = Path.exists

    def exists_then_made_by_the_other(self: Path, **kwargs: bool) -> bool:
        if self == folder and not real_exists(self):
            folder.mkdir(mode=0o700)  # the other first write, just now
            return False  # what this one saw a moment before
        return real_exists(self, **kwargs)

    monkeypatch.setattr(Path, "exists", exists_then_made_by_the_other)
    assert write(target, "{}\n") == target
    assert target.read_text(encoding="utf-8") == "{}\n"
    if sys.platform != "win32":
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
