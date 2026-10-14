"""A `chat` or `agent` run is a raw connection to a model: mcgyvr sets no limits.

Owner decision (2026-10-14, e2e run 3 T1): the cap model is decided by task
type, and `chat` and `agent` are a raw LLM connection. mcgyvr provides no
harness around one, so:

- no output cap is sent: a unit's ``output_tokens`` is not consulted;
- a contract that states ``limits.max_output_tokens`` is refused at load, by
  name, saying chat and agent are a raw connection with no limits;
- the prompt is not measured against ``context.max_input_tokens``;
- the contract is not measured against the window of the rung it reaches,
  nor against a share of it.

The one bound kept is the hub's, not the product's: a ride on another person's
unit is still given the rider's local unit's limit
(``tests/test_a_relief_rung_is_sent_the_smaller_of_the_contracts_cap_and_the_local_units.py``).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import ContractSchemaError, loads
from mcgyvr.local_pool import source_map
from tests.rungs import caps_sent

CHAT = """\
id: sky
task_type: chat
task: Why is the sky blue?
"""

AGENT = """\
id: brief
task_type: agent
task: Explain how the store saves a record.
sources: ["src/app/store.py"]
"""

#: A unit with a tiny window and its own reply room: everything a harnessed
#: contract is measured against, none of which a raw connection is.
LADDER = """\
units:
  local_small:
    address: http://localhost:8080
    model: qwen2.5-coder:3b
    width: 1
    window: 64
    output_tokens: 32
ladder: [local_small]
max_window_fraction: 0.1
"""

UNIT = "local_small"


@pytest.mark.parametrize("document", [CHAT, AGENT], ids=["chat", "agent"])
def test_a_stated_output_cap_is_refused_at_load(document: str) -> None:
    with pytest.raises(ContractSchemaError) as refused:
        loads(document + "limits:\n  max_output_tokens: 16\n")
    said = str(refused.value)
    assert said.startswith("limits.max_output_tokens:"), said
    assert "raw connection" in said, said
    assert "no limits" in said, said


@pytest.mark.parametrize("document", [CHAT, AGENT], ids=["chat", "agent"])
def test_a_contract_that_states_none_loads_uncapped(document: str) -> None:
    assert loads(document).limits.max_output_tokens is None


def test_the_prompt_is_not_measured_against_a_prompt_ceiling() -> None:
    from mcgyvr.worker.prompt import build_prompt

    big = "word " * 4000
    contract = replace(
        loads(AGENT + "context:\n  max_input_tokens: 64\n"), source_content=(big,)
    )
    prompt = build_prompt(contract)

    assert prompt.fits, prompt.fit_issue
    assert big in prompt.user


@pytest.mark.parametrize("document", [CHAT, AGENT], ids=["chat", "agent"])
def test_no_window_or_share_check_stands_between_it_and_the_unit(
    document: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.drive import dispatch_prompt, refuse_unsendable
    from mcgyvr.worker.prompt import build_prompt

    seen = caps_sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = replace(loads(document), task="why " * 2000)
    prompt = build_prompt(contract)

    refuse_unsendable(UNIT, pool.bind(UNIT), prompt, contract, window_fraction=0.1)
    dispatch_prompt(pool, UNIT, prompt, contract, window_fraction=0.1)

    assert seen == [(UNIT, None)], (
        f"a raw connection is sent no output cap, the unit's own output_tokens "
        f"included; got {seen!r}"
    )


def test_a_ride_still_carries_the_hubs_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcgyvr.gate.preflight import reply_cap
    from tests.rungs import RIDE, RUNG_ID

    monkeypatch.setenv("HUB_KEY", "mhu_" + "1" * 16)
    pool = source_map(
        parse_config(
            LADDER.replace("max_window_fraction: 0.1\n", "")
            + "fanout: idle\n"
            + "relief:\n"
            + f"  {RIDE}:\n"
            + "    address: http://localhost:8765/v1\n"
            + f"    model: hitchhike@{RUNG_ID}\n"
            + "    api_key_env: HUB_KEY\n"
            + "    width: 1\n"
            + "    position: within\n"
            + "    served_model: qwen2.5-coder-7b\n"
        )
    )

    assert reply_cap(loads(CHAT), pool.bind(RIDE)) == 32
    assert reply_cap(loads(CHAT), pool.bind(UNIT)) is None
