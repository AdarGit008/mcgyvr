"""The door's mode is said, not guessed: ``--mode user|lab``.

Owner, 2026-10-07 (Round 5): the product's callers pass ``--mode user`` and the
lab's tools pass ``--mode lab``. With no flag, a door whose run root is a
checkout holding the round's folder (:data:`mcgyvr.serving.run.LAB_MARK`)
refuses and asks which mode, because there it cannot tell a lab tool that forgot
the flag from a user; anywhere else it runs as the user's door. A campaign run
measures against the lab's round and campaigns, so it is a lab run and nothing
else.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr import wake
from mcgyvr.fleet import linkread, read
from mcgyvr.serving import run
from tests import onedoor, usermode

VERBS = {
    "serve": ["serve", "down", "--host", usermode.RIG, "--compose", "COMPOSE"],
    "read": ["read", "--host", usermode.RIG],
    "link": ["link", "--host", usermode.RIG, "--peer", "0", "1"],
    "campaign": [
        "--host",
        usermode.RIG,
        "--campaign",
        "invented",
        "--model",
        "/models/x.gguf",
        "--ctx-per-slot",
        "2048",
    ],
}


def _argv(verb: str, compose: Path, *extra: str) -> list[str]:
    return [str(compose) if word == "COMPOSE" else word for word in VERBS[verb]] + [
        *extra
    ]


@pytest.mark.parametrize("verb", sorted(VERBS))
def test_with_no_mode_in_a_lab_checkout_the_door_asks_which_and_reads_nothing(
    tmp_path: Path, verb: str
) -> None:
    stubs = usermode.machine(tmp_path, pending=())
    compose = usermode.compose_file(tmp_path)

    done = usermode.door(
        _argv(verb, compose),
        stubs=stubs,
        run_root=usermode.lab_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stderr
    assert "--mode lab" in done.stderr
    assert "--mode user" in done.stderr
    assert onedoor.ssh_log(stubs) == []
    assert onedoor.docker_log(stubs) == []


def test_with_no_mode_outside_a_lab_checkout_the_door_is_the_users(
    tmp_path: Path,
) -> None:
    """The user's door holds the rig to the user's rig file, so a rig with none
    is refused in the user's words."""
    stubs = usermode.machine(tmp_path, pending=())

    done = usermode.door(
        usermode.serve("down", usermode.compose_file(tmp_path), mode=None),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stderr
    assert f"mcgyvr scan --rig {usermode.RIG}" in done.stderr
    assert "hosts.json" not in done.stderr


@pytest.mark.parametrize("mode", [None, "user"])
def test_a_campaign_run_is_a_lab_run_and_nothing_else(
    tmp_path: Path, mode: str | None
) -> None:
    stubs = usermode.machine(tmp_path, pending=())
    extra = () if mode is None else ("--mode", mode)

    done = usermode.door(
        _argv("campaign", tmp_path, *extra),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stderr
    assert "campaign" in done.stderr
    assert "--mode lab" in done.stderr
    assert onedoor.ssh_log(stubs) == []


def test_a_mode_the_door_does_not_have_is_refused(tmp_path: Path) -> None:
    stubs = usermode.machine(tmp_path, pending=())

    done = usermode.door(
        usermode.serve("down", usermode.compose_file(tmp_path), mode="both"),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2
    assert onedoor.ssh_log(stubs) == []


def test_the_product_calls_the_door_as_the_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve = wake.door_argv(
        direction="up", host=usermode.RIG, compose=tmp_path / "c.yml", suffix="s1"
    )
    assert serve[serve.index("--mode") + 1] == "user"

    reading = read.door_read_argv(usermode.RIG, "run-20261007T000000-0a1b2c3d")
    assert reading[reading.index("--mode") + 1] == "user"

    started: list[list[str]] = []

    class StoppedError(Exception):
        pass

    def popen(argv: list[str], **_: object) -> subprocess.Popen[str]:
        started.append(list(argv))
        raise StoppedError

    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(StoppedError):
        linkread.DoorLinks().start(usermode.RIG, ["--peer", "0", "1"])
    [link] = started
    assert link[link.index("--mode") + 1] == "user"


def test_the_door_offers_both_modes_and_no_other() -> None:
    assert run.MODES == ("user", "lab")
