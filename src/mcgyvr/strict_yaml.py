"""YAML loading that refuses ambiguous mappings.

``strict_loader`` builds a ``yaml.SafeLoader`` subclass whose mapping
constructor rejects a key that cannot be hashed (a list, a mapping) and rejects a
key that already exists in the same mapping, reporting both through a caller
supplied error factory.
"""

from __future__ import annotations

import reprlib
from collections.abc import Callable
from typing import Any

import yaml

ErrorFactory = Callable[[str], Exception]

# Bounded repr() for keys quoted in error messages, so an oversized or deeply
# nested key cannot flood the message.
_KEY = reprlib.Repr(
    maxlevel=2, maxdict=4, maxlist=4, maxset=4, maxstring=200, maxlong=200, maxother=200
)


def _no_duplicate_keys(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, error: ErrorFactory
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError:
            # The key is a list, mapping or other unhashable node, so it can never
            # be looked up in the result; report it against its own source line
            # instead of letting a bare TypeError escape.
            mark = key_node.start_mark
            raise error(
                f"key {_KEY.repr(key)} at line {mark.line + 1} is not a plain name; a "
                "key is one word, never a list or a mapping."
            ) from None
        if key in mapping:
            mark = key_node.start_mark
            raise error(
                f"duplicate key {_KEY.repr(key)} at line {mark.line + 1} — YAML would "
                f"silently keep only the last one, so the file does not mean "
                f"what it looks like it means."
            ) from None
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


def strict_loader(error: ErrorFactory) -> type[yaml.SafeLoader]:
    """Return a SafeLoader subclass whose mappings go through key checking.

    Every mapping node is built by ``_no_duplicate_keys`` with the same
    ``error`` factory, so an unhashable or repeated key raises the exception
    that factory produces. The class is created fresh per call, so each loader
    carries its own error factory.
    """

    def _constructor(
        loader: yaml.SafeLoader, node: yaml.nodes.MappingNode
    ) -> dict[Any, Any]:
        return _no_duplicate_keys(loader, node, error)

    class _StrictLoader(yaml.SafeLoader):
        """SafeLoader whose default mapping tag construction is replaced."""

    _StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _constructor
    )
    return _StrictLoader
