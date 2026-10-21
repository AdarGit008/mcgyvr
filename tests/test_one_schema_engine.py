"""The config and the contract are read by one schema walk, each in its own dialect.

``mcgyvr.schema`` holds the one ``Field``, the one walker and the one
unknown-key refusal; ``config.py`` and ``contract.py`` keep their own kinds'
coercers, tables, errors and wording. One class serves both, so nothing stops
a config table from declaring a contract-only kind or attribute, or the other
way round; this file does, since a field the other schema's coercers would
read is a field this one's never do.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType
from typing import get_args

import pytest

from mcgyvr import config, contract, schema

CONFIG_KINDS = frozenset(
    {
        "int",
        "float",
        "str",
        "url",
        "bool",
        "enum",
        "env_name",
        "str_list",
        "mapping",
        "int_map",
        "block",
        "block_map",
        "block_list",
    }
)
CONTRACT_KINDS = frozenset(
    {
        "int",
        "float",
        "str",
        "bool",
        "enum",
        "str_list",
        "glob_list",
        "block",
        "block_list",
    }
)
#: Attributes only a contract field sets, and only a config field sets.
CONTRACT_ONLY = ("worker_facing", "hint", "choices_from", "session_optional")
CONFIG_ONLY = ("bind_hint",)


def _fields(module: ModuleType) -> Iterator[schema.Field]:
    def walk(fields: tuple[schema.Field, ...]) -> Iterator[schema.Field]:
        for spec in fields:
            yield spec
            yield from walk(spec.block)

    for value in vars(module).values():
        if (
            isinstance(value, tuple)
            and value
            and all(isinstance(f, schema.Field) for f in value)
        ):
            yield from walk(value)


def test_both_schemas_declare_their_keys_with_the_one_field_class() -> None:
    assert config.Field is schema.Field
    assert contract.Field is schema.Field


def test_every_kind_either_schema_reads_is_a_kind_of_the_one_walk() -> None:
    assert set(get_args(schema.Kind)) == CONFIG_KINDS | CONTRACT_KINDS


@pytest.mark.parametrize(
    ("module", "kinds", "foreign"),
    [(config, CONFIG_KINDS, CONTRACT_ONLY), (contract, CONTRACT_KINDS, CONFIG_ONLY)],
    ids=["config", "contract"],
)
def test_a_schema_declares_only_its_own_kinds_and_attributes(
    module: ModuleType, kinds: frozenset[str], foreign: tuple[str, ...]
) -> None:
    default = schema.Field("x", "str", "")
    fields = list(_fields(module))
    assert fields, f"{module.__name__} declares no field table"
    for spec in fields:
        assert spec.kind in kinds, (module.__name__, spec.name, spec.kind)
        for attribute in foreign:
            assert getattr(spec, attribute) == getattr(default, attribute), (
                module.__name__,
                spec.name,
                attribute,
            )


@pytest.mark.parametrize(
    ("module", "error", "noun"),
    [
        (config, config.ConfigSchemaError, "config"),
        (contract, contract.ContractSchemaError, "contract"),
    ],
    ids=["config", "contract"],
)
def test_an_unknown_key_is_refused_in_the_schemas_own_words(
    module: ModuleType, error: type[Exception], noun: str
) -> None:
    fields = (schema.Field("known", "str", "A key."),)
    with pytest.raises(error) as top:
        module._block({"other": 1}, fields, "")
    assert str(top.value) == (
        f"{noun}: unknown key 'other'. An ignored key is a {noun} that does not "
        f"do what it says. Valid keys here: known"
    )
    with pytest.raises(error) as nested:
        module._block({"other": 1}, fields, "a.b")
    assert str(nested.value).startswith("a.b: unknown key 'other'.")
