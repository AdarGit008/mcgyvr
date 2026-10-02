"""A rig's hello names its models, never their paths, and a head starts only on those.

The hub names a model; the agent finds it in its own inventory, so no name
can reach a file outside the owner's models folder. Of each file under the
folder the hello carries its own name, its size, and what the product's GGUF
reader reads from its header — architecture, layers, trained context,
embedding width, KV heads, and the KV cache's bytes per token at the head's
KV type — and a header that does not read leaves those unsaid. A hidden
folder, a later part of a split model, a link that leaves the folder, a name
the protocol cannot carry, and a second file of one name are not named.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

ARCH = "llama"


def _text(value: str) -> bytes:
    raw = value.encode()
    return struct.pack("<Q", len(raw)) + raw


def write_gguf(path: Path, *, layers: int = 2, embd: int = 64, heads: int = 8) -> None:
    """A GGUF of the fields the reader reads, and one small tensor."""
    kv = [
        (b"general.architecture", 8, _text(ARCH)),
        (f"{ARCH}.block_count".encode(), 4, struct.pack("<I", layers)),
        (f"{ARCH}.context_length".encode(), 4, struct.pack("<I", 4096)),
        (f"{ARCH}.embedding_length".encode(), 4, struct.pack("<I", embd)),
        (f"{ARCH}.attention.head_count".encode(), 4, struct.pack("<I", heads)),
        (f"{ARCH}.attention.head_count_kv".encode(), 4, struct.pack("<I", 2)),
    ]
    out = b"GGUF" + struct.pack("<IQQ", 3, 1, len(kv))
    for key, kind, value in kv:
        out += struct.pack("<Q", len(key)) + key + struct.pack("<I", kind) + value
    out += _text("blk.0.attn_q.weight") + struct.pack("<I", 2)
    out += struct.pack("<QQ", 4, 4) + struct.pack("<IQ", 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out + b"\x00" * 64)


@pytest.fixture
def models(tmp_path: Path) -> Path:
    folder = tmp_path / "models"
    write_gguf(folder / "dense" / "model-a.gguf")
    write_gguf(folder / "model-b.gguf", layers=4)
    write_gguf(folder / "split-00001-of-00002.gguf")
    write_gguf(folder / "split-00002-of-00002.gguf")
    write_gguf(folder / ".cache" / "hidden.gguf")
    write_gguf(folder / "other" / "model-b.gguf")
    write_gguf(folder / "with space.gguf")
    (folder / "broken.gguf").write_bytes(b"not a model at all")
    (folder / "notes.txt").write_text("not a model")
    outside = tmp_path / "outside.gguf"
    write_gguf(outside)
    os.symlink(outside, folder / "escape.gguf")
    os.symlink(folder / "model-b.gguf", folder / "dense" / "alias.gguf")
    return folder


def test_the_hello_names_each_model_once_by_its_own_name(models: Path) -> None:
    from mcgyvr.rig import inventory

    held = inventory.read(str(models))
    names = [m.name for m in held.models]
    assert sorted(names) == [
        "alias.gguf",
        "broken.gguf",
        "model-a.gguf",
        "model-b.gguf",
        "split-00001-of-00002.gguf",
    ]
    assert held.files["model-a.gguf"] == "dense/model-a.gguf"
    assert held.files["alias.gguf"] == "model-b.gguf"  # its link, resolved
    assert all("/" not in name for name in names)
    notes = " ".join(held.notes)
    assert "escape.gguf: leaves the models folder" in notes
    assert "with space.gguf: a name the hub's protocol cannot carry" in notes
    assert "a second file named model-b.gguf" in notes


def test_a_models_header_is_read_and_a_header_that_does_not_read_says_nothing(
    models: Path,
) -> None:
    from mcgyvr.rig import inventory

    held = {m.name: m for m in inventory.read(str(models)).models}
    model = held["model-b.gguf"]
    assert (model.arch, model.n_layers, model.n_ctx_train) == (ARCH, 4, 4096)
    assert (model.n_embd, model.n_head_kv) == (64, 2)
    # 4 layers x 2 KV heads x (64 / 8) wide, K and V, at 34 bytes per 32.
    assert model.kv_bytes_per_token == (4 * 2 * 8 * 2) * 34 // 32
    assert model.size_bytes == (models / "model-b.gguf").stat().st_size
    broken = held["broken.gguf"]
    assert broken.size_bytes == len(b"not a model at all")
    assert (broken.arch, broken.n_layers, broken.kv_bytes_per_token) == (
        None,
        None,
        None,
    )


def test_a_head_is_started_only_on_a_name_the_inventory_holds(models: Path) -> None:
    from mcgyvr.rig import inventory

    held = inventory.read(str(models))
    assert inventory.resolve(held, "model-a.gguf") == "dense/model-a.gguf"
    for name in ("../outside.gguf", "escape.gguf", "dense/model-a.gguf", "hidden.gguf"):
        assert inventory.resolve(held, name) is None


def test_no_folder_or_a_folder_that_is_not_there_holds_nothing(tmp_path: Path) -> None:
    from mcgyvr.rig import inventory

    assert inventory.read(None).models == ()
    missing = inventory.read(str(tmp_path / "nowhere"))
    assert missing.models == () and missing.notes
