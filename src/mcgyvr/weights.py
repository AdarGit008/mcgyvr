"""How a served model id is read against the name a config declares.

**Two vocabularies.** vLLM's served id is the model it was started with — the
repository id a config names — and those compare as strings. llama.cpp's is
the **path it was handed**, as ``/models/dense/<name>.gguf`` (the lab's
serving evidence for lcpp-srv1), against a config that declares ``<name>``.
``emit`` passes ``--alias <name>`` beside ``--model <path>``, so a unit it
rendered serves the declared name; a server started
without one (by hand, or from a file emitted before the alias was written)
still lists and answers by its path, and the two differ by construction.

This rule lives in a module of its own because two layers need it and it belongs
to neither. :mod:`mcgyvr.availability` reads it against a rig's *listing*, to
decide whether a rung is in service. :mod:`mcgyvr.runner` reads it against the
model a completion says it *answered with*, to decide whether an answer came
from the weights that were asked for, on a rung of one's own and on a relief
rung alike. One rule, spelled once: a reading that
drifted between those two would put a rung in service on one definition and
refuse its answers on the other.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

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

#: A GGUF quantisation as file names spell it, at the end of the name.
_GGUF_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)


def _name_and_quant(path: Path) -> tuple[str, str | None]:
    """A weights file's model id/name and quant, read off its name.

    A GGUF names its model before its quant tag; a safetensors shard names its
    model by the directory that holds it, and its quant is None (the dtype is
    in the header, not the file name).
    """
    name = path.name
    lower = name.lower()
    if lower.endswith(".gguf"):
        match = _GGUF_QUANT.search(name)
        if match is None:
            return name[: -len(".gguf")], None
        return name[: match.start()], match.group(1).upper()
    if lower.endswith(".safetensors"):
        return Path(name).stem, None
    return name, None


def models_in(roots: Iterable[Path]) -> tuple[tuple[str, str | None, int], ...]:
    """``(name, quant, size_bytes)`` for every ``*.gguf``/``*.safetensors``
    under ``roots``, used before a download to find one already on disk."""
    found: list[tuple[str, str | None, int]] = []
    seen: set[Path] = set()
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path in seen:
                continue
            lower = path.name.lower()
            if not (lower.endswith(".gguf") or lower.endswith(".safetensors")):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            seen.add(path)
            name, quant = _name_and_quant(path)
            found.append((name, quant, size))
    return tuple(found)


def existing_model(
    model_id: str,
    *,
    quant: str | None = None,
    size_bytes: int | None = None,
    roots: Sequence[Path] = (),
) -> tuple[str, str | None, int] | None:
    """The first on-disk model matching ``model_id`` + ``quant`` + ``size``.

    The size is matched only when the caller knows one; a file of the same id
    and quant but another size is a different checkpoint and must not be reused.
    """
    wanted = model_id.lower()
    wanted_quant = (quant or "").lower()
    for name, have_quant, size in models_in(roots):
        if name.lower() != wanted:
            continue
        if (have_quant or "").lower() != wanted_quant:
            continue
        if size_bytes is not None and size != size_bytes:
            continue
        return name, have_quant, size
    return None


def reuse_or_download(
    model_id: str,
    *,
    quant: str | None = None,
    size_bytes: int | None = None,
    roots: Sequence[Path] = (),
    prompt: Callable[[str], str] = input,
) -> bool:
    """Whether to reuse an on-disk match, asking once; defaults to reuse.

    ``prompt`` is injectable so a test can state the answer without a terminal.
    """
    hit = existing_model(model_id, quant=quant, size_bytes=size_bytes, roots=roots)
    if hit is None:
        return False
    name, have_quant, size = hit
    quant_text = f" {have_quant}" if have_quant else ""
    answer = prompt(
        f"{name}{quant_text} ({size} bytes) is already on disk. "
        f"Reuse it instead of downloading? [Y/n] "
    )
    return str(answer).strip().lower() not in {"n", "no"}


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
