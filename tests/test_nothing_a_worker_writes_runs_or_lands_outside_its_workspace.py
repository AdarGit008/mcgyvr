"""Nothing a worker writes runs on the host or lands outside its workspace.

Three holes, one boundary.

* **The container could write the git directory host git reads.** The task
  container bind-mounts the whole workspace read-write, ``.git`` included, and
  runs as the host user. An acceptance command is arbitrary contract shell, so
  it could set ``core.fsmonitor`` or plant a hook in ``/workspace/.git``, and the
  host's next ``git add -A`` or ``git commit`` over that workspace would run it
  — on the host, outside the container. The ``.git`` directory is mounted
  read-only over the writable workspace, so the container can read its history
  and cannot change a byte of it.
* **A tracked symlink steered the worker's bytes off the tree.** The workspace
  is extracted from ``git archive``, which recreates tracked symlinks. The
  host-side write of a reply (the gate, every best-of draw), the read of the
  original handed to the reviewer, and the deterministic rename all followed
  them, so a repository tracking ``target -> ~/.bashrc`` had the model's reply
  written into the user's shell profile. Delivery already refused to write
  through a symlink; the same refusal now guards every one of those paths.
* **A target inside ``.git/`` was accepted.** ``allow: ["**"]`` permits
  ``.git/config``, so a contract could aim a worker's reply straight at the
  git directory. The loader refuses it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.consensus import best_of
from mcgyvr.contract import ContractSchemaError
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import _base_content, gate_in_sandbox, gate_workspace
from mcgyvr.gate import GateResult
from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.rename import RenameError
from mcgyvr.rename import apply as rename_apply
from mcgyvr.sandbox import Sandbox
from mcgyvr.sandbox.docker import Resources, _run_args
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

SECRET = "export PATH=/usr/bin  # the user's own profile\n"
REPLY = "RETRY = 3\n"


def _contract(target: str, allow: str = "src/**") -> str:
    return f"""
id: retry
task_type: function_implementation
task: Give the fetch helper a retry budget named RETRY.
target: {target}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
demonstration: ["sh -c 'grep -q RETRY {target}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["{allow}"]
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def _repo_tracking(root: Path, links: dict[str, Path]) -> Path:
    """A committed repository whose tree holds each ``links`` path as a symlink."""
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "fetch.py").write_text("def fetch(u):\n    return u\n")
    for name, points_at in links.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).symlink_to(points_at)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """A file that is not in any workspace: the user's shell profile, say."""
    victim = tmp_path / "home" / ".bashrc"
    victim.parent.mkdir()
    victim.write_text(SECRET)
    return victim


def _never_gated(_: Sandbox) -> GateResult:
    raise AssertionError("the draw was written and handed to the gate")


# --- the container cannot write the git directory host git reads ------------


def test_the_container_mounts_the_git_directory_read_only(tmp_path: Path) -> None:
    args = _run_args(
        name="mcgyvr-task-abc",
        image="img:latest",
        workspace=tmp_path,
        resources=Resources(),
        gateway=[],
        user="1000:1000",
        env={},
    )
    mounts = [args[i + 1] for i, flag in enumerate(args) if flag == "--volume"]

    assert f"{tmp_path}/.git:/workspace/.git:ro" in mounts, mounts
    # After the writable workspace: a later mount is laid over an earlier one,
    # so the read-only one must come second to be the one the container sees.
    assert mounts.index(f"{tmp_path}:/workspace") < mounts.index(
        f"{tmp_path}/.git:/workspace/.git:ro"
    )


# --- a tracked symlink does not steer a write off the tree -------------------


def test_the_gate_does_not_write_a_reply_through_a_tracked_symlink(
    tmp_path: Path, outside: Path
) -> None:
    repo = _repo_tracking(tmp_path / "repo", {"src/pkg/retry.py": outside})
    contract = load_contract(_contract("src/pkg/retry.py"))

    with TempDirSandbox(repo) as sandbox, pytest.raises(Exception, match="symlink"):
        gate_in_sandbox(contract, sandbox, REPLY)

    assert outside.read_text() == SECRET


def test_the_gate_does_not_write_through_a_tracked_symlinked_directory(
    tmp_path: Path, outside: Path
) -> None:
    repo = _repo_tracking(tmp_path / "repo", {"src/elsewhere": outside.parent})
    contract = load_contract(_contract("src/elsewhere/retry.py"))

    with TempDirSandbox(repo) as sandbox, pytest.raises(Exception, match="symlink"):
        gate_in_sandbox(contract, sandbox, REPLY)

    assert not (outside.parent / "retry.py").exists()


def test_a_best_of_draw_is_not_written_through_a_tracked_symlink(
    tmp_path: Path, outside: Path
) -> None:
    repo = _repo_tracking(tmp_path / "repo", {"src/pkg/retry.py": outside})
    contract = load_contract(_contract("src/pkg/retry.py"))

    with pytest.raises(Exception, match="symlink"):
        best_of(contract=contract, sample=lambda _: REPLY, gate=_never_gated, repo=repo)

    assert outside.read_text() == SECRET


def test_the_reviewer_is_not_shown_a_file_read_through_a_tracked_symlink(
    tmp_path: Path, outside: Path
) -> None:
    repo = _repo_tracking(tmp_path / "repo", {"src/pkg/retry.py": outside})
    contract = load_contract(_contract("src/pkg/retry.py"))

    with TempDirSandbox(repo) as sandbox, pytest.raises(Exception, match="symlink"):
        _base_content(sandbox, contract)


def test_a_rename_does_not_rewrite_a_file_through_a_tracked_symlink(
    tmp_path: Path,
) -> None:
    elsewhere = tmp_path / "elsewhere.py"
    held = "from pkg.fetch import fetch\n\nfetch(1)\n"
    elsewhere.write_text(held)
    workspace = _repo_tracking(tmp_path / "repo", {"src/pkg/linked.py": elsewhere})

    with pytest.raises(RenameError, match="symlink"):
        rename_apply(workspace, "fetch", "fetch_document")

    assert elsewhere.read_text() == held
    # Refused before anything was written, as RenameError promises.
    assert "fetch_document" not in (workspace / "src/pkg/fetch.py").read_text()


# --- a target inside .git is refused at load ---------------------------------


@pytest.mark.parametrize(
    "target", [".git/config", ".git/hooks/pre-commit", "sub/.git/config"]
)
def test_a_target_inside_a_git_directory_is_refused_at_load(target: str) -> None:
    with pytest.raises(ContractSchemaError, match=r"\.git"):
        load_contract(_contract(target, allow="**"))


# --- a .git anywhere below the workspace root fails the attempt --------------
#
# Host git over a tree holding a nested repository descends into it: with the
# gitlink in the index, `git add -A`, `status` and `diff` run a child git in the
# nested repo, and that child runs the nested repo's own `core.fsmonitor` and
# filter drivers. The read-only mount above protects only the top-level `.git`;
# a command can create `sub/.git` anywhere else it can write. So a `.git` entry
# below the root, directory or file, fails the attempt by name before host git
# is run over it, and reset removes it.

NESTED = "git init -q sub"
GITFILE = "mkdir -p d && echo 'gitdir: /nowhere' > d/.git"


def _base_repo(root: Path) -> Path:
    root.mkdir()
    (root / "app.py").write_text("x = 1\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.mark.parametrize(
    ("script", "entry"), [(NESTED, "sub/.git"), (GITFILE, "d/.git")]
)
def test_an_acceptance_command_that_leaves_a_git_entry_fails_the_attempt_by_name(
    tmp_path: Path, script: str, entry: str
) -> None:
    """Checked on the host after ``Sandbox.run`` returns, so one code path for
    both modes: a container's command leaves its bytes in the bind-mounted
    workspace exactly where a temp-directory command leaves them."""
    repo = _base_repo(tmp_path / "repo")
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(
            sandbox, (("sh", "-c", script), ("sh", "-c", "exit 0"))
        ).run()

    (finding,) = report.findings
    assert finding.code == "nested-git", finding
    assert entry in finding.message


def test_a_baseline_command_that_leaves_a_git_entry_is_refused_by_name(
    tmp_path: Path,
) -> None:
    repo = _base_repo(tmp_path / "repo")
    with TempDirSandbox(repo) as sandbox:
        issue = Acceptance(sandbox, (("sh", "-c", NESTED),)).precondition()

    assert issue is not None
    assert "sub/.git" in str(issue)


def test_the_gate_fails_a_workspace_holding_a_nested_git_entry(tmp_path: Path) -> None:
    repo = _repo_tracking(tmp_path / "repo", {})
    contract = load_contract(_contract("src/pkg/retry.py"))
    with TempDirSandbox(repo) as sandbox:
        subprocess.run(
            ["git", "init", "-q", str(sandbox.workspace / "src/pkg/sub")], check=True
        )
        result = gate_workspace(contract, sandbox)

    assert not result.accepted
    assert any(
        f.code == "nested-git" and "src/pkg/sub/.git" in f.message
        for f in result.findings
    ), result.findings


def test_reset_removes_a_nested_repository(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path / "repo")
    with TempDirSandbox(repo) as sandbox:
        subprocess.run(
            ["git", "init", "-q", str(sandbox.workspace / "sub")], check=True
        )
        sandbox.reset()
        assert not (sandbox.workspace / "sub").exists()


def test_restoring_a_checkpoint_removes_a_nested_repository(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path / "repo")
    with TempDirSandbox(repo) as sandbox:
        checkpoint = sandbox.checkpoint()
        subprocess.run(
            ["git", "init", "-q", str(sandbox.workspace / "sub")], check=True
        )
        sandbox.restore_to(checkpoint)
        assert not (sandbox.workspace / "sub").exists()


def test_a_checkpoint_is_refused_over_a_nested_git_entry(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path / "repo")
    with TempDirSandbox(repo) as sandbox:
        subprocess.run(
            ["git", "init", "-q", str(sandbox.workspace / "sub")], check=True
        )
        with pytest.raises(Exception, match=r"sub/\.git"):
            sandbox.checkpoint()
