"""Every use of the definition is renamed, called or not; a shadowing local is not.

The index records calls, so a rename driven by it missed every use that was not
one — ``f = fetch_page``, ``map(fetch_page, xs)``, ``@fetch_page``,
``__all__ = ["fetch_page"]`` — and left a tree that named a function that no
longer exists. Uses through the defining module as an object (``w.fetch_page``)
are the same symbol and are renamed; a parameter that happens to share the name
is a different binding and is not.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed, read

WEB = """\
__all__ = ["fetch_page", 'other']


def fetch_page(url):
    return url


def other():
    return fetch_page
"""

USES = """\
from pkg.web import fetch_page

handler = fetch_page
pages = map(fetch_page, ["a", "b"])


@fetch_page
def decorated():
    pass


def shadowed(fetch_page):
    return fetch_page


def global_one():
    global fetch_page
    fetch_page = None


class Holder:
    hook = fetch_page
"""

VIA_MODULE = """\
import pkg.web
import pkg.web as w
from pkg import web


def go():
    return w.fetch_page(1), pkg.web.fetch_page(2), web.fetch_page


def leave():
    return go.fetch_page
"""

TREE = {
    "src/pkg/__init__.py": "",
    "src/pkg/web.py": WEB,
    "src/pkg/uses.py": USES,
    "src/pkg/via_module.py": VIA_MODULE,
}


def test_uses_that_are_not_calls_are_renamed(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TREE)

    rename_apply(repo, "fetch_page", "get_page")

    after = read(repo, TREE)
    assert after["src/pkg/web.py"] == (
        WEB.replace('"fetch_page"', '"get_page"')
        .replace("def fetch_page", "def get_page")
        .replace("return fetch_page", "return get_page")
    )
    uses = after["src/pkg/uses.py"]
    assert "from pkg.web import get_page\n" in uses
    assert "handler = get_page\n" in uses
    assert 'pages = map(get_page, ["a", "b"])\n' in uses
    assert "@get_page\n" in uses
    assert "    global get_page\n    get_page = None\n" in uses
    assert "    hook = get_page\n" in uses


def test_a_parameter_that_shares_the_name_is_not_renamed(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "fetch_page", "get_page")

    uses = read(repo, TREE)["src/pkg/uses.py"]
    assert "def shadowed(fetch_page):\n    return fetch_page\n" in uses
    assert "src/pkg/uses.py:13 fetch_page (local to shadowed)" in report.left_alone


def test_uses_through_the_defining_module_as_an_object_are_renamed(
    tmp_path: Path,
) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "fetch_page", "get_page")

    via = read(repo, TREE)["src/pkg/via_module.py"]
    assert "return w.get_page(1), pkg.web.get_page(2), web.get_page\n" in via
    assert "return go.fetch_page\n" in via, "`go` is not the module"
    assert "src/pkg/via_module.py:11 go.fetch_page" in report.left_alone


PACKAGE = {
    "src/pkg/__init__.py": "from .web import fetch_page\n\n__all__ = ['fetch_page']\n",
    "src/pkg/web.py": "def fetch_page(url):\n    return url\n",
    "src/app/main.py": (
        "import pkg\nfrom pkg import fetch_page\n\n"
        "print(fetch_page(1), pkg.fetch_page(2))\n"
    ),
}


def test_a_package_that_re_exports_the_name_carries_the_rename_to_its_importers(
    tmp_path: Path,
) -> None:
    """``pkg/__init__`` imports the name, so ``pkg`` is a module that has it."""
    repo = committed(tmp_path / "repo", PACKAGE)

    report = rename_apply(repo, "fetch_page", "get_page")

    assert read(repo, PACKAGE) == {
        "src/pkg/__init__.py": "from .web import get_page\n\n__all__ = ['get_page']\n",
        "src/pkg/web.py": "def get_page(url):\n    return url\n",
        "src/app/main.py": (
            "import pkg\nfrom pkg import get_page\n\n"
            "print(get_page(1), pkg.get_page(2))\n"
        ),
    }
    assert report.files == ("src/app/main.py", "src/pkg/__init__.py", "src/pkg/web.py")


def test_a_star_import_of_the_package_is_followed_too(tmp_path: Path) -> None:
    tree = {
        "src/pkg/__init__.py": "from .web import *\n",
        "src/pkg/web.py": "def fetch_page(url):\n    return url\n",
        "src/app/main.py": "from pkg import fetch_page\n\nfetch_page(1)\n",
    }
    repo = committed(tmp_path / "repo", tree)

    rename_apply(repo, "fetch_page", "get_page")

    assert (
        read(repo, tree)["src/app/main.py"]
        == "from pkg import get_page\n\nget_page(1)\n"
    )


def test_an_aliased_import_renames_the_import_and_keeps_the_alias(
    tmp_path: Path,
) -> None:
    tree = {
        "src/pkg/web.py": "def fetch_page(url):\n    return url\n",
        "src/app/main.py": "from pkg.web import fetch_page as fp\n\nfp(1)\n",
    }
    repo = committed(tmp_path / "repo", tree)

    rename_apply(repo, "fetch_page", "get_page")

    assert (
        read(repo, tree)["src/app/main.py"]
        == "from pkg.web import get_page as fp\n\nfp(1)\n"
    )


def test_a_string_that_names_the_symbol_is_reported_not_rewritten(
    tmp_path: Path,
) -> None:
    tree = {
        "src/pkg/web.py": "def fetch_page(url):\n    return url\n",
        "tests/test_web.py": (
            'from unittest import mock\n\nmock.patch("pkg.web.fetch_page")\n'
        ),
    }
    repo = committed(tmp_path / "repo", tree)

    report = rename_apply(repo, "fetch_page", "get_page")

    assert read(repo, tree)["tests/test_web.py"] == tree["tests/test_web.py"]
    assert "tests/test_web.py:3 the string 'pkg.web.fetch_page'" in report.unresolved
