"""The shipped numbers travel inside the installed package.

An installed mcgyvr has no checkout around it, so the estimates it sizes and
judges with must be a file of the package itself. The build copies the
checkout's file into the package (read here from ``pyproject.toml``; no wheel
is built), and the module looks for the packaged copy first and the checkout's
file second, the way :func:`mcgyvr.capability.table_path` finds its table. With
neither, the numbers are refused by name rather than read from anywhere else.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

import pytest

from mcgyvr import derived

REPO = Path(__file__).resolve().parent.parent


def _packaged_at(monkeypatch: pytest.MonkeyPatch, package_dir: Path) -> None:
    """The package's resources resolve to ``package_dir`` for one test."""
    monkeypatch.setattr(resources, "files", lambda _name: package_dir)


def test_the_build_copies_the_checkout_file_into_the_package() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    force = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    inside = f"mcgyvr/data/{derived.NUMBERS_FILENAME}"
    sources = [source for source, target in force.items() if target == inside]
    assert len(sources) == 1, force
    assert (REPO / sources[0]).resolve() == (
        REPO / "data" / derived.NUMBERS_FILENAME
    ).resolve()
    assert (REPO / sources[0]).is_file()


def test_a_packaged_copy_is_found_before_the_checkout_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged = tmp_path / "package" / "data" / derived.NUMBERS_FILENAME
    packaged.parent.mkdir(parents=True)
    packaged.write_text("{}", encoding="utf-8")
    _packaged_at(monkeypatch, tmp_path / "package")
    assert derived.shipped_path() == packaged


def test_without_a_packaged_copy_the_checkout_file_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package").mkdir()
    _packaged_at(monkeypatch, tmp_path / "package")
    assert (
        derived.shipped_path().resolve()
        == (REPO / "data" / derived.NUMBERS_FILENAME).resolve()
    )


def test_with_neither_the_shipped_numbers_are_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package").mkdir()
    _packaged_at(monkeypatch, tmp_path / "package")
    monkeypatch.setattr(derived, "CHECKOUT_DATA", tmp_path / "no-checkout")
    with pytest.raises(derived.DerivedNumbersError, match=derived.NUMBERS_FILENAME):
        derived.shipped_path()
    with pytest.raises(derived.DerivedNumbersError, match=derived.NUMBERS_FILENAME):
        derived.class_tolerances()
