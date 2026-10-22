"""After a swap, the wake judgment is asked only of a rung that is up.

A climb that reaches the RAM sleeper swaps it in and puts the fast rungs down.
The wake judgment, asked before the api family is paid for, must then not be
asked of one of those: it is asked of the first credential-free rung a record
does not have down, and with none it is skipped and said. A judge that does
not answer is a `WakeJudgeError`, never a raw refusal out of `escalate`.

The card is the swap test's one card (``test_a_full_top_rung_swaps_...``);
every dispatch, judgment and door run is faked, and the door keeps which units
are up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from mcgyvr.config import Config, parse
from tests.drives import SHARE_CONTRACT, a_git_repo
from tests.test_a_full_top_rung_swaps_the_ram_rung_in_and_the_fast_ones_back import (
    CARD_MIB,
    FAST_M,
    FAST_S,
    FLOOR,
    RAM,
    SCANS,
    SWAP_HOST,
    containers,
    home,
    ladder_text,
)

__all__ = ["home"]

PORT = {FAST_S: 8081, FAST_M: 8082, RAM: 8083}

#: A hosted rung above the swap card, so the climb has an api family to pay for
#: and the wake hook is asked before it.
API_UNIT = """\
  api_top:
    address: https://api.example.invalid
    model: top-model
    api_key_env: SWAP_TEST_KEY
    window: 200000
"""


class Rig:
    """The faked door and dispatches: which units are up, and what was asked."""

    def __init__(self, config: Config, specs: Path, good: set[str]) -> None:
        named = containers(specs)
        self.unit_of = {named[port]: unit for unit, port in PORT.items()}
        self.room = {unit: config.units[unit].room_mib or 0 for unit in PORT}
        self.up = {FLOOR, FAST_S, FAST_M}
        self.good = good
        self.events: list[str] = []
        self.peak = self.held()

    def held(self) -> int:
        return sum(self.room[unit] for unit in self.up if unit in PORT)

    def spawn(self, argv: list[str], **_: Any) -> int:
        verb = argv[argv.index("serve") + 1]
        unit = self.unit_of[argv[argv.index("--unit") + 1]]
        self.events.append(f"door {verb} {unit}")
        if verb in ("up", "wake"):
            self.up.add(unit)
        else:
            self.up.discard(unit)
        self.peak = max(self.peak, self.held())
        return 0

    def completion(self, rung: str, text: str, request: Any) -> Any:
        from mcgyvr.local_pool import Protocol
        from mcgyvr.runner import Completion, StopReason

        return Completion(
            text=text,
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="m",
            source=rung,
            protocol=Protocol.OPENAI,
            max_output_tokens=getattr(request, "max_output_tokens", None),
            latency_s=0.0,
        )

    def build(self, source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        from mcgyvr.runner import RefusedConnectionError

        self.events.append(f"build {rung}")
        if rung in PORT and rung not in self.up:
            raise RefusedConnectionError(f"{rung} is down")
        text = "```python\nVALUE = 1\n```" if rung in self.good else "nonsense"
        return self.completion(rung, text, request)


def _rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, good: set[str]
) -> tuple[Config, Rig]:
    import mcgyvr.wake as wake
    from mcgyvr import drive
    from mcgyvr.emit import emit_all
    from mcgyvr.serving import units_for

    specs = tmp_path / "specs"
    config = parse(text + "max_escalations: 9\nmax_attempts: 20\n")
    emit_all(
        units_for(parse(ladder_text(specs)), SCANS, specs=(), ctx_per_slot=None), specs
    )
    rig = Rig(config, specs, good)
    monkeypatch.setattr(wake, "spawn_door", rig.spawn)
    monkeypatch.setattr(wake, "saved_card_mib", lambda rigs: {SWAP_HOST: {0: CARD_MIB}})
    monkeypatch.setattr(drive, "dispatch", rig.build)
    return config, rig


def _climb(tmp_path: Path, config: Config, **kwargs: Any) -> Any:
    from mcgyvr.capacity import Capacity
    from mcgyvr.contract import loads
    from mcgyvr.drive import worker_attempt
    from mcgyvr.escalate import escalate
    from mcgyvr.local_pool import source_map
    from mcgyvr.pressure import Gauge
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    pool = source_map(config)
    contract = loads(SHARE_CONTRACT)
    capacity = Capacity.of(config, gauge=Gauge())
    reviewers = kwargs.pop("reviewers", None)
    with TempDirSandbox(a_git_repo(tmp_path)) as sandbox:
        attempt = worker_attempt(
            config,
            pool,
            contract,
            sandbox,
            reviewers=reviewers(config, pool, capacity) if reviewers else None,
        )
        return escalate(config, pool, contract, attempt, capacity=capacity, **kwargs)


def _with_api(specs: Path) -> str:
    """The swap ladder without the floor rung, with a hosted rung on top."""
    text = ladder_text(specs).replace(f"ladder:\n- {FLOOR}\n", "ladder:\n")
    text = text.replace("serving:", "- api_top\nserving:")
    return text.replace("ladder:\n", API_UNIT + "ladder:\n", 1)


def _judged(monkeypatch: pytest.MonkeyPatch, rig: Rig) -> None:
    """Every wake judgment is posted to a port: a unit that is down refuses it,
    and one that is up answers that the task is not worth a wake."""
    from mcgyvr import decision
    from mcgyvr.runner import RefusedConnectionError

    def post(url: str, payload: Any, headers: Any, timeout: Any) -> Any:
        unit = next((u for u, p in PORT.items() if p == urlparse(url).port), None)
        rig.events.append(f"judge {unit}")
        if unit is not None and unit not in rig.up:
            raise RefusedConnectionError(f"{unit} is down")
        raise AssertionError("no judgment is asked of a unit that is up here")

    monkeypatch.setattr(decision, "_post_json", post)


def test_the_wake_judgment_is_not_asked_of_a_rung_the_swap_put_down(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.local_pool import source_map
    from mcgyvr.wake_judge import hook_for

    monkeypatch.setenv("SWAP_TEST_KEY", "x")
    config, rig = _rig(tmp_path, monkeypatch, _with_api(tmp_path / "specs"), set())
    _judged(monkeypatch, rig)

    _climb(tmp_path, config, wake_hook=hook_for(config, source_map(config)))

    assert f"door up {RAM}" in rig.events, "the climb swapped the sleeper in"
    assert not [e for e in rig.events if e.startswith("judge")], rig.events
    assert "build api_top" in rig.events, "the climb went on to the api family"
    assert "no local rung is up to judge" in capsys.readouterr().err


def test_a_judge_that_does_not_answer_is_a_wake_judge_error(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import decision
    from mcgyvr.local_pool import source_map
    from mcgyvr.runner import RefusedConnectionError
    from mcgyvr.wake_judge import WakeJudgeError, judge

    config, _ = _rig(tmp_path, monkeypatch, ladder_text(tmp_path / "specs"), set())

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise RefusedConnectionError("nothing listens")

    monkeypatch.setattr(decision, "classify_for", refused)

    with pytest.raises(WakeJudgeError, match=f"{FAST_S!r}, which did not answer"):
        judge(source_map(config), FAST_S, {})
