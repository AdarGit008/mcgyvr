"""Setup writes `launcher: native` for a llama.cpp unit on this Mac or Windows machine.

A container reaches no GPU there, so the unit setup writes for a backend on
this machine runs the pinned native build; a Linux machine, a rig across ssh
and a vLLM unit keep the container, which is what a unit stating no launcher
runs as. `recommend`'s placement says the same, from the same rule.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import default_launcher
from tests.hostos_fakes import as_system


@pytest.mark.parametrize(
    ("local", "engine", "system", "expected"),
    [
        (True, None, "darwin", "native"),
        (True, "llama.cpp", "windows", "native"),
        (True, None, "linux", "docker"),
        (False, None, "darwin", "docker"),
        (True, "vllm", "windows", "docker"),
    ],
)
def test_the_launcher_setup_writes(
    local: bool, engine: str | None, system: str, expected: str
) -> None:
    assert default_launcher(local=local, engine=engine, system=system) == expected


def _unit_written(host: str, kind: str = "llama-server") -> dict[str, object]:
    from mcgyvr.detect import Backend, Detection
    from mcgyvr.initialize import _sources_for, build
    from mcgyvr.propose import propose

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
    as_system(monkeypatch, "linux")
    assert "launcher" not in _unit_written("localhost")
    as_system(monkeypatch, "darwin")
    assert "launcher" not in _unit_written("box1")
