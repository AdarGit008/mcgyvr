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

from pathlib import Path

import pytest

from mcgyvr.capacity import SlotUnavailableError
from mcgyvr.runner import Completion
from tests.rungs import (  # noqa: F401 - fixtures
    PROMPT,
    RIDE,
    RUNG_ID,
    SERVED,
    answering,
    completion,
    ride,
    set_hub_key,
)


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    set_hub_key(monkeypatch)


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
