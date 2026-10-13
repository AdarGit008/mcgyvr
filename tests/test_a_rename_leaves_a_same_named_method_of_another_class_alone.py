"""A rename of a module-level function leaves a same-named method alone.

``self.load()`` and ``obj.load()`` reach whatever ``load`` the receiver's type
has, and the index has no types. The index recorded both as references named
``load``, and the rename rewrote their lines; a method of an unrelated class was
renamed along with the function, and its callers were not. A receiver that is
not the defining module is now never rewritten, and the method's own ``def`` is
another definition, not this one.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed, read

HELPERS = """\
def load(path):
    return path
"""

CACHE = """\
from app.helpers import load


class Cache:
    def load(self, key):
        return key

    def warm(self, keys):
        return [self.load(key) for key in keys]


def fill(cache, path):
    cache.load(path)
    return load(path)
"""

TREE = {"src/app/helpers.py": HELPERS, "src/app/cache.py": CACHE}


def test_the_method_its_self_call_and_another_objects_call_are_untouched(
    tmp_path: Path,
) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "load", "read_path")

    after = read(repo, TREE)["src/app/cache.py"]
    assert "    def load(self, key):" in after
    assert "self.load(key)" in after
    assert "cache.load(path)" in after
    assert after.startswith("from app.helpers import read_path\n")
    assert "    return read_path(path)\n" in after
    assert report.occurrences == 3  # the def, the import, the bare call


def test_what_was_left_alone_is_named_with_its_receiver(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "load", "read_path")

    assert "src/app/cache.py:5 def load (in Cache)" in report.left_alone
    assert "src/app/cache.py:9 self.load" in report.left_alone
    assert "src/app/cache.py:13 cache.load" in report.left_alone
