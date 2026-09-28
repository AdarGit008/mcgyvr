"""How a served model id is read against the name a config declares.

**Two vocabularies.** vLLM's served id is the model it was started with — the
repository id a config names — and those compare as strings. llama.cpp's is
the **path it was handed**, as ``/models/dense/<name>.gguf``
(``records/evidence/serving-2026-08-30/lcpp-srv1.json``), against a config that
declares ``<name>``: ``emit`` passes ``--model <path>`` and no ``--alias``, so
the declared name and the served id differ by construction.

This rule lives in a module of its own because two layers need it and it belongs
to neither. :mod:`mcgyvr.availability` reads it against a rig's *listing*, to
decide whether a rung is in service. :mod:`mcgyvr.runner` reads it against the
model a completion says it *answered with*, to decide whether an answer came
from the weights that were asked for. One rule, spelled once: a reading that
drifted between those two would put a rung in service on one definition and
refuse its answers on the other.
"""

from __future__ import annotations

import re

#: What a weights file is called on this fleet. Only these are stripped off a
#: served id, and only off the last segment of a path: a suffix list is a claim
#: about file names and not about model names, and a model whose name genuinely
#: ends in one of these is a model nobody has.
WEIGHTS_SUFFIXES = (".gguf", ".safetensors", ".bin", ".pt")

#: The tail llama.cpp's own convention puts on a quant too big for one file —
#: ``...-00001-of-00002.gguf``. The server is given the first shard and lists
#: that path, so a stem that is the declared model plus this is the declared
#: model.
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")


def is_model(served: str, declared: str) -> bool:
    """Whether a served id names the weights a rung declares.

    Equal strings match. Otherwise a weights file is read as one: the last path
    segment, one weights suffix removed, and llama.cpp's own ``-00001-of-00002``
    shard tail with it. **Only where a weights suffix was actually there**,
    which is what keeps the reading narrow: ``model.v2`` is not ``model``, and
    ``org/model`` is not ``model`` either — a repository id is a name and not a
    file, and two organisations publishing one basename are two checkpoints.
    Compared case-insensitively: a file system may not preserve case, the config
    and the file name are written by different hands, and the direction to err
    in is the one that leaves a rung in service.

    Every loosening here can only *keep* a rung, never take one out, which is
    the discipline the whole check runs on: only an explicit, readable listing
    may shorten the ladder, and this is the reading of it.
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
