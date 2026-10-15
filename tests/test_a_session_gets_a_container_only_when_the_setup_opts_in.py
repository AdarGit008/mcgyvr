"""A `chat` or `agent` run gets a container only when the setup opts in (R10).

E2e run 2, R10: a `chat` run built the docker sandbox image before replying —
114.9 s for a 3.4 s reply — though a session has no target and runs no
command. Owner decision: "docker for chat/agent is opt-in at setup time;
default for code/media". So:

- a session that declares no command is staged in a throwaway checkout on this
  host by default (`sandbox.sessions: tempdir`): no daemon is probed and no
  image is built, pulled or started, so Docker need not be installed, and
  `sandbox.network: none` (about commands) does not refuse it;
- the checkout holds the repository at HEAD, so what an `agent` reads off the
  workspace is there without a container;
- `sandbox.sessions: docker`, or `--sandbox docker` for one run, gives it a
  task container;
- a session that declares a command, and every `code` run, is sandboxed by
  `sandbox.mode` exactly as before — `docker` unless the setup says otherwise;
- `mcgyvr setup --session-sandbox` writes `sandbox.sessions`.

Runs go through ``mcgyvr.cli.main`` with ``drive.dispatch`` scripted, as
``tests/test_a_chat_or_agent_run_is_a_session_kept_in_the_journal.py`` does.
The Docker layer is a spy: a container asked for is recorded and refused, so
nothing here needs or touches a daemon.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import POLICY_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.detect import PORT_CONVENTIONS
from mcgyvr.initialize import InitError, initialize
from mcgyvr.sandbox.base import SandboxError
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests.machine_shapes import detection, shape, with_server

CHAT = """\
id: sky
task_type: chat
task: Why is the sky blue?
"""

AGENT = """\
id: brief
task_type: agent
task: Summarise the report.
sources: ["src/report.txt"]
"""

CODE = """\
id: setv
task_type: code
task: Set VALUE to 2.
target: src/value.py
stop_conditions: ["VALUE is not defined."]
scope:
  allow: ["src/value.py"]
limits:
  max_output_tokens: 512
"""

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

#: What the spy says when a container is asked for, so a test can tell the
#: spy's refusal from any other.
ASKED = "stub: a task container was asked for"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "report.txt").write_text("The sky is blue.\n", encoding="utf-8")
    (root / "src" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _config(tmp_path: Path, sandbox: str = "") -> Path:
    """A one-rung dev setup; ``sandbox`` is the block's body, if any."""
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(
        "units:\n"
        "  local_qwen-7b:\n"
        "    address: http://localhost:11434\n"
        "    model: qwen2.5-coder:7b\n"
        "    rig: workstation\n"
        "    width: 2\n"
        "ladder:\n"
        "- local_qwen-7b\n"
        "journal:\n"
        f"  dir: {tmp_path / 'journal'}\n"
        + (f"sandbox:\n{sandbox}" if sandbox else ""),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Spy on the Docker layer: every probe and container asked for is kept.

    A container asked for is refused with :data:`ASKED`, so a run that wanted
    one ends there, before any image is built.
    """
    import mcgyvr.detect as detect
    import mcgyvr.sandbox.docker as sandbox_docker
    import mcgyvr.sandbox.image as image

    seen: dict[str, list[Any]] = {"probes": [], "containers": []}

    def probe() -> tuple[bool, str]:
        seen["probes"].append(True)
        return True, "stub daemon"

    class Container:
        def __init__(self, source: Any, **kwargs: Any) -> None:
            seen["containers"].append(kwargs)
            raise SandboxError(ASKED)

    monkeypatch.setattr(detect, "detect_docker", probe)
    monkeypatch.setattr(image, "foreign_daemon", lambda: None)
    monkeypatch.setattr(sandbox_docker, "DockerSandbox", Container)
    return seen


def _scripted(monkeypatch: pytest.MonkeyPatch, *replies: str) -> None:
    import mcgyvr.drive as drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    queue = list(replies)

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Completion:
        if not queue:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        return Completion(
            text=queue.pop(0),
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)


def _run(
    tmp_path: Path,
    document: str,
    repo: Path,
    config: Path,
    capsys: pytest.CaptureFixture[str],
    *flags: str,
) -> tuple[int, dict[str, Any], str]:
    from mcgyvr.cli import main

    contract = tmp_path / "contract.yaml"
    contract.write_text(document, encoding="utf-8")
    argv: Sequence[str] = [
        "run",
        str(contract),
        "--repo",
        str(repo),
        "--config",
        str(config),
        "--orchestrator",
        "t",
        *flags,
    ]
    try:
        code = main(list(argv))
    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 2
    printed = capsys.readouterr()
    last = printed.out.strip().splitlines()[-1]
    assert last.startswith("result: "), printed.out + printed.err
    result = json.loads(Path(last.removeprefix("result: ")).read_text("utf-8"))
    return code, result, printed.out + printed.err


# --- a session by default ---------------------------------------------------


def test_a_chat_run_by_default_builds_pulls_and_starts_no_container(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch, "Rayleigh scattering.")

    code, result, said = _run(tmp_path, CHAT, repo, _config(tmp_path), capsys)

    assert code == 0, said
    assert result["outcome"] == "accepted", said
    assert result["answer"] == "Rayleigh scattering."
    # Not asked for, and not even probed for: Docker need not be installed.
    assert docker["containers"] == []
    assert docker["probes"] == []
    assert "no container is built or started" in said, said
    # The weaker-mode note is about commands, and none runs.
    assert "explicitly weaker mode" not in said, said


def test_an_agent_run_by_default_reads_the_repository_off_a_host_checkout(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.drive as drive
    from mcgyvr.gate import output as gate_output

    # `agent` declares safety_pass, which shells out to a classifier this
    # machine does not have; it is not what is under test here.
    monkeypatch.setattr(gate_output, "safety_pass", lambda path, label="": [])
    _scripted(monkeypatch, "The sky is blue [1].")
    seen: list[tuple[type, str]] = []
    judge = drive.gate_prose_workspace

    def spy(contract: Any, sandbox: Any) -> Any:
        source = Path(sandbox.workspace) / "src" / "report.txt"
        seen.append((type(sandbox), source.read_text(encoding="utf-8")))
        return judge(contract, sandbox)

    monkeypatch.setattr(drive, "gate_prose_workspace", spy)

    code, result, said = _run(tmp_path, AGENT, repo, _config(tmp_path), capsys)

    assert code == 0, said
    assert result["outcome"] == "accepted", said
    assert docker["containers"] == [] and docker["probes"] == []
    assert seen == [(TempDirSandbox, "The sky is blue.\n")]


def test_a_session_staged_on_the_host_is_not_refused_for_a_network_it_never_uses(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch, "Rayleigh scattering.")
    config = _config(tmp_path, "  network: none\n")

    code, result, said = _run(tmp_path, CHAT, repo, config, capsys)

    assert code == 0, said
    assert result["outcome"] == "accepted", said
    assert docker["containers"] == []


# --- a container for a session ----------------------------------------------


def test_a_chat_run_gets_a_container_when_the_setup_opts_in(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch)
    config = _config(tmp_path, "  sessions: docker\n  network: none\n")

    code, result, said = _run(tmp_path, CHAT, repo, config, capsys)

    assert code == 1
    assert result["detail"] == ASKED, said
    # The rest of the block applies to the session's container as to any.
    assert [c["network"] for c in docker["containers"]] == ["none"]


def test_a_typed_sandbox_flag_gives_a_session_a_container_for_one_run(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch)

    code, result, said = _run(
        tmp_path, CHAT, repo, _config(tmp_path), capsys, "--sandbox", "docker"
    )

    assert code == 1
    assert result["detail"] == ASKED, said
    assert len(docker["containers"]) == 1


def test_a_session_that_declares_a_command_is_sandboxed_by_mode(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A command is arbitrary shell from a contract, session or not."""
    _scripted(monkeypatch)
    document = CHAT + 'acceptance: ["git status"]\n'

    code, result, said = _run(tmp_path, document, repo, _config(tmp_path), capsys)

    assert code == 1
    assert result["detail"] == ASKED, said
    assert len(docker["containers"]) == 1


# --- code is unchanged ------------------------------------------------------


def test_a_code_run_still_gets_a_container_by_default(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch)

    code, result, said = _run(tmp_path, CODE, repo, _config(tmp_path), capsys)

    assert code == 1
    assert result["detail"] == ASKED, said
    assert len(docker["containers"]) == 1


def test_sessions_tempdir_leaves_a_code_run_in_its_container(
    tmp_path: Path,
    repo: Path,
    docker: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch)
    config = _config(tmp_path, "  mode: docker\n  sessions: tempdir\n")

    code, result, said = _run(tmp_path, CODE, repo, config, capsys)

    assert code == 1
    assert result["detail"] == ASKED, said


# --- setup writes the choice ------------------------------------------------

RIG = with_server(
    shape("one-card"), kind=PORT_CONVENTIONS[0][0], models=("example-model-small",)
)


def _sessions(path: Path) -> str:
    return str(load_config(path).get("sandbox.sessions"))


def test_setup_writes_sessions_tempdir_by_default(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=dataclasses.replace(detection(RIG), docker=True))

    assert _sessions(path) == "tempdir"
    assert "sessions: tempdir" in (path / POLICY_FILENAME).read_text("utf-8")


def test_setup_session_sandbox_docker_writes_the_opt_in(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(
        path,
        detection=dataclasses.replace(detection(RIG), docker=True),
        session_sandbox="docker",
    )

    assert _sessions(path) == "docker"
    # Asked for with a daemon here: nothing to warn about.
    assert "No Docker daemon answered" not in (path / POLICY_FILENAME).read_text(
        "utf-8"
    )


def test_setup_says_beside_the_opt_in_when_no_daemon_answered(tmp_path: Path) -> None:
    path = tmp_path / "setup"
    initialize(path, detection=detection(RIG), session_sandbox="docker")

    policy = (path / POLICY_FILENAME).read_text("utf-8")
    assert _sessions(path) == "docker"
    assert "a chat or agent run is" in " ".join(policy.split()), policy


def test_the_setup_flag_reaches_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.cli as cli

    asked: dict[str, Any] = {}

    def fake_initialize(path: Path, **kwargs: Any) -> Any:
        asked.update(kwargs)
        raise InitError("stub: nothing is written")

    monkeypatch.setattr(cli.commands.setup, "initialize", fake_initialize)

    code = cli.main(["setup", str(tmp_path / "setup"), "--session-sandbox", "docker"])

    assert code == 1
    assert asked["session_sandbox"] == "docker"
