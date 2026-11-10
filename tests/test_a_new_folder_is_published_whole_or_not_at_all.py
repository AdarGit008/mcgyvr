"""A new folder is published whole or not at all, by ``atomic.publish_dir``.

A promoted fleet and a sample run's stamp are each a new folder that must hold
every file or never appear, and must never be written over one that appeared
while it was built. Both were the same build, re-check, rename and clean-up,
written twice; they are now :func:`mcgyvr.atomic.publish_dir`, and each keeps
its own refusal text around its :class:`~mcgyvr.atomic.TargetAppearedError`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from mcgyvr import atomic

FILES = {Path("fleet.yaml"): b"fleets: {}\n", Path("locks/a.json"): b"{}\n"}


class _Racing(Mapping[Path, bytes]):
    """The files, and a `target` someone else makes while they are written."""

    def __init__(self, target: Path) -> None:
        self.target = target

    def __getitem__(self, key: Path) -> bytes:
        return FILES[key]

    def __len__(self) -> int:
        return len(FILES)

    def __iter__(self) -> Iterator[Path]:
        self.target.mkdir()
        (self.target / "theirs").write_text("kept")
        return iter(FILES)


def _tree(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


def test_every_file_lands_and_no_staging_is_left(tmp_path: Path) -> None:
    target = tmp_path / "fleets" / "home@2026-11-11"

    atomic.publish_dir(target, FILES)

    assert _tree(target) == ["fleet.yaml", "locks", "locks/a.json"]
    assert (target / "locks/a.json").read_bytes() == b"{}\n"
    assert [p.name for p in target.parent.iterdir()] == [target.name]


def test_a_folder_that_appeared_is_refused_and_left_as_it_is(tmp_path: Path) -> None:
    target = tmp_path / "home@2026-11-11"

    with pytest.raises(atomic.TargetAppearedError, match="appeared while"):
        atomic.publish_dir(target, _Racing(target))

    assert _tree(target) == ["theirs"]
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_promote_says_its_own_refusal(tmp_path: Path) -> None:
    from mcgyvr.fleet import promote

    folder = tmp_path / "home@2026-11-11"

    with pytest.raises(promote.PromoteRefusedError) as refused:
        promote._build(folder, _Racing(folder))  # type: ignore[arg-type]

    assert str(refused.value) == (
        f"{folder} appeared while it was being built; it is left as it is"
    )
    assert _tree(folder) == ["theirs"]
