"""A rename of a module's own function leaves another module's attribute alone.

E2e run 2: renaming ``load`` to ``load_json`` in ``src/app/store.py`` turned the
function's own body, ``return json.load(f)``, into ``json.load_json(f)``. The
index records a call ``a.f()`` as a reference named ``f`` with no receiver, and
the rename substituted the name over every line the index named. The rewrite is
now made at the spans a parser resolved to the definition, so ``json.load`` —
an attribute of the ``json`` module — is left as it was, and said to be.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed, read

STORE = """\
import json


def load(path):
    with open(path) as f:
        return json.load(f)
"""

CLI = """\
from app.store import load


def main(path):
    return load(path)
"""

#: Its own ``load``, imported from the standard library: another symbol.
STDLIB = """\
from json import load


def parse(stream):
    return load(stream)
"""

TREE = {"src/app/store.py": STORE, "src/app/cli.py": CLI, "src/app/raw.py": STDLIB}


def test_the_attribute_of_the_json_module_is_not_renamed(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TREE)

    rename_apply(repo, "load", "load_json")

    after = read(repo, TREE)
    assert after["src/app/store.py"] == STORE.replace("def load(", "def load_json("), (
        "json.load(f) is the json module's load, not this module's"
    )
    assert "return json.load(f)" in after["src/app/store.py"]


def test_the_definition_its_import_and_its_call_are_renamed(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "load", "load_json")

    assert read(repo, TREE)["src/app/cli.py"] == (
        "from app.store import load_json\n\n\ndef main(path):\n"
        "    return load_json(path)\n"
    )
    assert report.files == ("src/app/cli.py", "src/app/store.py")
    assert report.occurrences == 3
    assert report.locations == (("src/app/cli.py", (1, 5)), ("src/app/store.py", (4,)))


def test_a_load_imported_from_the_standard_library_is_not_renamed(
    tmp_path: Path,
) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "load", "load_json")

    assert read(repo, TREE)["src/app/raw.py"] == STDLIB
    assert "src/app/raw.py:1 from json import load" in report.left_alone
    assert "src/app/raw.py:5 load" in report.left_alone


def test_the_report_names_what_it_left_alone_and_why(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "load", "load_json")

    assert "src/app/store.py:6 json.load" in report.left_alone
    assert report.summary().splitlines()[:3] == [
        "renamed load -> load_json: 3 occurrence(s) in 2 file(s)",
        "  src/app/cli.py: line(s) 1, 5",
        "  src/app/store.py: line(s) 4",
    ]
    assert (
        "3 same-named occurrence(s) of another symbol, left alone:"
        in report.summary().splitlines()
    )
    assert "  src/app/store.py:6 json.load" in report.summary().splitlines()
