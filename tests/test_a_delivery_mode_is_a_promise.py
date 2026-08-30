"""§4, fifth item — three delivery modes, one behaviour, and a default that lies.

``config.delivery.mode`` is the key an operator sets to say where accepted work
ends up. It ships three values and documents three outcomes: ``pull_request``
"proposes it", ``branch`` "stops after pushing", ``none`` "leaves it committed
locally". Measured on 2026-08-30, against the module as written:

    schema default for delivery.mode: 'pull_request'

    mode=None           HEAD moved: True   refs after: [refs/heads/master]
    mode='pull_request' HEAD moved: True   refs after: [refs/heads/master]
    mode='branch'       HEAD moved: True   refs after: [refs/heads/master]
    mode='none'         HEAD moved: True   refs after: [refs/heads/master]

Four runs, one commit SHA, one ref, and the operator's checked-out branch moved
every time. Nothing pushes and nothing branches, so ``branch`` and
``pull_request`` are two spellings of ``none`` — and ``pull_request``, the one
that ships by default and reads as *the least invasive of the three*, is the
most invasive thing the module does. The only trace of the difference is
``Delivery.handoff``, which comes back as the literal string ``'branch'`` or
``'pull_request'``: an obligation naming no action, recorded for a discharger
that does not exist anywhere in ``src/``.

The rule every test below measures against:

    A delivery mode is a promise about where the work ends up. Either the mode
    keeps it — observably, in the repository — or the mode is refused at the
    place it is set, naming one that can be kept. A mode that quietly does
    something else is worse than a mode that is not offered.

So there are two honoured modes and one refused one. ``none`` commits onto the
branch the operator has checked out, which is what it always did. ``branch``
commits onto a *new local branch* and leaves HEAD, the index and the working
tree exactly as it found them — the honest form of "hand it back rather than
land it" in a codebase with no remote and no credential path — and its
``handoff`` is the push command an operator can paste. ``pull_request`` is
refused where it is written, because opening one needs a forge nothing here
talks to.

The controls carry as much weight as the reproductions. "Refuse everything" and
"never commit anywhere" would both satisfy the first half of the rule and leave
mcgyvr unable to deliver at all, so ``none`` still has to land a commit on the
checked-out branch, the config still has to accept both honoured modes, and the
shipped default still has to be a value that delivers.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import Config, ConfigSchemaError, parse
from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import Delivery, DeliveryError, deliver

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

LADDER = """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
ladder:
  tiers:
    - name: cheap
      source: local
      model: qwen2.5-coder:7b
"""

BEFORE = "def fetch(url):\n    return url\n"
AFTER = 'def fetch(url):\n    """Retry."""\n    return url\n'

#: The modes this build can carry out, written as a literal rather than imported
#: from :mod:`mcgyvr.deliver`. A test that asks the module for its own honoured
#: set agrees with any answer the module gives, including one that put
#: ``pull_request`` back.
HONOURED = ("branch", "none")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def heads(repo: Path) -> set[str]:
    """Every local branch, by short name."""
    listed = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return set(listed.split())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    where = tmp_path / "repo"
    (where / "src/pkg").mkdir(parents=True)
    (where / "src/pkg/fetch.py").write_text(BEFORE, encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "work", str(where))
    git(where, "config", "user.email", "test@example.invalid")
    git(where, "config", "user.name", "test")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


@pytest.fixture
def contract() -> Contract:
    return loads(CONTRACT)


def config_for(mode: str | None) -> Config:
    """A valid config, with ``delivery.mode`` set when one is named."""
    body = LADDER if mode is None else f"{LADDER}delivery:\n  mode: {mode}\n"
    return parse(body)


def forced(mode: str) -> Config:
    """A :class:`~mcgyvr.config.Config` carrying a mode the loader would refuse.

    Not a stand-in: a real ``Config`` with one key replaced, which is the value a
    caller that assembled its own config rather than parsing a file can hold.
    The loader's refusal is the front door; this is what is behind it.
    """
    loaded = config_for(None)
    data = dict(loaded.data)
    data["delivery"] = {**data["delivery"], "mode": mode}
    return dataclasses.replace(loaded, data=data)


def delivered(repo: Path, contract: Contract, config: Config | None) -> Delivery:
    return deliver(
        repo=repo,
        contract=contract,
        content=AFTER,
        base=git(repo, "rev-parse", "HEAD").strip(),
        config=config,
    )


# --- `branch` means a branch --------------------------------------------------


def test_branch_mode_does_not_move_the_branch_the_operator_has_checked_out(
    repo: Path, contract: Contract
) -> None:
    """The reproduction. ``branch`` advanced ``work`` like every other mode."""
    head = git(repo, "rev-parse", "HEAD").strip()

    result = delivered(repo, contract, config_for("branch"))

    assert result.committed, f"nothing was delivered at all: {result}"
    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        f"`branch` moved the branch the operator has checked out: work was at "
        f"{head[:12]} and is now at {git(repo, 'rev-parse', 'HEAD').strip()[:12]}"
    )
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "work", (
        "`branch` changed which branch is checked out; it may create one, not "
        "switch to it"
    )


def test_branch_mode_puts_the_commit_on_a_branch_of_its_own(
    repo: Path, contract: Contract
) -> None:
    """A ref that did not exist before holds the commit, and it is not ``work``."""
    before = heads(repo)

    result = delivered(repo, contract, config_for("branch"))

    made = heads(repo) - before
    assert made, (
        f"`branch` created no branch: {sorted(heads(repo))} before and after. "
        f"The commit went somewhere, and the only somewhere is `work`"
    )
    assert len(made) == 1, f"one delivery made more than one branch: {sorted(made)}"

    landed = made.pop()
    assert git(repo, "rev-parse", landed).strip() == result.commit, (
        f"{landed} exists but does not hold {result.commit[:12]}"
    )
    assert contract.id in landed, (
        f"{landed!r} does not name the contract that made it, so an operator "
        f"with two deliveries in flight cannot tell which is which"
    )


def test_branch_mode_leaves_the_working_tree_exactly_as_it_found_it(
    repo: Path, contract: Contract
) -> None:
    """The commit is durable in a ref, so the tree does not have to carry it.

    A mode that hands work back on a branch and *also* leaves the change sitting
    in the operator's checkout has handed it back twice, and the second copy is
    uncommitted edits they did not make.
    """
    target = repo / "src/pkg/fetch.py"

    result = delivered(repo, contract, config_for("branch"))

    assert result.committed, f"nothing was delivered at all: {result}"
    assert target.read_text(encoding="utf-8") == BEFORE, (
        "`branch` left its change in the working tree as well as on the branch"
    )
    assert not git(repo, "status", "--porcelain").strip(), (
        f"`branch` left the tree dirty:\n{git(repo, 'status', '--porcelain')}"
    )


def test_two_branch_deliveries_of_one_contract_do_not_land_on_one_ref(
    repo: Path, contract: Contract
) -> None:
    """A second delivery may not quietly move the first one's branch.

    The ref is derived from the contract id, so two runs of one contract collide
    by construction. Overwriting would throw away a commit an operator was told
    to push.
    """
    first = delivered(repo, contract, config_for("branch"))
    second = delivered(repo, contract, config_for("branch"))

    assert first.committed and second.committed, f"{first} / {second}"
    made = sorted(heads(repo) - {"work"})
    assert len(made) == 2, f"two deliveries left {len(made)} branch(es): {made}"
    for ref in made:
        assert git(repo, "rev-parse", ref).strip() in (first.commit, second.commit)


def test_the_handoff_names_the_step_an_operator_can_actually_take(
    repo: Path, contract: Contract
) -> None:
    """``handoff`` was the word ``'branch'`` — an obligation naming no action.

    Nothing in ``src/`` discharges a mode name. What a caller can act on is a
    branch it can look up and a command it can run.
    """
    result = delivered(repo, contract, config_for("branch"))

    assert "push" in result.handoff, (
        f"the handoff is {result.handoff!r}, which tells an operator nothing to "
        f"do with the commit that was just made for them"
    )
    assert result.branch, f"the delivery names no branch to hand off: {result}"
    assert git(repo, "rev-parse", "--verify", "--quiet", result.branch).strip(), (
        f"{result.branch!r} is named as the handoff and does not resolve"
    )
    assert result.branch in result.handoff, (
        f"the handoff {result.handoff!r} does not name {result.branch!r}"
    )
    assert result.branch in str(result), (
        f"the one line a caller prints does not say where the work went: {result}"
    )


def test_the_handoff_names_the_repository_s_own_remote(
    repo: Path, contract: Contract
) -> None:
    """A pasteable command, which means the remote as this repository names it."""
    git(repo, "remote", "add", "upstream", "https://example.invalid/x.git")

    result = delivered(repo, contract, config_for("branch"))

    assert "upstream" in result.handoff, (
        f"the handoff {result.handoff!r} does not name the repository's remote, "
        f"so it is advice rather than a command"
    )


# --- `none` means here, and is the control ------------------------------------


def test_none_mode_commits_onto_the_checked_out_branch(
    repo: Path, contract: Contract
) -> None:
    """The control: the fix did not stop delivery from delivering.

    ``none`` is the mode that says "leave it committed locally", and locally is
    the branch in hand. If this goes red the modes differ, and mcgyvr can no
    longer put a commit where it always put one.
    """
    head = git(repo, "rev-parse", "HEAD").strip()
    before = heads(repo)

    result = delivered(repo, contract, config_for("none"))

    assert result.committed, f"`none` delivered nothing: {result}"
    assert git(repo, "rev-parse", "HEAD").strip() == result.commit, (
        "`none` did not put the commit on the checked-out branch"
    )
    assert git(repo, "rev-parse", "HEAD~1").strip() == head
    assert heads(repo) == before, (
        f"`none` created a branch: {sorted(heads(repo) - before)}"
    )
    assert not result.handoff, (
        f"`none` owes nothing and claims {result.handoff!r} is still to do"
    )
    assert (repo / "src/pkg/fetch.py").read_text(encoding="utf-8") == AFTER


def test_the_two_honoured_modes_end_in_two_different_places(
    tmp_path: Path, contract: Contract
) -> None:
    """Both halves of the rule in one assertion, over two identical repositories.

    Same bytes, same base, same contract; only the mode differs. If the two ends
    are indistinguishable, the key is decoration.
    """
    ends: dict[str, tuple[str, frozenset[str]]] = {}
    for mode in HONOURED:
        where = tmp_path / mode
        (where / "src/pkg").mkdir(parents=True)
        (where / "src/pkg/fetch.py").write_text(BEFORE, encoding="utf-8")
        git(tmp_path, "init", "-q", "-b", "work", str(where))
        git(where, "config", "user.email", "test@example.invalid")
        git(where, "config", "user.name", "test")
        git(where, "add", "-A")
        git(where, "commit", "-qm", "base")

        result = delivered(where, contract, config_for(mode))
        assert result.committed, f"{mode} delivered nothing: {result}"
        ends[mode] = (
            git(where, "rev-parse", "HEAD").strip(),
            frozenset(heads(where)),
        )

    assert ends["branch"] != ends["none"], (
        f"`branch` and `none` left the repository in the same state "
        f"({ends['none']}), so one of the two names is not true"
    )


# --- `pull_request` is refused where it is set --------------------------------


def test_pull_request_is_refused_where_the_operator_writes_it() -> None:
    """The config file is where the promise is made, so it is where it is broken."""
    with pytest.raises(ConfigSchemaError) as raised:
        config_for("pull_request")

    assert "delivery.mode" in str(raised.value), (
        f"the refusal does not name the key to edit: {raised.value}"
    )


def test_the_refusal_names_a_mode_that_can_be_kept() -> None:
    """A refusal an operator cannot act on is a wall, not an answer."""
    with pytest.raises(ConfigSchemaError) as raised:
        config_for("pull_request")

    message = str(raised.value)
    for mode in HONOURED:
        assert f"`{mode}`" in message, (
            f"the refusal does not offer `{mode}` as what to set instead: {message}"
        )


def test_delivery_refuses_the_mode_rather_than_committing_under_it(
    repo: Path, contract: Contract
) -> None:
    """Behind the loader's front door, for a config that did not come through it.

    This is the assertion the reproduction failed: ``pull_request`` committed to
    the checked-out branch and reported the pull request as owed.
    """
    head = git(repo, "rev-parse", "HEAD").strip()

    with pytest.raises(DeliveryError) as raised:
        delivered(repo, contract, forced("pull_request"))

    assert "branch" in str(raised.value), (
        f"the refusal does not name a mode delivery can carry out: {raised.value}"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        "delivery refused the mode and committed under it anyway"
    )
    assert (repo / "src/pkg/fetch.py").read_text(encoding="utf-8") == BEFORE, (
        "a refused mode still wrote the worker's change into the tree"
    )


def test_a_mode_delivery_has_never_heard_of_is_refused_too(
    repo: Path, contract: Contract
) -> None:
    """The default for an unrecognised mode is a refusal, not a local commit.

    Falling back to a commit is how ``pull_request`` came to mean ``none`` in the
    first place.
    """
    with pytest.raises(DeliveryError):
        delivered(repo, contract, forced("gerrit"))


# --- the controls the refusal must not break ----------------------------------


def test_both_honoured_modes_are_still_accepted_by_the_config() -> None:
    """The control for the refusal: it refuses one value, not the key."""
    for mode in HONOURED:
        assert config_for(mode).data["delivery"]["mode"] == mode


def test_the_shipped_default_is_a_mode_the_code_can_carry_out(
    repo: Path, contract: Contract
) -> None:
    """A config that says nothing about delivery still delivers, and honestly.

    Both halves matter. The default has to be in the honoured set — it was
    ``pull_request``, which is now refused, so a config with no ``delivery``
    block would fail to deliver at all — and it has to actually commit, so that
    "make the default honourable" is not satisfied by a default that refuses.
    """
    default = config_for(None).data["delivery"]["mode"]
    assert default in HONOURED, (
        f"the shipped default is {default!r}, which this build cannot carry out"
    )

    result = delivered(repo, contract, config_for(None))

    assert result.committed, f"the shipped default delivers nothing: {result}"
    assert result.mode == default
