"""D16 — a demonstration that never went red demonstrates nothing.

GREEN by design. The acceptance model being ported over is an exit code: run the
commands, zero is a pass. There is no way to say "this command must fail before
the change", so there is no way to tell a fix from a plausible edit that left the
suite as green as it already was. mcgyvr splits the two lists — ``acceptance``
expects green at baseline, ``demonstration`` expects red — and enforces both
halves, at load and at run.

``tests/test_contract.py`` already refuses a ``bug_fix`` with no demonstration and
``tests/test_acceptance.py`` already names the baseline refusal. Each holds one
half. What neither holds, and what a port would take out without tripping either,
is that the two lists have *opposite* baseline expectations at all: a rewrite that
collapsed ``demonstration`` into "just more acceptance commands" would keep the
load-time requirement (the field is still required, still non-empty) and would
lose the entire point of it, because a green command would then be as acceptable
in one list as in the other.

So the two tests here are:

* **The requirement is a requirement, not a default.** Absent and explicitly empty
  are asserted to be refused identically, since a schema that quietly accepted
  ``demonstration: []`` would let every bug_fix through while the required-field
  test still passed. A type that does not require one is loaded alongside, so the
  refusal is shown to be about the evidence the type needs rather than about a
  field that is always mandatory.
* **One command, both lists, opposite verdicts.** The same green command is put
  in ``acceptance`` and then in ``demonstration`` against the same unchanged
  tree. As acceptance it is a clean baseline; as a demonstration it is refused,
  by its own name, before an attempt is funded. If the two lists ever mean the
  same thing again, this is the assertion that cannot be satisfied.

Nothing here reaches the network or a Docker daemon: the baseline check runs in
the temp-directory sandbox, which is a copy of the tree and a shell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.contract import ContractSchemaError
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.sandbox.tempdir import TempDirSandbox

BUG_FIX = """
id: fix-pager
task_type: bug_fix
task: The pager drops the last line of every file. Fix it.
target: src/pkg/pager.py
stop_conditions:
  - The defect cannot be reproduced from the demonstrating command.
{demonstration}
scope:
  allow: ["src/**/*.py"]
"""

# A type whose evidence needs no red-first command, so the refusal below is
# demonstrably about the evidence the task type requires and not about a field
# every contract must carry.
DOCSTRING = """
id: document-pager
task_type: docstring
task: Document the pager.
target: src/pkg/pager.py
stop_conditions:
  - What the pager is for is not stated anywhere in the repo.
scope:
  allow: ["src/**/*.py"]
"""

ALREADY_GREEN = ("sh", "-c", "exit 0")


@pytest.mark.parametrize(
    ("slot", "how"),
    [("", "the key is absent"), ("demonstration: []", "the key is present but empty")],
)
def test_a_type_that_requires_a_demonstration_is_rejected_at_load_without_one(
    slot: str, how: str
) -> None:
    """No demonstration, no contract — and an empty list is no demonstration.

    Both spellings are asserted because they are the same claim to a reader and
    two different code paths to a validator. A schema that treated the declared
    default as satisfying the requirement would refuse the absent key and accept
    the empty list, which is the shape the requirement quietly stops meaning
    anything.

    Asserted as a schema error rather than any failure, because "this document is
    not a contract" and "this file would not parse" are different things to fix,
    and the message has to name the field and the evidence so a reader knows
    which. The control at the end is the load that must still succeed: without
    it this test would also pass against a validator that had started refusing
    everything.
    """
    with pytest.raises(ContractSchemaError) as refused:
        load_contract(BUG_FIX.format(demonstration=slot))

    message = str(refused.value)
    assert message.startswith("demonstration:"), (
        f"the refusal does not name the field ({how})"
    )
    assert "failing_test_first" in message, (
        "the refusal does not name the evidence required"
    )
    assert "fails before the change" in message, (
        "the refusal does not say what a demonstration is"
    )

    assert load_contract(DOCSTRING).demonstration == (), (
        "a type that needs no red-first evidence was made to carry one anyway"
    )


def test_a_demonstration_that_already_passes_is_refused_though_it_is_a_fine_acceptance(
    tmp_path: Path,
) -> None:
    """The same green command, in the two lists, gets opposite verdicts.

    This is the statement an exit-code-only model cannot make. One command, one
    unchanged tree, one sandbox: in ``acceptance`` it is a usable baseline, in
    ``demonstration`` it is refused before any attempt is spent, because a
    command that is already green cannot become evidence that anything was
    fixed.

    The refusal is checked by its own reason token rather than by "an issue was
    returned". A demonstration can also be refused for being unrunnable, for
    timing out, or for mutating the tree, and a port that had lost the red-first
    rule while keeping the others would still return *an* issue here.
    """
    source = tmp_path / "checkout"
    source.mkdir()
    (source / "pager.py").write_text("def page(items):\n    return items\n")

    with TempDirSandbox(source) as sandbox:
        as_acceptance = Acceptance(sandbox, (ALREADY_GREEN,)).precondition()
        as_demonstration = Acceptance(
            sandbox, (), demonstrations=(ALREADY_GREEN,)
        ).precondition()

    assert as_acceptance is None, (
        f"a green command was refused as a regression baseline: {as_acceptance}"
    )
    assert as_demonstration is not None, (
        "a demonstration that never went red was accepted"
    )
    assert as_demonstration.reason == "demonstration-passes-at-baseline", (
        f"refused, but for the wrong reason: {as_demonstration.reason}"
    )
    assert "already passes" in as_demonstration.message
