"""The hub's borders only narrow against the base branch.

The two checks of ``tests/hub_borders.py`` hold the tree to its lists; a pull
request that raised a list and the tree together would pass both. So CI runs
``python3 tests/hub_borders.py --compare <base copy>`` on a pull request, and
this file shows that comparison refuses every way of widening and lets every
way of narrowing through. Copies are this file's own text with one change made,
read as CI reads the base: from the syntax tree, never run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import tests.hub_borders as borders
from tests.hub_borders import narrowed, read_borders

HERE = Path(borders.__file__)
TEXT = HERE.read_text(encoding="utf-8")


def _with(old: str, new: str) -> str:
    assert TEXT.count(old) == 1, old
    return TEXT.replace(old, new)


def _narrowed(changed: str) -> list[str]:
    """What the comparison finds when the base holds ``TEXT`` and the head
    ``changed``."""
    return narrowed(
        read_borders(TEXT, source="base"), read_borders(changed, source="head")
    )


def test_the_copy_read_from_the_syntax_tree_is_the_module() -> None:
    read = read_borders(TEXT, source=str(HERE))
    assert read.hub_client == borders.HUB_CLIENT
    assert read.not_core_files == borders.NOT_CORE_FILES
    assert read.not_core_dirs == borders.NOT_CORE_DIRS
    assert read.hf_hub_files == borders.HF_HUB_FILES
    assert read.hub_words == borders.HUB_WORDS
    assert read.imports == borders.IMPORTS_NOT_YET_MOVED
    assert read.words == borders.WORDS_NOT_YET_MOVED
    assert _narrowed(TEXT) == []


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        ('"route.py": {"relief": 3}', '"route.py": {"relief": 4}', "words: route.py"),
        (
            '"route.py": {"relief": 3}',
            '"route.py": {"relief": 3, "hub": 1}',
            "words: route.py: hub 0 -> 1",
        ),
        (
            '"route.py": {"relief": 3},',
            '"route.py": {"relief": 3},\n    "verify.py": {"rider": 1},',
            "words: verify.py: rider 0 -> 1",
        ),
        (
            '("mcgyvr.sandbox.pooled", "mcgyvr.rig.sessionwire"),',
            '("mcgyvr.sandbox.pooled", "mcgyvr.rig.sessionwire"),\n'
            '        ("mcgyvr.runner", "mcgyvr.rig.rungs"),',
            "imports: mcgyvr.runner: mcgyvr.rig.rungs 0 -> 1",
        ),
        (
            '    "crew": r"(?<![a-z])(?:crew|Crew|CREW)",\n',
            "",
            "HUB_WORDS: 'crew' was dropped",
        ),
        (
            '(?:crew|Crew|CREW)"',
            '(?:crew)"',
            "HUB_WORDS: the pattern of 'crew' changed",
        ),
        (
            'NOT_CORE_FILES = frozenset({"cli.py"})',
            'NOT_CORE_FILES = frozenset({"cli.py", "runner.py"})',
            "NOT_CORE_FILES: 'runner.py' left the core",
        ),
        (
            'NOT_CORE_DIRS = frozenset({"rig"})',
            'NOT_CORE_DIRS = frozenset({"rig", "sandbox"})',
            "NOT_CORE_DIRS: 'sandbox' left the core",
        ),
        (
            '        "serving/run.py",\n',
            '        "serving/run.py",\n        "runner.py",\n',
            "HF_HUB_FILES: 'hub' is no longer read in 'runner.py'",
        ),
        (
            'HUB_CLIENT = "mcgyvr.rig"',
            'HUB_CLIENT = "mcgyvr.rig.verbs"',
            "HUB_CLIENT:",
        ),
    ],
)
def test_every_way_of_widening_is_refused(old: str, new: str, said: str) -> None:
    found = _narrowed(_with(old, new))
    assert len(found) == 1 and found[0].startswith(said), found


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"route.py": {"relief": 3}', '"route.py": {"relief": 2}'),
        ('    "route.py": {"relief": 3},\n', ""),
        ('        ("mcgyvr.sandbox.pooled", "mcgyvr.rig.sessionwire"),\n', ""),
        (
            '    "crew": r"(?<![a-z])(?:crew|Crew|CREW)",\n',
            '    "crew": r"(?<![a-z])(?:crew|Crew|CREW)",\n    "lend": r"lend",\n',
        ),
        ('NOT_CORE_DIRS = frozenset({"rig"})', "NOT_CORE_DIRS = frozenset()"),
        ('        "serving/run.py",\n', ""),
    ],
)
def test_every_way_of_narrowing_passes(old: str, new: str) -> None:
    assert _narrowed(_with(old, new)) == []


def test_a_copy_without_the_literals_is_refused() -> None:
    with pytest.raises(ValueError, match="WORDS_NOT_YET_MOVED"):
        read_borders(_with("WORDS_NOT_YET_MOVED: dict", "WORDS_LIST: dict"), source="x")


def _compare(base: Path) -> subprocess.CompletedProcess[str]:
    """The command as CI runs it: by its path, on the standard library alone."""
    return subprocess.run(
        [sys.executable, "-I", str(HERE), "--compare", str(base)],
        cwd=HERE.parent.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_the_command_passes_a_base_like_the_head(tmp_path: Path) -> None:
    base = tmp_path / "base.py"
    base.write_text(TEXT, encoding="utf-8")
    done = _compare(base)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "did not widen" in done.stdout


def test_the_command_fails_a_head_that_raised_a_list(tmp_path: Path) -> None:
    base = tmp_path / "base.py"
    base.write_text(
        _with('"route.py": {"relief": 3}', '"route.py": {"relief": 2}'),
        encoding="utf-8",
    )
    done = _compare(base)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "grew: words: route.py: relief 2 -> 3" in done.stdout
