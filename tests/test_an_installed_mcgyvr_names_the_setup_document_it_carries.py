"""An installed mcgyvr names the SETUP.md it carries; a checkout names its own.

`mcgyvr run` with no setup to load says where SETUP.md is. A wheel has no
``skills/`` folder beside it, so the build copies the checkout's SETUP.md into
the package (read here from ``pyproject.toml``; no wheel is built) and
``setup_doc`` names that copy when it is there, and the checkout's path
otherwise, the order every shipped data file is looked for in.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

import pytest

from mcgyvr.cli.common import SETUP_DOC, setup_doc
from tests._paths import REPO


def test_the_build_copies_the_checkouts_setup_document_into_the_package() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    force = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    sources = [s for s, target in force.items() if target == "mcgyvr/data/SETUP.md"]
    assert sources == [SETUP_DOC], force
    assert (REPO / SETUP_DOC).is_file()


def test_a_packaged_copy_is_named_before_the_checkouts_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged = tmp_path / "package" / "data" / "SETUP.md"
    packaged.parent.mkdir(parents=True)
    packaged.write_text("# Setting up mcgyvr\n", encoding="utf-8")
    monkeypatch.setattr(resources, "files", lambda _name: tmp_path / "package")
    assert setup_doc() == str(packaged)


def test_without_a_packaged_copy_the_checkouts_path_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package").mkdir()
    monkeypatch.setattr(resources, "files", lambda _name: tmp_path / "package")
    assert setup_doc() == SETUP_DOC
