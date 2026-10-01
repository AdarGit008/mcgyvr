"""The door can put a vLLM card to sleep with its process kept, and wake it.

``serve down`` stops a card's containers, so the next ``serve up`` is a cold
start: a container start and a full model load. A vLLM unit run with sleep
mode can do better. Level 2 drops its weights and KV cache from the card and
keeps the process, and its wake route puts them back. Level 1 stays banned
(:func:`mcgyvr.serving.servelib.sleep`).

* ``serve sleep`` opens on the serving rig, as ``serve down`` does, and sleeps
  every unit at level 2. Gate 7 then expects the declared containers still
  running, because a sleep keeps them.
* A unit with no sleep route — llama.cpp, or vLLM run without its dev routes —
  is not touched. The run exits :data:`~mcgyvr.serving.gatelib.NO_SLEEP_ROUTE`
  so that its caller can fall back to ``serve down``.
* ``serve wake`` wakes each sleeping unit through vLLM's three wake calls and
  waits until it serves. It does not start a container.

Everything here is the stubbed rig of :mod:`tests.onedoor`; no machine is
reached.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file


def sleeps_asked(root: Path) -> list[str]:
    return [line for line in onedoor.ssh_log(root) if "/sleep?level=" in line]


def compose_calls(root: Path, verb: str) -> list[str]:
    return [
        line
        for line in onedoor.docker_log(root)
        if "compose" in line and f" {verb}" in line
    ]


def test_serve_sleep_sleeps_every_unit_at_level_two_and_leaves_it_running(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    stubs = onedoor.stubs_dir(root)
    onedoor.serving(stubs, UNITS, already_up=True)
    onedoor.sleep_route(stubs)

    result = onedoor.serve_door(root, "sleep", compose, suffix="rest-1")

    assert result.returncode == 0, result.stderr[-1500:]
    asked = sleeps_asked(root)
    assert len(asked) == len(UNITS), asked
    assert all("level=2" in line for line in asked), asked
    assert compose_calls(root, "down") == [], "a sleep stopped the containers"
    assert (stubs / "asleep").exists()
    listed = (stubs / "serving-names").read_text(encoding="utf-8").split()
    assert sorted(listed) == sorted(UNITS), "the containers are kept"


def test_serve_sleep_on_a_unit_with_no_sleep_route_does_nothing_and_says_so(
    tmp_path: Path,
) -> None:
    from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE

    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    stubs = onedoor.stubs_dir(root)
    onedoor.serving(stubs, UNITS, already_up=True)

    result = onedoor.serve_door(root, "sleep", compose, suffix="rest-1")

    assert result.returncode == NO_SLEEP_ROUTE, (result.stdout, result.stderr)
    assert sleeps_asked(root) == []
    assert compose_calls(root, "down") == []
    listed = (stubs / "serving-names").read_text(encoding="utf-8").split()
    assert sorted(listed) == sorted(UNITS)


def test_serve_wake_wakes_a_level_two_sleeper_through_its_wake_route(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    stubs = onedoor.stubs_dir(root)
    onedoor.serving(stubs, UNITS, already_up=True)
    onedoor.sleep_route(stubs, asleep=True)

    result = onedoor.serve_door(root, "wake", compose, suffix="rest-1")

    assert result.returncode == 0, result.stderr[-1500:]
    calls = [
        line
        for line in onedoor.ssh_log(root)
        if "/wake_up" in line or "/collective_rpc" in line
    ]
    assert calls, "no wake route was asked"
    assert "tags=weights" in calls[0], calls
    assert "collective_rpc" in calls[1], calls
    assert "tags=kv_cache" in calls[2], calls
    assert not (stubs / "asleep").exists()
    assert compose_calls(root, "up") == [], "a wake started a container"
