""

from __future__ import annotations

import reprlib
from collections.abc import Callable
from typing import Any

import yaml

ErrorFactory = Callable[[str], Exception]

#
#
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
            #or
            #
            #
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
    ""

    def _constructor(
        loader: yaml.SafeLoader, node: yaml.nodes.MappingNode
    ) -> dict[Any, Any]:
        return _no_duplicate_keys(loader, node, error)

    class _StrictLoader(yaml.SafeLoader):
        ""

    _StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _constructor
    )
    return _StrictLoader
