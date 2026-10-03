"""The fleet-manager hook: a Jev difficulty judgment that routes to the smarter
resident rung before the API.

The hook answers one bounded question — "is this task hard enough to want the
smarter rung?" — through :mod:`mcgyvr.decision.classify`, and when the answer
is yes it names the asleep smart rung so the climb can wake it on demand before
escalating to the API. When the answer is no it names nothing and the climb
escalates to the API as it does today.

Two rules are pinned below, beside the pure helpers:

* **Wake-before-API routing.** A hard task, with an asleep smarter resident rung
  on the ladder, is routed to that rung before the api family is entered.
* **The hook never sleeps.** It routes, and the dispatch it routes to wakes;
  putting a unit back to sleep is the ladder manager's
  (:mod:`mcgyvr.ladder_manager`), not this per-task hook's. The hook has no
  sleep path, and driving the climb with the hook wired reaches the door's
  ``down`` never — ``mcgyvr.wake.sleep`` is monkeypatched to fail the test if
  it is so much as called.
* **A cooling smart rung is not routed to.** Where the cooldown names the smart
  rung, the hook names nothing and Jev is not asked.

Nothing here touches a network or a rig. The judgment is stubbed at
``mcgyvr.decision._post_json`` for the hook and at the ``wake_hook`` seam for
the climb; the attempt function is a recorder, exactly as
``tests/test_escalate.py`` drives :func:`~mcgyvr.escalate.escalate`.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import decision as decision_module
from mcgyvr import fleet_manager
from mcgyvr.config import parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import Assurance, Delivered, Halted, Judgement, escalate
from mcgyvr.pool import source_map
from mcgyvr.route import Try, Verdict

FAST = "local_fast"
SMART = "local_smart"
API_RUNG = "api_big"
FAST_HOST = "fast-box"
SMART_HOST = "smart-box"

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""


def ladder_text(compose_dir: str | None, *, with_smart_spec: bool) -> str:
    """A fast rung, a smart rung and an api rung; the smart rung may be asleep.

    The smart rung's host holds a launch spec only when ``with_smart_spec`` is
    true, so a config built with it false has no asleep rung at all.
    """
    serving = ""
    if compose_dir is not None:
        serving = f"serving:\n  compose_dir: {compose_dir}\n  enable_sleep_wake: true\n"
    return (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: qwen2.5-coder-3b\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        f"  {SMART}:\n"
        f"    address: http://{SMART_HOST}:8001\n"
        "    model: qwen2.5-coder-7b\n"
        "    rig: smart-rig\n"
        "    width: 2\n"
        f"  {API_RUNG}:\n"
        "    address: https://api.example.com/v1\n"
        "    model: vendor-large\n"
        "    rig: vendor\n"
        "    width: 4\n"
        "    api_key_env: EXAMPLE_API_KEY\n"
        "ladder:\n"
        f"- {FAST}\n"
        f"- {SMART}\n"
        f"- {API_RUNG}\n"
        + "max_escalations: 2\n"
        + serving
        + ("profile: dev\n" if not serving else "")
    )


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential for the api source, assembled rather than written literally."""
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


def mapped(text: str) -> tuple[Any, Any]:
    config = parse(text)
    return config, source_map(config)


def judge_pool() -> tuple[Any, Any]:
    """A single fast rung, for the judgment to run on."""
    text = (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: qwen2.5-coder-3b\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        "ladder:\n"
        f"- {FAST}\n"
    )
    return mapped(text)


def write_smart_spec(tmp_path: Path) -> Path:
    """One launch spec for the smart rung's host, as ``emit`` would write it."""
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    (where / f"{COMPOSE_PREFIX}{SMART_HOST}{COMPOSE_SUFFIX}").write_text(
        "services:\n  qwen7b:\n    image: vllm/vllm-openai:v0.26.0\n",
        encoding="utf-8",
    )
    return where


def entry(token: str, logprob: float) -> dict[str, Any]:
    return {"token": token, "logprob": logprob}


def logprobs_document(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "logprobs": {
                    "content": [{"token": entries[0]["token"], "top_logprobs": entries}]
                },
                "finish_reason": "length",
            }
        ]
    }


def yes_judge() -> Callable[
    [str, dict[str, Any], dict[str, str], float], dict[str, Any]
]:
    """A transport that answers the difficulty question with ``Yes``."""

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        return logprobs_document([entry("Yes", -0.1), entry("No", -2.3)])

    return fake_post


def no_judge() -> Callable[
    [str, dict[str, Any], dict[str, str], float], dict[str, Any]
]:
    """A transport that answers the difficulty question with ``No``."""

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        return logprobs_document([entry("Yes", -2.3), entry("No", -0.1)])

    return fake_post


def with_hook(config: Any, pool: Any) -> Callable[[Contract], str | None]:
    """The hook the climb consults, judging on the fast rung's endpoint."""
    hook = fleet_manager.hook_for(config, pool)
    assert hook is not None, "the hook should exist for a fast+smart+api ladder"
    return hook


def contract(text: str = CONTRACT) -> Contract:
    return load_contract(text)


class Recorder:
    """An attempt function that answers from a script and records what it saw."""

    def __init__(self, *verdicts: Verdict) -> None:
        self._verdicts = list(verdicts)
        self.seen: list[Try] = []

    def __call__(self, this: Try) -> Judgement:
        self.seen.append(this)
        if not self._verdicts:
            raise AssertionError(
                f"an unscripted attempt was made on {this.rung.name!r}"
            )
        verdict = self._verdicts.pop(0)
        if verdict is Verdict.PASSED:
            return Judgement(verdict=Verdict.PASSED, assurance=Assurance.UNVERIFIED)
        if verdict is Verdict.DECLINED:
            return Judgement(verdict=Verdict.DECLINED, detail="not work this rung does")
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")

    @property
    def rungs(self) -> list[str]:
        return [t.rung.name for t in self.seen]


def delivered(result: Delivered | Halted) -> Delivered:
    assert isinstance(result, Delivered), f"expected an accepted task, got {result}"
    return result


# --- the judgment -----------------------------------------------------------


def test_a_hard_task_reads_as_wake_the_smarter_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(decision_module, "_post_json", yes_judge())
    _, pool = judge_pool()
    answer = fleet_manager.judge(pool, FAST, {"task": "write a parser"})
    assert answer.wake is True
    assert answer.probability_true > 0.5
    assert 0.0 < answer.confidence <= 1.0


def test_an_easy_task_reads_as_leave_the_smarter_rung_asleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(decision_module, "_post_json", no_judge())
    _, pool = judge_pool()
    answer = fleet_manager.judge(pool, FAST, {"task": "tweak a string"})
    assert answer.wake is False
    assert answer.probability_true < 0.5


def test_the_judgement_is_one_bounded_question_over_the_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append(payload)
        return logprobs_document([entry("Yes", -0.1), entry("No", -2.3)])

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    _, pool = judge_pool()
    fleet_manager.judge(pool, FAST, {"task": "write a parser"})

    assert len(sent) == 1
    payload = sent[0]
    assert payload["max_tokens"] == 1
    assert payload["logprobs"] is True
    assert fleet_manager.INSTRUCTIONS in payload["messages"][0]["content"]
    assert "write a parser" in payload["messages"][0]["content"]


def test_the_state_carries_the_task_and_what_the_fast_rung_said() -> None:
    state = fleet_manager.state_for(contract(), detail="the gate rejected it")
    assert state["task_type"] == "function_implementation"
    assert "retry with backoff" in state["task"]
    assert state["target"] == "src/pkg/fetch.py"
    assert state["detail"] == "the gate rejected it"


# --- which rungs are asleep, smart and fast ---------------------------------


def test_asleep_rungs_are_the_resident_rungs_with_a_launch_spec(
    tmp_path: Path, key: None
) -> None:
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))

    asleep = fleet_manager.asleep_rungs(config, pool)

    assert [r.name for r in asleep] == [SMART], (
        "only the smart rung's host holds a launch spec; the fast rung's host "
        "holds none, and the api rung has no card at all"
    )


def test_a_rung_without_a_launch_spec_is_not_asleep(tmp_path: Path, key: None) -> None:
    config, pool = mapped(ladder_text(None, with_smart_spec=False))
    assert fleet_manager.asleep_rungs(config, pool) == ()


def test_smart_rung_is_the_dearest_asleep_resident_rung(
    tmp_path: Path, key: None
) -> None:
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    smart = fleet_manager.smart_rung(config, pool)
    assert smart is not None and smart.name == SMART


def test_fast_rung_is_the_cheapest_resident_rung(key: None) -> None:
    config, pool = mapped(ladder_text(None, with_smart_spec=False))
    fast = fleet_manager.fast_rung(config, pool)
    assert fast is not None and fast.name == FAST


# --- the hook ---------------------------------------------------------------


def test_the_hook_names_the_smart_rung_when_the_task_is_hard(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    monkeypatch.setattr(decision_module, "_post_json", yes_judge())

    named = fleet_manager.wake_before_api(config, pool, contract(), judge_with=FAST)

    assert named == SMART


def test_the_hook_names_nothing_when_the_task_is_not_hard(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    monkeypatch.setattr(decision_module, "_post_json", no_judge())

    named = fleet_manager.wake_before_api(config, pool, contract(), judge_with=FAST)

    assert named is None


def test_the_hook_names_nothing_when_no_rung_is_asleep(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, pool = mapped(ladder_text(None, with_smart_spec=False))
    monkeypatch.setattr(decision_module, "_post_json", yes_judge())

    named = fleet_manager.wake_before_api(config, pool, contract(), judge_with=FAST)

    assert named is None


def test_hook_for_is_none_without_a_distinct_smarter_rung(key: None) -> None:
    """One resident rung is no smarter rung, so there is nothing to decide."""
    config, pool = mapped(
        ladder_text(None, with_smart_spec=False).replace(
            f"- {SMART}\n- {API_RUNG}\n", f"- {API_RUNG}\n"
        )
    )
    assert fleet_manager.hook_for(config, pool) is None


def test_hook_for_is_none_when_sleep_wake_is_off(tmp_path: Path, key: None) -> None:
    """Routing to wake is refused where waking is refused; the gate stands."""
    specs = write_smart_spec(tmp_path)
    text = ladder_text(str(specs), with_smart_spec=True).replace(
        "  enable_sleep_wake: true\n", "  enable_sleep_wake: false\n"
    )
    config, pool = mapped(text)
    assert fleet_manager.hook_for(config, pool) is None


# --- the hook never sleeps a card -------------------------------------------


def test_the_hook_has_no_sleep_path() -> None:
    """The hook routes and a dispatch wakes; sleeping is the manager's, not this hook's.

    Asserted over the module's own source rather than by behaviour, because the
    absence being guarded is the absence of a path: a ``sleep`` call added to
    the hook later must fail this test even if nothing exercises it.
    """
    source = inspect.getsource(fleet_manager)
    assert "sleep(" not in source, "the hook must never call the sleep path"
    assert '"down"' not in source, "the hook must never reach for the door's down"
    assert "'down'" not in source, "the hook must never reach for the door's down"


# --- a cooling rung is not routed to ----------------------------------------


class Cooling:
    """A cooldown that holds out the rungs it is told to."""

    def __init__(self, *held: str) -> None:
        self.held = set(held)

    def unavailable(self, endpoints: Any) -> dict[str, str]:
        return {
            endpoint.source: "cooling down"
            for endpoint in endpoints
            if endpoint.source in self.held
        }


def test_a_cooled_down_smart_rung_is_never_routed_to_and_jev_is_not_asked(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))

    def asked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Jev was asked about a rung that is cooling down")

    monkeypatch.setattr(decision_module, "_post_json", asked)

    named = fleet_manager.wake_before_api(
        config, pool, contract(), judge_with=FAST, cooldown=Cooling(SMART)
    )

    assert named is None


def test_a_smart_rung_the_cooldown_does_not_name_is_routed_to_as_before(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    monkeypatch.setattr(decision_module, "_post_json", yes_judge())
    hook = fleet_manager.hook_for(config, pool, cooldown=Cooling(FAST))
    assert hook is not None

    assert hook(contract()) == SMART


def test_the_hook_built_with_a_cooldown_reads_it_at_each_task(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rung that cools after the hook was built is still not routed to."""
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    monkeypatch.setattr(decision_module, "_post_json", yes_judge())
    cooling = Cooling()
    hook = fleet_manager.hook_for(config, pool, cooldown=cooling)
    assert hook is not None

    assert hook(contract()) == SMART
    cooling.held.add(SMART)
    assert hook(contract()) is None


# --- wake-before-API routing through the climb ------------------------------


def test_a_hard_task_is_routed_to_the_smart_rung_before_the_api(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Jev says the task is hard, the smart rung is tried before the api.

    The ladder is ``fast, smart, api``. The fast rung fails, the smart rung
    declines its ordinary pass (a sleeping card stepped aside), the hook then
    names the smart rung — Jev says wake it — and the climb gives it a real
    attempt before ever entering the api family.
    """
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    hook = with_hook(config, pool)
    monkeypatch.setattr(decision_module, "_post_json", yes_judge())

    # The fast rung fails; the smart rung's ordinary pass is declined (its card
    # is asleep); the hook's pass passes. The api rung is never reached.
    attempts = Recorder(Verdict.FAILED, Verdict.DECLINED, Verdict.PASSED)

    # Auto-sleep is never taken: any call to the sleep path fails the test.
    import mcgyvr.wake as wake

    def no_sleep(config: Any, host: str) -> Any:
        raise AssertionError(
            "the hook routed to a sleep; sleeping is the manager's, not the hook's"
        )

    monkeypatch.setattr(wake, "sleep", no_sleep)

    result = delivered(escalate(config, pool, contract(), attempts, wake_hook=hook))

    assert result.rung == SMART
    assert result.family.name == "local"
    assert attempts.rungs == [FAST, SMART, SMART], attempts.rungs
    assert API_RUNG not in attempts.rungs, (
        "the api rung was reached before the smart rung; the hook did not route "
        "wake-before-API"
    )


def test_a_not_hard_task_escalates_to_the_api_as_before(
    tmp_path: Path, key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Jev says the task is not hard, the climb escalates to the api."""
    specs = write_smart_spec(tmp_path)
    config, pool = mapped(ladder_text(str(specs), with_smart_spec=True))
    hook = with_hook(config, pool)
    monkeypatch.setattr(decision_module, "_post_json", no_judge())

    attempts = Recorder(Verdict.FAILED, Verdict.FAILED, Verdict.PASSED)

    import mcgyvr.wake as wake

    def no_sleep(config: Any, host: str) -> Any:
        raise AssertionError(
            "the hook routed to a sleep; sleeping is the manager's, not the hook's"
        )

    monkeypatch.setattr(wake, "sleep", no_sleep)

    result = delivered(escalate(config, pool, contract(), attempts, wake_hook=hook))

    assert result.rung == API_RUNG
    assert result.family.name == "api"
    assert attempts.rungs == [FAST, SMART, API_RUNG], attempts.rungs
