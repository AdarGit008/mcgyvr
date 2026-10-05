"""A ridden answer from a model other than the rung's is the rung refusing it.

A relief rung is asked for ``hitchhike@<id>``, and the hub passes the host's
real model name through in the answer's ``model``: the ``served_model`` the
rung was matched on, or that model's weights file as the host's server names it
(``tests/test_a_unit_answers_by_the_name_its_rung_declares.py``). An answer
naming anything else — or
nothing — is not an answer from the unit the rider was matched to, so the
dispatch ends as :class:`~mcgyvr.runner.ReliefUnavailableError`: the rung
refused the request, and the climb passes it over as a full rung. One line
says so on stderr, naming the rung and the two models and nothing of the
prompt.

An answer that does name the served model is the completion, and is not held
to the ``hitchhike@<id>`` it was asked for: that name is the hub's address for
the rung, not a model.

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import parse
from mcgyvr.pool import source_map
from mcgyvr.runner import Completion, Request, dispatch
from tests.test_a_relief_rung_that_cannot_take_the_request_now_is_full import (
    RIDE,
    RUNG_ID,
    answering,
)

SERVED = "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"
PROMPT = "the rider's private prompt"


def completion(model: str | None) -> bytes:
    body: dict[str, Any] = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    if model is not None:
        body["model"] = model
    return json.dumps(body).encode()


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", "mhu_" + "1" * 16)


def ride(answer: bytes, tmp_path: Path) -> Any:
    seen: list[dict[str, Any]] = []
    with answering(200, answer, seen) as address:
        config = parse(
            f"""
units:
  local_fast:
    address: {address}
    model: qwen2.5-coder-3b
    width: 1
ladder: [local_fast]
fanout: idle
relief:
  {RIDE}:
    address: {address}
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: within
    served_model: {SERVED}
"""
        )
        capacity = Capacity.of(config, root=tmp_path / "slots")
        try:
            return dispatch(
                source_map(config),
                RIDE,
                Request(prompt=PROMPT, max_output_tokens=8),
                capacity=capacity,
            )
        except Exception as exc:
            return exc


def test_an_answer_naming_the_served_model_is_the_completion(tmp_path: Path) -> None:
    done = ride(completion(SERVED), tmp_path)

    assert isinstance(done, Completion)
    assert done.text == "ok"


@pytest.mark.parametrize("model", ["another-model.gguf", f"hitchhike@{RUNG_ID}", None])
def test_an_answer_from_another_model_is_the_rung_refusing_it(
    tmp_path: Path, model: str | None, capsys: pytest.CaptureFixture[str]
) -> None:
    refused = ride(completion(model), tmp_path)

    assert isinstance(refused, SlotUnavailableError)
    said = capsys.readouterr().err
    assert RIDE in said and SERVED in said
    assert PROMPT not in said and PROMPT not in str(refused)
