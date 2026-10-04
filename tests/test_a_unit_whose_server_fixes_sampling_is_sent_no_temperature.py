"""A unit whose server fixes its sampling is sent no `temperature`.

The runner sends `temperature` on every request — 0.0 for the greedy first
draw, `breadth.temperature` for the rest — because a worker's reply is judged
by a deterministic gate and the first draw must be the same draw every time.
Some hosted models refuse the parameter outright: in the campaign every
dispatch to `claude-opus-5-5` failed with HTTP 400 (Anthropic's migration
guide: sampling parameters removed on Opus 4.7 and later, Fable 5, Claude 5).
The repository's determinism rule needs the parameter everywhere else, so the
answer is a fact declared on the unit, not a model name in code:
`units.<unit>.sampling: server` says the server fixes its own sampling and
refuses the parameters, and the runner and the typed-decision primitive send
none to it. Every other unit is sent exactly what it was sent before. A
server-sampled unit asked for more than one draw is refused at load: without
a temperature every draw is the first draw again.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import decision, runner
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.decision import Noul
from mcgyvr.pool import source_map

SETUP = """\
units:
  local:
    address: http://box.invalid:8080
    model: coder-7b
    rig: box
    width: 2
  hosted:
    address: https://api.example.com/v1
    model: hosted-big
    api_key_env: EXAMPLE_KEY
    sampling: server
ladder:
- local
- hosted
"""


def _wire(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[dict[str, Any]]:
    posted: list[dict[str, Any]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append(payload)
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "hi"},
                    "logprobs": {
                        "content": [
                            {"top_logprobs": [{"token": "Yes", "logprob": -0.1}]}
                        ]
                    },
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(module, "_post_json", post)
    return posted


def test_the_declared_fact_reaches_the_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXAMPLE_KEY", "k")
    config = parse(SETUP)
    assert config.units["hosted"].sampling == "server"
    assert config.units["local"].sampling == "request"
    pool = source_map(config)
    assert pool.bind("hosted").sampling == "server"
    assert pool.bind("local").sampling == "request"


def test_a_server_sampled_unit_is_sent_no_temperature_and_a_local_one_still_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXAMPLE_KEY", "k")
    pool = source_map(parse(SETUP))
    posted = _wire(monkeypatch, runner)
    ask = runner.Request(prompt="hello", max_output_tokens=16)
    runner.runner_for(pool.bind("hosted")).generate("hosted-big", ask)
    runner.runner_for(pool.bind("local")).generate("coder-7b", ask)
    hosted, local = posted
    assert "temperature" not in hosted
    assert local["temperature"] == 0.0
    # A draw above the first still names its temperature on a local unit.
    posted.clear()
    runner.runner_for(pool.bind("local")).generate(
        "coder-7b",
        runner.Request(prompt="hello", max_output_tokens=16, temperature=0.7),
    )
    assert posted[0]["temperature"] == 0.7


def test_a_typed_decision_on_a_server_sampled_unit_sends_no_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXAMPLE_KEY", "k")
    pool = source_map(parse(SETUP))
    posted = _wire(monkeypatch, decision)
    decision.classify(pool.bind("hosted"), "hosted-big", {"x": 1}, {"q": Noul("Q?")})
    decision.classify(pool.bind("local"), "coder-7b", {"x": 1}, {"q": Noul("Q?")})
    hosted, local = posted
    assert "temperature" not in hosted
    assert local["temperature"] == 0.0
    assert hosted["max_tokens"] == 1 and hosted["logprobs"] is True


def test_more_than_one_draw_on_a_server_sampled_unit_is_refused_at_load() -> None:
    with pytest.raises(ConfigSchemaError, match="sampling: server"):
        parse(SETUP + "draws:\n  hosted: 3\nbreadth:\n  temperature: 0.7\n")
    # The same breadth on the local unit alone is legal, as before.
    parse(SETUP + "draws:\n  local: 3\nbreadth:\n  temperature: 0.7\n")


def test_sampling_is_a_unit_fact_the_fleet_file_accepts() -> None:
    from mcgyvr.fleet.files import _UNIT_KEYS

    assert "sampling" in _UNIT_KEYS
