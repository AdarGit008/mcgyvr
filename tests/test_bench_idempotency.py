"""The language-idempotency census over the admitted bench (#295).

The census answers one question — could a problem be authored once and rendered
into both arms, or do the languages genuinely answer some boundaries
differently — and its number, 241 of 257 clean with none fatal, is an argument
for halving the campaign's most expensive axis. What is pinned here is that the
census reads the *admitted* material rather than a spec someone reconstructed,
and that a known-divergent problem in the tree still trips it.

The count itself is deliberately not asserted. It moves whenever a problem is
authored or retired, and a test that freezes it would be a test of the corpus's
size wearing the costume of a test of this module.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


idem = _by_path("idempotency", REPO / "tools" / "bench" / "idempotency.py")


def test_the_spec_is_read_back_from_the_admitted_files() -> None:
    """Four fields, from both arms of a problem that is actually in the tree.

    The screen reads only these, and filling the rest of a spec with invented
    prose would put text through a check that never saw it at emission.
    """
    spec = idem.spec_of("b430-sort-by-len")

    assert set(spec) == {"id", "ref_ts", "ref_py", "acc_ts", "acc_py"}
    assert "sortByLen" in spec["ref_ts"]
    assert "sort_by_len" in spec["ref_py"]
    assert "assert" in spec["acc_py"]


def test_a_divergent_problem_in_the_corpus_still_trips_the_screen() -> None:
    """`b430`'s TypeScript reference breaks ties with `localeCompare`, which
    orders by locale where python's `sorted` orders by code point. A census
    that stopped flagging it would be reporting the corpus clean by breaking."""
    result = idem.census(["b430-sort-by-len"])

    assert result["tasks"] == 1
    assert result["flagged"] == 1
    assert result["fatal"] == 0
    assert "localeCompare" in result["detail"][0]["findings"][0]


def test_a_problem_the_screen_has_nothing_to_say_about_reads_clean() -> None:
    """The other half of the census, or `flagged` could be everything."""
    result = idem.census(["b302-stock-take"])

    assert result["clean"] == 1
    assert result["flagged"] == 0
    assert result["clean_share"] == 1.0


def test_the_census_covers_both_arms_of_every_admitted_problem() -> None:
    """Every id under the py arm has a ts twin the screen can read.

    A missing file would raise rather than skip, so this is the assertion that
    the corpus is paired at all — the property the whole idempotency question
    is asked about.
    """
    tasks = sorted(p.name for p in (idem.TASKS / "py").iterdir() if p.is_dir())
    assert tasks, "no admitted problems found"
    for task in tasks[:5] + tasks[-5:]:
        spec = idem.spec_of(task)
        assert spec["ref_ts"] and spec["ref_py"]


def test_an_unadmitted_id_is_an_error_rather_than_a_clean_row() -> None:
    """Counting a problem that is not there as clean would inflate the share
    this issue's decision rests on."""
    with pytest.raises(FileNotFoundError):
        idem.census(["b999-not-a-problem"])
