"""The hardware table travels inside the installed package; no product code reads it.

The build copies the checkout's ``data/hardware-capabilities.json`` into the
package (read here from ``pyproject.toml``; no wheel is built), and the loader
finds the packaged copy first and the checkout's second; with neither, it
refuses by the file's name. No module of the product imports the loader or
names its file: the table ships ahead of its first reader, so it changes nothing
a user gets.
"""

from __future__ import annotations

import ast
import tomllib
from importlib import resources
from pathlib import Path

import pytest

from mcgyvr import hardware_table, shipped
from tests._paths import REPO, SRC


def _packaged_at(monkeypatch: pytest.MonkeyPatch, package_dir: Path) -> None:
    """The package's resources resolve to ``package_dir`` for one test."""
    monkeypatch.setattr(resources, "files", lambda _name: package_dir)


def test_the_build_copies_the_checkout_table_into_the_package() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    force = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    inside = f"mcgyvr/data/{hardware_table.TABLE_FILENAME}"
    sources = [source for source, target in force.items() if target == inside]
    assert sources == [f"data/{hardware_table.TABLE_FILENAME}"], force
    assert (REPO / sources[0]).is_file()


def test_a_packaged_copy_is_found_before_the_checkout_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged = tmp_path / "package" / "data" / hardware_table.TABLE_FILENAME
    packaged.parent.mkdir(parents=True)
    packaged.write_text("{}", encoding="utf-8")
    _packaged_at(monkeypatch, tmp_path / "package")
    assert hardware_table.table_path() == packaged


def test_without_a_packaged_copy_the_checkout_table_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package").mkdir()
    _packaged_at(monkeypatch, tmp_path / "package")
    assert (
        hardware_table.table_path().resolve()
        == (REPO / "data" / hardware_table.TABLE_FILENAME).resolve()
    )


def test_with_neither_the_table_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package").mkdir()
    _packaged_at(monkeypatch, tmp_path / "package")
    monkeypatch.setattr(shipped, "CHECKOUT_DATA", tmp_path / "no-checkout")
    with pytest.raises(
        hardware_table.HardwareTableError, match=hardware_table.TABLE_FILENAME
    ):
        hardware_table.table_path()


def test_no_product_module_imports_the_hardware_table() -> None:
    readers = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "hardware_table.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            if any(name.endswith("hardware_table") for name in names):
                readers.append(str(path.relative_to(SRC)))
    assert not readers, readers


def test_no_product_module_names_the_table_file_but_its_loader() -> None:
    named = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*.py"))
        if path.name != "hardware_table.py"
        and hardware_table.TABLE_FILENAME in path.read_text(encoding="utf-8")
    ]
    assert not named, named
