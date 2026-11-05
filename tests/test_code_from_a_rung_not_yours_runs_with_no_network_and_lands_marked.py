"""Code from a rung that is not yours runs with no network, and lands marked.

A rung's `scope` bounds whose machines may serve it (`own`, `crew`,
`anyone`), and a relief rung is lent by another member's host. The code such a
rung returns is somebody else's, so:

* **the gate** runs it in a second task container with ``--network none``,
  whatever ``sandbox.network`` says, while your own rungs' code keeps the
  task's own container; the temp-directory sandbox, which runs on this host,
  declines the try before anything is sent unless the repository is listed
  under ``sandbox.lent_code_on_host``;
* **delivery** commits it with ``Mcgyvr-Source`` and ``Mcgyvr-Model``
  trailers, and under ``delivery.lent_code: branch`` (the default) onto
  ``mcgyvr/<contract id>`` (``-2``, ``-3``, … beside an earlier run's, which
  is never overwritten), never into your checkout — whatever
  ``delivery.commit`` says. ``checkout`` delivers it as your own.

Your own rungs' code is gated and delivered exactly as before.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse, whose
from mcgyvr.contract import loads
from mcgyvr.deliver import (
    MODEL_TRAILER,
    SOURCE_TRAILER,
    deliver,
    lent_trailers,
)
from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.base import confine_for
from mcgyvr.sandbox.docker import (
    CONFINED_ARGS,
    ENDPOINTS_ENV,
    DockerSandbox,
    _ExecResult,
)
from mcgyvr.sandbox.image import DockerResult
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj

# --- whose code a rung returns -----------------------------------------------


@pytest.mark.parametrize(
    ("scope", "relief", "expected"),
    [
        (None, False, "own"),
        ("own", False, "own"),
        ("crew", False, "crew"),
        ("anyone", False, "anyone"),
        (None, True, "anyone"),
        ("own", True, "anyone"),
        ("crew", True, "crew"),
        ("anyone", True, "anyone"),
    ],
)
def test_whose_code_a_rung_returns_is_its_scope_and_a_relief_rung_is_never_yours(
    scope: str | None, relief: bool, expected: str
) -> None:
    assert whose(scope, relief=relief) == expected


def test_a_unit_says_whose_code_it_returns() -> None:
    config = parse(
        "units:\n"
        "  mine:\n    address: http://localhost:1\n    model: m\n    rig: r\n"
        "  lent:\n    address: http://localhost:2\n    model: m\n    rig: r\n"
        "    scope: crew\n"
        "ladder: [mine, lent]\n"
    )
    assert config.units["mine"].whose == "own"
    assert config.units["lent"].whose == "crew"


# --- the gate: where each rung's code runs -----------------------------------


class _Daemon:
    """A docker that answers every call and records it."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.argvs.append(list(args))
        return DockerResult(0, "container-id", "")

    def started(self) -> list[list[str]]:
        return [argv for argv in self.argvs if argv[:1] == ["run"]]

    def removed(self) -> set[str]:
        return {argv[-1] for argv in self.argvs if argv[:1] == ["rm"]}

    def restarted(self) -> list[str]:
        return [argv[-1] for argv in self.argvs if argv[:1] == ["restart"]]


def _name(run: list[str]) -> str:
    return run[run.index("--name") + 1]


def _network(run: list[str]) -> str:
    return run[run.index("--network") + 1] if "--network" in run else "bridge"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return lj.make_repo(tmp_path / "repo")


@pytest.fixture
def execs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The container each command was executed in, in order."""
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    names: list[str] = []

    def exec_in(args: Sequence[str], timeout: float | None) -> _ExecResult:
        # `exec --workdir W [--env K=V ...] NAME true`: the name is the one
        # before the command, which is `true` throughout this file.
        names.append(args[-2])
        return _ExecResult(0, "", "", False)

    monkeypatch.setattr(docker_module, "_docker_exec", exec_in)
    return names


def _docker(repo: Path, daemon: _Daemon, network: str = "bridge") -> DockerSandbox:
    return DockerSandbox(
        repo,
        image="img:latest",
        endpoints=["http://localhost:11434"],
        runner=daemon,
        system="Linux",
        network=network,
    )


@pytest.mark.parametrize("from_whom", ["crew", "anyone"])
def test_docker_runs_code_not_yours_in_a_second_container_with_no_network(
    repo: Path, execs: list[str], from_whom: str
) -> None:
    daemon = _Daemon()
    with _docker(repo, daemon) as sandbox:
        assert confine_for(sandbox, "lent", from_whom) is None
        sandbox.run(["true"])
    own, confined = daemon.started()
    assert _network(own) == "bridge"
    assert _network(confined) == "none"
    assert not any(token.startswith(ENDPOINTS_ENV) for token in confined)
    # Hardened as the engine a host serves strangers from is, /tmp in memory.
    for flag in ("--cap-drop", "--security-opt", "--read-only", "--tmpfs"):
        assert flag in confined and flag not in own, flag
    assert " ".join(CONFINED_ARGS) in " ".join(confined)
    assert execs == [_name(confined)], "the lent code ran in the task's container"
    assert daemon.removed() == {_name(own), _name(confined)}


def test_docker_runs_your_own_rungs_code_in_the_tasks_container_as_before(
    repo: Path, execs: list[str]
) -> None:
    daemon = _Daemon()
    with _docker(repo, daemon) as sandbox:
        assert confine_for(sandbox, "mine", "own") is None
        sandbox.run(["true"])
    (own,) = daemon.started()
    assert _network(own) == "bridge"
    assert execs == [_name(own)]


def test_switching_between_rungs_is_a_choice_of_container_never_a_new_one(
    repo: Path, execs: list[str]
) -> None:
    """Under fan-out the climb goes own → lent → own → lent: the container with
    no network is started once, given a restart (not a new container) before
    the second lent try, and the task's own never runs lent code."""
    daemon = _Daemon()
    with _docker(repo, daemon) as sandbox:
        for from_whom in ("own", "anyone", "own", "crew"):
            confine_for(sandbox, "rung", from_whom)
            sandbox.run(["true"])
    own, confined = daemon.started()
    assert execs == [_name(own), _name(confined), _name(own), _name(confined)]
    assert daemon.restarted() == [_name(confined)]


def test_each_lent_try_after_the_first_gets_the_container_started_again(
    repo: Path, execs: list[str]
) -> None:
    """What one host's code leaves in /tmp or running is gone before the next
    lent try — the same rung too, since a hub may serve it from another host.
    Your own tries never restart anything."""
    daemon = _Daemon()
    with _docker(repo, daemon) as sandbox:
        for from_whom in ("anyone", "anyone", "own", "own", "crew"):
            confine_for(sandbox, "rung", from_whom)
            sandbox.run(["true"])
    _own, confined = daemon.started()
    assert daemon.restarted() == [_name(confined)] * 2


def test_a_task_with_no_network_still_keeps_lent_code_out_of_its_own_container(
    repo: Path, execs: list[str]
) -> None:
    daemon = _Daemon()
    with _docker(repo, daemon, network="none") as sandbox:
        for from_whom in ("own", "anyone"):
            confine_for(sandbox, "rung", from_whom)
            sandbox.run(["true"])
    own, confined = daemon.started()
    assert _network(own) == _network(confined) == "none"
    assert "--tmpfs" in confined and "--tmpfs" not in own
    assert execs == [_name(own), _name(confined)]


class _NoRestart(_Daemon):
    """A docker that cannot restart a container."""

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.argvs.append(list(args))
        if args[:1] == ["restart"]:
            return DockerResult(1, "", "restart failed")
        return DockerResult(0, "container-id", "")


def test_a_container_that_will_not_restart_passes_later_lent_rungs_over(
    repo: Path, execs: list[str]
) -> None:
    daemon = _NoRestart()
    with _docker(repo, daemon) as sandbox:
        assert confine_for(sandbox, "lent", "anyone") is None
        sandbox.run(["true"])
        refused = confine_for(sandbox, "lent", "anyone")
        assert refused is not None and "restart failed" in refused, refused
        # A stray command is not sent to the container that did not restart.
        sandbox.run(["true"])
        assert confine_for(sandbox, "mine", "own") is None
        sandbox.run(["true"])
    own, confined = daemon.started()
    assert execs == [_name(confined), _name(own), _name(own)]


class _NoNoneNetwork(_Daemon):
    """A docker that cannot start a container with no network."""

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.argvs.append(list(args))
        if args[:1] == ["run"] and "none" in args:
            return DockerResult(1, "", "network none is not available")
        return DockerResult(0, "container-id", "")


def test_a_container_with_no_network_that_does_not_start_passes_the_rung_over(
    repo: Path, execs: list[str]
) -> None:
    daemon = _NoNoneNetwork()
    with _docker(repo, daemon) as sandbox:
        refused = confine_for(sandbox, "lent", "anyone")
        assert refused is not None and "it is not sent" in refused, refused
        assert "network none is not available" in refused
        # Your own rungs go on in the task's own container.
        assert confine_for(sandbox, "mine", "own") is None
        sandbox.run(["true"])
        # A later lent try is refused the same way, not sent to a dead name.
        again = confine_for(sandbox, "lent", "crew")
        assert again is not None and "network none is not available" in again
    # One start of each: the failed one is not tried again.
    own, confined = daemon.started()
    assert execs == [_name(own)]
    assert daemon.removed() == {_name(own), _name(confined)}


@pytest.mark.parametrize("from_whom", ["crew", "anyone"])
def test_the_tempdir_sandbox_refuses_code_not_yours_and_names_the_key(
    repo: Path, from_whom: str
) -> None:
    with TempDirSandbox(repo) as sandbox:
        refused = confine_for(sandbox, "lent", from_whom)
    assert refused is not None
    assert "it is not sent" in refused
    assert "`sandbox.lent_code_on_host`" in refused
    assert "`sandbox.mode: docker`" in refused
    assert f"`scope: {from_whom}`" in refused


def test_the_tempdir_sandbox_runs_your_own_code_and_listed_lent_code(
    repo: Path,
) -> None:
    with TempDirSandbox(repo) as sandbox:
        assert confine_for(sandbox, "mine", "own") is None
        assert confine_for(sandbox, "lent", "anyone", on_host=True) is None


# --- a whole run: the gate's policy and delivery ------------------------------

#: The harness's one unit, served from your crews' machines.
CREW_FLEET = lj.LADDER_FLEET + "    scope: crew\n"


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *flags: str,
    fleet: str = CREW_FLEET,
    policy: str = "",
    on_host: bool = True,
) -> tuple[int, Path, str, dict[str, Any], list[str]]:
    """One `direct` run in the tempdir sandbox: the exit code, the repo, its
    starting HEAD, the result and the prompts that were sent."""
    sent = lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    head = lj.git(repo, "rev-parse", "HEAD").strip()
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    (config / "fleet.yaml").write_text(fleet, encoding="utf-8")
    if on_host:
        policy += f"sandbox:\n  lent_code_on_host: [{repo}]\n"
    if policy:
        lj.append_policy(config, policy)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    code = lj.main(lj.run_args(contract, repo, config, *flags))
    result = dict(json.loads(lj.result_of(contract).read_text()))
    return code, repo, head, result, sent


def _trailers(repo: Path, ref: str) -> dict[str, str]:
    """The trailers git itself reads off `ref`'s commit message."""
    parsed = lj.git(repo, "log", "-1", "--format=%(trailers:only,unfold)", ref)
    return dict(line.split(": ", 1) for line in parsed.splitlines() if line)


def test_a_lent_rung_in_the_tempdir_sandbox_is_declined_before_it_is_sent(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, head, result, sent = _run(tmp_path, monkeypatch, on_host=False)

    assert code != 0, result
    assert sent == [], "a prompt went to a rung whose code would run on this host"
    (attempt,) = result["attempts"]
    assert attempt["verdict"] == "declined", attempt
    assert "`sandbox.lent_code_on_host`" in attempt["detail"]
    assert attempt["whose"] == "crew"
    # The halt names the remedy — the sandbox — not the ladder.
    assert result["outcome"] == "declined_throughout", result
    assert "serves code that is not yours" in result["detail"], result
    assert "`sandbox.lent_code_on_host`" in result["detail"], result
    assert "`sandbox.mode: docker`" in result["detail"], result
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head
    assert not lj.git(repo, "status", "--porcelain").strip()


def test_lent_code_lands_on_a_branch_of_its_own_marked_even_with_commit_off(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, head, result, _ = _run(tmp_path, monkeypatch)

    assert code == 0, result
    assert result["whose"] == "crew"
    assert result["committed"] is True, result
    assert result["branch"] == "mcgyvr/impl", result
    assert lj.git(repo, "rev-parse", "mcgyvr/impl").strip() == result["commit"]
    assert lj.git(repo, "rev-parse", "mcgyvr/impl~1").strip() == head
    # Your checkout is as it was: same commit, the change not in the tree.
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head
    assert "VALUE = 1" not in (repo / "src/pkg/messy.py").read_text()
    assert not lj.git(repo, "status", "--porcelain").strip()
    trailers = _trailers(repo, "mcgyvr/impl")
    assert trailers[SOURCE_TRAILER] == "crew"
    assert trailers[MODEL_TRAILER] == "qwen2.5-coder:7b"
    assert "localhost" not in lj.git(repo, "log", "-1", "--format=%B", "mcgyvr/impl")


def test_running_the_same_lent_contract_again_lands_on_a_branch_beside_it(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, head, first, _ = _run(tmp_path, monkeypatch)
    assert code == 0 and first["branch"] == "mcgyvr/impl", first
    contract = tmp_path / "impl.yaml"
    lj.scripted(monkeypatch, lj.GOOD_REPLY)

    again = lj.main(lj.run_args(contract, repo, tmp_path / "setup"))
    second = dict(json.loads(lj.result_of(contract).read_text()))

    assert again == 0, second
    assert second["committed"] is True and second["branch"] == "mcgyvr/impl-2"
    assert lj.git(repo, "rev-parse", "mcgyvr/impl").strip() == first["commit"]
    assert lj.git(repo, "rev-parse", "mcgyvr/impl-2~1").strip() == head
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head
    assert not lj.git(repo, "status", "--porcelain").strip()


def test_a_named_branch_you_have_not_checked_out_takes_lent_code(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, head, result, _ = _run(tmp_path, monkeypatch, "--branch", "review")

    assert code == 0, result
    assert result["branch"] == "review", result
    assert _trailers(repo, "review")[SOURCE_TRAILER] == "crew"
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head


def test_checkout_delivers_lent_code_as_your_own_and_still_marks_it(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, _head, result, _ = _run(
        tmp_path,
        monkeypatch,
        "--commit",
        policy="delivery:\n  lent_code: checkout\n",
    )

    assert code == 0, result
    assert result["committed"] is True and result["branch"] == "", result
    assert lj.git(repo, "rev-parse", "HEAD").strip() == result["commit"]
    assert _trailers(repo, "HEAD")[SOURCE_TRAILER] == "crew"


def test_checkout_with_commit_off_leaves_lent_code_in_the_tree_and_says_whose(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, _head, result, _ = _run(
        tmp_path, monkeypatch, policy="delivery:\n  lent_code: checkout\n"
    )

    assert code == 0, result
    assert result["committed"] is False, result
    assert "VALUE = 1" in (repo / "src/pkg/messy.py").read_text()
    assert any("your crews' machines" in note for note in result["notes"]), result


def test_your_own_rungs_change_is_delivered_and_committed_as_before(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, _head, result, _ = _run(
        tmp_path, monkeypatch, "--commit", fleet=lj.LADDER_FLEET, on_host=False
    )

    assert code == 0, result
    assert result["whose"] == "own"
    assert result["committed"] is True and result["branch"] == "", result
    assert lj.git(repo, "rev-parse", "HEAD").strip() == result["commit"]
    trailers = _trailers(repo, "HEAD")
    assert SOURCE_TRAILER not in trailers and MODEL_TRAILER not in trailers
    assert lj.git(repo, "branch", "--list", "mcgyvr/*").strip() == ""


# --- delivery's own edges -----------------------------------------------------

CONTRACT = """
id: fetch-retry
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions: ["The retry policy is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""


@pytest.fixture
def work(tmp_path: Path) -> Path:
    where = tmp_path / "work"
    (where / "src/pkg").mkdir(parents=True)
    (where / "src/pkg/fetch.py").write_text("def fetch(u):\n    return u\n")
    lj.git(tmp_path, "init", "-q", "-b", "main", str(where))
    lj.git(where, "add", "-A")
    lj.git(where, "commit", "-qm", "base")
    return where


def _checkout(repo: Path) -> dict[str, tuple[bytes, int]]:
    """Every file of the checkout, and the index, with its bytes and mtime."""
    held = {
        str(path.relative_to(repo)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(repo.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    }
    index = repo / ".git" / "index"
    held[".git/index"] = (index.read_bytes(), index.stat().st_mtime_ns)
    return held


def test_a_lent_change_never_touches_the_checkout_or_its_index(work: Path) -> None:
    """Not written and put back: never written. The checkout is byte-identical,
    to the mtime, though it is dirty — the target edited, a file untracked."""
    (work / "src/pkg/fetch.py").write_text("def fetch(u):\n    return u  # wip\n")
    (work / "notes.txt").write_text("mine\n")
    lj.git(work, "add", "notes.txt")
    head = lj.git(work, "rev-parse", "HEAD").strip()
    before = _checkout(work)

    result = deliver(
        repo=work,
        contract=loads(CONTRACT),
        content='def fetch(u):\n    """Retry."""\n    return u\n',
        base=head,
        trailers=lent_trailers("anyone", "m"),
        away="mcgyvr/fetch-retry",
    )

    assert result.committed, result
    assert result.branch == "mcgyvr/fetch-retry"
    assert _checkout(work) == before, "delivery touched the checkout"
    assert lj.git(work, "rev-parse", "HEAD").strip() == head
    assert '"""Retry."""' in lj.git(work, "show", "mcgyvr/fetch-retry:src/pkg/fetch.py")
    assert lj.git(work, "rev-parse", "mcgyvr/fetch-retry~1").strip() == head
    listed = lj.git(work, "worktree", "list", "--porcelain")
    assert listed.count("worktree ") == 1, f"a worktree was left behind:\n{listed}"


def _lend(work: Path, body: str, base: str = "HEAD") -> Any:
    return deliver(
        repo=work,
        contract=loads(CONTRACT),
        content=f'def fetch(u):\n    """{body}"""\n    return u\n',
        base=base,
        trailers=lent_trailers("anyone", "m"),
        away="mcgyvr/fetch-retry",
    )


def test_the_same_contract_lent_again_lands_beside_its_earlier_branch(
    work: Path,
) -> None:
    """A rerun finds ``mcgyvr/<id>`` taken, holding a different copy of the
    target: it lands on the first free ``-2``, ``-3`` from the base it was
    judged on, and neither the earlier branch nor the checkout moves."""
    head = lj.git(work, "rev-parse", "HEAD").strip()
    first = _lend(work, "One.")
    assert first.committed and first.branch == "mcgyvr/fetch-retry", first
    before = _checkout(work)

    second = _lend(work, "Two.")
    third = _lend(work, "Three.")

    assert second.committed, second.reason
    assert (second.branch, third.branch) == (
        "mcgyvr/fetch-retry-2",
        "mcgyvr/fetch-retry-3",
    )
    assert lj.git(work, "rev-parse", "mcgyvr/fetch-retry").strip() == first.commit
    for done, body in ((second, "Two."), (third, "Three.")):
        assert lj.git(work, "rev-parse", f"{done.branch}~1").strip() == head
        shown = lj.git(work, "show", f"{done.branch}:src/pkg/fetch.py")
        assert f'"""{body}"""' in shown
        assert _trailers(work, done.branch)[SOURCE_TRAILER] == "anyone"
    assert _checkout(work) == before, "delivery touched the checkout"
    assert lj.git(work, "rev-parse", "HEAD").strip() == head


def test_a_lent_branch_you_have_checked_out_is_left_as_it_is(work: Path) -> None:
    """Reviewing the earlier lent change with it checked out: the rerun lands
    beside it, and the checkout you are reading is byte-identical."""
    _lend(work, "One.")
    lj.git(work, "checkout", "-q", "mcgyvr/fetch-retry")
    tip = lj.git(work, "rev-parse", "HEAD").strip()
    before = _checkout(work)

    result = _lend(work, "Two.")

    assert result.committed, result.reason
    assert result.branch == "mcgyvr/fetch-retry-2"
    assert lj.git(work, "rev-parse", "mcgyvr/fetch-retry").strip() == tip
    assert _checkout(work) == before
    assert not lj.git(work, "status", "--porcelain").strip()


def test_a_branch_named_like_the_lent_prefix_is_refused_with_the_way_out(
    work: Path,
) -> None:
    """A plain ``mcgyvr`` branch leaves git no ``mcgyvr/<id>``: a refusal that
    names the setting, not git's ref-lock error and a temporary path."""
    lj.git(work, "branch", "mcgyvr")
    before = _checkout(work)

    result = _lend(work, "One.")

    assert not result.committed
    assert "branch named mcgyvr" in result.reason, result.reason
    assert "`delivery.lent_code: checkout`" in result.reason
    assert "/tmp" not in result.reason and "lock" not in result.reason
    assert _checkout(work) == before


@pytest.mark.parametrize(
    ("ref", "kind"),
    [("mcgyvr/fetch-retry/old", "branch"), ("mcgyvr/fetch-retry", "tag")],
)
def test_a_branch_under_the_lent_name_or_a_tag_of_it_is_stepped_past(
    work: Path, ref: str, kind: str
) -> None:
    lj.git(work, kind, ref)
    result = _lend(work, "One.")
    assert result.committed, result.reason
    assert result.branch == "mcgyvr/fetch-retry-2"


def test_a_model_name_cannot_add_a_line_or_a_trailer_of_its_own() -> None:
    trailers = lent_trailers("anyone", "evil\nMcgyvr-Source: own\x1b[0m" + "x" * 300)
    (source, model) = trailers
    assert source == (SOURCE_TRAILER, "anyone")
    assert "\n" not in model[1] and "\x1b" not in model[1]
    assert len(model[1]) <= 100


def test_your_own_code_carries_no_trailer() -> None:
    assert lent_trailers("own", "m") == ()
