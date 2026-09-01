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
from collections.abc import Sequence
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


def test_a_passing_judgement_carries_no_binding_unless_one_was_minted(
    missions_run: object,
) -> None:
    """The default is the refusing direction.

    The runner's delivery branches on ``outcome.judgement.accepted`` and records
    a refusal at stage ``deliver`` when it is ``None`` — the case of a
    caller-supplied ``attempt_for`` that never minted one, which is the old
    defect's exact shape: a passing verdict, and a caller holding bytes nothing
    re-read. That branch is only reachable if a judgement built without a binding
    actually has none, so that is what is pinned here rather than the branch,
    which a full mission run would have to spend a pool to reach.
    """
    assert Judgement(verdict=Verdict.PASSED).accepted is None, (
        "a judgement built without a binding has one, so the runner's `None` "
        "branch can never fire and an unbound climb would be delivered"
    )
    assert missions_run.STAGE_DELIVER == "deliver"  # type: ignore[attr-defined]


def test_delivery_runs_none_of_the_repositorys_hooks(tmp_path: Path) -> None:
    """All four, not the two ``--no-verify`` covers.

    Delivery commits into whatever tree the run was pointed at, and a mission
    points it at a detached worktree of someone else's clone. A hook there runs
    with the runner's environment, on the runner's machine, while mcgyvr holds
    the repository lock.

    This test exists because the first fix used ``--no-verify`` and the commit
    message claimed the hooks were closed. ``--no-verify`` suppresses
    ``pre-commit`` and ``commit-msg`` only: ``prepare-commit-msg`` still ran,
    before the object was written and holding the message file, and
    ``post-commit`` still ran after. Both were reproduced firing under a real
    delivery. So the assertion is over all four by name, and each hook records
    itself rather than being inferred from a side effect.

    The control matters as much as the claim: a plain ``git commit`` in the same
    repository must fire them, or the test would pass against hooks that were
    never live.
    """
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})
    ran = tmp_path / "ran.txt"
    hooks = ("pre-commit", "commit-msg", "prepare-commit-msg", "post-commit")
    for hook in hooks:
        script = repo / ".git" / "hooks" / hook
        script.write_text(f'#!/bin/sh\necho {hook} >> "{ran}"\nexit 0\n')
        script.chmod(0o755)

    # The control: these hooks are live in this repository.
    (repo / "unrelated.txt").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "control")
    fired = ran.read_text().split() if ran.is_file() else []
    assert sorted(fired) == sorted(hooks), (
        f"the premise did not hold: a plain commit fired {fired}, not every hook, "
        f"so this test could pass against hooks that never ran"
    )
    ran.unlink()

    contract = contract_for(target)
    base = git(repo, "rev-parse", "HEAD").strip()
    workspace = make_repo(
        tmp_path / "workspace", {target: "def fetch(url):\n    return url\n"}
    )
    (workspace / target).write_text("def fetch(url):\n    return url.strip()\n")
    result = Gate().run(
        ChangeSet.detect(workspace, git(workspace, "rev-parse", "HEAD").strip()),
        contract.scope,
    )
    assert result.accepted, f"the premise did not hold: {result.findings}"
    bound = Accepted.read(repo=workspace, contract=contract, result=result)

    delivery = deliver(repo=repo, contract=contract, content=bound, base=base)

    assert delivery.committed, f"the delivery did not commit: {delivery.reason}"
    assert not ran.is_file(), (
        f"delivery ran the repository's hooks: {ran.read_text().split()}. "
        f"`--no-verify` covers `pre-commit` and `commit-msg` only; disabling all "
        f"four is `core.hooksPath` pointed at a path that does not exist."
    )


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
    "src/mcgyvr/deliver.py": "the single delivery",
    # Commits only into a workspace it has just `git init`-ed, to give the
    # sandbox a base to diff against. Nothing it commits is anybody's tree.
    "src/mcgyvr/sandbox/base.py": "the sandbox's own base commit",
}

#: Directories whose ``.py`` files are corpus rather than product — benchmark
#: tasks, problem fixtures, word counters. ``commit`` appears in them as English
#: and as a transaction verb (there is a task named ``p178-commit-index``), and
#: nothing in them runs git. Excluded by path so the detector below can be blunt.
NOT_PRODUCT_CODE = (
    "tools/bundle/",
    "tools/problems/tasks/",
    "tools/reach/",
)

#: What marks a run of arguments as a git command line rather than a word list.
#: Any dash-led token — ``-m`` and ``-q`` count, and their absence is what the
#: first version of this guard got wrong — or the program name itself.
_GIT_MARKERS = ("git",)


def _is_git_commit(argv: Sequence[str]) -> bool:
    """Whether a run of string arguments is a ``git commit`` invocation.

    ``"commit"`` beside either a dash-led token or the word ``git``.

    The first version asked for a ``--flag`` and missed ``git commit -m msg``,
    which is the most common spelling of this command in existence — an
    adversarial pass planted nine committing modules and the guard reported one.
    Single dashes count now, and so does ``"git"`` on its own, which is what
    catches a commit whose flags were splatted from a variable or concatenated
    from a second list: the verb and the program name are the two tokens a git
    invocation cannot avoid writing down.

    What still escapes, stated so the next reader does not assume otherwise: a
    verb held in a variable (``_git(repo, VERB, ...)``) has no literal to match.
    Const-propagation is where that ends, and this guard deliberately stops
    short of it — :func:`_is_shell_git_commit` covers the shapes that are
    reachable by accident, and a name chosen to evade a test in this file is not
    a defect this test can be asked to catch.
    """
    if "commit" not in argv:
        return False
    return any(
        arg.startswith("-") or arg in _GIT_MARKERS for arg in argv if arg != "commit"
    )


def _is_shell_git_commit(text: str) -> bool:
    """Whether one string is a shell command line that commits.

    ``subprocess.run(..., shell=True)`` and :func:`os.system` take the whole
    command as one string, so there is no argument list to walk and the check
    above cannot see them. Both are how a second delivery would most plausibly
    be written by someone reaching for the shortest thing that works.
    """
    words = text.split()
    if "git" not in words:
        return False
    # The subcommand, not merely the word somewhere in the string. Prose in this
    # repository says "is not a git repository" one clause away from "for commit
    # {sha}", and a membership test called both of those a commit invocation.
    # After the program name, dash-led tokens are options and what follows is the
    # verb — checked over the first two non-dash tokens because a `-C <path>`
    # puts the path there, and an interpolated path is not in the literal at all.
    after = words[words.index("git") + 1 :]
    return "commit" in [word for word in after if not word.startswith("-")][:2]


def _string_constants(node: ast.expr) -> list[str]:
    """Every string literal directly inside one expression, f-strings included.

    An f-string is an :class:`ast.JoinedStr` rather than a
    :class:`ast.Constant`, so a command line built by interpolation — the usual
    way a repository path reaches a git call — is invisible to a check that
    looks only for constants. Its literal pieces are constants, and they are
    what carry the verb.
    """
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.JoinedStr):
        pieces = [
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ]
        # The pieces *and* their join. An interpolated command line splits the
        # verb from the program name — `f"git -C {root} commit ..."` is two
        # constants, neither of which holds both words — so a shell check run
        # per piece sees nothing. The join puts the line back together, with the
        # interpolations standing in as whitespace, which is what a shell would
        # have received anyway.
        return [*pieces, " ".join(pieces)]
    return []


def commit_sites(repo: Path) -> list[str]:
    """Every module under ``repo`` that runs ``git commit``, with where.

    Reported as a path relative to ``repo``, and allowlisted the same way. The
    first version keyed on the *basename*, so a second ``base.py`` anywhere in
    the tree inherited the sandbox's exemption without anybody arguing for it —
    and ``base.py`` is one of the most common module names there is.

    Three argument shapes, because the repository uses two and a third is the
    obvious way to write a fourth: a sequence literal's elements, a call's
    positional arguments, and a single string handed to a shell.
    """
    found: list[str] = []
    for where in ("src", "tools"):
        for path in sorted((repo / where).rglob("*.py")):
            rel = path.relative_to(repo).as_posix()
            if rel in MAY_COMMIT or rel.startswith(NOT_PRODUCT_CODE):
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
                    text for element in elements for text in _string_constants(element)
                ]
                if _is_git_commit(argv) or any(map(_is_shell_git_commit, argv)):
                    found.append(f"{rel}:{node.lineno}")
    return sorted(set(found))


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
    offenders = commit_sites(here)
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
