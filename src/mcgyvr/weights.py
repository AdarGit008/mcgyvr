"""Decides whether a served model reference names the same model as a declared
model id.
"""

from __future__ import annotations

import re

#: Filename suffixes treated as model weight files, used by is_model to strip
#: the extension off a served model reference before comparing the base name
#: with the declared model id.
WEIGHTS_SUFFIXES = (".gguf", ".safetensors", ".bin", ".pt")

#: Split checkpoints put a shard counter before the extension, for example
#: "model-00001-of-00002.safetensors". This pattern matches that trailing
#: "-00001-of-00002" so the counter can be removed and the sharded file still
#: compares equal to the unsuffixed declared model id.
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")


def is_model(served: str, declared: str) -> bool:
    """Report whether a served model reference names the declared model.

    Identical strings match immediately. Otherwise the served reference is
    reduced to its basename, one of :data:`WEIGHTS_SUFFIXES` is removed, and
    the remaining stem, with any :data:`_SHARD` counter stripped, is compared
    case-insensitively against ``declared``. A reference ending in an
    unrecognized suffix, or in no suffix at all, does not match.
    """
    if served == declared:
        return True
    name = served.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in WEIGHTS_SUFFIXES:
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            break
    else:
        return False
    wanted = declared.lower()
    return stem == wanted or _SHARD.sub("", stem) == wanted
