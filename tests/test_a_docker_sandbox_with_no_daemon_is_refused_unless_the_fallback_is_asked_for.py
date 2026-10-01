"""A docker sandbox with no daemon is refused, unless the fallback was asked for.

``sandbox.mode: docker`` is a request for a container. When no daemon answers,
running the task in the temp-directory sandbox instead puts a contract's
acceptance commands — arbitrary shell — on the host, and a note printed once
at the top of a run is not the same as having chosen that. So the task is
refused, and the refusal names both ways on:

* choose the weaker mode by name — ``sandbox.mode: tempdir``, or
  ``--sandbox tempdir`` for one run;
* or keep ``docker`` and opt into the fallback with
  ``sandbox.allow_fallback: true``, which then falls back and says so.

``tempdir`` chosen by name keeps working, with its note, daemon or not.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import ConfigSchemaError
from mcgyvr.config import load as load_config
from mcgyvr.sandbox.base import SandboxError, open_sandbox
from mcgyvr.sandbox.docker import DockerSandbox
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the floor under test is a real ruff; there is nothing to fake here",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return lj.make_repo(tmp_path / "repo")


@pytest.fixture
def no_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    """No docker daemon answers, and nothing points the CLI at another one."""
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(
        detect, "detect_docker", lambda: (False, "no daemon answered the probe")
    )


def _says_both_ways_on(message: str) -> None:
    assert "sandbox.mode: tempdir" in message
    assert "--sandbox tempdir" in message
    assert "sandbox.allow_fallback: true" in message


# --- the factory ------------------------------------------------------------


def test_docker_with_no_daemon_is_refused_and_names_both_ways_on(repo: Path) -> None:
    with pytest.raises(SandboxError) as refused:
        open_sandbox(repo, mode="docker", docker_available=False)
    _says_both_ways_on(str(refused.value))


def test_docker_with_no_daemon_falls_back_when_asked_to_and_says_so(
    repo: Path,
) -> None:
    sandbox = open_sandbox(
        repo, mode="docker", docker_available=False, allow_fallback=True
    )
    assert isinstance(sandbox, TempDirSandbox)
    assert any("no daemon answered" in note for note in sandbox.notes)
    assert any("weaker" in note for note in sandbox.notes)


def test_docker_with_a_daemon_is_a_container_whether_or_not_fallback_is_on(
    repo: Path,
) -> None:
    for allow in (False, True):
        sandbox = open_sandbox(
            repo,
            mode="docker",
            docker_available=True,
            allow_fallback=allow,
            image="img:latest",
        )
        assert isinstance(sandbox, DockerSandbox)
        assert sandbox.notes == ()


def test_tempdir_chosen_by_name_still_runs_with_its_note(repo: Path) -> None:
    for available in (False, True):
        sandbox = open_sandbox(repo, mode="tempdir", docker_available=available)
        assert isinstance(sandbox, TempDirSandbox)
        assert any("weaker" in note for note in sandbox.notes)


# --- the setting ------------------------------------------------------------


def test_the_fallback_is_off_unless_the_setup_turns_it_on(tmp_path: Path) -> None:
    config = lj.make_config(tmp_path / "setup")
    assert load_config(config).get("sandbox.allow_fallback") is False
    lj.append_policy(config, "sandbox:\n  allow_fallback: true\n")
    assert load_config(config).get("sandbox.allow_fallback") is True


def test_the_fallback_setting_takes_true_or_false_only(tmp_path: Path) -> None:
    config = lj.make_config(tmp_path / "setup")
    lj.append_policy(config, "sandbox:\n  allow_fallback: sometimes\n")
    with pytest.raises(ConfigSchemaError, match="allow_fallback"):
        load_config(config)


# --- a run ------------------------------------------------------------------


def _floor(contract: Path, repo: Path, *extra: str) -> list[str]:
    return ["run", str(contract), "--repo", str(repo), *extra]


@pytest.mark.usefixtures("no_daemon")
def test_a_run_with_no_daemon_is_refused_before_any_command_runs(
    repo: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    (repo / "src" / "pkg" / "messy.py").write_text("x=0\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "misformatted")

    code = lj.main(_floor(contract, repo))
    out = capsys.readouterr()

    assert code != 0
    _says_both_ways_on(out.out + out.err)
    # Refused, not run: nothing touched the tree.
    assert (repo / "src" / "pkg" / "messy.py").read_text(encoding="utf-8") == "x=0\n"


@needs_ruff
@pytest.mark.usefixtures("no_daemon")
def test_a_run_whose_setup_allows_the_fallback_runs_in_tempdir_and_says_so(
    repo: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    lj.append_policy(config, "sandbox:\n  allow_fallback: true\n")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    (repo / "src" / "pkg" / "messy.py").write_text("x=0\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "misformatted")

    code = lj.main(_floor(contract, repo, "--config", str(config)))
    out = capsys.readouterr().out

    assert code == 0, out
    assert "no daemon answered" in out
