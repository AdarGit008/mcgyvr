"""A dependent of a contract that did not land is held, not climbed.

One module renames a function and another moves its caller to the new name.
When the rename fails, the caller would climb every rung against an import
that cannot work: the tree holds it instead, says who held it and what it
needed, and sends it again only if the rename comes back. Every case here is
read from the contracts and the committed tree; nothing asks a model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.board import Board, held_result, tree_id_for
from mcgyvr.contract import Contract, Dependency
from mcgyvr.scope import Scope
from mcgyvr.tree import BLOCKED, Reason, State, Tree

CODEC = (
    "def rec_to_map(record):\n"
    "    return sorted(record.items())\n\n\n"
    "def average(values):\n"
    "    raise NotImplementedError\n"
)
EXPORT = "from pkg.codec import rec_to_map\n\n\ndef export(rs):\n    return rs\n"
REPORT = "from pkg.codec import rec_to_map\n\n\ndef report(rs):\n    return rs\n"


class Files:
    """A committed tree held in memory."""

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


def source() -> Files:
    return Files(
        {"pkg/codec.py": CODEC, "pkg/export.py": EXPORT, "pkg/report.py": REPORT}
    )


def test_a_dependent_waits_until_its_provider_lands() -> None:
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t")

    assert [c.id for c in tree.ready()] == ["rename"]
    assert tree.state("caller") is State.WAITING
    tree.start("rename")
    assert tree.ready() == ()


def test_a_provider_that_landed_frees_its_dependent() -> None:
    files = source()
    tree = Tree.of([RENAME, CALLER], files, tree_id="t")
    tree.start("rename")
    files.files["pkg/codec.py"] = CODEC.replace("rec_to_map", "pairs_of")

    tree.settle("rename", outcome="accepted", landed=True)

    assert [c.id for c in tree.ready()] == ["caller"]


def test_a_provider_that_failed_holds_its_dependent_and_says_what_it_needed() -> None:
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="ladder_spent", landed=False, result="r.json")

    assert tree.ready() == ()
    assert tree.state("caller") is State.BLOCKED
    hold = tree.held("caller")
    assert hold is not None
    assert hold.reason is Reason.PROVIDER_FAILED
    assert [(p.contract, p.outcome, p.result) for p in hold.providers] == [
        ("rename", "ladder_spent", "r.json")
    ]
    assert [(n.symbol, n.creates) for n in hold.needs] == [
        ("pairs_of", True),
        ("rec_to_map", False),
    ]
    assert "create pairs_of and change rec_to_map" in hold.sentence()
    assert "no rung spent" in hold.sentence()


def test_a_stub_its_provider_was_to_implement_is_a_need_though_it_exists() -> None:
    implement = a_contract("implement", "pkg/codec.py", "Implement the average stub.")
    caller = a_contract(
        "caller",
        "pkg/report.py",
        "Use average from pkg.codec for the mean.",
        target_content=REPORT,
        depends_on=("implement",),
    )
    tree = Tree.of([implement, caller], source(), tree_id="t")
    tree.start("implement")
    tree.settle("implement", outcome="ladder_spent", landed=False)

    hold = tree.held("caller")
    assert hold is not None
    assert [(n.symbol, n.creates) for n in hold.needs] == [("average", False)]


def test_a_dependent_using_only_what_its_failed_provider_leaves_alone_runs() -> None:
    implement = a_contract("implement", "pkg/codec.py", "Implement the average stub.")
    caller = a_contract(
        "caller",
        "pkg/report.py",
        "Rename report to build_report.",
        target_content=REPORT,
        depends_on=("implement",),
    )
    tree = Tree.of([implement, caller], source(), tree_id="t")
    assert tree.edges("caller")[0].uses == ("rec_to_map",)
    tree.start("implement")
    tree.settle("implement", outcome="ladder_spent", landed=False)

    assert [c.id for c in tree.ready()] == ["caller"]


def test_a_stated_wait_with_nothing_to_read_holds_when_the_provider_fails() -> None:
    other = a_contract("other", "pkg/other.py", "Tidy it.", depends_on=("rename",))
    tree = Tree.of([RENAME, other], source(), tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="rejected", landed=False)

    hold = tree.held("other")
    assert hold is not None
    assert hold.reason is Reason.PROVIDER_FAILED
    assert hold.needs == ()
    assert "nothing shows this contract can do without it" in hold.sentence()


def test_a_provider_accepted_but_not_delivered_did_not_land() -> None:
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="accepted", landed=False, detail="left uncommitted")

    hold = tree.held("caller")
    assert hold is not None
    assert hold.reason is Reason.PROVIDER_NOT_LANDED
    assert "left uncommitted" in hold.sentence()


def test_a_provider_that_landed_without_the_new_name_holds_its_dependent() -> None:
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="accepted", landed=True)

    hold = tree.held("caller")
    assert hold is not None
    assert hold.reason is Reason.PROVIDER_LANDED_WITHOUT
    assert [n.symbol for n in hold.needs] == ["pairs_of"]


def test_a_hold_comes_down_the_chain() -> None:
    last = a_contract("last", "pkg/report.py", "Tidy it.", depends_on=("caller",))
    tree = Tree.of([RENAME, CALLER, last], source(), tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="ladder_spent", landed=False)

    hold = tree.held("last")
    assert hold is not None
    assert hold.reason is Reason.PROVIDER_BLOCKED
    assert hold.chain == ("caller",)


def test_a_retried_provider_frees_what_it_held() -> None:
    files = source()
    tree = Tree.of([RENAME, CALLER], files, tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="ladder_spent", landed=False)
    assert tree.state("caller") is State.BLOCKED

    tree.retry("rename")
    assert tree.state("caller") is State.WAITING
    tree.start("rename")
    files.files["pkg/codec.py"] = CODEC.replace("rec_to_map", "pairs_of")
    tree.settle("rename", outcome="accepted", landed=True)

    assert [c.id for c in tree.ready()] == ["caller"]


def test_a_replaced_provider_on_the_same_target_takes_over_its_waits() -> None:
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t")
    tree.start("rename")
    tree.settle("rename", outcome="ladder_spent", landed=False)

    again = a_contract(
        "rename-2", RENAME.target, RENAME.task, interface=RENAME.interface
    )
    tree.replace("rename", again)

    assert tree.state("caller") is State.WAITING
    assert [e.provider for e in tree.edges("caller")] == ["rename-2"]
    assert [c.id for c in tree.ready()] == ["rename-2"]


def test_a_cycle_is_held_and_never_sent() -> None:
    a = a_contract("a", "pkg/codec.py", "Tidy it.", depends_on=("b",))
    b = a_contract("b", "pkg/report.py", "Tidy it.", depends_on=("a",))
    tree = Tree.of([a, b], source(), tree_id="t")

    assert tree.ready() == ()
    hold = tree.held("a")
    assert hold is not None
    assert hold.reason is Reason.CYCLE
    assert hold.chain == ("a", "b")


def test_an_unknown_id_holds_a_sealed_set_and_waits_in_an_open_one() -> None:
    lost = a_contract("lost", "pkg/report.py", "Tidy it.", depends_on=("gone",))

    sealed = Tree.of([lost], source(), tree_id="t")
    open_ = Tree.of([lost], source(), tree_id="t", sealed=False)

    held = sealed.held("lost")
    assert held is not None
    assert held.reason is Reason.UNKNOWN_DEPENDENCY
    assert open_.state("lost") is State.WAITING
    assert [c for c, _ in open_.seal()] == [lost]


def test_a_dep_already_in_the_tree_needs_no_provider() -> None:
    caller = a_contract(
        "caller",
        "pkg/report.py",
        "Map each record.",
        deps=(Dependency("pkg/codec.py", "def rec_to_map(record):\n    ..."),),
    )
    tree = Tree.of([caller], source(), tree_id="t")

    assert [c.id for c in tree.ready()] == ["caller"]


def test_a_dep_nothing_defines_or_creates_is_unprovided() -> None:
    caller = a_contract(
        "caller",
        "pkg/report.py",
        "Map each record.",
        deps=(Dependency("pkg/codec.py", "def nowhere(record) -> list"),),
    )
    tree = Tree.of([caller], source(), tree_id="t")

    hold = tree.held("caller")
    assert hold is not None
    assert hold.reason is Reason.UNPROVIDED
    assert [(n.path, n.symbol) for n in hold.needs] == [("pkg/codec.py", "nowhere")]


def test_a_dep_a_sibling_creates_is_waited_on_though_not_stated() -> None:
    caller = a_contract(
        "caller",
        "pkg/report.py",
        "Map each record.",
        deps=(Dependency("pkg/codec.py", "def pairs_of(record) -> list"),),
    )
    tree = Tree.of([RENAME, caller], source(), tree_id="t")

    assert [e.provider for e in tree.edges("caller")] == ["rename"]
    assert [c.id for c in tree.ready()] == ["rename"]


def test_under_run_a_dependent_goes_once_its_provider_came_to_anything() -> None:
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t", hold=False)
    tree.start("rename")
    assert tree.ready() == ()
    tree.settle("rename", outcome="ladder_spent", landed=False)

    assert [c.id for c in tree.ready()] == ["caller"]


def test_levels_are_waves_by_what_each_contract_waits_on() -> None:
    last = a_contract("last", "pkg/report.py", "Tidy it.", depends_on=("caller",))
    tree = Tree.of([last, CALLER, RENAME], source(), tree_id="t")

    assert tree.levels() == {"rename": 1, "caller": 2, "last": 3}


def test_a_board_keeps_its_trees_apart_and_takes_each_in_turn() -> None:
    one = Tree.of([RENAME, CALLER], source(), tree_id="one")
    two = Tree.of([RENAME, CALLER], source(), tree_id="two")
    board = Board()
    board.attach(one)
    board.attach(two)

    assert [(t.tree_id, c.id) for t, c in board.ready()] == [
        ("one", "rename"),
        ("two", "rename"),
    ]
    board.start("one", "rename")
    board.settle("one", "rename", outcome="ladder_spent", landed=False)

    assert one.state("caller") is State.BLOCKED
    assert two.state("caller") is State.WAITING
    with pytest.raises(ValueError, match="already on this board"):
        board.attach(Tree.of([RENAME], source(), tree_id="one"))


def test_a_drained_board_hands_back_its_held_contracts_as_blocked_results(
    tmp_path: Path,
) -> None:
    journal = tmp_path
    board = Board(journal)
    tree = Tree.of([RENAME, CALLER], source(), tree_id="t")
    board.attach(tree)
    board.start("t", "rename")
    board.settle("t", "rename", outcome="ladder_spent", landed=False)

    dead = board.drain()

    assert [(t.tree_id, c.id) for t, c, _ in dead] == [("t", "caller")]
    assert tree.state("caller") is State.DEAD
    _, contract, hold = dead[0]
    result = held_result(contract, hold, session="o", run="s")
    assert result.outcome == BLOCKED
    assert result.attempts == []
    assert result.exit_code == 3
    assert result.as_json()["blocked_by"]["reason"] == "provider_failed"
    state = (journal / "trees" / "t.json").read_text()
    assert '"state": "dead"' in state


def test_a_tree_id_is_a_digest_not_a_path() -> None:
    name = tree_id_for("/some/where/repo", "abc", ["b", "a"])

    assert name == tree_id_for("/some/where/repo", "abc", ["a", "b"])
    assert "/" not in name and name.startswith("tree-")


def test_a_result_that_was_not_held_carries_no_blocked_by() -> None:
    from mcgyvr.result import RunResult

    result = RunResult(contract="c", task_type="code", target="t", session="o")

    assert "blocked_by" not in result.as_json()
