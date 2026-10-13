"""A rename that cannot tell which symbol is meant refuses, and writes nothing.

Each case is one where a parser can say where the name is but not which of
several things it means — or where renaming it would change what some other
use means. A half-right rename across a tree is worse than none: it parses,
it passes, and it is wrong. So each is a :class:`RenameError` raised before any
file is written, and each test asserts the tree is byte for byte as committed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.rename import RenameError
from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed, read, untouched


def test_a_name_defined_only_as_a_method_is_refused(tmp_path: Path) -> None:
    tree = {
        "src/app/store.py": "class Store:\n    def load(self):\n        return 1\n",
        "src/app/use.py": "def go(store):\n    return store.load()\n",
    }
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match="only as a method") as refused:
        rename_apply(repo, "load", "load_all")

    assert "type of `x`" in str(refused.value)
    assert untouched(repo, tree)


TWO = {
    "src/app/a.py": "def load():\n    return 1\n",
    "src/app/b.py": "def load():\n    return 2\n",
    "src/app/use.py": "from app.a import load\n\nload()\n",
}


def test_two_defining_modules_and_no_target_to_pick_one_is_refused(
    tmp_path: Path,
) -> None:
    repo = committed(tmp_path / "repo", TWO)

    with pytest.raises(
        RenameError, match="`target` must name the one meant"
    ) as refused:
        rename_apply(repo, "load", "load_all")

    assert "src/app/a.py, src/app/b.py" in str(refused.value)
    assert untouched(repo, TWO)


def test_a_target_that_names_one_of_them_picks_it(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TWO)

    report = rename_apply(repo, "load", "load_all", target="src/app/a.py")

    after = read(repo, TWO)
    assert after["src/app/a.py"] == "def load_all():\n    return 1\n"
    assert after["src/app/b.py"] == TWO["src/app/b.py"]
    assert after["src/app/use.py"] == "from app.a import load_all\n\nload_all()\n"
    assert report.files == ("src/app/a.py", "src/app/use.py")


def test_a_target_glob_that_matches_both_is_still_refused(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TWO)

    with pytest.raises(RenameError, match="matches 2 of them"):
        rename_apply(repo, "load", "load_all", target="src/app/*.py")

    assert untouched(repo, TWO)


def test_a_new_name_already_bound_where_the_rename_lands_is_refused(
    tmp_path: Path,
) -> None:
    tree = {
        "src/app/a.py": "def load():\n    return 1\n",
        "src/app/use.py": (
            "from app.a import load\n\nload_all = 3\n\nprint(load(), load_all)\n"
        ),
    }
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match=r"src/app/use\.py:3") as refused:
        rename_apply(repo, "load", "load_all")

    assert "collide" in str(refused.value)
    assert untouched(repo, tree)


def test_a_new_name_that_would_capture_a_reference_is_refused(tmp_path: Path) -> None:
    tree = {
        "src/app/a.py": "def load():\n    return 1\n",
        "src/app/use.py": (
            "from app.a import load\n\n\ndef go(load_all):\n    return load()\n"
        ),
    }
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match="captured") as refused:
        rename_apply(repo, "load", "load_all")

    assert "src/app/use.py:5" in str(refused.value)
    assert untouched(repo, tree)


def test_a_module_that_binds_the_name_twice_over_is_refused(tmp_path: Path) -> None:
    tree = {
        "src/app/a.py": "def load():\n    return 1\n",
        "src/app/use.py": (
            "try:\n    from app.a import load\nexcept ImportError:\n"
            "    from json import load\n\nload()\n"
        ),
    }
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match="both to the symbol being renamed"):
        rename_apply(repo, "load", "load_all")

    assert untouched(repo, tree)


def test_a_class_body_that_reads_a_name_it_also_binds_is_refused(
    tmp_path: Path,
) -> None:
    """``load = load`` in a class reads the module's ``load`` the first time."""
    tree = {
        "src/app/a.py": "def load():\n    return 1\n\n\nclass C:\n    load = load\n"
    }
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match=r"src/app/a\.py:6"):
        rename_apply(repo, "load", "load_all")

    assert untouched(repo, tree)


def test_a_javascript_shorthand_property_is_refused(tmp_path: Path) -> None:
    tree = {
        "src/a.js": "export function fetchPage() {}\n",
        "src/b.js": (
            'import { fetchPage } from "./a.js";\nexport const api = { fetchPage };\n'
        ),
    }
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match="shorthand") as refused:
        rename_apply(repo, "fetchPage", "getPage")

    assert "src/b.js:2" in str(refused.value)
    assert untouched(repo, tree)


def test_a_name_with_no_definition_at_all_is_refused(tmp_path: Path) -> None:
    tree = {"src/app/use.py": "from json import load\n\nload()\n"}
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match="no definition of 'load'"):
        rename_apply(repo, "load", "load_all")

    assert untouched(repo, tree)
