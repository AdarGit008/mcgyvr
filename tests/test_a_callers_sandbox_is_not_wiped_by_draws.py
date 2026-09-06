"""G1/S3 — ``best_of`` must not destroy a caller's own sandbox.

``best_of`` was taught to take a caller-supplied ``sandbox`` ("a caller
mid-attempt already holds one and should pass it"), and then reset that sandbox
to its base after every draw. Two consequences, both on the exact caller the
docstring invites:

* the caller's accumulated work — a file it had already written before asking
  for draws — is silently deleted by ``git reset --hard`` + ``git clean -fdx``;
* draw 0 is staged on top of that accumulated work while draw 1 is staged on a
  clean base, so the two draws are gated against different trees and the gate
  is asked to rank incomparable changes.

The fix is a checkpoint: the workspace is committed as it was handed over, and
after every draw it is restored to that checkpoint, not reset to the base. The
caller's state survives, and every draw starts from the same tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.consensus import best_of
from mcgyvr.contract import loads
from mcgyvr.gate import Finding, GateResult
from mcgyvr.sandbox import Sandbox, open_sandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/fetch.py"
BASE = "def fetch(url):\n    return url\n"
DRAW = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"

CONTRACT = f"""
id: retry
task_type: function_implementation
task: Give the fetch helper a retry budget named RETRY.
target: {TARGET}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
demonstration: ["sh -c 'grep -q RETRY {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**"]
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={**_IDENTITY},
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text(BASE, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _gate_recording(seen: list[bool]):  # type: ignore[no-untyped-def]
    """A gate that records whether the caller's sentinel is present at gate time.

    The sentinel is the caller's accumulated work. A draw gated while it is
    present was staged against the caller's state; one gated while it is absent
    was staged against a bare base, which is the draw-0 bias this file exists to
    remove.
    """

    def gate(sandbox: Sandbox) -> GateResult:
        seen.append((sandbox.workspace / "notes.txt").exists())
        content = (sandbox.workspace / TARGET).read_text(encoding="utf-8")
        if "RETRY" in content:
            return GateResult()
        return GateResult(
            findings=(Finding(check="acceptance", path=TARGET, message="no RETRY"),)
        )

    return gate


def test_the_callers_state_survives_the_draws(source: Path) -> None:
    """A file the caller wrote before ``best_of`` is still there afterwards."""
    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        (sandbox.workspace / "notes.txt").write_text("caller state", encoding="utf-8")

        best_of(
            sandbox=sandbox,
            contract=loads(CONTRACT),
            sample=lambda _index: DRAW,
            gate=lambda _space: GateResult(),
            n=2,
        )

        sentinel = sandbox.workspace / "notes.txt"
        assert sentinel.exists(), "the caller's file was wiped by the draws"
        assert sentinel.read_text(encoding="utf-8") == "caller state", (
            "the caller's file changed across the draws"
        )


def test_every_draw_is_staged_against_the_callers_state(source: Path) -> None:
    """Draw 0 and draw 1 both see the caller's state — neither is biased."""
    seen: list[bool] = []
    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        (sandbox.workspace / "notes.txt").write_text("caller state", encoding="utf-8")

        best_of(
            sandbox=sandbox,
            contract=loads(CONTRACT),
            sample=lambda _index: DRAW,
            gate=_gate_recording(seen),
            n=2,
        )

    assert seen == [True, True], (
        f"draws were staged against different trees: sentinel seen at {seen}"
    )


def test_a_gitignored_callers_file_survives_the_draws(source: Path) -> None:
    """A file the caller wrote that ``.gitignore`` covers is not swept.

    ``checkpoint`` snapshots with ``git add -A``, which honours ``.gitignore``,
    so the ignored file is never in the snapshot commit. ``restore_to`` must
    still leave it alone — ``clean -fd`` without ``-x`` — or the caller's
    ignored state is destroyed the same way ``reset`` used to destroy it.
    """
    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        (sandbox.workspace / ".gitignore").write_text("secret.bin\n", encoding="utf-8")
        (sandbox.workspace / "secret.bin").write_bytes(b"caller secret")

        best_of(
            sandbox=sandbox,
            contract=loads(CONTRACT),
            sample=lambda _index: DRAW,
            gate=lambda _space: GateResult(),
            n=2,
        )

        secret = sandbox.workspace / "secret.bin"
        assert secret.exists(), "the caller's ignored file was swept by the draws"
        assert secret.read_bytes() == b"caller secret", (
            "the caller's ignored file changed across the draws"
        )


def test_a_gate_that_raises_still_restores_the_callers_state(source: Path) -> None:
    """The ``finally`` restores even when the gate blows up mid-draw."""
    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        (sandbox.workspace / "notes.txt").write_text("caller state", encoding="utf-8")

        def gate(_space: Sandbox) -> GateResult:
            raise RuntimeError("gate exploded")

        with pytest.raises(RuntimeError):
            best_of(
                sandbox=sandbox,
                contract=loads(CONTRACT),
                sample=lambda _index: DRAW,
                gate=gate,
                n=2,
            )

        sentinel = sandbox.workspace / "notes.txt"
        assert sentinel.read_text(encoding="utf-8") == "caller state", (
            "the caller's state was lost when the gate raised"
        )
        assert (sandbox.workspace / TARGET).read_text(encoding="utf-8") == BASE, (
            "the draw's bytes were left in the caller's tree after the gate raised"
        )


def test_a_draws_by_products_do_not_leak_into_the_next_draw(source: Path) -> None:
    """A file one gate writes is gone when the next draw is judged."""
    leaked: list[bool] = []
    draws = 0

    def gate(sandbox: Sandbox) -> GateResult:
        nonlocal draws
        leaked.append((sandbox.workspace / "byproduct.txt").exists())
        draws += 1
        if draws == 1:
            (sandbox.workspace / "byproduct.txt").write_text(
                "draw 0 by-product", encoding="utf-8"
            )
        content = (sandbox.workspace / TARGET).read_text(encoding="utf-8")
        if "RETRY" in content:
            return GateResult()
        return GateResult(
            findings=(Finding(check="acceptance", path=TARGET, message="no RETRY"),)
        )

    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        (sandbox.workspace / "notes.txt").write_text("caller state", encoding="utf-8")
        best_of(
            sandbox=sandbox,
            contract=loads(CONTRACT),
            sample=lambda _index: DRAW,
            gate=gate,
            n=2,
        )

    assert leaked == [False, False], f"draw 0's by-product leaked into draw 1: {leaked}"


def test_the_ephemeral_repo_path_still_resets_between_draws(source: Path) -> None:
    """The ``repo`` path keeps the ordinary base reset, not the checkpoint."""
    leaked: list[bool] = []
    draws = 0

    def gate(sandbox: Sandbox) -> GateResult:
        nonlocal draws
        leaked.append((sandbox.workspace / "byproduct.txt").exists())
        draws += 1
        if draws == 1:
            (sandbox.workspace / "byproduct.txt").write_text(
                "draw 0 by-product", encoding="utf-8"
            )
        return GateResult()

    best_of(
        repo=source,
        contract=loads(CONTRACT),
        sample=lambda _index: DRAW,
        gate=gate,
        n=2,
    )

    assert leaked == [False, False], f"draw 0's by-product leaked into draw 1: {leaked}"


def test_head_returns_to_the_base_after_best_of(source: Path) -> None:
    """The snapshot commit does not stay checked out once the draws finish."""
    with open_sandbox(source, mode="tempdir", docker_available=False) as sandbox:
        (sandbox.workspace / "notes.txt").write_text("caller state", encoding="utf-8")
        base = sandbox.base_changeset_ref()

        best_of(
            sandbox=sandbox,
            contract=loads(CONTRACT),
            sample=lambda _index: DRAW,
            gate=lambda _space: GateResult(),
            n=2,
        )

        head = subprocess.run(
            ["git", "-C", str(sandbox.workspace), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert head == base, (
            f"best_of left HEAD at the snapshot ({head}), not the base ({base})"
        )
        assert (sandbox.workspace / "notes.txt").read_text(encoding="utf-8") == (
            "caller state"
        ), "the caller's state was not left in the working tree"
