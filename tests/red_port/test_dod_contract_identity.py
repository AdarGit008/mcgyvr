"""E5 — a contract's identity does not depend on the order it lists its deps.

:meth:`mcgyvr.contract.Contract.as_dict` emits ``depends_on`` in the order the
YAML wrote it, and ``tools/instruments.py`` pins ``sha256(dumps(contract))`` as
a task's identity. Two contracts that name the same dependencies in a different
order are the same contract, but they got two identities — which re-keys a
recorded run against an instrument that is byte-identical in meaning.

The fix emits ``depends_on`` sorted, so the declared form is order-independent.
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
