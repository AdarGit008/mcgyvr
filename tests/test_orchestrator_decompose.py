"""#50 is the judgment step, so these tests hold it to the three things it makes
acceptance criteria — an emitted contract is accepted by the direct-mode API
unchanged, a request that cannot be decomposed produces an explanation rather
than a degenerate single contract, and the same prompt over the same repository
yields the same shape — plus the boundary ADR-0007 draws through the middle of
it: the proposer names references, the index states facts.

The reproducibility tests hold the one non-deterministic ingredient still by
supplying a fixed proposer. That is deliberate and is the only honest way to
assert the property: what must be reproducible is *this module's* treatment of a
judgement, not a model's temperature.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr import contract as contract_module
from mcgyvr.catalog import catalog
from mcgyvr.config import Config, Ladder
from mcgyvr.orchestrator.decompose import (
    DepRef,
    Proposal,
    RecordedProposer,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import estimate_tokens


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    """A small repository with a helper worth depending on and a target to fix."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "pagination.py").write_text(
        "def paginate(items: list[int], size: int = 10) -> list[int]:\n"
        '    """Split into pages."""\n'
        "    return items[:size]\n"
    )
    (root / "listing.py").write_text(
        "from pagination import paginate\n\n\ndef listing(items):\n    return items\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def a_fix(**overrides: object) -> Proposal:
    """A well-formed proposal: a bug fix on listing.py depending on paginate.

    Carries stop conditions and acceptance commands because ``bug_fix`` is a
    type a model executes, and the schema requires both of a contract nobody
    could otherwise judge. The decomposer does not invent either — which is why
    they are here and not in the module.
    """
    base = {
        "task_type": "bug_fix",
        "task": "listing() ignores the page size; page the items before returning.",
        "target": "listing.py",
        "interface": "listing(items, size=10) -> list",
        "deps": (DepRef("pagination.py", "paginate", "page the items with this"),),
        "stop_conditions": ("the pager's contract is ambiguous",),
        "acceptance": ("pytest -q",),
    }
    return Proposal(**{**base, **overrides})  # type: ignore[arg-type]


# --- acceptance: direct mode accepts what the orchestrator emits ------------


def test_an_emitted_contract_round_trips_through_the_public_api(repo: Index) -> None:
    """The emitted text is what `mcgyvr contract` would accept, byte for byte."""
    result = decompose(
        repo, "fix the listing pager", propose=RecordedProposer((a_fix(),))
    )

    assert result.refusals == ()
    (built,) = result.contracts
    (document,) = result.documents
    assert contract_module.loads(document) == built
    assert contract_module.loads(contract_module.dumps(built)) == built


def test_the_emitted_contract_carries_what_the_proposal_asked_for(repo: Index) -> None:
    (built,) = decompose(
        repo, "fix the listing pager", propose=RecordedProposer((a_fix(),))
    ).contracts

    assert built.task_type == "bug_fix"
    assert built.target == "listing.py"
    assert built.acceptance == ("pytest -q",)
    # Scope defaults to the target alone — the smallest well-scoped unit.
    assert built.scope.allow == ("listing.py",)


# --- ADR-0007: the proposer names, the index states -------------------------


def test_the_dependency_signature_comes_from_the_index(repo: Index) -> None:
    """Not from the proposal — there is no field on DepRef that could carry it."""
    (built,) = decompose(
        repo, "fix the listing pager", propose=RecordedProposer((a_fix(),))
    ).contracts

    (dep,) = built.deps
    assert dep.path == "pagination.py"
    assert dep.note == "page the items with this"
    assert dep.signature == (
        "def paginate(items: list[int], size: int=10) -> list[int]:\n"
        '    """Split into pages."""'
    )
    # The signature is exactly what the index holds, not a paraphrase of it.
    indexed = repo.symbols.definitions("paginate")[0]
    assert dep.signature == indexed.signature


def test_a_dependency_the_index_cannot_name_is_refused_not_described(
    repo: Index,
) -> None:
    """ADR-0007's deliberate trade: a missing dep degrades, an invented one poisons."""
    proposal = a_fix(deps=(DepRef("pagination.py", "conjured_helper"),))
    result = decompose(repo, "fix it", propose=RecordedProposer((proposal,)))

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert "conjured_helper" in refusal.reason
    assert "ADR-0007" in refusal.reason


def test_an_import_is_not_a_definition_for_dependency_purposes(repo: Index) -> None:
    """listing.py imports paginate; that is a mention, not a statement of shape."""
    proposal = a_fix(deps=(DepRef("listing.py", "paginate"),))
    result = decompose(repo, "fix it", propose=RecordedProposer((proposal,)))

    assert result.contracts == ()
    assert "cannot state a signature" in result.refusals[0].reason


def test_a_target_the_repository_does_not_hold_is_refused(repo: Index) -> None:
    proposal = a_fix(target="nowhere.py", deps=())
    result = decompose(repo, "fix it", propose=RecordedProposer((proposal,)))

    assert result.contracts == ()
    assert "no such file in the index" in result.refusals[0].reason


# --- acceptance: an undecomposable request explains itself ------------------


def test_proposing_nothing_explains_rather_than_emitting_one_big_contract(
    repo: Index,
) -> None:
    result = decompose(repo, "make it better somehow", propose=RecordedProposer(()))

    assert result.contracts == ()
    assert result.empty
    (refusal,) = result.refusals
    assert refusal.subject == "request"
    assert "nothing could be proposed" in refusal.reason
    # The explanation names the way forward, not just the failure.
    assert "Servable types:" in refusal.reason


def test_a_refused_proposal_leaves_the_others_standing(repo: Index) -> None:
    """One bad unit of work does not sink a decomposition that also found good ones."""
    bad = a_fix(target="gone.py", deps=())
    result = decompose(repo, "two things", propose=RecordedProposer((a_fix(), bad)))

    assert [c.target for c in result.contracts] == ["listing.py"]
    assert [r.subject for r in result.refusals] == ["gone.py"]


def test_a_contract_the_schema_rejects_becomes_a_refusal_with_its_message(
    repo: Index,
) -> None:
    """bug_fix requires evidence only a command can produce, so this cannot load."""
    result = decompose(
        repo, "fix it", propose=RecordedProposer((a_fix(acceptance=()),))
    )

    assert result.contracts == ()
    reason = result.refusals[0].reason
    assert "does not validate" in reason
    # The loader's own message, which already names the field and states the fix.
    assert "acceptance" in reason


def test_the_decomposer_invents_neither_stop_conditions_nor_acceptance(
    repo: Index,
) -> None:
    """Both are judgements. A module that filled them in would be fabricating."""
    result = decompose(
        repo, "fix it", propose=RecordedProposer((a_fix(stop_conditions=()),))
    )

    assert result.contracts == ()
    assert "stop_conditions" in result.refusals[0].reason


# --- acceptance: the same prompt and repository yield the same shape --------


def test_two_decompositions_are_identical(repo: Index) -> None:
    first = decompose(repo, "fix the pager", propose=RecordedProposer((a_fix(),)))
    second = decompose(repo, "fix the pager", propose=RecordedProposer((a_fix(),)))

    assert first.contracts == second.contracts
    assert first.documents == second.documents


def test_the_contract_id_is_a_function_of_the_work_not_of_the_clock(
    repo: Index,
) -> None:
    """An id from a clock or a counter would defeat reproducibility at field one."""
    (built,) = decompose(repo, "fix", propose=RecordedProposer((a_fix(),))).contracts
    (again,) = decompose(repo, "fix", propose=RecordedProposer((a_fix(),))).contracts

    assert built.id == again.id
    assert built.id.startswith("bug_fix-")

    changed = a_fix(task="a different directive")
    (other,) = decompose(repo, "fix", propose=RecordedProposer((changed,))).contracts
    assert other.id != built.id


def test_the_same_unit_of_work_twice_is_refused_as_a_duplicate(repo: Index) -> None:
    result = decompose(repo, "fix", propose=RecordedProposer((a_fix(), a_fix())))

    assert len(result.contracts) == 1
    assert "duplicates contract" in result.refusals[0].reason


# --- refusing what no configured ladder can serve ---------------------------


def tools_only_config() -> Config:
    """An install with nothing bound: the deterministic family and no other.

    Built directly rather than parsed, the same way `tests/test_catalog.py` does
    it — what is under test is the refusal, not the config loader. No shipped
    type starts on `api`, so a keyless install refuses nothing; a machine with
    no rung bound at all is the configuration that genuinely cannot serve work a
    model has to do.
    """
    return Config(path=None, data={}, sources={}, ladder=Ladder(tiers=()))


def test_without_a_config_the_whole_vocabulary_is_on_offer(repo: Index) -> None:
    """Inspecting a repository before a machine is configured is a real case."""
    proposer = RecordedProposer((a_fix(),))
    decompose(repo, "fix", propose=proposer)

    (evidence,) = proposer.seen
    assert {t.name for t in evidence.vocabulary} == set(
        contract_module.task_type_names()
    )


def test_a_type_no_configured_rung_serves_is_refused_by_name(repo: Index) -> None:
    """Routing optimistically and failing at dispatch is the alternative."""
    config = tools_only_config()
    servable = {t.name for t in catalog().servable(config)}
    assert "bug_fix" not in servable, "bug_fix starts on local; nothing is bound"

    result = decompose(
        repo, "fix it", propose=RecordedProposer((a_fix(),)), config=config
    )

    assert result.contracts == ()
    reason = result.refusals[0].reason
    assert "must start on the 'local' family" in reason
    assert "no configured rung serves it" in reason
    # The refusal names what this ladder *can* run, not just what it cannot.
    assert sorted(servable)[0] in reason


def test_the_proposer_is_only_offered_types_the_ladder_can_serve(repo: Index) -> None:
    """A proposer that never sees an unservable type cannot propose one."""
    proposer = RecordedProposer(())
    decompose(repo, "fix it", propose=proposer, config=tools_only_config())

    (evidence,) = proposer.seen
    assert {t.name for t in evidence.vocabulary} == {
        t.name for t in catalog().servable(tools_only_config())
    }
    assert "bug_fix" not in {t.name for t in evidence.vocabulary}


def test_an_unknown_task_type_names_the_vocabulary(repo: Index) -> None:
    proposal = a_fix(task_type="teleport", deps=())
    result = decompose(repo, "do it", propose=RecordedProposer((proposal,)))

    assert result.contracts == ()
    assert "is not a task type" in result.refusals[0].reason


# --- the deterministic pass always runs first -------------------------------


def test_the_proposer_is_handed_the_deterministic_pass(repo: Index) -> None:
    """ADR-0001 boundary 2 as a type: evidence is given, never fetched."""
    proposer = RecordedProposer((a_fix(),))
    result = decompose(repo, "the listing pager", propose=proposer)

    (evidence,) = proposer.seen
    assert evidence.prompt == "the listing pager"
    assert evidence.index is repo
    assert evidence.resolution is result.resolution
    assert evidence.exploration is result.exploration
    assert [c.path for c in evidence.resolution.candidates]


# --- sizing the context budget (#115 left this open, #50 closes it) ---------


def test_a_small_contract_keeps_the_schema_default_budget(repo: Index) -> None:
    (built,) = decompose(repo, "fix", propose=RecordedProposer((a_fix(),))).contracts
    assert built.max_input_tokens == 4096


def test_a_contract_whose_worker_view_exceeds_the_default_is_sized_up(
    tmp_path: Path,
) -> None:
    """The budget is measured off worker_view, the only thing a prompt is built from."""
    root = tmp_path / "big"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    body = "\n".join(f"    x{i} = {i}" for i in range(50))
    documented = "documented. " * 4000
    (root / "huge.py").write_text(
        f'def huge(a: int) -> int:\n    """{documented}"""\n{body}\n    return a\n'
    )
    (root / "t.py").write_text("def t():\n    return 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    index = build_index(root)

    proposal = a_fix(target="t.py", deps=(DepRef("huge.py", "huge"),))
    (built,) = decompose(index, "fix", propose=RecordedProposer((proposal,))).contracts

    assert built.max_input_tokens > 4096
    assert built.max_input_tokens >= estimate_tokens(built.deps[0].signature)
    # Still a contract the public API accepts.
    assert contract_module.loads(contract_module.dumps(built)) == built
