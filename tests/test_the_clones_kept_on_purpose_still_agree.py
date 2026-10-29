"""Four pairs of functions are copies on purpose, and each pair still agrees.

* ``serving.fetcher.weights_dir`` and ``serving.rigscan.default_weights_dir``:
  both files are sent to a rig as one standard-library file each, so neither
  can import the other.
* ``hostos.popen_group_kwargs``/``kill_group`` and rigscan's
  ``_group_kwargs``/``_kill_group``: rigscan is that one file, so it cannot
  import ``hostos``.
* ``detect._quoted`` and ``fleet.harness._bounded``: the harness is piped to a
  rig as source and must stay standard-library only.
* ``orchestrator.languages.engine.walk`` and ``gate.adapters.javascript._walk``:
  the adapter importing the orchestrator would be an import cycle.

A fix made to one copy and not the other would leave the two disagreeing
without any test noticing, so each pair is held to one answer here.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr import detect, hostos
from mcgyvr.fleet import harness
from mcgyvr.gate.adapters import javascript
from mcgyvr.orchestrator.languages import engine
from mcgyvr.serving import fetcher, rigscan
from tests.hostos_fakes import PLATFORMS, as_system


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


@pytest.mark.parametrize("system", sorted(PLATFORMS))
def test_both_start_a_child_heading_its_own_group_the_same_way(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    assert rigscan._group_kwargs() == hostos.popen_group_kwargs()


class _Child:
    pid = 4242

    def __init__(self, done: list[Any]) -> None:
        self.done = done

    def kill(self) -> None:
        self.done.append("kill")


@pytest.mark.parametrize("system", sorted(PLATFORMS))
def test_both_kill_a_group_the_same_way(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    done: list[Any] = []
    monkeypatch.setattr(
        os, "killpg", lambda pid, sig: done.append(("killpg", pid, sig))
    )
    monkeypatch.setattr(
        subprocess, "run", lambda argv, **_kw: done.append(("run", argv))
    )
    hostos.kill_group(cast(Any, _Child(done)))
    by_hostos = list(done)
    done.clear()
    rigscan._kill_group(cast(Any, _Child(done)))
    assert done == by_hostos
    assert done


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
    one = [cast(_Node, n).name for n in engine.walk(cast(Any, tree))]
    other = [cast(_Node, n).name for n in javascript._walk(cast(Any, tree))]
    assert one == other
    assert sorted(one) == sorted(["root", "a", "a1", "a2", "a2x", "b"])
