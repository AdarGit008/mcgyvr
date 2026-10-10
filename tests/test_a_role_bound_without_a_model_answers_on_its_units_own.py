"""A role bound to a unit without a `model` answers on the unit's own model.

`skills/mcgyvr/SETUP.md` says of every role block's `model`: "absent means the
unit's own". The pool honoured that for the verifier and dropped every other
role silently — an `orchestrator: {unit: x}` resolved to no binding at all, so
`mcgyvr delegate` reported the role unconfigured while the file plainly bound
it. One rule for every role, in one place: a bound unit with no model named is
the unit's model.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import parse
from mcgyvr.local_pool import _ROLES, source_map

SETUP = """\
units:
  cheap:
    address: http://box.invalid:11434
    model: coder-7b
    rig: box
    width: 3
ladder:
- cheap
"""


@pytest.mark.parametrize("role", _ROLES)
def test_every_role_bound_without_a_model_answers_on_the_units_own(role: str) -> None:
    pool = source_map(parse(SETUP + f"{role}:\n  unit: cheap\n"))
    assert pool.role_model(role) == "coder-7b"


@pytest.mark.parametrize("role", _ROLES)
def test_a_named_model_still_wins(role: str) -> None:
    pool = source_map(parse(SETUP + f"{role}:\n  unit: cheap\n  model: coder-14b\n"))
    assert pool.role_model(role) == "coder-14b"


def test_a_delegate_orchestrator_bound_by_unit_alone_is_configured() -> None:
    from mcgyvr.delegate import proposer_for

    pool = source_map(parse(SETUP + "orchestrator:\n  unit: cheap\n"))
    assert proposer_for(pool) is not None
