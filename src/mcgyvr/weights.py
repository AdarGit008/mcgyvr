"""Helpers for finding model weight files that are already on disk.

Walks configured root directories for ".gguf" and ".safetensors" files, derives
a model name and a GGUF quantization tag from each filename, and offers lookup
and confirmation helpers so a caller can reuse local weights instead of
downloading them again. Also decides whether a served model reference names the
same model as a declared model id.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

#: Filename suffixes treated as model weight files, used by is_model to strip
#: the extension off a served model reference before comparing the base name
#: with the declared model id. ".bin" and ".pt" appear only in this list,
#: since models_in scans for ".gguf" and ".safetensors" alone.
WEIGHTS_SUFFIXES = (".gguf", ".safetensors", ".bin", ".pt")

#: Split checkpoints put a shard counter before the extension, for example
#: "model-00001-of-00002.safetensors". This pattern matches that trailing
#: "-00001-of-00002" so the counter can be removed and the sharded file still
#: compares equal to the unsuffixed declared model id.
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")

#: Quantization tag in a GGUF filename, e.g. "q4_k_m", "Q8_0", "BF16", "F32" or
#: "MXFP4_MOE": a separator (or underscore variant) followed by the tag and the
#: ".gguf" extension.
_GGUF_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)


def _name_and_quant(path: Path) -> tuple[str, str | None]:
    """Derive a model name and quantization tag from a weight filename.

    For ".gguf" files the name is everything before the quantization tag and
    the tag is upper-cased, or the name is the whole stem with a tag of None
    when no tag matches. For ".safetensors" files the name is the stem. Any
    other filename is returned unchanged.
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
    """List the weight files found under the given roots.

    Each root is expanded and skipped unless it is an existing directory; the
    remaining roots are searched recursively for ".gguf" and ".safetensors"
    files. Every file contributes a ``(name, quant, size)`` triple, where the
    first two fields come from :func:`_name_and_quant` and the third is the
    size in bytes. A path is reported only once, and files whose size cannot
    be read are dropped.
    """
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
    """Look for a weight file on disk that matches the requested model.

    The name and the quantization tag are compared case-insensitively, with a
    missing tag treated as an empty string. When ``size_bytes`` is given the
    file size must match exactly as well. Returns the first matching
    ``(name, quant, size)`` triple from :func:`models_in`, or None when nothing
    matches.
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
    """Ask whether an already-downloaded weight file should be reused.

    Returns False without prompting when :func:`existing_model` finds no match.
    Otherwise the found file name, quantization tag and size are shown through
    ``prompt``, and the answer counts as reuse unless it is "n" or "no", so an
    empty answer means reuse.
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
