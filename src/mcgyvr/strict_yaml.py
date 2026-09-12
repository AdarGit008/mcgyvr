"""A strict YAML loader shared by the config and contract schemas.

PyYAML's ``SafeLoader`` silently keeps the last of a repeated key, and lets a
list or dict sit as a key until something hashes it. Both are defects a config
or a contract must fail loudly on, so this loader refuses both. ``config.py``
and ``contract.py`` each carried their own copy — this is the one they now
share, with the schema's own error type injected so every failure reads as the
file that produced it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml

ErrorFactory = Callable[[str], Exception]


def _no_duplicate_keys(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, error: ErrorFactory
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError:
            # `[dev]: x` — a list as a key. YAML allows it; a config or
            # contract does not, and `key in mapping` would have raised a
            # TypeError past every caller expecting the schema's own error.
            mark = key_node.start_mark
            raise error(
                f"key {key!r} at line {mark.line + 1} is not a plain name; a "
                "key is one word, never a list or a mapping."
            ) from None
        if key in mapping:
            mark = key_node.start_mark
            raise error(
                f"duplicate key {key!r} at line {mark.line + 1} — YAML would "
                f"silently keep only the last one, so the file does not mean "
                f"what it looks like it means."
            ) from None
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


def strict_loader(error: ErrorFactory) -> type[yaml.SafeLoader]:
    """A ``SafeLoader`` subclass that refuses duplicate and unhashable keys.

    ``error`` is the schema's own error class, so a duplicate key in a config
    raises ``ConfigSchemaError`` and one in a contract raises
    ``ContractSchemaError``.
    """

    def _constructor(
        loader: yaml.SafeLoader, node: yaml.nodes.MappingNode
    ) -> dict[Any, Any]:
        return _no_duplicate_keys(loader, node, error)

    class _StrictLoader(yaml.SafeLoader):
        """SafeLoader that refuses duplicate keys instead of taking the last."""

    _StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _constructor
    )
    return _StrictLoader
