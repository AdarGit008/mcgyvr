"""mcorch refuses to edit the target of an open contract, and says why to the rung.

Work lands only through mcgyvr's gate. In the pilot the rung read a preflight
refusal as "the tool is broken" and edited the target itself, in every repo.
mcorch cannot stop the harness from editing — the harness runs the tools — but
it sees every tool call it hands over, so a call to the harness's write or
edit tool on a file that is the target of an open contract is not handed over:
the rung gets a refusal naming the contract and the way through (fix the
contract, run it), and is asked again.

An open contract is read from the conversation the request carries: a write
tool call whose content loads as a contract opens its target; a `mcgyvr run`
result for that contract id (a tool result holding the result document)
closes it. Writing the contract file itself is never a target edit. A `bash`
edit (`sed -i`) is outside what this can see, and the prompt says so to the
rung instead.
"""

from __future__ import annotations

import json

from mcgyvr.mcorch import guard, loop
from mcgyvr.mcorch.anthropic import MessagesRequest
from tests.mcorch_fakes import ScriptedJev, ScriptedRung, calls, text

CONTRACT = (
    "id: fmt-a\ntask_type: format\ntask: Format.\ntarget: src/a.py\n"
    "scope:\n  allow: ['src/a.py']\n"
)


def _wrote(path: str, content: str, tool: str = "Write") -> dict[str, object]:
    return {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": f"toolu_{abs(hash(path)) % 1000}",
                "name": tool,
                "input": {"file_path": path, "content": content},
            }
        ],
    }


def _ok(tool_use_id: str = "toolu_x", content: str = "ok") -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
        ],
    }


def _result(contract: str) -> dict[str, object]:
    return _ok(content=json.dumps({"contract": contract, "outcome": "rejected"}))


def test_a_written_contract_opens_its_target_until_its_run_result_arrives() -> None:
    messages = (
        {"role": "user", "content": "format a"},
        _wrote("/work/fmt-a.yaml", CONTRACT),
        _ok(),
    )
    assert guard.open_targets(messages) == {"src/a.py": "fmt-a"}
    closed = (*messages, _result("fmt-a"))
    assert guard.open_targets(closed) == {}


def test_pi_style_write_with_a_path_key_opens_too() -> None:
    messages = (
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "write",
                    "input": {"path": "fmt-a.yaml", "content": CONTRACT},
                }
            ],
        },
    )
    assert guard.open_targets(messages) == {"src/a.py": "fmt-a"}


def test_a_write_that_is_not_a_contract_opens_nothing() -> None:
    messages = (_wrote("/work/notes.md", "hello\n"),)
    assert guard.open_targets(messages) == {}


def test_an_edit_of_an_open_target_is_named_by_its_contract() -> None:
    targets = {"src/a.py": "fmt-a"}
    assert (
        guard.edits_open_target(
            "Edit",
            {"file_path": "/home/someone/work/src/a.py", "old_string": "x"},
            targets,
        )
        == "fmt-a"
    )
    assert guard.edits_open_target("write", {"path": "src/a.py"}, targets) == "fmt-a"
    assert (
        guard.edits_open_target("Write", {"file_path": "/work/fmt-a.yaml"}, targets)
        is None
    )
    assert (
        guard.edits_open_target("Edit", {"file_path": "/work/src/b.py"}, targets)
        is None
    )
    assert (
        guard.edits_open_target("Read", {"file_path": "/work/src/a.py"}, targets)
        is None
    )
    # A different file whose name merely ends the same is not the target.
    assert (
        guard.edits_open_target("Edit", {"file_path": "/work/xsrc/a.py"}, targets)
        is None
    )


def test_the_loop_refuses_the_edit_and_asks_the_rung_again() -> None:
    request = MessagesRequest(
        model="mcorch",
        max_tokens=500,
        messages=(
            {"role": "user", "content": "format a"},
            _wrote("/work/fmt-a.yaml", CONTRACT),
            _ok(),
        ),
        tools=(
            {"name": "Edit", "description": "e", "input_schema": {"type": "object"}},
            {"name": "Bash", "description": "b", "input_schema": {"type": "object"}},
        ),
    )
    rung = ScriptedRung(
        calls(("Edit", json.dumps({"file_path": "/work/src/a.py", "old_string": "x"}))),
        calls(("Bash", json.dumps({"command": "mcgyvr run fmt-a.yaml --repo ."}))),
    )
    turn = loop.respond(
        request,
        rung=rung,
        jev=ScriptedJev(),
        system="s {jev_notes}",
        keep_tools=(),
        internal=(),
        limits=loop.Limits(max_rounds=3, side_reply_tokens=64),
    )
    assert len(rung.calls) == 2
    refusal = rung.calls[1].turns[-1]
    assert refusal["role"] == "tool"
    assert refusal["content"].startswith("refused:")
    assert "fmt-a" in refusal["content"]
    assert "src/a.py" in refusal["content"]
    assert turn.reply.tool_calls[0].name == "Bash"
    assert turn.trace.refused_edits == ("src/a.py",)


def test_a_turn_with_no_open_contract_hands_edits_over() -> None:
    request = MessagesRequest(
        model="mcorch",
        max_tokens=500,
        messages=({"role": "user", "content": "fix a"},),
        tools=(
            {"name": "Edit", "description": "e", "input_schema": {"type": "object"}},
        ),
    )
    rung = ScriptedRung(calls(("Edit", json.dumps({"file_path": "/work/src/a.py"}))))
    turn = loop.respond(
        request,
        rung=rung,
        jev=ScriptedJev(intent="work"),
        system="s {jev_notes}",
        keep_tools=(),
        internal=(),
        limits=loop.Limits(max_rounds=3, side_reply_tokens=64),
    )
    assert turn.reply.tool_calls[0].name == "Edit"
    assert turn.trace.refused_edits == ()
    _ = text  # the fakes module stays the one import site for replies
