""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

#
#
#
#
WEIGHTS_SUFFIXES = (".gguf", ".safetensors", ".bin", ".pt")

#€”
#
#
#
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")

#
_GGUF_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)


def _name_and_quant(path: Path) -> tuple[str, str | None]:
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
