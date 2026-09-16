"""A round is written whole: a reader of ``rounds.json`` never meets half of one.

``tools/bench/rounds.json`` is read by whatever stamps or checks a round —
telemetry stamping a journal row, the live index, gate 1 itself — and it is
written by two: gate 1, through ``product.ensure_open``, when the tree has moved
off the open round, and an operator's ``product.py --open``. Both wrote it with
``Path.write_text``, which empties the file at open and then fills it, so a
reader in between reads a prefix and fails on the JSON.

What must be observably true: at every moment either writer opens a file to
write, a reader of ``rounds.json`` reads the whole file as it stood before the
append; afterwards it reads the whole file with the new round in it, and
nothing staged is left beside it. Read at each write-mode open rather than
raced, so it holds for no timing reason: a writer that truncates the file in
place is caught at the very open that truncates it.
"""

from __future__ import annotations

import argparse
import builtins
import contextlib
import importlib
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

OPEN = "r1-01-09-2026"


def _product() -> Any:
    return importlib.import_module("tools.bench.product")


def _off_round(tmp_path: Path) -> Path:
    """A rounds file whose open round pins no tree, so an append has one to add."""
    path = tmp_path / "rounds.json"
    doc = {
        "doctrine": {"clauses": ["a boundary is drained, not taken"]},
        "rounds": [{"id": OPEN, "product_sha256": "0" * 64, "adopted": []}],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


@contextlib.contextmanager
def _a_reader_at_every_write(path: Path) -> Iterator[list[bytes]]:
    """What a reader of ``path`` gets each time a file is opened to write.

    ``Path.write_text``, ``open`` and ``os.fdopen`` all arrive at ``io.open`` or
    ``builtins.open``. The read is taken after the open returns, which is when
    a truncating open has already emptied the file. A writer that reaches
    neither is not missed silently: it leaves nothing read, and that is
    asserted against.
    """
    seen: list[bytes] = []
    real = io.open

    def reading(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        handle = real(file, mode, *args, **kwargs)
        if any(flag in mode for flag in "wax+"):
            with real(path, "rb") as reader:
                seen.append(reader.read())
        return handle

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(io, "open", reading)
        patch.setattr(builtins, "open", reading)
        yield seen


def _assert_whole(seen: list[bytes], before: bytes, path: Path, opened: str) -> None:
    assert seen, (
        "the append opened no file through io.open or open, so there was no "
        "moment to read at and this proves nothing about how it wrote"
    )
    for got in seen:
        assert got == before, (
            f"a reader that opened {path.name} while a round was being appended "
            f"read {len(got)} of its {len(before)} bytes: the file was emptied "
            "in place before it was filled"
        )
    rounds = json.loads(path.read_text(encoding="utf-8"))["rounds"]
    assert [entry["id"] for entry in rounds] == [OPEN, opened]
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name], (
        "a staged copy was left beside the rounds file"
    )


def test_a_reader_during_the_doors_append_reads_the_whole_file(
    tmp_path: Path,
) -> None:
    """Gate 1's writer: ``ensure_open`` on a tree that has moved off its round."""
    product = _product()
    path = _off_round(tmp_path)
    before = path.read_bytes()

    with _a_reader_at_every_write(path) as seen:
        opened, _ = product.ensure_open(Path(product.REPO), path)

    _assert_whole(seen, before, path, opened)


def test_a_reader_during_an_operators_open_reads_the_whole_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other writer: ``product.py --open``, a boundary drawn by hand."""
    product = _product()
    path = _off_round(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(product, "ROUNDS_FILE", path)
    args = argparse.Namespace(
        open="r2-15-09-2026",
        opened="2026-09-15",
        issue=None,
        why="a boundary drawn by hand",
        adopted=["#0 the one change this boundary carries"],
    )

    with _a_reader_at_every_write(path) as seen:
        assert product._open_cli(args) == 0

    _assert_whole(seen, before, path, "r2-15-09-2026")
