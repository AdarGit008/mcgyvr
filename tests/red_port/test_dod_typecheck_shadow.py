"""D7 — a lambda or comprehension that shadows a parameter is not that parameter.

The ``param-mutation`` family walks every expression with :func:`ast.walk`,
which descends into a lambda's body and a comprehension's element as though
their names were the enclosing function's. But a lambda binds its own
parameters, and a comprehension binds its own targets: ``lambda target:
target.append(1)`` mutates the lambda's argument, not the caller's object, and a
comprehension that rebinds ``target`` has done the same. Reporting those as the
parameter's mutation rejects correct code that happens to reuse a name.

The fix makes the walk scope-aware — the names a lambda or comprehension binds
stop being the caller's as the walk crosses into it, while a name the inner
scope does not bind still means the caller's object.
"""

from __future__ import annotations

import ast

from mcgyvr.gate.typecheck import compliance_findings

LAMBDA_SHADOW = "def f(target):\n    return (lambda target: target.append(1))([])\n"

COMPREHENSION_SHADOW = (
    "def f(target):\n"
    "    return [target.append(x) for x in range(1) for target in [[]]]\n"
)

PLAIN_MUTATION = "def f(target):\n    target.append(1)\n    return target\n"


def _param_findings(source: str) -> list[str]:
    """The PARAM-MUTATION messages ``source`` produces, if any."""
    tree = ast.parse(source)
    return [
        f.message
        for f in compliance_findings(
            tree, "f.py", frozenset(range(1, 200)), contract_text=""
        )
        if f.code == "PARAM-MUTATION"
    ]


def test_a_lambda_that_shadows_a_parameter_is_not_that_parameters_mutation() -> None:
    """A lambda's own argument is not the object the caller still owns."""
    assert _param_findings(LAMBDA_SHADOW) == [], (
        "a lambda whose parameter shadows the function's was reported as a "
        f"mutation of the caller's object: {_param_findings(LAMBDA_SHADOW)}"
    )


def test_a_comprehension_that_shadows_a_parameter_is_not_that_mutation() -> None:
    """A comprehension target is a fresh name, not the parameter it shadows."""
    assert _param_findings(COMPREHENSION_SHADOW) == [], (
        "a comprehension whose target shadows the function's parameter was "
        f"reported as a mutation of the caller's object: "
        f"{_param_findings(COMPREHENSION_SHADOW)}"
    )


def test_a_plain_mutation_is_still_reported() -> None:
    """Control: the walk that stops shadowing must not stop seeing real mutations."""
    assert _param_findings(PLAIN_MUTATION), (
        "the scope-aware walk stopped reporting a mutation that really is the "
        "caller's object"
    )
