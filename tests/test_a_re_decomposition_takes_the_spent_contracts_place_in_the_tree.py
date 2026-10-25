"""A re-decomposition takes the spent contract's place in the tree.

A re-plan can come back as more than one contract: a helper first, then the
change on the spent contract's own target that waits on it. The tree takes
them all in the spent one's place, and what waited on the spent contract now
waits on the replacement on its target — or, when none of them is on it, on
every replacement, so nothing that waited is let through before the work that
stands for its provider is done. The board writes the swap to the tree's
state file like any other change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcgyvr.board import Board
from mcgyvr.contract import Contract
from mcgyvr.scope import Scope
from mcgyvr.tree import State, Tree

CODEC = "def rec_to_map(record):\n    return sorted(record.items())\n"
EXPORT = "from pkg.codec import rec_to_map\n\n\ndef export(rs):\n    return rs\n"


class Files:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = dict(files)

    def read(self, path: str) -> bytes | None:
        text = self.files.get(path)
        return None if text is None else text.encode()


def a_contract(cid: str, target: str, task: str, **fields: Any) -> Contract:
    return Contract(
        id=cid,
        task_type="code",
        task=task,
        target=target,
        scope=Scope.of([target], []),
        **fields,
    )


RENAME = a_contract(
    "rename",
    "pkg/codec.py",
    "Rename rec_to_map to pairs_of and update callers within the module.",
    interface="def pairs_of(record) -> list",
)
CALLER = a_contract(
    "caller",
    "pkg/export.py",
    "Call pairs_of from pkg.codec instead of the old rec_to_map.",
    target_content=EXPORT,
    depends_on=("rename",),
)
HELPER = a_contract("helper", "pkg/pairs.py", "Write pairs(record) -> list.")
HEIR = a_contract(
    "heir",
    "pkg/codec.py",
    "Rename rec_to_map to pairs_of, calling pairs from pkg.pairs.",
    interface="def pairs_of(record) -> list",
    depends_on=("helper",),
)
ELSEWHERE = a_contract("elsewhere", "pkg/maps.py", "Write pairs_of(record) -> list.")


def spent_tree() -> Tree:
    tree = Tree.of(
        [RENAME, CALLER],
        Files({"pkg/codec.py": CODEC, "pkg/export.py": EXPORT}),
        tree_id="t",
    )
    tree.start("rename")
    tree.settle("rename", outcome="ladder_spent", landed=False)
    assert tree.state("caller") is State.BLOCKED
    return tree


def test_two_replacements_go_in_and_the_dependent_waits_on_the_one_on_its_target() -> (
    None
):
    tree = spent_tree()

    tree.replace("rename", HELPER, HEIR)

    assert [c.id for c in tree.contracts()] == ["helper", "heir", "caller"]
    assert [e.provider for e in tree.edges("caller")] == ["heir"]
    assert tree.state("caller") is State.WAITING
    assert [c.id for c in tree.ready()] == ["helper"]


def test_with_none_on_its_target_the_dependent_waits_on_every_replacement() -> None:
    tree = spent_tree()

    tree.replace("rename", HELPER, ELSEWHERE)

    assert [e.provider for e in tree.edges("caller")] == ["helper", "elsewhere"]
    assert tree.state("caller") is State.WAITING
    assert tree.held("caller") is None


def test_the_board_writes_the_swap_to_the_trees_state_file(tmp_path: Path) -> None:
    board = Board(tmp_path)
    tree = spent_tree()
    board.attach(tree)

    board.replace("t", "rename", HELPER, HEIR)

    path = board.state_file("t")
    assert path is not None
    rows = [r["contract"] for r in json.loads(path.read_text())["contracts"]]
    assert rows == ["helper", "heir", "caller"]
