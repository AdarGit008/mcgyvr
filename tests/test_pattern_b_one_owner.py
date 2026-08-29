"""Pattern B — the tree owns the bytes, and one seam commits them.

The 2026-08-29 pressure test's pattern B: *"Nothing owns the bytes. Five modules
write file content and disagree about where truth lives."* B6 closed half of it
— :func:`mcgyvr.deliver.deliver` now re-runs the gate over the bytes on disk,
inside the repository lock, immediately before staging, so a caller holding a
string cannot commit it under a verdict reached on something else.

**That fix protects one of the two delivery implementations.** The other is
``tools/missions/run.py``, which imports nothing from :mod:`mcgyvr.deliver`: it
reads ``Delivered.value`` — a ``str`` carried four hops from
:func:`mcgyvr.escalate.judge` — writes it into the worktree with ``_place`` and
commits it with ``_commit_delivery``. No re-gate, no digest, no lock. And it is
the implementation with the mileage on it: the mission runner is what drove the
contracts the pressure test recomputed digests over, while ``mcgyvr run``, the
only production caller of ``deliver``, was added the day before this file.

So ``Judgement.value`` is not a design decision anybody made. It is the coupling
between two deliveries, and the second one applies no bar. The rule these two
tests hold is therefore not "carry the bytes more carefully" but:

    The tree is the owner. Content never travels as a value, and one seam
    commits.

Both tests are RED on purpose. The first states the property the mission
runner's delivery path violates; the second is the guard that stops a third
delivery growing back once the second is gone.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.gate import ChangeSet, Gate
from mcgyvr.repair import repair

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


def test_the_mission_runner_cannot_commit_bytes_the_gate_rejected(
    tmp_path: Path, missions_run: object
) -> None:
    """B6's scenario, followed into the delivery ``deliver`` does not own.

    The port's documented repair loop, run as written. ``repair`` rewrites the
    worker's file in place and the second gate run accepts what is now on disk —
    so the caller's ``Delivered.value``, still the reply the worker sent, is
    bytes the gate rejected and no gate has read since.

    ``deliver`` refuses these; ``test_fix_b6_verdict_binding`` pins that. The
    mission runner never asks. It calls ``_files_of(contract, outcome.value)``,
    writes what comes back and commits it, so the rejected bytes land in a
    repository under a verdict reached on the repaired ones.

    Asserted against the committed tree rather than against a return value: what
    is wrong here is not what the runner reports, it is what is in the
    repository afterwards.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    worktree = make_repo(tmp_path / "worktree", {target: original})
    contract = contract_for(target)
    base = git(worktree, "rev-parse", "HEAD").strip()

    # The worker's reply, which the caller keeps holding.
    (worktree / target).write_text(UNFORMATTED)
    rejected = Gate().run(ChangeSet.detect(worktree, base), contract.scope)
    assert not rejected.accepted, (
        f"the premise did not hold: the gate accepted unformatted content "
        f"(is ruff installed? {rejected.environment_issues})"
    )

    # Repair rewrites the tree; the second verdict is about the repaired bytes.
    outcome = repair(repo=worktree, contract=contract, base=base)
    assert outcome.changed, "the premise did not hold: nothing was repaired"
    accepted = Gate().run(ChangeSet.detect(worktree, base), contract.scope)
    assert accepted.accepted, (
        "the premise did not hold: repair did not satisfy the gate"
    )
    repaired = (worktree / target).read_text()
    assert repaired != UNFORMATTED

    # What the mission runner does with the value the caller is still holding.
    delivered = missions_run._files_of(contract, UNFORMATTED)  # type: ignore[attr-defined]
    for path, content in delivered.items():
        missions_run._place(worktree, path, content)  # type: ignore[attr-defined]
    missions_run._commit_delivery(worktree, contract, delivered)  # type: ignore[attr-defined]

    committed = git(worktree, "show", f"HEAD:{target}")
    assert committed != UNFORMATTED, (
        "the mission runner committed the bytes the gate rejected: it writes "
        "`Delivered.value` and commits without re-gating, so B6's fix — which "
        "lives in `deliver` — does not apply to the delivery that has actually "
        "been used."
    )
    assert committed == repaired, (
        "the committed bytes are not the ones the accepting verdict was reached "
        "on; the tree is the owner, so what is committed is what is on it."
    )


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
