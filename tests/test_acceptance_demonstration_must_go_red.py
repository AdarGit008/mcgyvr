"""D16 — a demonstration that never went red demonstrates nothing.

An acceptance model that is only an exit code — run the commands, zero is a pass —
has no way to say "this command must fail before the change", so no way to tell a
fix from a plausible edit that left the suite as green as it already was. mcgyvr
splits the two lists — ``acceptance`` expects green at baseline, ``demonstration``
expects red — and enforces both halves at run. A `code` contract derives
``failing_test_first`` from a non-empty ``demonstration`` and ``tests_pass`` from
a non-empty ``acceptance``; neither list is forced.

So the two tests here are:

* **A demonstration is optional, not required.** Absent and explicitly empty
  both load, and neither derives ``failing_test_first`` — the evidence follows
  the field, so a `code` contract that declares no demonstration is judged on
  the gate and whatever else it carries. A contract that *does* declare one
  derives the kind.
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

from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.sandbox.tempdir import TempDirSandbox

BUG_FIX = """
id: fix-pager
task_type: code
task: The pager drops the last line of every file. Fix it.
target: src/pkg/pager.py
stop_conditions:
  - The defect cannot be reproduced from the demonstrating command.
{demonstration}
scope:
  allow: ["src/**/*.py"]
"""

ALREADY_GREEN = ("sh", "-c", "exit 0")


@pytest.mark.parametrize(
    ("slot", "how"),
    [("", "the key is absent"), ("demonstration: []", "the key is present but empty")],
)
def test_a_code_contract_without_a_demonstration_derives_no_failing_test(
    slot: str, how: str
) -> None:
    """A demonstration is optional for `code`, and an empty list is no demonstration.

    Both spellings are asserted because they are the same claim to a reader and
    two different code paths to a loader. Neither is refused — a `code`
    contract's evidence follows its fields, so with no demonstration there is
    simply no `failing_test_first`. The control that follows is the contract
    that *does* declare one: it derives the kind.
    """
    contract = load_contract(BUG_FIX.format(demonstration=slot))
    assert contract.demonstration == ()
    assert "failing_test_first" not in contract.evidence_names, (
        f"a code contract with no demonstration derived failing_test_first ({how})"
    )

    demonstrated = load_contract(
        BUG_FIX.format(demonstration='demonstration: ["pytest -q tests/test_pager.py"]')
    )
    assert "failing_test_first" in demonstrated.evidence_names, (
        "a code contract with a demonstration did not derive failing_test_first"
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
