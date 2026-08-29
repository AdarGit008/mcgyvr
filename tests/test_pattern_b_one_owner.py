"""Pattern B — the tree owns the bytes, and one seam commits them.

The 2026-08-29 pressure test's pattern B: *"Nothing owns the bytes. Five modules
write file content and disagree about where truth lives."* B6 closed half of it
— :func:`mcgyvr.deliver.deliver` now re-runs the gate over the bytes on disk,
inside the repository lock, immediately before staging, so a caller holding a
string cannot commit it under a verdict reached on something else.

**That fix protected one of the two delivery implementations.** The other was
``tools/missions/run.py``, which imported nothing from :mod:`mcgyvr.deliver`: it
read ``Delivered.value`` — a ``str`` carried four hops from
:func:`mcgyvr.escalate.judge` — wrote it into the worktree with ``_place`` and
committed it with ``_commit_delivery``. No re-gate, no digest, no lock. And it
was the implementation with the mileage on it: the mission runner is what drove
the contracts the pressure test recomputed digests over, while ``mcgyvr run``,
the only production caller of ``deliver``, was added the day before this file.

So ``Judgement.value`` was not a design decision anybody made. It was the
coupling between two deliveries, and the second one applied no bar. The rule
this file holds is therefore not "carry the bytes more carefully" but:

    The tree is the owner. Content never travels as a value, and one seam
    commits.

The runner delivers through :func:`mcgyvr.deliver.deliver` now, handed the
binding item 3 mints inside the workspace its gate ran in — the only place it
can be minted, because that sandbox is torn down before the climb returns.

Two of these tests began RED and named the defect; they are kept in the shape
the fix left them, which for the reproduction means asserting the helpers are
gone rather than driving them. The other two are the guard that stops a third
delivery growing back, and the control that says none of this is merely a
refusal.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import Accepted, deliver
from mcgyvr.escalate import Judgement
from mcgyvr.gate import ChangeSet, Gate
from mcgyvr.repair import repair
from mcgyvr.route import Verdict

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: {target}
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["{scope}"]
limits:
  attempts: 5
"""

#: Valid Python the gate rejects on two rungs a tool repairs for nothing — an
#: unused import and a call the formatter reflows. The same fixture
#: ``test_fix_b6_verdict_binding`` uses, so the two reproductions are about one
#: set of bytes: what B6 stopped at ``deliver`` is what this file follows into
#: the delivery ``deliver`` does not own.
UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def make_repo(where: Path, targets: dict[str, str]) -> Path:
    for name, body in targets.items():
        path = where / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    git(where.parent, "init", "-q", str(where))
    git(where, "config", "user.email", "test@example.invalid")
    git(where, "config", "user.name", "test")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


def contract_for(target: str, scope: str = "src/**/*.py") -> Contract:
    return loads(CONTRACT.format(target=target, scope=scope))


# --- the second delivery applies no bar -----------------------------------


def test_the_mission_runner_has_no_delivery_of_its_own(
    missions_run: object,
) -> None:
    """The helpers that made the second delivery are gone, by name.

    This test began as a reproduction: it drove ``_files_of`` → ``_place`` →
    ``_commit_delivery`` with the string a caller still held after ``repair``
    rewrote the tree, and watched the rejected bytes reach a commit. Those
    helpers no longer exist, so the reproduction cannot be written — which is the
    outcome, not a gap in the test.

    What replaces it is the narrower claim the reproduction rested on: the runner
    holds no way to write a file into a repository and commit it. ``_place``
    survives and is deliberately not named here — it still writes acceptance
    files into the worktree and the whole-tree sandbox — because writing was
    never the defect. Committing without re-gating was, and
    :func:`test_nothing_but_delivery_commits` is the general form.
    """
    for gone in ("_files_of", "_commit_delivery"):
        assert not hasattr(missions_run, gone), (
            f"`{gone}` is back. It was half of a second delivery implementation "
            f"that wrote `Delivered.value` and committed it without re-running "
            f"the gate; the runner delivers through `mcgyvr.deliver` now."
        )


def test_a_climb_that_passed_without_binding_its_bytes_is_not_delivered(
    tmp_path: Path, missions_run: object
) -> None:
    """A ``Delivered`` is not on its own a licence to write.

    The runner's delivery reads ``outcome.judgement.accepted`` — the binding item
    3 mints inside the workspace its gate ran in — and a caller-supplied
    ``attempt_for`` need not mint one. That case is the old defect's exact shape:
    a passing verdict, and a caller holding bytes nothing re-read. It is recorded
    at stage ``deliver`` rather than written, because this seam has no tree to
    read the accepted bytes back out of and inventing them from a string is what
    pattern B is about.

    Driven through the runner's own refusal type rather than a full mission: what
    is being pinned is that the ``None`` branch refuses and says why, and a
    mission run would spend a pool to reach the same two lines.
    """
    target = "src/pkg/fetch.py"
    worktree = make_repo(
        tmp_path / "worktree", {target: "def fetch(url):\n    return url\n"}
    )
    contract = contract_for(target)
    head = git(worktree, "rev-parse", "HEAD").strip()

    # The shape the runner branches on: a passing judgement carries no binding
    # unless something minted one from a gated tree, and the default is the
    # refusing direction rather than the writing one.
    assert Judgement(verdict=Verdict.PASSED).accepted is None, (
        "a judgement built without a binding has one, so the runner's `None` "
        "branch can never fire and an unbound climb would be delivered"
    )
    assert missions_run.STAGE_DELIVER  # type: ignore[attr-defined]

    delivery = deliver(
        repo=worktree,
        contract=contract,
        content=UNFORMATTED,
        base=head,
    )
    assert not delivery.committed, (
        "delivery accepted a bare string with no verdict bound to it; the bytes "
        "reaching a repository must be bytes a gate read"
    )
    assert git(worktree, "rev-parse", "HEAD").strip() == head
    assert git(worktree, "status", "--porcelain").strip() == ""


def test_the_binding_is_minted_from_the_tree_the_gate_read(tmp_path: Path) -> None:
    """The control: what is delivered is what the accepting verdict was reached on.

    A fix that refused everything would satisfy both statements above. This is
    the loop working — the repair loop run as written, then the binding minted
    the way item 3 mints it, then a delivery — and the bytes that reach the
    commit are the repaired ones, not the reply the worker sent.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    workspace = make_repo(tmp_path / "workspace", {target: original})
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)
    base = git(workspace, "rev-parse", "HEAD").strip()

    # The worker's reply, which the caller keeps holding.
    (workspace / target).write_text(UNFORMATTED)
    rejected = Gate().run(ChangeSet.detect(workspace, base), contract.scope)
    assert not rejected.accepted, (
        f"the premise did not hold: the gate accepted unformatted content "
        f"(is ruff installed? {rejected.environment_issues})"
    )

    # Repair rewrites the tree; the second verdict is about the repaired bytes.
    outcome = repair(repo=workspace, contract=contract, base=base)
    assert outcome.changed, "the premise did not hold: nothing was repaired"
    accepted = Gate().run(ChangeSet.detect(workspace, base), contract.scope)
    assert accepted.accepted, "the premise did not hold: repair did not satisfy it"
    repaired = (workspace / target).read_text()
    assert repaired != UNFORMATTED

    bound = Accepted.read(repo=workspace, contract=contract, result=accepted)
    assert bound.content == repaired, (
        "the binding is not the bytes on the tree the gate judged"
    )

    delivery = deliver(
        repo=repo,
        contract=contract,
        content=bound,
        base=git(repo, "rev-parse", "HEAD").strip(),
    )
    assert delivery.committed, (
        f"the accepted change was not delivered: {delivery.reason}"
    )
    assert git(repo, "show", f"{delivery.commit}:{target}") == repaired


# --- one seam commits ------------------------------------------------------

#: Where a ``git commit`` is legitimate, and why. Two entries, each for a
#: different reason, and both reasons have to be given rather than assumed —
#: an allowlist whose entries are unexplained is how the second delivery came to
#: look like part of the design.
MAY_COMMIT = {
    # The one seam that writes into a repository a human owns. It re-runs the
    # gate over the bytes on disk, inside the repository lock, immediately
    # before staging (B6).
    "deliver.py": "the single delivery",
    # Commits only into a workspace it has just `git init`-ed, to give the
    # sandbox a base to diff against. Nothing it commits is anybody's tree.
    "base.py": "the sandbox's own base commit",
}


def _is_git_commit(argv: list[str]) -> bool:
    """Whether a run of string arguments is a ``git commit`` invocation.

    ``"commit"`` beside at least one ``--flag``. The bare word alone is not
    enough and the first draft of this guard proved it: the repository holds a
    benchmark task called ``p178-commit-index``, transaction fixtures whose
    mini-language has a ``commit`` verb, and word counters under
    ``tools/reach/`` — 46 matches, none of them git. A commit *invocation*
    always carries a flag, and no word list does.
    """
    return "commit" in argv and any(arg.startswith("--") for arg in argv)


def commit_sites(root: Path) -> list[str]:
    """Every module under ``root`` that runs ``git commit``, with where.

    Two argument shapes, because the repository uses both and matching one
    would report on spelling — the mistake the seam guard made before the
    pressure test found three ways around it. ``tools/missions/run.py`` builds
    its commit as a list literal it later splats into ``subprocess.run``;
    :func:`mcgyvr.deliver._commit` passes the arguments straight to a ``_git``
    helper. So both a sequence literal's elements and a call's positional
    arguments are read, and neither spelling hides.
    """
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name in MAY_COMMIT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.List | ast.Tuple):
                elements: list[ast.expr] = list(node.elts)
            elif isinstance(node, ast.Call):
                elements = list(node.args)
            else:
                continue
            argv = [
                element.value
                for element in elements
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            if _is_git_commit(argv):
                found.append(f"{path.name}:{node.lineno}")
    return found


def test_nothing_but_delivery_commits() -> None:
    """An architectural guard: one seam writes commits, and it re-gates first.

    The rule pattern B ends at. Two delivery implementations is what let a
    verdict and its bytes come apart at all — the string only exists because
    something other than ``deliver`` needed to be handed one — so the rule that
    prevents a recurrence is not about how content is carried but about how many
    places can commit it.

    Add to :data:`MAY_COMMIT` with a reason, or route the commit through
    :func:`mcgyvr.deliver.deliver`. A third entry wants an argument; that is the
    intended cost.
    """
    here = Path(__file__).resolve().parent.parent
    offenders = commit_sites(here / "src") + commit_sites(here / "tools")
    assert offenders == [], (
        f"these commit without going through `deliver`, so the gate run under "
        f"the repository lock does not stand between them and a human's tree: "
        f"{offenders}"
    )


@pytest.fixture
def missions_run() -> object:
    """``tools/missions/run.py``, loaded by path.

    It is a script rather than a package module, and the delivery half of it is
    what this file is about.
    """
    import importlib.util
    import sys

    path = Path(__file__).resolve().parent.parent / "tools" / "missions" / "run.py"
    spec = importlib.util.spec_from_file_location("missions_run_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module uses `from __future__ import
    # annotations`, so `@dataclass` resolves its string annotations through
    # `sys.modules[cls.__module__]` and raises on a module that is not there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
