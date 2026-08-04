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
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.orchestrator.decompose import (
    DepRef,
    Proposal,
    RecordedProposer,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import estimate_tokens
from mcgyvr.worker.prompt import build_prompt


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


# --- filling the target's content (#155; #150 built the slot) ---------------
#
# #150 gave the contract somewhere to put the file a worker is about to rewrite
# and filled it only where contracts are authored by hand. These hold the other
# half: the delegated path fills it too, from the index, up to a ceiling that
# exists so that sizing the budget off the content cannot make the fit check
# ask whether a number exceeds itself.


def test_an_emitted_contract_carries_its_targets_current_content(repo: Index) -> None:
    """Acceptance: a bug_fix on an existing target reaches the worker seeing it."""
    (built,) = decompose(
        repo, "fix the listing pager", propose=RecordedProposer((a_fix(),))
    ).contracts

    assert built.target_content == (repo.root / "listing.py").read_text()


def test_the_content_is_what_the_index_holds_not_a_fresh_read(repo: Index) -> None:
    """One decomposition, one revision — the whole reason it is not re-read.

    Two contracts emitted from one run must not be able to disagree about one
    file, so the bytes come from the state resolution and exploration already
    judged from. Editing the tree after the index was built is how that becomes
    visible: a fresh read at emit time would pick the new content up.
    """
    (repo.root / "listing.py").write_text("# rewritten after the index was built\n")

    (built,) = decompose(
        repo, "fix the listing pager", propose=RecordedProposer((a_fix(),))
    ).contracts

    assert built.target_content.startswith("from pagination import paginate")
    assert "rewritten after the index" not in built.target_content


def test_the_content_round_trips_through_the_public_loader(repo: Index) -> None:
    """Direct mode accepts what the orchestrator emits — content included."""
    result = decompose(repo, "fix", propose=RecordedProposer((a_fix(),)))

    (built,) = result.contracts
    (document,) = result.documents
    assert contract_module.loads(document) == built
    assert contract_module.loads(contract_module.dumps(built)) == built
    assert contract_module.loads(document).target_content == built.target_content


def test_the_worker_is_shown_the_file_it_is_asked_to_change(repo: Index) -> None:
    """The end #155 exists for, asserted where a worker would see it."""
    (built,) = decompose(repo, "fix", propose=RecordedProposer((a_fix(),))).contracts

    prompt = build_prompt(built)
    assert "CURRENT CONTENT OF listing.py (this is the file to change):" in prompt.user
    assert "def listing(items):" in prompt.user


def test_content_is_filled_for_every_type_not_a_chosen_list(repo: Index) -> None:
    """No task-type branch: the slot is filled from the target, whatever the work.

    The deterministic tier never reads it — a tool opens the file itself — but
    it is not the tier that decides. Ascent (#43) climbs from a contract's floor
    family upward, and the deterministic family binds no rung at all until #81,
    so a contract of any type can end up in front of a model. Content it does
    not need costs a tool nothing; content it needed and lacks is #150's whole
    subject.
    """
    documenting = Proposal(
        task_type="docstring",
        task="document listing()",
        target="listing.py",
        stop_conditions=("the function's behaviour is ambiguous",),
    )

    (built,) = decompose(
        repo, "document it", propose=RecordedProposer((documenting,))
    ).contracts

    assert built.task_type == "docstring"
    assert built.target_content == (repo.root / "listing.py").read_text()


def test_a_target_the_index_does_not_hold_never_reaches_the_content_question(
    repo: Index,
) -> None:
    """ "No content" is not an error here because it is not reachable here.

    A target the index does not hold is refused before content is considered
    (`_indexed`), so the delegated path cannot emit a contract for a file that
    does not exist yet — which direct mode can, and which is why the schema
    calls an empty slot "the target does not exist yet, or its content is not
    needed". Held as a test so the asymmetry is recorded rather than assumed.
    """
    result = decompose(
        repo, "fix", propose=RecordedProposer((a_fix(target="new_module.py"),))
    )

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert "no such file in the index" in refusal.reason


def test_content_that_outgrows_the_default_budget_sizes_it_up_and_survives(
    tmp_path: Path,
) -> None:
    """The budget follows the content — and the rebuild that resizes keeps it.

    ``_resize`` re-emits the document to write the new ceiling, and the content
    has to be carried through that rebuild explicitly. A rebuild that dropped it
    would leave a contract whose budget was sized for a file it no longer holds.
    """
    root = tmp_path / "wide"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    body = "\n".join(
        f"    value_{i} = {i} * 2  # a line of real content" for i in range(400)
    )
    (root / "wide.py").write_text(f"def wide() -> int:\n{body}\n    return value_0\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    index = build_index(root)

    proposal = a_fix(target="wide.py", deps=())
    (built,) = decompose(index, "fix", propose=RecordedProposer((proposal,))).contracts

    assert built.max_input_tokens > 4096
    assert built.target_content == (root / "wide.py").read_text()
    assert built.max_input_tokens >= estimate_tokens(built.target_content)
    assert contract_module.loads(contract_module.dumps(built)) == built


def test_a_target_too_large_to_send_is_refused_not_budgeted_around(
    repo: Index,
) -> None:
    """The ceiling is a stop, not a starting point the sizing negotiates past."""
    result = decompose(
        repo, "fix", propose=RecordedProposer((a_fix(),)), max_input_tokens=20
    )

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert refusal.subject == "listing.py"
    assert "against a ceiling of 20" in refusal.reason
    assert "the target's own content" in refusal.reason
    assert "#126" in refusal.reason


def test_the_ceiling_is_the_callers_to_raise(repo: Index) -> None:
    """It is policy with no measurement behind it, so it is an argument."""
    proposals = RecordedProposer((a_fix(),))

    refused = decompose(repo, "fix", propose=proposals, max_input_tokens=20)
    emitted = decompose(repo, "fix", propose=proposals, max_input_tokens=100_000)

    assert refused.contracts == ()
    assert len(emitted.contracts) == 1


def test_a_target_larger_than_the_default_ceiling_is_refused(tmp_path: Path) -> None:
    """The shipped default is a real bound, not only the argument's placeholder."""
    root = tmp_path / "huge"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    lines = "\n".join(
        f"    entry_{i} = 'a fairly long literal value here'" for i in range(4000)
    )
    (root / "huge.py").write_text(f"def huge() -> None:\n{lines}\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    index = build_index(root)

    result = decompose(
        index, "fix", propose=RecordedProposer((a_fix(target="huge.py", deps=()),))
    )

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert "against a ceiling of 32768" in refusal.reason


# --- the located type checker reaches the contract (#142, ADR-0006) ---------
#
# ADR-0006 ends by naming the gap these cover: "the schema already demands a
# type-check command for the one task type whose guarantee requires one, and
# nothing yet supplies it." #114 built the locator; this is the wiring.


def an_annotation(**overrides: object) -> Proposal:
    """A `type_annotation` proposal with no acceptance of its own.

    The empty `acceptance` is the point. `type_annotation` requires `type_check`
    evidence, which only a command can produce, so a contract that reaches the
    loader like this cannot load — which is what the decomposer has to prevent
    by filling the list in or by refusing.
    """
    base = {
        "task_type": "type_annotation",
        "task": "annotate listing() and its return.",
        "target": "listing.py",
        "stop_conditions": ("the intended element type is ambiguous",),
    }
    return Proposal(**{**base, **overrides})  # type: ignore[arg-type]


def declaring_mypy(repo: Index) -> Index:
    """The same repository, having declared mypy the way mypy reads it."""
    (repo.root / "pyproject.toml").write_text(
        '[tool.mypy]\nfiles = ["."]\nstrict = true\n'
    )
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "declare mypy")
    return build_index(repo.root)


class StubAdapter(PythonAdapter):
    """An adapter that declares a fixed multi-token command for every repository.

    The positive control. "The target is never appended" is an assertion about
    an absence, and an absence is easy to satisfy vacuously — a pipeline that
    dropped every argument would pass it too. This transmits `--flag`, so the
    absence tests are known to be reading a command that arguments *can* reach.
    """

    def locate_type_check_command(self, repo: Path) -> list[str] | None:
        return ["checker", "--flag"]


def test_the_repositorys_own_checker_becomes_the_acceptance_command(
    repo: Index,
) -> None:
    (built,) = decompose(
        declaring_mypy(repo), "annotate", propose=RecordedProposer((an_annotation(),))
    ).contracts

    assert built.acceptance == ("mypy",)


def test_a_repository_declaring_no_checker_emits_no_type_annotation(
    repo: Index,
) -> None:
    """ADR-0006: the correct outcome arriving at the correct layer.

    The contract would fail to load anyway. Refusing here is what makes the
    answer a sentence about the repository rather than a complaint about a field.
    """
    result = decompose(repo, "annotate", propose=RecordedProposer((an_annotation(),)))

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert refusal.subject == "listing.py"
    assert "declares no type checker" in refusal.reason
    assert "ADR-0006" in refusal.reason
    # It names both ways forward, not just the failure.
    assert "Configure a checker" in refusal.reason
    assert "declare the command" in refusal.reason


def test_a_proposals_own_acceptance_is_neither_overruled_nor_appended_to(
    repo: Index,
) -> None:
    """The contract always wins over a sniff — `adapter.py:102-105` says so.

    Appending would let it win and lose at once: the declared command would run,
    and so would the one it was declared instead of.
    """
    declared = an_annotation(acceptance=("make typecheck",))
    (built,) = decompose(
        declaring_mypy(repo), "annotate", propose=RecordedProposer((declared,))
    ).contracts

    assert built.acceptance == ("make typecheck",)


def test_the_located_command_is_emitted_exactly_as_located(repo: Index) -> None:
    """Nothing is appended — not the target, not a path, not a flag.

    `tsc --noEmit file.ts` discards `tsconfig.json` entirely, and mypy's
    `exclude` does not apply to a file named on the command line, so appending
    the target would not narrow the check in either language: it would replace
    it with a different one. Measured on both tools; the reasoning is in
    `_acceptance_for`.
    """
    (built,) = decompose(
        declaring_mypy(repo), "annotate", propose=RecordedProposer((an_annotation(),))
    ).contracts

    (command,) = built.acceptance
    assert command == "mypy"
    assert built.target not in command


def test_arguments_do_reach_the_contract_when_the_locator_states_them(
    repo: Index,
) -> None:
    """The positive control for the assertion above: absence, not emptiness."""
    (built,) = decompose(
        repo,
        "annotate",
        propose=RecordedProposer((an_annotation(),)),
        adapters=(StubAdapter(),),
    ).contracts

    assert built.acceptance == ("checker --flag",)


def test_a_typescript_repository_gets_its_own_project_wide_check(
    tmp_path: Path,
) -> None:
    """The JS/TS arm, which is where per-file checking is not expressible at all."""
    root = tmp_path / "ts"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}\n')
    (root / "listing.ts").write_text(
        "export function listing(items) {\n  return items;\n}\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")

    proposal = an_annotation(target="listing.ts")
    (built,) = decompose(
        build_index(root), "annotate", propose=RecordedProposer((proposal,))
    ).contracts

    assert built.acceptance == ("tsc --noEmit",)
    assert "listing.ts" not in built.acceptance[0]


def test_a_target_no_language_owns_cannot_be_type_checked(tmp_path: Path) -> None:
    root = tmp_path / "prose"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "pyproject.toml").write_text('[tool.mypy]\nfiles = ["."]\n')
    (root / "notes.md").write_text("# notes\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")

    proposal = an_annotation(target="notes.md")
    result = decompose(
        build_index(root), "annotate", propose=RecordedProposer((proposal,))
    )

    assert result.contracts == ()
    reason = result.refusals[0].reason
    assert "no language adapter owns 'notes.md'" in reason
    # The refusal names the languages this build actually carries.
    assert "python" in reason and "js/ts" in reason


def test_a_test_command_is_not_located_for_a_type_that_needs_one(repo: Index) -> None:
    """Only `type_check` is filled in — `tests_pass` still fails at the loader.

    `locate_test_command` answers `pytest` for any repository with a `tests/`
    directory, which is a guess about the runner rather than a reading of a
    declaration; and `failing_test_first` needs a *specific* test that fails
    before the change, which no locator can name. Both stay the proposer's.
    """
    (repo.root / "tests").mkdir()
    (repo.root / "tests" / "test_listing.py").write_text(
        "def test_x() -> None:\n    pass\n"
    )
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "add tests")
    result = decompose(
        build_index(repo.root), "fix", propose=RecordedProposer((a_fix(acceptance=()),))
    )

    assert result.contracts == ()
    assert "does not validate" in result.refusals[0].reason


def test_the_repository_level_refusal_is_reported_once_per_proposal(
    repo: Index,
) -> None:
    """Two annotation proposals, one repository fact — each is told the same thing.

    The check sits before dependency resolution so that "this repository runs no
    checker" cannot arrive disguised as a different complaint per proposal.
    """
    proposals = (an_annotation(), an_annotation(target="pagination.py"))
    result = decompose(repo, "annotate", propose=RecordedProposer(proposals))

    assert result.contracts == ()
    assert [r.subject for r in result.refusals] == ["listing.py", "pagination.py"]
    assert all("declares no type checker" in r.reason for r in result.refusals)
