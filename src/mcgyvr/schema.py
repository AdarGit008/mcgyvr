"""The schema walk both setup files and contracts are read with.

A schema is a tuple of :class:`Field`, one per declared key, and a block of a
document is read by :func:`walk_block`: every key checked against the table,
defaults filled in, a missing required key refused, each value coerced by its
field's kind. What differs between a config and a contract — the noun an error
names, the error class, how each kind is coerced, what an absent key defaults
to, and any check a key earns before it is looked up — is the
:class:`Dialect` the walk is handed. The kind coercers stay with each schema.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

#: Every kind a field may declare. A config uses all but `glob_list`; a
#: contract uses `int`, `float`, `str`, `bool`, `enum`, `str_list`,
#: `glob_list`, `block` and `block_list`.
Kind = Literal[
    "int",
    "float",
    "str",
    "url",
    "bool",
    "enum",
    "env_name",
    "str_list",
    "glob_list",
    "mapping",
    "int_map",
    "block",
    "block_map",
    "block_list",
]


@dataclass(frozen=True)
class Field:
    """One declared key: how a value for it is read, checked and defaulted,
    and the prose an error about it quotes."""

    name: str
    kind: Kind
    doc: str
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    block: tuple[Field, ...] = ()
    min_value: float | None = None
    #: Inclusive bounds for the `int` and `float` kinds; a value outside them is
    #: refused by name rather than clamped. In a config `min_value` also floors
    #: each entry of an `int_map`. `choices` closes an `enum`, and `block` names
    #: the fields a `block`, `block_map` or `block_list` holds.
    max_value: float | None = None
    #: A config key's word on how to set it, quoted by the error that calls it
    #: unset.
    bind_hint: str = ""
    #: A contract key's audience: whether the worker reads it, or only the
    #: orchestrator.
    worker_facing: bool = False
    #: A contract key's extra sentence, quoted after its doc when it is missing.
    hint: str = ""
    #: Where an `enum`'s values come from when they are not fixed in `choices`.
    choices_from: Callable[[], tuple[str, ...]] | None = None

    def valid_choices(self) -> tuple[str, ...]:
        """The values it accepts, from `choices_from` when given, else `choices`."""
        return self.choices_from() if self.choices_from is not None else self.choices


def join_path(path: str, name: str) -> str:
    """`name` under the dotted `path`, or `name` alone at the top."""
    return f"{path}.{name}" if path else name


@dataclass(frozen=True)
class Dialect:
    """What one schema makes of the shared walk.

    `noun` names a whole document in an error (`config`, `contract`); `error`
    builds the error a refusal raises; `mapping` reads a raw block as a mapping of
    text keys; `value` coerces one present value by its field's kind;
    `missing` builds the refusal of an unset required key; `default_for` is
    what an absent optional key reads as; `check_key`, when given, sees every
    key of a block before it is looked up, and raises to refuse it.
    """

    noun: str
    error: Callable[[str], Exception]
    mapping: Callable[[object, str], Mapping[str, Any]]
    value: Callable[[object, Field, str], Any]
    missing: Callable[[Field, str], Exception]
    default_for: Callable[[Field], Any]
    check_key: Callable[[str, str], None] | None = None


def walk_block(
    raw: object, fields: tuple[Field, ...], path: str, dialect: Dialect
) -> dict[str, Any]:
    """Validate one block: defaults filled in, unknown and missing keys refused."""
    given = dialect.mapping(raw if raw is not None else {}, path)
    known = {f.name: f for f in fields}

    for key in given:
        if dialect.check_key is not None:
            dialect.check_key(key, path)
        if key not in known:
            raise dialect.error(
                f"{path or dialect.noun}: unknown key {key!r}. An ignored key is a "
                f"{dialect.noun} that does not do what it says. Valid keys here: "
                f"{', '.join(sorted(known))}"
            )

    result: dict[str, Any] = {}
    for spec in fields:
        here = join_path(path, spec.name)
        if spec.name in given and given[spec.name] is not None:
            result[spec.name] = dialect.value(given[spec.name], spec, here)
        elif spec.required:
            raise dialect.missing(spec, here)
        else:
            result[spec.name] = dialect.default_for(spec)
    return result
