"""A changed-argument setting that is not a mode is refused by name.

``gate.param_mutation`` takes one of the modes the gate implements. Anything
else is refused when the setup is loaded, before anything runs, and the refusal
names the key and the modes it takes. A value typed as a YAML boolean (a bare
``off``) is refused the same way. The schema offers exactly the modes the gate
implements, read from both modules, and an adapter built in code with a mode
the gate does not implement is refused by name as well.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import ConfigSchemaError, field_at, parse

KEY = "gate.param_mutation"

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""


def _load(value: str) -> None:
    parse(FLEET, f"ladder: [cheap]\ngate:\n  param_mutation: {value}\n")


def test_a_word_that_is_not_a_mode_is_refused_naming_the_key_and_the_modes() -> None:
    from mcgyvr.gate.typecheck import ParamMutation

    with pytest.raises(ConfigSchemaError) as refused:
        _load("sometimes")

    message = str(refused.value)
    assert KEY in message, message
    assert "sometimes" in message, message
    for mode in ParamMutation:
        assert mode.value in message, message


def test_a_yaml_boolean_is_refused_naming_the_key() -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        _load("off")

    assert KEY in str(refused.value), str(refused.value)


def test_the_setting_offers_exactly_the_modes_the_gate_implements() -> None:
    from mcgyvr.gate.typecheck import ParamMutation

    field = field_at(KEY)

    assert field is not None, f"{KEY} is not in the schema"
    assert field.choices == tuple(mode.value for mode in ParamMutation)
    assert field.default == ParamMutation.REFUSE


def test_an_adapter_built_in_code_with_an_unknown_mode_is_refused_by_name() -> None:
    from mcgyvr.gate.adapters import PythonAdapter

    with pytest.raises(ValueError, match="sometimes"):
        PythonAdapter(param_mutation="sometimes")
