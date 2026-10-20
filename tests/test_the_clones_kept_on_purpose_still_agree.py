"""Three pairs of functions are copies on purpose, and each pair still agrees.

* ``serving.fetcher.weights_dir`` and ``serving.rigscan.default_weights_dir``:
  both files are sent to a rig as one standard-library file each, so neither
  can import the other.
* ``detect._quoted`` and ``fleet.harness._bounded``: the harness is piped to a
  rig as source and must stay standard-library only.
* ``orchestrator.symbols._walk`` and ``gate.adapters.javascript._walk``: the
  adapter importing the orchestrator would be an import cycle.

A fix made to one copy and not the other would leave the two disagreeing
without any test noticing, so each pair is held to one answer here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr import detect
from mcgyvr.fleet import harness
from mcgyvr.gate.adapters import javascript
from mcgyvr.orchestrator import symbols
from mcgyvr.serving import fetcher, rigscan


def test_both_weights_directories_read_the_same_variable() -> None:
    assert fetcher.WEIGHTS_DIR_ENV == rigscan.WEIGHTS_DIR_ENV


@pytest.mark.parametrize("value", [None, "", "/srv/weights", "~/x"])
def test_both_weights_directories_give_one_answer(
    value: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    if value is None:
        monkeypatch.delenv(fetcher.WEIGHTS_DIR_ENV, raising=False)
    else:
        monkeypatch.setenv(fetcher.WEIGHTS_DIR_ENV, value)
    assert fetcher.weights_dir() == rigscan.default_weights_dir()


def test_both_quoting_bounds_are_the_same_number() -> None:
    assert detect.ROW_QUOTED_AT_MOST == harness.REPLY_QUOTED_AT_MOST


@pytest.mark.parametrize("length", [0, 10, 197, 198, 199, 200, 201, 5_000])
def test_both_quoters_cut_a_text_the_same_way(length: int) -> None:
    text = "".join(chr(ord("a") + i % 26) for i in range(length)) + "\n'\""
    assert detect._quoted(text) == harness._bounded(text)


@dataclass
class _Node:
    name: str
    children: list[_Node] = field(default_factory=list)


def test_both_walks_visit_a_tree_in_the_same_order() -> None:
    tree = _Node(
        "root",
        [_Node("a", [_Node("a1"), _Node("a2", [_Node("a2x")])]), _Node("b")],
    )
    one = [cast(_Node, n).name for n in symbols._walk(cast(Any, tree))]
    other = [cast(_Node, n).name for n in javascript._walk(cast(Any, tree))]
    assert one == other
    assert sorted(one) == sorted(["root", "a", "a1", "a2", "a2x", "b"])
