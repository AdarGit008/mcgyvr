"""§4, third item — the mutation rung reads a rebind without asking where it is.

``param-mutation`` (:mod:`mcgyvr.gate.typecheck`) rejects a function that
mutates the object its caller passed in, and stands down for the sanctioned
defensive copy: ``items = list(items)`` rebinds the name, so what is mutated
afterwards is the function's own list and the caller's next read is still
right. That stand-down is correct and it has to keep working — a rung that
flags a real defensive copy rejects correct code, which costs a model call and
a rung of the ladder every time somebody writes the fix the rung asked for.

What the rung actually asked was *is this name rebound anywhere in this
function*, which is a different question. ``ast.walk`` over the body has no
order and no control flow in it, so every one of these reads as a defence:

``if target is None: target = []`` then ``target.append(extra)``
    The canonical shape, and the one that matters. The rebind runs only when
    the caller passed nothing. A caller that passed a list gets it appended to,
    which is exactly the fault the family exists to catch — and it is the
    single most common way the fault is written.

``items.append(x)`` and then ``items = list(items)``
    A copy placed after the mutation it was meant to prevent. It reads as the
    fix, it silences the rung, and the caller's list is already longer.

``if False: items = list(items)``
    Dead code. Nothing executes and the rung stands down anyway.

a rebind in a branch that returns, or in a loop that may run zero times
    Neither is on the path that reaches the mutation.

The rule all of these are measured against:

    A rebind defends a mutation only if it runs on **every** path from the
    function's entry to that mutation. A rebind that some path skips — a
    branch not taken, a loop not entered, a line not yet reached — leaves the
    caller's object exposed on that path, and one exposed path is the fault.

So the defended shapes below are as load-bearing as the undefended ones. Every
one of them is a correct program, and a rung that flags them is worse than the
rung that missed the canonical none-guard: it argues with the fix.

**The second half: the stand-down that nothing could reach.**
``compliance_findings`` takes ``contract_text`` so that a contract which asks
for in-place work — "sort the rows in place" — is not made unsatisfiable by a
rung that rejects the thing the contract ordered. Nothing passed it.
:meth:`~mcgyvr.gate.adapter.LanguageAdapter.structural_checks` has no contract
parameter, :meth:`~mcgyvr.gate.Gate.run` has none either, and the only caller
of ``compliance_findings`` in the tree passes three arguments. A default
argument no call site can set is not a policy; it is dead code that reads like
one, and the contract it was written for still cannot be satisfied.

Asserted here through :func:`~mcgyvr.drive.gate_in_sandbox` — the driver's own
gate call, with a real sandbox and a real diff — because the defect is
precisely that the seam does not join up, and a test that called
``compliance_findings`` directly would pass today while the contract stayed
unsatisfiable. The controls are the two ways the stand-down could be too wide:
a contract that asks for a *new* list must not stand it down, and a caller with
no contract at all gets the strict reading.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import gate_in_sandbox
from mcgyvr.gate import ChangeSet, Gate
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.typecheck import compliance_findings
from mcgyvr.sandbox.tempdir import TempDirSandbox

PARAM_MUTATION = "PARAM-MUTATION"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

# Sources where a rebind exists and does not reach the mutation. Every one is a
# function that appends to, sorts or deletes from the object its caller owns.
UNDEFENDED = [
    pytest.param(
        """def merge_into(target, extra):
    if target is None:
        target = []
    target.append(extra)
    return target
""",
        id="the-canonical-none-guard",
    ),
    pytest.param(
        """def merge_into(items, extra):
    items.append(extra)
    items = list(items)
    return items
""",
        id="a-copy-placed-after-the-mutation",
    ),
    pytest.param(
        """def merge_into(items, extra):
    if False:
        items = list(items)
    items.append(extra)
    return items
""",
        id="a-copy-in-dead-code",
    ),
    pytest.param(
        """def merge_into(items, extra, copy):
    if copy:
        items = list(items)
        return items
    items.append(extra)
    return items
""",
        id="a-copy-in-a-branch-that-returns",
    ),
    pytest.param(
        """def merge_into(items, extra, copy):
    if copy:
        items = list(items)
    items.append(extra)
    return items
""",
        id="a-copy-in-one-arm-of-two",
    ),
    pytest.param(
        """def merge_into(items, more):
    for _ in more:
        items = list(items)
    items.append(more)
    return items
""",
        id="a-copy-in-a-loop-that-may-not-run",
    ),
    pytest.param(
        """def merge_into(items, extra, pending):
    while pending:
        items = list(items)
    items.append(extra)
    return items
""",
        id="a-copy-in-a-while-that-may-not-run",
    ),
    pytest.param(
        """def merge_into(items, extra, copy, other):
    if copy:
        items = list(items)
    elif other:
        items = []
    items.append(extra)
    return items
""",
        id="an-elif-chain-with-no-else",
    ),
    pytest.param(
        """def merge_into(items, extra):
    try:
        items[0]
    except IndexError:
        items = list(items)
    items.append(extra)
    return items
""",
        id="a-copy-only-on-the-error-path",
    ),
    pytest.param(
        """def tidy(rows):
    rows.sort()
    rows = list(rows)
    return rows
""",
        id="a-sort-before-the-copy",
    ),
    pytest.param(
        """def drop_first(items):
    if not items:
        items = []
    del items[0]
    return items
""",
        id="a-del-behind-an-empty-guard",
    ),
]

# Sources where the rebind is on every path to the mutation, or where there is
# no mutation of the caller's object at all. A rung that flags any of these
# rejects a correct program, and the fix it would demand is the one already
# written.
DEFENDED = [
    pytest.param(
        """def merge_into(items, extra):
    items = list(items)
    items.append(extra)
    return items
""",
        id="the-copy-the-rung-asks-for",
    ),
    pytest.param(
        """def merge_into(items, extra):
    if items is None:
        items = []
    else:
        items = list(items)
    items.append(extra)
    return items
""",
        id="both-arms-rebind",
    ),
    pytest.param(
        """def merge_into(items, extra, copy, other):
    if copy:
        items = list(items)
    elif other:
        items = []
    else:
        items = sorted(items)
    items.append(extra)
    return items
""",
        id="every-arm-of-an-elif-chain-rebinds",
    ),
    pytest.param(
        """async def merge_into(items, extra):
    await ready()
    items = list(items)
    items.append(extra)
    return items
""",
        id="the-copy-precedes-the-mutation-in-a-coroutine",
    ),
    pytest.param(
        """def merge_into(items, extra, copy):
    if copy:
        items = list(items)
    else:
        return sorted(items)
    items.append(extra)
    return items
""",
        id="the-arm-that-does-not-rebind-returns",
    ),
    pytest.param(
        """def merge_into(items, extra):
    try:
        items = list(items)
    except TypeError:
        items = []
    items.append(extra)
    return items
""",
        id="the-body-and-every-handler-rebind",
    ),
    pytest.param(
        """def merge_into(items, more):
    items = list(items)
    for extra in more:
        items.append(extra)
    return items
""",
        id="the-copy-precedes-the-loop",
    ),
    pytest.param(
        """def merge_into(items, more):
    for extra in more:
        items = [*items, extra]
        items.append(extra)
    return items
""",
        id="the-copy-precedes-the-mutation-inside-the-loop",
    ),
    pytest.param(
        """def merge_into(items, extra):
    with borrowed(items) as items:
        items.append(extra)
    return items
""",
        id="with-as-binds-the-name-away",
    ),
    pytest.param(
        """def merge_into(items, extra):
    out = list(items)
    out.append(extra)
    return out
""",
        id="a-local-built-from-the-parameter",
    ),
    pytest.param(
        """def merge_into(rows, extra):
    out = []
    for row in rows:
        out.append(row + extra)
    return out
""",
        id="a-loop-that-only-reads-the-parameter",
    ),
    pytest.param(
        """def merge_into(**kwargs):
    kwargs.pop("extra", None)
    return kwargs
""",
        id="kwargs-is-built-fresh-per-call",
    ),
]

MUTATES_IN_PLACE = """def tidy(rows):
    rows.sort()
    return rows
"""

PLACEHOLDER = """def tidy(rows):
    return rows
"""

# A contract that ordered the mutation. Both fields are here because the rung's
# own docstring says the contract's prose is `task` and `interface` joined, and
# a worker reads both.
ASKS_IN_PLACE_TASK = """
id: tidy-rows
task_type: function_implementation
task: Sort the caller's rows in place and return them.
target: src/pkg/rows.py
stop_conditions:
  - The rows are not comparable to each other.
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""

ASKS_IN_PLACE_INTERFACE = """
id: tidy-rows
task_type: function_implementation
task: Order the rows.
interface: tidy(rows) sorts rows in-place and returns it.
target: src/pkg/rows.py
stop_conditions:
  - The rows are not comparable to each other.
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""

# The control: the same file, under a contract that ordered the opposite.
ASKS_FOR_A_NEW_LIST = """
id: tidy-rows
task_type: function_implementation
task: Return a new list holding the rows in order.
interface: tidy(rows) returns a sorted copy and leaves rows alone.
target: src/pkg/rows.py
stop_conditions:
  - The rows are not comparable to each other.
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""

# The negation case: the prose names mutation and forbids it.
FORBIDS_MUTATION = """
id: tidy-rows
task_type: function_implementation
task: Return the rows in order, and do not mutate the caller's list.
interface: tidy(rows) returns a sorted copy and never mutates rows.
target: src/pkg/rows.py
stop_conditions:
  - The rows are not comparable to each other.
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository whose committed ``rows.py`` mutates nothing.

    Committed rather than left untracked so the mutation below is a line the
    *worker* added: the gate attributes every structural finding to an added
    line, and a hazard already in the base is out of scope by construction.
    """
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "rows.py").write_text(PLACEHOLDER, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _mutation_findings(source: str) -> list[Finding]:
    """The ``param-mutation`` findings over a whole file the worker wrote.

    Every line counts as added, because these sources are what a worker handed
    back in full. Filtered to the one family so a stray style observation
    cannot make a red test green or a green one red.
    """
    tree = ast.parse(source)
    added = frozenset(range(1, len(source.splitlines()) + 1))
    return [
        finding
        for finding in compliance_findings(tree, "m.py", added)
        if finding.code == PARAM_MUTATION
    ]


@pytest.mark.parametrize("source", UNDEFENDED)
def test_a_rebind_that_does_not_reach_the_mutation_is_not_a_defence(
    source: str,
) -> None:
    """One path reaches the mutation without the rebind, so the caller is exposed."""
    findings = _mutation_findings(source)

    assert findings, (
        f"a rebind that some path to the mutation skips was read as a defensive "
        f"copy, and the caller's object is mutated under it:\n{source}"
    )


@pytest.mark.parametrize("source", DEFENDED)
def test_a_rebind_on_every_path_to_the_mutation_stands_the_rung_down(
    source: str,
) -> None:
    """The control, and the more expensive half to get wrong.

    These are correct programs. Rejecting one costs an attempt to rewrite the
    fix the rung itself asked for.
    """
    findings = _mutation_findings(source)

    assert not findings, (
        f"a correct program was rejected for mutating the caller's object — "
        f"{[str(f) for f in findings]}:\n{source}"
    )


def test_the_canonical_none_guard_is_rejected_by_the_whole_gate(repo: Path) -> None:
    """Asserted on the verdict, not on the presence of a note.

    The family's whole claim is that it rejects; a finding that does not stop
    the change from landing has prevented nothing.
    """
    (repo / "src" / "pkg" / "rows.py").write_text(
        """def merge_into(target, extra):
    if target is None:
        target = []
    target.append(extra)
    return target
""",
        encoding="utf-8",
    )
    changed = ChangeSet.detect(repo)

    result = Gate().run(changed)

    assert not result.accepted, (
        "`if target is None: target = []` followed by `target.append(extra)` was "
        "accepted: a caller that passed a list has it appended to"
    )
    assert any(f.code == PARAM_MUTATION for f in result.findings), (
        f"the change was rejected, but not for the mutation: {result.findings}"
    )


@pytest.mark.parametrize(
    "contract_source",
    [
        pytest.param(ASKS_IN_PLACE_TASK, id="asked-in-the-task"),
        pytest.param(ASKS_IN_PLACE_INTERFACE, id="asked-in-the-interface"),
    ],
)
def test_a_contract_that_asks_for_in_place_work_stands_the_rung_down(
    repo: Path, contract_source: str
) -> None:
    """The stand-down the rung already implements, reached from a real gate run.

    Through the driver's own call rather than through ``compliance_findings``,
    because what is missing is not the policy but every parameter between the
    contract and it.
    """
    contract = load_contract(contract_source)

    with TempDirSandbox(repo) as sandbox:
        result = gate_in_sandbox(contract, sandbox, MUTATES_IN_PLACE)

    assert result.accepted, (
        f"the contract ordered the sort in place and the gate rejected the worker "
        f"for obeying it — the contract cannot be satisfied: {result.findings}"
    )


def test_a_contract_that_asks_for_a_copy_does_not_stand_the_rung_down(
    repo: Path,
) -> None:
    """The control on the other side: the stand-down is the contract's, not a
    blanket amnesty for any contract that happens to be in hand."""
    contract = load_contract(ASKS_FOR_A_NEW_LIST)

    with TempDirSandbox(repo) as sandbox:
        result = gate_in_sandbox(contract, sandbox, MUTATES_IN_PLACE)

    assert not result.accepted, (
        "the contract asked for a sorted copy, the worker sorted the caller's "
        "list in place, and the gate accepted it"
    )
    assert any(f.code == PARAM_MUTATION for f in result.findings), (
        f"the change was rejected, but not for the mutation: {result.findings}"
    )


def test_a_contract_that_forbids_mutation_does_not_stand_the_rung_down(
    repo: Path,
) -> None:
    """ "do not mutate" is a prohibition, not an ask — the substring trap.

    The pressure test's reach leftovers caught this: ``_INPLACE_WORDS`` was a
    substring match, so a contract saying "do not mutate the caller's list"
    stood the rung down for the whole file — the one contract that most needs
    the backstop. The negation cancels the ask.
    """
    contract = load_contract(FORBIDS_MUTATION)

    with TempDirSandbox(repo) as sandbox:
        result = gate_in_sandbox(contract, sandbox, MUTATES_IN_PLACE)

    assert not result.accepted, (
        "the contract forbade mutation, the worker mutated the caller's list, "
        "and the gate accepted it because the word 'mutate' stood the rung down"
    )
    assert any(f.code == PARAM_MUTATION for f in result.findings), (
        f"the change was rejected, but not for the mutation: {result.findings}"
    )


def test_a_caller_with_no_contract_gets_the_strict_reading(repo: Path) -> None:
    """No prose to read is not permission. Delivery gates without a contract's
    scope and every bench harness runs the gate bare; the absence of an
    instruction must not be louder than the instruction itself."""
    (repo / "src" / "pkg" / "rows.py").write_text(MUTATES_IN_PLACE, encoding="utf-8")

    result = Gate().run(ChangeSet.detect(repo))

    assert not result.accepted, (
        "a gate run with no contract in hand accepted an in-place sort of the "
        "caller's list"
    )
