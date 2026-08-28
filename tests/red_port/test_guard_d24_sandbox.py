"""D24 — a task's commands run somewhere they cannot reach, holding secrets they cannot
see.

GREEN by design. Everything here already works; the file exists so a port cannot
quietly replace it. The thing being ported over runs acceptance commands with
``shell=True`` **in the caller's live checkout**, hands them ``os.environ``
untouched, and treats the absence of a Docker daemon as a reason to give up on
isolation entirely. Each of those is one deletion away from being true here too,
and none of the three would fail an existing test.

So the level is chosen deliberately. ``tests/test_sandbox_tempdir.py`` already
asserts that one named credential is missing from one command's environment and
that one workspace path is gone after one ``with`` block. Those are the right
tests for the machinery. They are not enough to stop the port, because a
replacement that scrubbed a hardcoded list of well-known keys and left
``$DEPLOY_TOKEN`` standing would pass both.

What is asserted instead:

* **The whole environment, not a named variable.** The command dumps everything
  it can see and the result is put back through the project's own predicate. A
  variable that is credential-shaped but not famous is included on purpose,
  because a list-based scrub is exactly the weaker thing a port would arrive
  with, and a benign variable is asserted to survive so "scrubbed" cannot
  degrade into "empty".
* **The caller's checkout, not the workspace.** The command is destructive on
  purpose and is aimed at the file the contract targets. A sandbox that ran in
  the live tree would pass every isolation test in the suite and still eat the
  user's work, which is the failure this whole lever exists to prevent.
* **Falling back is not giving up.** Docker asked for and no daemon answering is
  the common case on a laptop and in CI. The sandbox that comes back must still
  be usable *and* still hold the hardening, and it must say out loud that it is
  weaker — a silent downgrade is how an operator ends up believing in isolation
  they do not have.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcgyvr.sandbox import open_sandbox
from mcgyvr.sandbox.base import credential_env_names

TARGET = "src/pkg/fetch.py"


def _env_seen_by(command_stdout: str) -> dict[str, str]:
    """The environment a command reported, as a mapping."""
    seen: dict[str, str] = {}
    for line in command_stdout.splitlines():
        name, sep, value = line.partition("=")
        if sep:
            seen[name] = value
    return seen


def test_a_task_command_cannot_see_a_credential_shaped_variable(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command's whole environment is credential-free, not just the famous names.

    ``ANTHROPIC_API_KEY`` is on the project's known list; ``DEPLOY_TOKEN`` and
    ``DB_PASSWORD`` are not, and are caught by shape alone. A port that swapped
    the shape rule for a list would keep the first and leak the other two, so
    the assertion is made against the project's own predicate over everything
    the command could see rather than against three names it happened to check.

    The benign variable is the other half: an environment scrubbed by emptying it
    is not isolation, it is a sandbox nothing can run in.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-known-list-value")
    monkeypatch.setenv("DEPLOY_TOKEN", "shape-matched-not-listed")
    monkeypatch.setenv("DB_PASSWORD", "shape-matched-not-listed")
    monkeypatch.setenv("MCGYVR_GUARD_BENIGN", "carried")

    with open_sandbox(repo, mode="tempdir") as sandbox:
        result = sandbox.run(["env"], timeout=30)

    assert result.ok, f"could not read the environment back: {result.stderr}"
    seen = _env_seen_by(result.stdout)
    assert credential_env_names(seen) == frozenset(), (
        f"credential-shaped variables reached the command: "
        f"{sorted(credential_env_names(seen))}"
    )
    assert "shape-matched-not-listed" not in result.stdout, (
        "a value leaked by another name"
    )
    assert seen.get("MCGYVR_GUARD_BENIGN") == "carried", (
        "the environment was emptied, not scrubbed"
    )


def test_a_destructive_command_cannot_reach_the_callers_checkout(repo: Path) -> None:
    """Commands run on a copy, so the worst a contract's command can do is local.

    The command overwrites the contract's target, deletes a tracked sibling and
    drops a marker at the top of the tree — the three things a careless
    acceptance script does by accident. Afterwards the caller's checkout must be
    byte-identical and its git status clean, and the workspace must be gone.

    Asserted on the *source* rather than on the workspace, because a sandbox that
    had quietly run in the live tree would satisfy every isolation assertion in
    the suite and still be the failure this lever exists to prevent.
    """
    (repo / "src" / "pkg" / "keep.py").write_text("KEEP = 1\n")
    before = (repo / TARGET).read_text()

    with open_sandbox(repo, mode="tempdir") as sandbox:
        workspace = sandbox.workspace
        result = sandbox.run(
            [
                "sh",
                "-c",
                f"echo tampered > {TARGET} && rm -f src/pkg/keep.py && touch MARKER",
            ],
            timeout=30,
        )
        assert result.ok, f"the command did not run: {result.stderr}"
        assert (workspace / "MARKER").exists(), "the command ran nowhere at all"

    assert (repo / TARGET).read_text() == before, "the caller's target was rewritten"
    assert (repo / "src" / "pkg" / "keep.py").exists(), "the caller's file was deleted"
    assert not (repo / "MARKER").exists(), "the command wrote into the caller's tree"
    assert not workspace.exists(), f"the workspace survived at {workspace}"


def test_docker_with_no_daemon_still_yields_a_working_sandbox_that_says_it_is_weaker(
    repo: Path,
) -> None:
    """No daemon is a degrade, not a failure — and never a silent one.

    Three things at once, because a port could drop any one of them and leave the
    other two looking right:

    * it still runs, so a laptop with no Docker is a supported machine rather
      than a stuck one;
    * it still strips credentials, so the fallback is weaker in isolation and not
      in hardening — this is the clause a rewrite is most likely to lose, since
      the strong path is the one anyone tests;
    * it says which mode it is in, in words an operator reads, so believing in
      container isolation you do not have takes a deliberate act.
    """
    sandbox = open_sandbox(repo, mode="docker", docker_available=False)

    assert sandbox.isolation == "process", "reported container isolation with no daemon"
    note = " ".join(sandbox.notes).lower()
    assert "weaker" in note and "daemon" in note, (
        f"the downgrade was silent: {sandbox.notes}"
    )

    with sandbox as opened:
        env = opened.run(["env"], timeout=30)
        ran = opened.run(["sh", "-c", "echo alive"], timeout=30)

    assert ran.ok and ran.stdout.strip() == "alive", (
        "the fallback sandbox could not run anything"
    )
    assert credential_env_names(_env_seen_by(env.stdout)) == frozenset(), (
        "the fallback dropped the credential stripping along with the container"
    )
    assert os.environ.get("PATH"), "sanity: the host environment was not itself emptied"
