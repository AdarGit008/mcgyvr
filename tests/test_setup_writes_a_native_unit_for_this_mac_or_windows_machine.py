"""Setup writes `launcher: native` for a llama.cpp unit on a Mac or Windows machine.

A container reaches no GPU there, so the unit setup writes for a backend on
this machine, or on a rig whose rig file records macOS or Windows, runs the
pinned native build; a Linux machine, a rig across ssh with no such record and
a vLLM unit keep the container, which is what a unit stating no launcher runs
as. `recommend`'s placement says the same, from the same rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import config as configlib
from mcgyvr.config import default_launcher
from tests.hostos_fakes import as_system
from tests.remote_rigs import record_rig


@pytest.mark.parametrize(
    ("engine", "system", "has_docker", "expected"),
    [
        (None, "darwin", True, "native"),
        ("llama.cpp", "windows", True, "native"),
        (None, "linux", True, "docker"),
        ("vllm", "windows", True, "docker"),
        (None, "linux", False, "native"),
        ("llama.cpp", "linux", False, "native"),
        ("vllm", "linux", False, "docker"),
    ],
)
def test_the_launcher_setup_writes(
    engine: str | None, system: str, has_docker: bool, expected: str
) -> None:
    assert (
        default_launcher(engine=engine, system=system, has_docker=has_docker)
        == expected
    )


def _unit_written(host: str, kind: str = "llama-server") -> dict[str, object]:
    from mcgyvr.detect import Backend, Detection
    from mcgyvr.initialize import _sources_for, build
    from mcgyvr.ladder_proposal import propose

    detection = Detection(
        backends=(
            Backend(
                name=kind,
                base_url=f"http://{host}:8080",
                api="openai",
                models=("small-coder",),
                how="substituted",
                host=host,
                kind=kind,
                window=8192,
            ),
        ),
        provenance={"backends": "substituted"},
    )
    data = build(detection, propose(sources=_sources_for(detection)))
    (unit,) = data["units"].values()
    return dict(unit)


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_a_unit_on_this_mac_or_windows_machine_is_written_native(
    monkeypatch: pytest.MonkeyPatch, system: str
) -> None:
    as_system(monkeypatch, system)
    assert _unit_written("localhost")["launcher"] == "native"


def test_a_unit_on_linux_or_across_ssh_is_written_with_no_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(configlib, "docker_on_path", lambda: True)
    as_system(monkeypatch, "linux")
    assert "launcher" not in _unit_written("localhost")
    as_system(monkeypatch, "darwin")
    assert "launcher" not in _unit_written("box1")


@pytest.mark.parametrize("label", ["unified-laptop", "windows-one-card"])
def test_a_unit_on_a_rig_recorded_as_mac_or_windows_is_written_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, label: str
) -> None:
    as_system(monkeypatch, "linux")
    record_rig(monkeypatch, tmp_path, "box1", label)
    assert _unit_written("box1")["launcher"] == "native"


def test_a_unit_on_a_rig_recorded_as_linux_keeps_its_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(configlib, "docker_on_path", lambda: True)
    as_system(monkeypatch, "darwin")
    record_rig(monkeypatch, tmp_path, "box1", "linux-one-card")
    assert "launcher" not in _unit_written("box1")


def test_a_unit_on_this_linux_machine_with_no_docker_is_written_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(configlib, "docker_on_path", lambda: False)
    as_system(monkeypatch, "linux")
    assert _unit_written("localhost")["launcher"] == "native"
