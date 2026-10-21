"""``mcgyvr setup`` surfaces a lock refusal and skips the PATH offer after it.

Owner, 2026-10-21: a "No fleet was made live" refusal used to be one line
buried in the "What is NOT configured, and what that costs" list, after which
setup still offered to append ``~/.local/bin`` to PATH. The refusal is now
boxed on its own, the remaining limits stay under the usual heading, and the
PATH offer is skipped when a refusal is among the limits.
"""

from __future__ import annotations

import pytest

from mcgyvr.cli.commands.setup import _report_limits

REFUSAL = (
    "No fleet was made live: own: local_unit names no card in launch.shards. "
    "A live run is refused until a fleet is live (`mcgyvr fleet use`)."
)
LIMIT = "sandbox.mode is `tempdir`, the explicitly weaker mode."


def test_a_lock_refusal_is_reported_on_its_own(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _report_limits((REFUSAL,)) is True
    out = capsys.readouterr().out
    assert REFUSAL in out
    assert "What is NOT configured" not in out


def test_an_ordinary_limit_keeps_the_usual_heading(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _report_limits((LIMIT,)) is False
    out = capsys.readouterr().out
    assert "What is NOT configured, and what that costs:" in out
    assert LIMIT in out


def test_a_refusal_is_split_from_the_limits_it_ships_with(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _report_limits((LIMIT, REFUSAL)) is True
    out = capsys.readouterr().out
    assert REFUSAL in out
    assert "What is NOT configured, and what that costs:" in out
    assert LIMIT in out
