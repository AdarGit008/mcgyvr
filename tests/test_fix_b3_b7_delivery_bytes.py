"""Four defects the pressure test found in the delivery/repair cluster.

Every test here failed by execution before the fix it guards, and each states a
property a person could check by hand rather than a call sequence:

* **B3** — two deliveries into one repository. The git index and ``HEAD`` are a
  shared, locked resource; the per-call snapshot-and-restore in ``deliver``'s
  ``finally`` is not atomic with respect to another call's stage-and-commit, so
  concurrent deliveries lost accepted changes and left the tree dirty.
* **B5** — ``repair`` scope-checks the change set's path and then follows a
  symlink out of the scope, handing ``ruff format`` a file the contract forbids.
* **B6** — a verdict and the bytes it was reached on travelled separately, so
  the bytes a gate *rejected* could be the bytes that got committed. The
  reproduction is the port's own documented loop, with no mock in it: the gate
  rejects, ``repair`` rewrites the tree, the re-run gate accepts, and the caller
  delivers the string it is still holding.
* **B7** — the value ``Delivery.base`` documented (the sandbox base commit)
  named a commit in the sandbox's own throwaway repository, so supplying it to
  ``deliver`` always raised.

and one instance of the report's pattern A: a lone surrogate is a legal JSON
escape, survives ``json.loads`` into a completion, parses as a valid reply, and
then cannot be encoded by ``surrogateescape`` — which is the repository's
convention for *bytes*, not for a code point that denotes none.
"""

from __future__ import annotations

import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import Accepted, Delivery, DeliveryError, deliver
from mcgyvr.gate import ChangeSet, Gate, GateResult
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.pending import resume, stash
from mcgyvr.repair import repair
from mcgyvr.sandbox import open_sandbox

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

# Valid Python the gate rejects on two rungs a tool repairs for nothing: an
# unused import and a line the formatter would reflow. The same fixture the D21
# tests use, restated here so this file stands on its own.
UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising with stderr on failure."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def make_repo(where: Path, targets: dict[str, str]) -> Path:
    """A real git repository holding ``targets``, committed once.

    Real rather than mocked throughout this file: every property asserted here
    is about what git and the filesystem end up holding, and a fake git would
    let exactly the wrong answers pass.
    """
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


# --- B3: concurrent delivery into one repository -------------------------


def test_two_deliveries_into_one_repository_do_not_corrupt_it(tmp_path: Path) -> None:
    """Concurrency, held on the outcome rather than on the mechanism.

    Before the fix this lost 18 of 20 accepted changes: git refuses a second
    ``index.lock`` outright and refuses a ``HEAD`` update whose old value moved
    under it, both of which arrived as a raised :class:`DeliveryError` — and
    ``deliver``'s own ``finally`` then rolled the accepted content back out of
    the tree. Repeated because a race that only sometimes fires is still a
    defect; every round must be clean, not most of them.
    """
    rounds, workers = 3, 3
    names = [f"src/pkg/f{n}.py" for n in range(workers)]

    for attempt in range(rounds):
        repo = make_repo(
            tmp_path / f"round{attempt}",
            {name: f"def f{n}():\n    return {n}\n" for n, name in enumerate(names)},
        )
        base = git(repo, "rev-parse", "HEAD").strip()
        wanted = {
            name: f"def f{n}():\n    return {n} + 1\n" for n, name in enumerate(names)
        }

        def one(
            name: str,
            repo: Path = repo,
            base: str = base,
            wanted: dict[str, str] = wanted,
        ) -> Delivery:
            # Bound as defaults rather than closed over: the round is a loop, and
            # a closure would hand every thread the last round's repository.
            return deliver(
                repo=repo,
                contract=contract_for(name),
                content=wanted[name],
                base=base,
            )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, names))

        for name, result in zip(names, results, strict=True):
            assert result.committed, f"{name} was not delivered: {result.reason}"
            assert (repo / name).read_text() == wanted[name], (
                f"round {attempt}: {name} does not hold the accepted content"
            )
        assert git(repo, "status", "--porcelain").strip() == "", (
            f"round {attempt}: the tree was left dirty"
        )
        shipped = sorted(git(repo, "diff", "--name-only", f"{base}..HEAD").split())
        assert shipped == sorted(names), f"round {attempt}: the commits ship {shipped}"


def test_two_repositories_are_inside_delivery_at_the_same_moment(
    tmp_path: Path,
) -> None:
    """The exclusion is per repository, which is the whole of what B3 needs.

    The D22 statement this must not regress: delivery holds no process-global
    state, so two orchestrators pointed at two repositories are a supported case
    (§9), and a module-level lock would pass B3 while destroying it.

    **The version of this test that shipped with the B3 fix could not tell.** It
    started two deliveries into two repositories and asserted both committed —
    which a module-global lock also produces, because serialising them still
    commits both, just one after the other. Measured: it passed with
    ``_exclusive`` replaced by a module-global ``threading.Lock()`` and with
    ``_exclusive`` replaced by a no-op. An outcome cannot see concurrency; only
    an overlap can.

    So the overlap is *forced* and the test fails if it does not happen. Each
    delivery blocks on a shared barrier from inside its own locked section — the
    adapter seam is called after the lock is taken and before the commit — and
    the barrier only releases when both are there at once. Under a per-repository
    exclusion both arrive and it releases; under one lock for the process the
    second can never arrive, and the first waits out the timeout and raises.

    What this does *not* discriminate is the lock existing at all: a no-op
    ``_exclusive`` also lets both threads meet. That is the right division of
    labour — safety is
    :func:`test_two_deliveries_into_one_repository_do_not_corrupt_it`, which a
    no-op fails outright; this one owns liveness, and states only that.
    """
    left = make_repo(
        tmp_path / "left", {"src/pkg/fetch.py": "def fetch():\n    pass\n"}
    )
    right = make_repo(
        tmp_path / "right", {"src/pkg/fetch.py": "def fetch():\n    pass\n"}
    )
    contract = contract_for("src/pkg/fetch.py")
    both_inside = threading.Barrier(2, timeout=30)
    arrived: list[str] = []

    class Rendezvous(PythonAdapter):
        """An adapter that will not answer until the other delivery is here too.

        It stands where a delivery's own gate run stands: after the repository
        lock is taken, before anything is staged. Waiting here is waiting while
        holding the exclusion, which is exactly the condition a process-wide
        lock cannot satisfy twice.
        """

        def check_syntax(self, change: FileChange, root: Path) -> list[Finding]:
            arrived.append(root.name)
            both_inside.wait()
            return super().check_syntax(change, root)

    def job(where: Path, text: str) -> Delivery:
        return deliver(
            repo=where,
            contract=contract,
            content=text,
            base=git(where, "rev-parse", "HEAD").strip(),
            adapters=[Rendezvous()],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(job, left, "def fetch():\n    return 1\n"),
            pool.submit(job, right, "def fetch():\n    return 2\n"),
        ]
        # `BrokenBarrierError` out of here is the failure this test exists for:
        # the two deliveries were never inside at the same moment.
        results = [future.result() for future in futures]

    assert sorted(arrived) == ["left", "right"], (
        f"both deliveries did not reach the rendezvous: {arrived}"
    )
    assert all(result.committed for result in results), (
        f"{[result.reason for result in results]}"
    )
    assert (left / "src" / "pkg" / "fetch.py").read_text().endswith("return 1\n")
    assert (right / "src" / "pkg" / "fetch.py").read_text().endswith("return 2\n")


# --- B5: a symlink out of the contract's scope ---------------------------


def test_repair_does_not_write_through_a_symlink_out_of_scope(tmp_path: Path) -> None:
    """The scope check was on the change set's path, not on the file it names.

    ``notes/secrets.py`` is committed before the change, so it is not in the
    change set at all and the *only* route to it is the link the worker left
    inside the scope. Before the fix ``ruff format`` rewrote it through the link
    and the outcome reported the repair against the in-scope name.
    """
    repo = make_repo(
        tmp_path / "work",
        {
            "src/pkg/fetch.py": "def fetch(url):\n    return url\n",
            "notes/secrets.py": UNFORMATTED,
        },
    )
    base = git(repo, "rev-parse", "HEAD").strip()
    outside = repo / "notes" / "secrets.py"
    untouched = outside.read_text()

    (repo / "src" / "pkg" / "link.py").symlink_to("../../notes/secrets.py")
    (repo / "src" / "pkg" / "fetch.py").write_text(UNFORMATTED)

    outcome = repair(repo=repo, contract=contract_for("src/pkg/fetch.py"), base=base)

    assert outside.read_text() == untouched, (
        "repair rewrote notes/secrets.py through a symlink, and the contract's "
        "scope src/**/*.py forbids it"
    )
    assert "src/pkg/link.py" not in outcome.repaired, (
        "repair reported a repair of the link rather than refusing to follow it"
    )
    assert (repo / "src" / "pkg" / "fetch.py").read_text() != UNFORMATTED, (
        "control: the in-scope file was not repaired either"
    )


def test_repair_names_what_it_changed_and_leaves_it_in_the_tree(
    tmp_path: Path,
) -> None:
    """Half of B6, on the writing side: repair mutates the tree and says which.

    A caller holding the worker's reply as a string has no way to learn what a
    repair left behind — which is how the bytes a gate rejected stay in the
    caller's hand while the bytes it accepted sit only on disk.

    What it learns is the *path*, not a copy of the bytes.
    ``RepairOutcome.content`` used to carry the second copy, for a caller that
    would hand it to :func:`~mcgyvr.deliver.deliver`; delivery takes an
    :class:`~mcgyvr.deliver.Accepted` minted off the tree now, so the copy was a
    value channel with no reader (pattern B, phase 3). The replacement is
    asserted here rather than assumed: the named path is bound off the tree, and
    the binding holds what the repair wrote.
    """
    repo = make_repo(tmp_path / "work", {"src/pkg/fetch.py": UNFORMATTED})
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "src" / "pkg" / "fetch.py").write_text(UNFORMATTED.replace("os", "os "))
    contract = contract_for("src/pkg/fetch.py")

    outcome = repair(repo=repo, contract=contract, base=base)

    assert outcome.repaired == ("src/pkg/fetch.py",), (
        f"the repair did not name the file it rewrote: {outcome}"
    )
    on_disk = (repo / "src" / "pkg" / "fetch.py").read_text()
    assert on_disk != UNFORMATTED.replace("os", "os "), (
        "the premise did not hold: nothing was rewritten"
    )
    bound = Accepted.read(
        repo=repo,
        contract=contract,
        result=Gate().run(ChangeSet.detect(repo, base), contract.scope),
    )
    assert bound.content == on_disk, (
        "the binding a caller carries onward is not the file the repair left"
    )


# --- B6: the bytes a verdict was reached on ------------------------------


def _gate_repair_gate(repo: Path, contract: Contract, base: str) -> GateResult:
    """The port's own documented loop: gate, repair, gate again.

    Returns the second verdict. The bytes it was reached on are deliberately not
    returned beside it — they are in ``repo``, which is the whole of B6: a value
    that hands a caller "the verdict" and "some bytes" as two returns is the
    substitution waiting to happen. ``Accepted.read`` goes and gets them.
    """
    first = Gate().run(ChangeSet.detect(repo, base), contract.scope)
    assert not first.accepted, (
        f"the premise did not hold: the gate accepted unformatted content "
        f"(is ruff installed? {first.environment_issues})"
    )
    outcome = repair(repo=repo, contract=contract, base=base)
    assert outcome.changed, "the premise did not hold: nothing was repaired"
    return Gate().run(ChangeSet.detect(repo, base), contract.scope)


def test_the_bytes_the_gate_rejected_do_not_reach_the_repository(
    tmp_path: Path,
) -> None:
    """B6 end to end, with no mock anywhere in it.

    The worker ran in one tree and the commit lands in another, which is the
    arrangement that makes this reachable: the gate and the repair own bytes on
    disk in the workspace, delivery is handed a string, and nothing bound the
    two. Before the fix the committed blob was ``UNFORMATTED`` — the exact bytes
    the gate had rejected on ``lint`` and ``format``.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    workspace = make_repo(tmp_path / "workspace", {target: original})
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)

    workspace_base = git(workspace, "rev-parse", "HEAD").strip()
    (workspace / target).write_text(UNFORMATTED)  # what the worker replied
    verdict = _gate_repair_gate(workspace, contract, workspace_base)
    assert verdict.accepted

    # Minted in the workspace the gate ran in, from the tree the gate read. The
    # caller never names the bytes, which is the point: what it is holding is
    # still UNFORMATTED, and there is no parameter to offer that through.
    bound = Accepted.read(repo=workspace, contract=contract, result=verdict)
    judged = bound.content
    assert judged != UNFORMATTED

    result = deliver(
        repo=repo,
        contract=contract,
        content=bound,
        base=git(repo, "rev-parse", "HEAD").strip(),
    )

    assert result.committed, f"the accepted change was not delivered: {result.reason}"
    committed = git(repo, "show", f"{result.commit}:{target}")
    assert committed != UNFORMATTED, (
        "the bytes the gate rejected reached the repository"
    )
    assert committed == judged, "the committed bytes are not the bytes the gate judged"


def test_a_verdict_does_not_travel_apart_from_the_bytes_it_was_reached_on(
    tmp_path: Path,
) -> None:
    """A substitution between the verdict and the commit is refused, by name.

    This statement is the one the first B6 fix could not hold. Its test built
    ``Accepted(content=X, digest=digest_of(Y))`` by hand — a value the only
    constructor could not produce — so the check it guarded was true of every
    ``Accepted`` the system could make, and reverting the production code broke
    nothing that could actually happen. Pattern D, inside the fix for it.

    So the substitution here is made the way the system makes one. The verdict
    and its digest are minted in the workspace the gate ran in and carried to a
    recovery run through :mod:`mcgyvr.pending`, which stores the digest in
    ``meta.json`` and the bytes in ``files/`` — two files, in a directory an
    operator is expected to open. Editing one of them is the substitution, and
    the edit is deliberately to bytes the gate would *accept*, so that nothing
    but the binding can catch it.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    repo = make_repo(tmp_path / "repo", {target: original})
    contract = contract_for(target)
    store = tmp_path / "pending"
    head = git(repo, "rev-parse", "HEAD").strip()

    judged = "def fetch(url):\n    return url.strip()\n"
    (repo / target).write_text(judged)
    verdict = Gate().run(ChangeSet.detect(repo, head), contract.scope)
    assert verdict.accepted, f"the premise did not hold: {verdict.findings}"
    bound = Accepted.read(repo=repo, contract=contract, result=verdict)
    git(repo, "checkout", "--", target)

    entry = stash(store=store, repo=repo, contract=contract, content=bound)
    # The substitution: valid, formatted, lint-clean Python that no gate read.
    swapped = "def fetch(url):\n    return url.lstrip()\n"
    (entry.entry / "files" / target).write_text(swapped)

    result = resume(
        store=store, repo=repo, task=contract.id, verify=lambda _t: True, base=head
    )

    assert not result.completed, "committed bytes no verdict was reached on"
    assert result.delivery is not None
    assert "verdict" in result.delivery.reason, (
        f"the refusal must say why: {result.delivery.reason!r}"
    )
    assert (repo / target).read_text() == original
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_writer_between_the_write_and_the_commit_cannot_substitute_the_bytes(
    tmp_path: Path,
) -> None:
    """The commit-time re-check re-establishes identity, not only syntax.

    The meddler is injected through ``adapters`` — a public argument, called
    after delivery writes and before it stages — and it leaves valid Python
    behind, so a syntax-only re-check cannot see it. Before the fix the
    substituted bytes were committed and reported as a successful delivery.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    repo = make_repo(tmp_path / "repo", {target: original})
    head = git(repo, "rev-parse", "HEAD").strip()
    substituted = "def fetch(url):\n    return 'not what was accepted'\n"

    class Meddler(PythonAdapter):
        """A concurrent writer, standing exactly where one could stand."""

        def check_syntax(self, change: FileChange, root: Path) -> list[Finding]:
            (repo / target).write_text(substituted)
            return super().check_syntax(change, root)

    result = deliver(
        repo=repo,
        contract=contract_for(target),
        content="def fetch(url):\n    return url.strip()\n",
        base=head,
        adapters=[Meddler()],
    )

    assert not result.committed, "committed bytes that were not the accepted ones"
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert (repo / target).read_text() == original, "the tree was not put back"
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_verdict_the_caller_contradicts_is_an_error_rather_than_a_commit(
    tmp_path: Path,
) -> None:
    """Two answers to one question is a caller fault, not something to pick from.

    ``accepted=`` survives as a way to say *no* — a caller that already knows the
    gate refused saves delivery a gate run. Saying *yes* is what it may no longer
    do, whether or not a bound verdict disagrees: an acceptance delivery cannot
    check is the claim B6 travelled in.
    """
    target = "src/pkg/fetch.py"
    contract = contract_for(target)
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})
    head = git(repo, "rev-parse", "HEAD").strip()

    (repo / target).write_text(UNFORMATTED)
    rejected = Accepted.read(
        repo=repo,
        contract=contract,
        result=Gate().run(ChangeSet.detect(repo, head), contract.scope),
    )
    git(repo, "checkout", "--", target)
    assert not rejected.accepted, "the premise did not hold: the gate accepted"

    with pytest.raises(DeliveryError, match="verdict"):
        deliver(
            repo=repo,
            contract=contract,
            content=rejected,
            base=head,
            accepted=True,
        )


# --- B7: the base a delivery is diffed against ---------------------------


def test_the_revision_the_worker_started_from_is_a_usable_delivery_base(
    tmp_path: Path,
) -> None:
    """What ``Delivery.base`` documents, made obtainable.

    A sandbox's ``base_changeset_ref`` is a commit in the workspace's own fresh
    repository and exists nowhere else; the revision a delivery has to diff
    against is the one in the *source* repository the workspace was populated
    from. Before the fix the sandbox exposed only the former.
    """
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})
    head = git(repo, "rev-parse", "HEAD").strip()

    with open_sandbox(repo, mode="tempdir", docker_available=False) as sandbox:
        base = sandbox.source_base_commit()
        workspace_base = sandbox.base_changeset_ref()

    assert base == head, (
        "the source revision is not the one the workspace was built from"
    )
    result = deliver(
        repo=repo,
        contract=contract_for(target),
        content="def fetch(url):\n    return url.strip()\n",
        base=base,
    )
    assert result.committed, f"the documented base refused: {result.reason}"
    assert result.base == head
    assert workspace_base != head, "the premise did not hold: the two bases coincided"


def test_a_workspace_base_commit_is_not_a_delivery_base(tmp_path: Path) -> None:
    """The statement the corrected docstring makes, pinned.

    Green before the fix as well as after — it is what the prose was wrong
    about, not what the code was wrong about, and it is here so the two cannot
    drift apart again.
    """
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})

    with open_sandbox(repo, mode="tempdir", docker_available=False) as sandbox:
        workspace_base = sandbox.base_changeset_ref()

    with pytest.raises(DeliveryError, match="cannot diff against"):
        deliver(
            repo=repo,
            contract=contract_for(target),
            content="def fetch(url):\n    return url.strip()\n",
            base=workspace_base,
        )


# --- pattern A: the repository's own byte convention ---------------------


def test_a_lone_surrogate_is_refused_rather_than_crashing_the_delivery(
    tmp_path: Path,
) -> None:
    """``\\ud800`` is a legal JSON escape and reaches here as ordinary content.

    ``surrogateescape`` round-trips *bytes* — U+DC80..U+DCFF — and a lone
    high surrogate is not one, so encoding it raised ``UnicodeEncodeError``
    straight out of ``deliver``. There is no UTF-8 for U+D800, so a delivery
    that wrote something anyway would ship bytes nobody gated; it refuses, and
    the refusal is an answer the caller can log like any other.
    """
    target = "src/pkg/fetch.py"
    original = "def fetch(url):\n    return url\n"
    repo = make_repo(tmp_path / "repo", {target: original})
    head = git(repo, "rev-parse", "HEAD").strip()

    # Exactly the path off the wire: a completion's JSON, decoded.
    content = json.loads(r'"def fetch(url):\n    return \"\ud800\"\n"')

    result = deliver(
        repo=repo, contract=contract_for(target), content=content, base=head
    )

    assert not result.committed
    assert "surrogate" in result.reason, f"the refusal must say why: {result.reason!r}"
    assert (repo / target).read_text() == original
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_surrogate_escaped_byte_still_delivers(tmp_path: Path) -> None:
    """The control: the convention the rest of mcgyvr uses must keep working.

    ``\\udcff`` is byte ``0xFF`` as ``surrogateescape`` carries it, which is how a
    non-UTF-8 file reaches this module at all and what the pending store's
    round trip rests on. Refusing that would trade one crash for a delivery that
    cannot ship half the files in a repository.

    The target is deliberately not Python: ``ast.parse`` cannot be handed a
    surrogate either, so the delivery-time re-parse raises on this content — a
    separate instance of the same pattern, in
    :meth:`mcgyvr.gate.adapters.PythonAdapter.check_syntax`, which is not this
    module's to fix.
    """
    target = "src/pkg/fixture.txt"
    repo = make_repo(tmp_path / "repo", {target: "fixture\n"})
    head = git(repo, "rev-parse", "HEAD").strip()

    result = deliver(
        repo=repo,
        contract=contract_for(target, scope="src/**"),
        content="fixture \udcff\n",
        base=head,
    )

    assert result.committed, f"a surrogate-escaped byte was refused: {result.reason}"
    assert (repo / target).read_bytes() == b"fixture \xff\n"
