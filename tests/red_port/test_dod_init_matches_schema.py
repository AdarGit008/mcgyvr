"""`mcgyvr init` never writes a value that contradicts the schema's own default.

``initialize.build`` writes a starting config. Where a key has no machine to be
detected from, the value it writes is a second copy of the number in
``mcgyvr.config``'s schema — and a copy that nothing binds is a copy that drifts.

It has already drifted once, and the direction matters. The owner ruled on
2026-09-05 that ``cleanup.enabled`` is on by default: the first live ladder
rejected all nine replies on a reflowed line, and repairing after a rung instead
of climbing is the whole point of the ruling. The schema was changed to
``default=True``. ``initialize.build`` still writes ``False``, as a live key, so
every install created by ``mcgyvr init`` since that ruling ships with the
behaviour the ruling was written to end — and the operator cannot tell, because
the file says what it does.

What must be observably true: for every key `init` writes that is not derived
from the machine it detected, the value written equals the schema's default. A
new default is then a one-line change in one place, which is what a default is
for.
"""

from __future__ import annotations

from typing import Any

from tests.red_port.conftest import required

#: Keys `init` writes with no machine to read them off. ``sandbox.mode`` is
#: deliberately absent: it is detected (docker present or not) and is *meant*
#: to differ from the schema's default on a machine without docker.
STATIC: tuple[tuple[str, str], ...] = (
    ("cleanup", "enabled"),
    ("breadth", "draws"),
    ("delivery", "mode"),
    ("journal", "dir"),
)

FIELDS = {
    "cleanup": "CLEANUP_FIELDS",
    "breadth": "BREADTH_FIELDS",
    "delivery": "DELIVERY_FIELDS",
    "journal": "JOURNAL_FIELDS",
    "budgets": "BUDGET_FIELDS",
}


def _default(block: str, leaf: str) -> Any:
    from mcgyvr import config

    for field in getattr(config, FIELDS[block]):
        if field.name == leaf:
            return field.default
    raise AssertionError(f"{block}.{leaf} is not in the schema")


def _built() -> dict[str, Any]:
    """What `mcgyvr init` would write on a machine with nothing detected."""
    from mcgyvr.detect import Detection
    from mcgyvr.initialize import build

    written = required(
        "write a starting config whose static values are the schema's own "
        "defaults, so a changed default reaches a new install",
        lambda: build(Detection(), _proposal()),
    )
    return dict(written)


def _proposal() -> Any:
    from mcgyvr.propose import Proposal

    return Proposal()


def test_init_writes_the_cleanup_default_the_owner_set() -> None:
    """The drift that already happened, named on its own.

    Stated separately from the sweep below because this one is not hypothetical:
    it is shipping, and what it silently turns off is the repair loop.
    """
    written = _built()
    assert written["cleanup"]["enabled"] == _default("cleanup", "enabled"), (
        "init writes cleanup.enabled=False against a schema default of True; "
        "every fresh install disables repair-and-regate (owner, 2026-09-05)"
    )


def test_no_static_key_init_writes_contradicts_its_schema_default() -> None:
    """The binding that would have caught it.

    One assertion over every key `init` restates, so the next default that moves
    does not need someone to remember the initializer exists.
    """
    written = _built()
    drifted = [
        f"{block}.{leaf}: init writes {written[block][leaf]!r}, "
        f"schema default is {_default(block, leaf)!r}"
        for block, leaf in STATIC
        if written.get(block, {}).get(leaf) != _default(block, leaf)
    ]
    assert not drifted, "\n".join(drifted)
