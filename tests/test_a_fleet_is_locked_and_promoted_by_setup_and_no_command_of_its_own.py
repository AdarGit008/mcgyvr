"""A fleet is locked and promoted by ``mcgyvr setup``, and by no command of its own.

The user locks a fleet once: ``mcgyvr setup`` samples it, stamps it, locks it
from the stamp and promotes it (:func:`mcgyvr.fleet.lock.write_from_stamp`,
:func:`mcgyvr.fleet.promote.promote`), and ``mcgyvr fleet use`` names a
promoted folder live. Writing a lock from evidence of the caller's own, and
promoting it, are the library's (and the lab's): ``fleet lock``, ``fleet
promote`` and the one-off ``fleet tag`` are no commands.
"""

from __future__ import annotations

import pytest

from mcgyvr.cli import main


@pytest.mark.parametrize("verb", ["lock", "promote", "tag"])
def test_the_fleet_command_has_no_verb_that_locks_promotes_or_renames(
    verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["fleet", verb, "--help"])
    assert exited.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_the_library_seams_setup_locks_and_promotes_by_are_there() -> None:
    from mcgyvr.fleet import lock, promote

    for name in ("write", "write_from_stamp", "write_unsampled"):
        assert callable(getattr(lock, name)), name
    assert callable(promote.promote)
    assert callable(promote.use)
    assert not hasattr(promote, "tag")
