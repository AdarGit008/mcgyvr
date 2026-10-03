"""mcorch authors contracts by the strategy the config names, never a hardcoded one.

``orchestrator.authoring`` picks how a request becomes a contract. ``direct``
gives the rung an internal tool, ``author_contract``, that validates the
document through the public contract loader and then asks Jev whether it is
ready to run (J2): a refused document comes back naming the key, a document
Jev doubts comes back with its doubt, and a ready one comes back canonical so
the rung writes exactly that to the tree with the harness's tools. Internal
tools run inside one request and are never shown to the harness; a reply that
mixes an internal call with harness calls runs the internal ones and tells the
rung to call the harness again after reading them.

``prose`` and ``classifier`` need the repository's index, which the server does
not hold (it executes nothing and knows no path), so asking for them is refused
by name at serve time rather than failing mid-conversation. The default is not
picked here: a config that leaves ``authoring`` unbound is refused by the config
loader, not filled in.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr.mcorch import authoring, loop
from mcgyvr.mcorch.anthropic import MessagesRequest
from tests.mcorch_fakes import ScriptedJev, ScriptedRung, calls, text

CONTRACT = """
id: fmt-a
task_type: format
task: Format the file.
target: src/a.py
scope:
  allow: ["src/a.py"]
"""


AUTHORED = json.dumps({"contract": CONTRACT})


def _request() -> MessagesRequest:
    return MessagesRequest(
        model="mcorch",
        max_tokens=1000,
        messages=({"role": "user", "content": "format src/a.py"},),
        tools=(
            {"name": "Write", "description": "w", "input_schema": {"type": "object"}},
        ),
    )


def _respond(
    rung: ScriptedRung, jev: ScriptedJev, strategy: authoring.Authoring
) -> loop.Turn:
    return loop.respond(
        _request(),
        rung=rung,
        jev=jev,
        system="mcorch {jev_notes}",
        keep_tools=(),
        internal=(strategy,),
        limits=loop.Limits(max_rounds=4, side_reply_tokens=64),
    )


def test_direct_authoring_validates_through_the_public_loader() -> None:
    jev = ScriptedJev(intent="work", ready_to_run=True)
    direct = authoring.authoring_for("direct", jev=jev)
    assert [tool["function"]["name"] for tool in direct.tools()] == ["author_contract"]
    rung = ScriptedRung(
        calls(("author_contract", AUTHORED)),
        calls(("Write", '{"file_path": "fmt-a.yaml", "content": "..."}')),
    )
    turn = _respond(rung, jev, direct)
    # The internal tool ran inside the request; the harness sees only the Write.
    assert len(rung.calls) == 2
    second = rung.calls[1]
    assert second.turns[-1]["role"] == "tool"
    assert "fmt-a" in second.turns[-1]["content"]
    assert "ready" in second.turns[-1]["content"]
    assert [name for name, _ in jev.asked] == ["intent", "ready_to_run"]
    assert turn.reply.tool_calls[0].name == "Write"
    assert turn.trace.internal_calls == ("author_contract",)
    # The internal tool is never offered to or seen by the harness.
    assert all(call.name != "author_contract" for call in turn.reply.tool_calls)


def test_a_document_the_loader_refuses_comes_back_naming_the_key() -> None:
    jev = ScriptedJev(intent="work")
    direct = authoring.authoring_for("direct", jev=jev)
    bad = '{"contract": "id: x\\ntask_type: nonsense\\ntask: t\\ntarget: a.py\\n"}'
    rung = ScriptedRung(calls(("author_contract", bad)), text("I will fix task_type."))
    turn = _respond(rung, jev, direct)
    result = rung.calls[1].turns[-1]
    assert result["role"] == "tool"
    assert result["content"].startswith("refused:")
    assert "task_type" in result["content"]
    assert [name for name, _ in jev.asked] == ["intent"]  # nothing to ask Jev about
    assert turn.reply.text == "I will fix task_type."


def test_a_document_jev_doubts_comes_back_with_the_doubt() -> None:
    jev = ScriptedJev(intent="work", ready_to_run=False)
    direct = authoring.authoring_for("direct", jev=jev)
    rung = ScriptedRung(
        calls(("author_contract", AUTHORED)),
        text("Let me add an acceptance command."),
    )
    _respond(rung, jev, direct)
    result = rung.calls[1].turns[-1]
    assert result["content"].startswith("Jev:")
    assert "not ready" in result["content"]
    state = jev.asked[1][1]
    assert state["id"] == "fmt-a"
    assert state["task_type"] == "format"


def test_internal_and_harness_calls_in_one_reply_run_the_internal_ones_first() -> None:
    jev = ScriptedJev(intent="work", ready_to_run=True)
    direct = authoring.authoring_for("direct", jev=jev)
    rung = ScriptedRung(
        calls(
            ("author_contract", AUTHORED),
            ("Write", '{"file_path": "fmt-a.yaml"}'),
        ),
        calls(("Write", '{"file_path": "fmt-a.yaml"}')),
    )
    turn = _respond(rung, jev, direct)
    second = rung.calls[1]
    # The assistant turn fed back carries only the internal call, and the
    # rung is told the harness call was not forwarded.
    assistant = second.turns[-2]
    assert [call["function"]["name"] for call in assistant["tool_calls"]] == [
        "author_contract"
    ]
    assert "not forwarded" in second.turns[-1]["content"]
    assert turn.reply.tool_calls[0].name == "Write"


@pytest.mark.parametrize("strategy", ["prose", "classifier"])
def test_prose_and_classifier_are_refused_by_name_while_the_server_has_no_index(
    strategy: str,
) -> None:
    with pytest.raises(authoring.AuthoringUnavailableError) as refused:
        authoring.authoring_for(strategy, jev=ScriptedJev())
    assert strategy in str(refused.value)
    assert "index" in str(refused.value)


def test_an_unknown_strategy_is_a_callers_mistake() -> None:
    with pytest.raises(ValueError, match="nonsense"):
        authoring.authoring_for("nonsense", jev=ScriptedJev())
