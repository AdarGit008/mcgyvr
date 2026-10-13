"""A committed tree to rename in, and a way to read it back.

The rename builds mcgyvr's index first, and the index enumerates with ``git
ls-files``: a tree that is not a commit is a tree with no files in it. One
helper, so every rename test builds its tree the same way.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tests import livejournal as lj


def committed(root: Path, files: Mapping[str, str | bytes]) -> Path:
    """``files`` written under ``root`` and committed; ``root`` returned."""
    root.mkdir(parents=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    lj.git(root, "init", "-q")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-qm", "base")
    return root


def read(root: Path, files: Mapping[str, str | bytes]) -> dict[str, str]:
    """The text now at each of ``files``' paths."""
    return {name: (root / name).read_text(encoding="utf-8") for name in files}


def untouched(root: Path, files: Mapping[str, str | bytes]) -> bool:
    """Whether every file is byte for byte what it was committed as."""
    return all(
        (root / name).read_bytes()
        == (content if isinstance(content, bytes) else content.encode("utf-8"))
        for name, content in files.items()
    )
