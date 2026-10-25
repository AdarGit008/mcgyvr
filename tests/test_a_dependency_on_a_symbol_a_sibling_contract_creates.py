"""A dependency may name a symbol another contract in the same set creates.

A cross-file rename is the ordinary case: one contract renames a function in its
module and keeps the old name as an alias, another changes a caller in a second
module to the new name. The index holds only the old name, so the new one has
no signature there yet — but the contract that creates it states it, through
its interface or the rename its task names. The dependency is stated from that
contract, and the dependent waits on it. A symbol nothing in the set creates is
refused as before, and two contracts that each need the other's new symbol have
no order and are refused as a cycle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import contract as contract_module
from mcgyvr.orchestrator.decompose import DepRef, Proposal, RecordedProposer, decompose
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.worker.prompt import build_prompt
from tests.decomposes import git


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    """A module with a function about to be renamed, and a caller of it."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "codec.py").write_text(
        "def rec_to_map(record: dict[str, int]) -> list[tuple[str, int]]:\n"
        "    return sorted(record.items())\n"
    )
    (root / "export.py").write_text(
        "from codec import rec_to_map\n\n\n"
        "def export(records):\n"
        "    return [rec_to_map(r) for r in records]\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def a_change(**overrides: object) -> Proposal:
    base = {
        "task_type": "code",
        "task": "change it",
        "target": "codec.py",
        "stop_conditions": ("the change is ambiguous",),
        "acceptance": ("pytest -q",),
    }
    return Proposal(**{**base, **overrides})  # type: ignore[arg-type]


def a_caller(symbol: str, **overrides: object) -> Proposal:
    """The change to export.py that calls `symbol` in codec.py."""
    return a_change(
        task=f"call {symbol} instead of the old name",
        target="export.py",
        deps=(DepRef("codec.py", symbol, "map each record with this"),),
        **overrides,
    )


@pytest.mark.parametrize(
    ("interface", "signature"),
    [
        # A bare header the parser cannot read is stated as written.
        (
            "def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]",
            "def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]",
        ),
        # A header the parser can read is stated as the index would state it.
        (
            "def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]: ...",
            "def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]:\n    ...",
        ),
    ],
)
def test_a_dependency_on_a_symbol_a_sibling_creates_is_stated_from_its_interface(
    repo: Index, interface: str, signature: str
) -> None:
    # The caller is listed first and states no depends_on: the order and the
    # edge both come from the dependency on the symbol the other one creates.
    caller = a_caller("pairs_of")
    creator = a_change(task="add pairs_of beside rec_to_map", interface=interface)

    result = decompose(
        repo, "add and use it", propose=RecordedProposer((caller, creator))
    )

    assert result.refusals == ()
    first, second = result.contracts
    assert (first.target, second.target) == ("codec.py", "export.py")
    assert second.depends_on == (first.id,)
    (dep,) = second.deps
    assert (dep.path, dep.signature) == ("codec.py", signature)
    assert dep.note == "map each record with this"
    for built, document in zip(result.contracts, result.documents, strict=True):
        assert contract_module.loads(document) == built


def test_a_dependency_on_a_renamed_symbol_is_stated_from_the_rename_its_sibling_states(
    repo: Index,
) -> None:
    # The renaming contract states no interface: its task names the rename,
    # and the index holds the old name's signature, which the new name keeps.
    renamer = a_change(
        task="Rename rec_to_map to record_pairs, keeping rec_to_map as an alias."
    )
    caller = a_caller("record_pairs")

    result = decompose(repo, "rename it", propose=RecordedProposer((renamer, caller)))

    assert result.refusals == ()
    renamed, calling = result.contracts
    assert calling.depends_on == (renamed.id,)
    (dep,) = calling.deps
    assert dep.signature == (
        "def record_pairs(record: dict[str, int]) -> list[tuple[str, int]]:\n    ..."
    )


def test_the_worker_is_shown_the_siblings_signature_not_a_description(
    repo: Index,
) -> None:
    renamer = a_change(task="rename `rec_to_map` to `record_pairs`")
    caller = a_caller("record_pairs")

    result = decompose(repo, "rename it", propose=RecordedProposer((renamer, caller)))

    user = build_prompt(result.contracts[1]).user
    deps = user[user.index("DEPENDENCIES") :].split("\n\n", 1)[0]
    assert "- codec.py: def record_pairs(record: dict[str, int])" in deps, deps
    assert "# map each record with this" in deps, deps


@pytest.mark.parametrize(
    "sibling",
    [
        a_change(task="add pairs_of", interface="def other(x: int) -> int"),
        # A name merely mentioned, as a type here, is not a declaration of it.
        a_change(task="add helper", interface="def helper(x: pairs_of) -> int"),
        # The right interface on another path provides nothing at codec.py.
        a_change(
            task="add pairs_of",
            target="export.py",
            interface="def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]",
        ),
        a_change(task="rename rec_to_map to something_else"),
    ],
)
def test_a_symbol_no_contract_in_the_set_creates_is_still_refused(
    repo: Index, sibling: Proposal
) -> None:
    caller = a_caller("pairs_of")

    result = decompose(repo, "use it", propose=RecordedProposer((sibling, caller)))

    assert [c.target for c in result.contracts] == [sibling.target]
    (refusal,) = result.refusals
    assert refusal.subject == "export.py"
    assert refusal.field == "deps"
    assert "'pairs_of'" in refusal.reason
    assert "no contract in this set creates it" in refusal.reason


def test_a_dependency_on_a_sibling_that_was_refused_is_refused_too(
    repo: Index,
) -> None:
    # The signature is stated from the emitted contract, so when the creator
    # is refused there is nothing to state it from.
    creator = a_change(
        task_type="no-such-type",
        interface="def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]",
    )
    caller = a_caller("pairs_of")

    result = decompose(
        repo, "add and use it", propose=RecordedProposer((creator, caller))
    )

    assert result.contracts == ()
    assert [r.field for r in result.refusals] == ["task_type", "deps"]


def test_two_contracts_that_each_need_the_others_new_symbol_are_refused_as_a_cycle(
    repo: Index,
) -> None:
    codec = a_change(
        task="add pairs_of, built on export's new flatten",
        interface="def pairs_of(record: dict[str, int]) -> list[tuple[str, int]]",
        deps=(DepRef("export.py", "flatten"),),
    )
    export = a_change(
        task="add flatten, built on codec's new pairs_of",
        target="export.py",
        interface="def flatten(records: list[dict[str, int]]) -> list[int]",
        deps=(DepRef("codec.py", "pairs_of"),),
    )

    result = decompose(repo, "both", propose=RecordedProposer((codec, export)))

    assert result.contracts == ()
    assert [r.subject for r in result.refusals] == ["codec.py", "export.py"]
    for refusal in result.refusals:
        assert refusal.field == "deps"
        assert "cycle" in refusal.reason
        assert "another proposal creates" in refusal.reason
