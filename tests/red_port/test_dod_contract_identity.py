"""E5 — a contract's identity does not depend on the order it lists its deps.

:meth:`mcgyvr.contract.Contract.as_dict` emits ``depends_on`` sorted, so two
contracts that name the same dependencies in a different order are the same contract
and get one identity.
"""

from __future__ import annotations

BASE = """
id: x
task_type: function_implementation
task: Add the helper.
target: src/pkg/fetch.py
stop_conditions: ["The interface is not stated."]
acceptance: ["sh -c 'exit 0'"]
scope:
  allow: ["src/**"]
"""


def test_depends_on_order_does_not_change_the_contracts_identity() -> None:
    from mcgyvr.contract import dumps, loads

    ab = loads(BASE + "depends_on:\n  - a\n  - b\n")
    ba = loads(BASE + "depends_on:\n  - b\n  - a\n")

    assert dumps(ab) == dumps(ba)
