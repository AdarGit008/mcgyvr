"""B6, round two — the bytes that reach the repository are bytes a gate read.

The first fix for B6 added a digest and a check that the digest still answers
for the content it travels with. The check could not fire: the only constructor
minted the digest *from the content it was handed*, so every value the system
could build was intact by construction, and the test that guarded it hand-built
a value no production path produces. Green, and holding nothing — the pressure
test's own pattern D, reproduced inside the fix for it.

So this file states the property the way an attacker would have to defeat it,
and every reproduction here is driven through the real gate and the real repair
loop rather than through a hand-assembled value:

* A caller that still holds the worker's reply after a repair rewrote the tree
  must not be able to commit it. That is the port's documented loop, run as
  written.
* A caller that mints the binding *itself*, at delivery time, out of the bytes
  it holds and a verdict reached on other bytes, must not be able to commit them
  either — and the forgery asserted here is the strongest one available: an
  ``Accepted`` that is entirely self-consistent. If a self-consistent forgery
  still commits, the mechanism is a naming convention, not a check.
* ``pending.resume`` — the only production caller of ``deliver`` — must not be
  able to finish work no gate ever accepted.

Delivery is the last seam before a human's repository, and it is the only one
that can establish, non-negotiably, that what it is about to write passes the
checks it can run. A verdict a caller asserts is a claim; a verdict delivery
reaches over the bytes on disk is a fact.

B7's second half and N7 are here too, because both are the same shape: a value
that means "there is no answer" being softened into an answer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.consensus import ConsensusError, best_of
from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import DeliveryError, deliver
from mcgyvr.gate import ChangeSet, Gate, GateResult
from mcgyvr.pending import resume, stash
from mcgyvr.repair import repair
from mcgyvr.sandbox import SandboxError, open_sandbox

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
#: unused import and a call the formatter reflows. The same fixture the B3/B7
#: file uses, so the two reproductions are about one set of bytes.
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


def gate_repair_gate(repo: Path, contract: Contract, base: str) -> GateResult:
    """The port's own documented loop, run as written: gate, repair, gate again.

    Returns the second verdict. The bytes it was reached on are on disk in
    ``repo`` — which is the whole of B6: they are *not* the bytes the caller
    that dispatched the worker is still holding.
    """
    first = Gate().run(ChangeSet.detect(repo, base), contract.scope)
    assert not first.accepted, (
        f"the premise did not hold: the gate accepted unformatted content "
        f"(is ruff installed? {first.environment_issues})"
    )
    outcome = repair(repo=repo, contract=contract, base=base)
    assert outcome.changed, "the premise did not hold: nothing was repaired"
    second = Gate().run(ChangeSet.detect(repo, base), contract.scope)
    assert second.accepted, "the premise did not hold: repair did not satisfy the gate"
    assert outcome.content[contract.target] != UNFORMATTED
    return second


# --- B6: no un-gated bytes reach the repository --------------------------


def test_a_caller_still_holding_the_workers_reply_cannot_commit_it(
    tmp_path: Path,
) -> None:
    """The measured defect, with no forgery in it at all.

    The worker replied with ``UNFORMATTED``; the gate rejected it; ``repair``
    rewrote the tree; the re-run gate accepted what repair left. The caller is
    still holding the reply — which is the ordinary state of a caller in this
    port, because ``repair`` mutates a tree and returns its outcome while the
    reply lives in a local variable. Delivering it must not put the rejected
    bytes in the repository.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    workspace = make_repo(tmp_path / "workspace", {target: original})
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)

    (workspace / target).write_text(UNFORMATTED)  # what the worker replied
    gate_repair_gate(workspace, contract, git(workspace, "rev-parse", "HEAD").strip())

    head = git(repo, "rev-parse", "HEAD").strip()
    result = deliver(repo=repo, contract=contract, content=UNFORMATTED, base=head)

    assert not result.committed, (
        "delivery committed the bytes the gate rejected, on nothing but the "
        "caller's word that they were accepted"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert (repo / target).read_text() == original, "the tree was not put back"
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_self_consistent_forged_acceptance_is_still_refused(tmp_path: Path) -> None:
    """The acceptance bar: minting the binding at delivery time buys nothing.

    This is the strongest forgery the module's own types allow — an ``Accepted``
    whose digest genuinely answers for its content, carrying ``accepted=True``,
    built from the bytes the gate rejected and the verdict it reached on the
    repaired ones. Every consistency check inside the value passes. The only
    thing that can refuse it is delivery establishing the verdict itself over
    the bytes it is about to write.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    workspace = make_repo(tmp_path / "workspace", {target: original})
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)

    (workspace / target).write_text(UNFORMATTED)
    verdict = gate_repair_gate(
        workspace, contract, git(workspace, "rev-parse", "HEAD").strip()
    )

    head = git(repo, "rev-parse", "HEAD").strip()
    result = deliver(
        repo=repo,
        contract=contract,
        content=_forge(UNFORMATTED, verdict),
        base=head,
    )

    assert not result.committed, (
        "a caller minted the binding itself, at delivery time, out of bytes it "
        "held and a verdict about other bytes — and it committed"
    )
    assert result.findings, (
        "the refusal carries no findings, so delivery did not judge the bytes "
        "it was about to write; it only re-read the caller's assertion"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert git(repo, "status", "--porcelain").strip() == ""


def _forge(content: str, verdict: GateResult) -> Any:
    """The best binding a laundering caller can build, whatever the shape is.

    Written reflectively so it keeps testing *forgery* rather than testing one
    constructor: whichever way ``Accepted`` is minted today, a caller holding a
    string and a verdict can reach the dataclass fields directly, and that is
    the thing this file has to remain able to build.
    """
    from mcgyvr import deliver as module

    return module.Accepted(
        content=content,
        accepted=verdict.accepted,
        digest=module.digest_of(content),
    )


def test_delivery_does_not_take_a_callers_word_for_an_acceptance(
    tmp_path: Path,
) -> None:
    """``accepted=True`` is a claim, and delivery is where claims stop.

    A caller that gated somewhere else can hand the binding its gate minted. A
    caller that only says "this passed" is asserting the one thing delivery
    exists to not take on trust.
    """
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})
    head = git(repo, "rev-parse", "HEAD").strip()

    with pytest.raises(DeliveryError, match="verdict"):
        deliver(
            repo=repo,
            contract=contract_for(target),
            content=UNFORMATTED,
            base=head,
            accepted=True,
        )

    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_resume_does_not_finish_work_no_gate_accepted(tmp_path: Path) -> None:
    """``pending.resume`` is the only production caller of ``deliver``.

    It stashes what the caller was holding, and a recovery run hands those bytes
    straight to delivery. Measured: the stash held the bytes the gate rejected,
    a stub verifier approved, and the rejected bytes were committed — after
    which the gate rejects what is in the repository.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)
    store = tmp_path / "pending"

    stash(store=store, repo=repo, contract=contract, content=UNFORMATTED)
    head = git(repo, "rev-parse", "HEAD").strip()

    recovered = resume(
        store=store,
        repo=repo,
        task=contract.id,
        verify=lambda _text: True,
        base=head,
    )

    assert not recovered.completed, (
        f"a resume committed bytes no gate accepted: {recovered}"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert (repo / target).read_text() == original
    assert git(repo, "status", "--porcelain").strip() == ""


def test_the_repaired_bytes_are_the_ones_that_reach_the_repository(
    tmp_path: Path,
) -> None:
    """The control, and the reason none of the above is merely a refusal.

    A fix that refused everything would pass every statement above. What the
    loop is *for* is that the bytes repair left — the ones the second gate run
    accepted — are the bytes that get committed.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    workspace = make_repo(tmp_path / "workspace", {target: original})
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)

    (workspace / target).write_text(UNFORMATTED)
    gate_repair_gate(workspace, contract, git(workspace, "rev-parse", "HEAD").strip())
    judged = (workspace / target).read_text()

    result = deliver(
        repo=repo,
        contract=contract,
        content=judged,
        base=git(repo, "rev-parse", "HEAD").strip(),
    )

    assert result.committed, f"the accepted change was not delivered: {result.reason}"
    assert git(repo, "show", f"{result.commit}:{target}") == judged


# --- B7 / N2: a base that names nothing ----------------------------------


def test_an_empty_base_is_refused_rather_than_softened_to_head(tmp_path: Path) -> None:
    """An empty base is not a request to diff against HEAD.

    ``Sandbox.source_base_commit()`` returns ``""`` for a source that can name
    no commit. ``_resolve`` treated a falsy base as ``HEAD`` — the moving name
    ``_source_commit``'s own docstring says it exists to prevent.
    """
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})
    head = git(repo, "rev-parse", "HEAD").strip()

    with pytest.raises(DeliveryError, match="base"):
        deliver(
            repo=repo,
            contract=contract_for(target),
            content="def fetch(url):\n    return url.strip()\n",
            base="",
        )

    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_sandbox_over_a_source_with_no_revision_refuses_to_name_one(
    tmp_path: Path,
) -> None:
    """The other end of the same defect: the value that should never exist.

    A non-git source has no revision a delivery can diff against. Handing back
    ``""`` puts a caller one falsy-check away from committing against whatever
    the branch has got to, so the sandbox says so instead.
    """
    source = tmp_path / "plain"
    (source / "src" / "pkg").mkdir(parents=True)
    (source / "src" / "pkg" / "fetch.py").write_text(
        "def fetch(url):\n    return url\n"
    )

    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        assert sandbox.base_changeset_ref(), "the workspace's own base is still real"
        with pytest.raises(SandboxError, match="revision"):
            sandbox.source_base_commit()


# --- N7: consensus and the convention it cites ---------------------------


def test_a_draw_with_no_byte_form_is_a_consensus_error(tmp_path: Path) -> None:
    """``_draw``'s own comment cites ``pending.stash`` as its model.

    ``stash`` was fixed to raise ``PendingError`` for content that has no byte
    form; ``_draw`` still let the raw ``UnicodeEncodeError`` out. A lone
    surrogate is a legal JSON escape, so it arrives here as ordinary draw text.
    """
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})

    with pytest.raises(ConsensusError, match="surrogate"):
        best_of(
            repo=repo,
            contract=contract_for(target),
            sample=lambda _index: 'def fetch(url):\n    return "\ud800"\n',
            gate=lambda _workspace: GateResult(),
        )
