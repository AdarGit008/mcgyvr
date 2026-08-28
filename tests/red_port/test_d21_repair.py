"""D21 — a change rejected for a missing blank line costs a whole rung of the ladder.

mcgyvr's gate is deliberately read-only. ``ruff format --diff`` reports what the
formatter *would* change; ``ruff check`` runs without ``--fix``; a formatting violation
becomes a :class:`~mcgyvr.gate.Finding` and never a rewrite. That is the right shape for
a gate — a checker that edits what it is checking cannot be trusted to have checked
it — but it leaves the whole class of failures a tool can repair for nothing being paid
for with a model call, and on a weak local model that call is the scarce thing. A 7B
that produced correct logic with an unsorted import block is asked to try again, and it
is at least as likely to produce different logic as the same logic sorted.

So this lever is worth exactly one free attempt per fixable rejection, and the tests are
shaped around what that sentence promises:

* **The re-run gate accepts, and no model was asked.** Both halves in one statement,
  because either alone is worthless. A repair that fixes the file but escalates anyway
  has bought nothing; a repair that spends a call to fix a blank line has bought a worse
  version of what the ladder already did. The no-model half is held by poisoning the
  dispatch seam so that reaching a model raises, rather than by counting calls — a call
  made and ignored is still the spend. The worker's own change is asserted to still be
  there afterwards, because "the gate accepts" is also true of a file repaired back to
  the state the worker was asked to change.
* **Nothing changed is reported as nothing changed.** The caller's next move is to
  re-run a gate it already knows the answer to, or to escalate; a repair that reports
  success on a file it did not touch sends it into a loop that ends at the attempt
  ceiling. Asserted against the bytes, not against a return value alone.
* **An undefined name that the contract already declared as a dependency gets its
  import.** This is the one repair that is not a formatting rewrite, and the constraint
  is what keeps it honest: the name has to come from a dependency the contract states,
  so the repair is only ever writing down something the contract already said. Asserted
  on the file still parsing and on the import naming both the module and the name — an
  inserted line that does not resolve is a new failure, not a repair.
* **Nothing outside the contract's scope is touched.** The repair runs tools across a
  tree, which is precisely how a tidy-up escapes its contract; a formatter pointed at
  the wrong directory rewrites a human's unrelated file and the gate never sees it,
  because the gate only looks at the change. Held with a fixable file placed out of
  scope beside a fixable file inside it: asserting the out-of-scope file is untouched
  alone would pass against a repair that does nothing at all.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from mcgyvr import runner
from mcgyvr.contract import loads
from mcgyvr.gate import ChangeSet, Gate
from tests.red_port.conftest import git, required

BEHAVIOR = (
    "repair a mechanically fixable gate rejection in place and re-run the gate on the "
    "same rung, without spending a model call"
)

# Valid Python, correct logic, and rejected by the gate for three things a tool fixes:
# an unused import, an unsorted import block, and a line the formatter would reflow.
UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)

# The same file after any competent repair: nothing about the worker's logic changed.
WORKER_LOGIC = "time.sleep(1)"

DEPS_CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
deps:
  - path: src/pkg/backoff.py
    signature: "def sleep_backoff(attempt: int) -> None"
    note: The backoff the retry loop must wait with.
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""


def _repair() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.repair", fromlist=["repair"]).repair
    )


def _changed(outcome: Any) -> Any:
    """Whether a repair says it rewrote anything, however it chooses to report it."""
    return getattr(outcome, "changed", outcome)


def _refuse_to_dispatch(*args: Any, **kwargs: Any) -> Any:
    """The dispatch seam, poisoned. See the free-attempt test."""
    raise AssertionError(
        "repair reached a model: the free attempt this lever exists to buy was spent"
    )


def test_a_mechanically_fixable_rejection_is_repaired_and_the_re_run_gate_accepts(
    repo: Path, contract: Any, monkeypatch: Any
) -> None:
    """The whole value of the lever, stated once: a rejected attempt becomes an accepted
    one.

    Both dispatch entry points are poisoned before anything runs, so a repair that asks
    a model fails here and says so. The worker's own line is asserted afterwards because
    a file reverted to its pre-change state also passes a gate.
    """
    repair = _repair()
    monkeypatch.setattr(runner, "dispatch", _refuse_to_dispatch)
    monkeypatch.setattr(runner, "dispatch_role", _refuse_to_dispatch)
    base = git(repo, "rev-parse", "HEAD").strip()
    target = repo / "src" / "pkg" / "fetch.py"
    target.write_text(UNFORMATTED)

    before = Gate().run(ChangeSet.detect(repo, base), contract.scope)
    assert not before.accepted, (
        f"the premise did not hold: the gate accepted an unformatted change "
        f"(is ruff installed? {before.environment_issues})"
    )

    outcome = repair(repo=repo, contract=contract, base=base)

    assert _changed(outcome), f"repair reported no repair for {before.by_check()}"
    after = Gate().run(ChangeSet.detect(repo, base), contract.scope)
    assert after.accepted, f"the re-run gate still rejects: {after.findings}"
    assert WORKER_LOGIC in target.read_text(), "repair discarded the worker's change"


def test_repair_reports_that_it_did_nothing_when_no_bytes_changed(
    repo: Path, contract: Any
) -> None:
    """A clean file is left alone, and the report says so rather than claiming a fix.

    Asserted on the bytes as well as on the report: a repair that rewrote the file
    identically has still touched it, and a caller told "repaired" re-runs a gate whose
    answer it already has — which on a failing attempt is a loop, not a recovery.
    """
    repair = _repair()
    base = git(repo, "rev-parse", "HEAD").strip()
    target = repo / "src" / "pkg" / "fetch.py"
    clean = "import time\n\n\ndef fetch(url):\n    time.sleep(1)\n    return url\n"
    target.write_text(clean)

    outcome = repair(repo=repo, contract=contract, base=base)

    assert not _changed(outcome), "repair claimed a fix it did not make"
    assert target.read_text() == clean, "repair rewrote a file that needed nothing"


def test_an_undefined_name_that_the_contract_declared_as_a_dependency_gets_its_import(
    repo: Path,
) -> None:
    """The one repair that adds code — and it may only write down what the contract
    said.

    The name is undefined and the contract already names the file it comes from, so the
    repair is transcription rather than invention. Asserted on the module and the name
    together, and on the file still parsing: an import line that does not resolve has
    replaced one failure with another.
    """
    repair = _repair()
    contract = loads(DEPS_CONTRACT)
    (repo / "src" / "pkg" / "backoff.py").write_text(
        "def sleep_backoff(attempt: int) -> None:\n    return None\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "backoff")
    base = git(repo, "rev-parse", "HEAD").strip()
    target = repo / "src" / "pkg" / "fetch.py"
    target.write_text(
        "def fetch(url):\n"
        "    for attempt in range(3):\n"
        "        sleep_backoff(attempt)\n"
        "    return url\n"
    )

    repair(repo=repo, contract=contract, base=base)

    repaired = target.read_text()
    imports = [
        line for line in repaired.splitlines() if line.startswith(("import ", "from "))
    ]
    assert any("sleep_backoff" in line and "backoff" in line for line in imports), (
        f"the undefined name was declared as a dependency and no import was added: "
        f"{imports}"
    )
    ast.parse(repaired)


def test_repair_never_touches_a_file_outside_the_contracts_scope(
    repo: Path, contract: Any
) -> None:
    """A tool run across a tree is how a tidy-up escapes its contract.

    The out-of-scope file is fixable in exactly the same way as the in-scope one, so a
    repair that walks the tree rather than the contract's change rewrites a file nobody
    asked it to and the gate never sees it — the gate only looks at the change. The
    in-scope assertion is the control: without it, doing nothing at all would pass.
    """
    repair = _repair()
    base = git(repo, "rev-parse", "HEAD").strip()
    outside = repo / "notes" / "scratch.py"
    outside.parent.mkdir()
    outside.write_text(UNFORMATTED)
    untouched = outside.read_text()
    (repo / "src" / "pkg" / "fetch.py").write_text(UNFORMATTED)

    repair(repo=repo, contract=contract, base=base)

    assert outside.read_text() == untouched, (
        f"repair rewrote {outside.name}, which the contract's scope "
        f"{contract.scope.allow} does not permit"
    )
    assert (repo / "src" / "pkg" / "fetch.py").read_text() != UNFORMATTED, (
        "control: the in-scope file was not repaired either"
    )
