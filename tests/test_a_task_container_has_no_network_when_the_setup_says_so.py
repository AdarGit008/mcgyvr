"""A task container has no network when the setup says so.

A task container on Docker's default network can reach whatever the machine
running it can: the internet, the local network, the host's own services
through the gateway alias. Acceptance commands are arbitrary shell, so that is
reach handed to a contract. Taking it away is a trade, not a fix — a contract
whose commands fetch dependencies, or talk to a worker endpoint, stops working
— so it is a setting, ``sandbox.network``:

* ``bridge`` (the default) is Docker's default network, as before;
* ``none`` runs the container with no network at all, and with no route to the
  host to advertise.

The temp-directory sandbox runs commands on the host, where mcgyvr cannot take
the network away, so ``none`` is refused there rather than claimed and not
kept — whether ``tempdir`` was chosen by name or reached by the fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import ConfigSchemaError
from mcgyvr.config import load as load_config
from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.base import SandboxError, open_sandbox
from mcgyvr.sandbox.docker import HOST_ALIAS, DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import DockerResult
from tests import livejournal as lj


class _Daemon:
    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.argvs.append(list(args))
        return DockerResult(0, "container-id", "")

    def run_argv(self) -> list[str]:
        (run,) = [argv for argv in self.argvs if argv[:1] == ["run"]]
        return run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return lj.make_repo(tmp_path / "repo")


@pytest.fixture(autouse=True)
def _no_daemon_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(
        docker_module, "_docker_exec", lambda a, t: _ExecResult(0, "", "", False)
    )


def _started(repo: Path, **kwargs: object) -> list[str]:
    daemon = _Daemon()
    with DockerSandbox(
        repo,
        image="img:latest",
        endpoints=["http://localhost:11434"],
        runner=daemon,
        system="Linux",
        **kwargs,  # type: ignore[arg-type]
    ):
        pass
    return daemon.run_argv()


def test_by_default_the_container_is_on_dockers_default_network(repo: Path) -> None:
    run = _started(repo)
    assert "--network" not in run
    assert f"{HOST_ALIAS}:host-gateway" in run


def test_with_network_none_the_container_has_no_network(repo: Path) -> None:
    run = _started(repo, network="none")
    assert run[run.index("--network") + 1] == "none"
    # Nothing to route to, so no route to the host is mapped or advertised.
    assert "--add-host" not in run
    assert not any(token.startswith("MCGYVR_ENDPOINTS=") for token in run)


def test_the_factory_hands_the_setting_to_the_container(repo: Path) -> None:
    sandbox = open_sandbox(
        repo, mode="docker", docker_available=True, image="img:latest", network="none"
    )
    assert isinstance(sandbox, DockerSandbox)
    daemon = _Daemon()
    sandbox._runner = daemon
    with sandbox:
        pass
    run = daemon.run_argv()
    assert run[run.index("--network") + 1] == "none"


def test_an_unknown_network_is_refused_by_name(repo: Path) -> None:
    with pytest.raises(SandboxError, match="host"):
        _started(repo, network="host")


def test_tempdir_by_name_refuses_network_none(repo: Path) -> None:
    with pytest.raises(SandboxError, match=r"sandbox\.network"):
        open_sandbox(repo, mode="tempdir", docker_available=True, network="none")


def test_the_fallback_refuses_network_none(repo: Path) -> None:
    with pytest.raises(SandboxError, match=r"sandbox\.network"):
        open_sandbox(
            repo,
            mode="docker",
            docker_available=False,
            allow_fallback=True,
            network="none",
        )


def test_the_setting_defaults_to_bridge_and_takes_none(tmp_path: Path) -> None:
    config = lj.make_config(tmp_path / "setup")
    assert load_config(config).get("sandbox.network") == "bridge"
    lj.append_policy(config, "sandbox:\n  network: none\n")
    assert load_config(config).get("sandbox.network") == "none"


def test_the_setting_refuses_a_network_it_does_not_offer(tmp_path: Path) -> None:
    config = lj.make_config(tmp_path / "setup")
    lj.append_policy(config, "sandbox:\n  network: host\n")
    with pytest.raises(ConfigSchemaError, match="network"):
        load_config(config)


def test_a_run_reads_the_setting_from_its_setup(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No daemon, the fallback allowed, and no network asked for: refused."""
    monkeypatch.setattr(detect, "detect_docker", lambda: (False, "no daemon"))
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    lj.append_policy(config, "sandbox:\n  allow_fallback: true\n  network: none\n")
    contract = lj.make_contract(
        tmp_path / "tidy.yaml",
        "id: tidy\ntask_type: format\ntask: Reformat the module.\n"
        'target: src/pkg/messy.py\nscope:\n  allow: ["src/**"]\n',
    )

    code = lj.main(["run", str(contract), "--repo", str(repo), "--config", str(config)])
    out = capsys.readouterr()

    assert code != 0
    assert "sandbox.network" in out.out + out.err
