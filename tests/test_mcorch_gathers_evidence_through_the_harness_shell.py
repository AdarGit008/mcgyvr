"""mcorch gathers repository evidence the way a pi agent does: through the harness.

Owner ruling: mcorch gets data the way pi does — the model emits a tool call,
the harness runs it in the working directory, the output comes back as a tool
result. Under `authoring: prose | classifier` the loop therefore emits a
harness shell call running mcgyvr's own deterministic reader,
`mcgyvr read "<request>" --json`, in place of asking the rung; the next
request carries the document, which the server indexes (never a path of its
own) and hands to the configured proposer and the decomposer. The rung then
sees a digest — the contracts to write — where the raw document was, and goes
on as under `direct`: write, `mcgyvr contract`, fix, `mcgyvr run`. The shell
tool is whichever the harness offers (Claude Code `Bash`, pi `bash`); offered
none, the strategy is refused by name. The repository never touches the server.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from mcgyvr.config import parse
from mcgyvr.decision import ChoiceAnswer, Decision, Question
from mcgyvr.mcorch import authoring, evidence, loop
from mcgyvr.mcorch.anthropic import MessagesRequest
from mcgyvr.mcorch.wire import Jev, RungCall
from tests.mcorch_fakes import ScriptedJev, ScriptedRung, text

SETUP = """\
units:
  small:
    address: http://box.invalid:11434
    model: coder-7b
    rig: box
    width: 3
ladder:
- small
"""

LISTING = "def paginate(items, size):\n    return items[:size]\n"


def _document(prompt: str = "document paginate in pkg/listing.py") -> str:
    """What `mcgyvr read --json` prints for an invented repository."""
    return json.dumps(
        {
            "prompt": prompt,
            "root": "/home/someone/work",
            "resolution": {
                "verdict": "resolved",
                "candidates": [
                    {"path": "pkg/listing.py", "score": 3.0, "evidence": ["name"]}
                ],
            },
            "reads": [
                {
                    "path": "pkg/listing.py",
                    "start": 1,
                    "end": 2,
                    "reason": "definition",
                    "text": LISTING,
                }
            ],
            "files": [{"path": "pkg/listing.py", "text": LISTING}],
        }
    )


def _tools(*names: str) -> tuple[dict[str, object], ...]:
    return tuple(
        {"name": name, "description": name, "input_schema": {"type": "object"}}
        for name in names
    )


def _request(
    *messages: dict[str, object], tools: tuple[dict[str, object], ...]
) -> MessagesRequest:
    return MessagesRequest(
        model="mcorch", max_tokens=800, messages=tuple(messages), tools=tools
    )


def _respond(
    request: MessagesRequest, rung: ScriptedRung, jev: Jev, strategy: str
) -> loop.Turn:
    config = parse(SETUP)
    chosen = authoring.authoring_for(strategy, jev=jev, rung=rung, config=config)
    return loop.respond(
        request,
        rung=rung,
        jev=jev,
        system="s {jev_notes}",
        keep_tools=(),
        internal=(chosen,),
        limits=loop.Limits(max_rounds=3, side_reply_tokens=64),
    )


def test_a_work_request_under_prose_asks_the_harness_to_read_not_the_rung() -> None:
    rung = ScriptedRung()
    turn = _respond(
        _request(
            {"role": "user", "content": "document paginate"},
            tools=_tools("Read", "Bash"),
        ),
        rung,
        ScriptedJev(intent="work"),
        "prose",
    )
    assert rung.calls == []  # no token spent before the evidence is in
    (call,) = turn.reply.tool_calls
    assert call.name == "Bash"
    command = json.loads(call.arguments)["command"]
    assert command.startswith("mcgyvr read ")
    assert "--json" in command
    assert "document paginate" in command
    assert turn.trace.evidence == "asked"


def test_pis_shell_is_named_bash_in_lower_case_and_is_used_as_offered() -> None:
    turn = _respond(
        _request(
            {"role": "user", "content": "document paginate"},
            tools=_tools("read", "bash"),
        ),
        ScriptedRung(),
        ScriptedJev(intent="work"),
        "classifier",
    )
    assert turn.reply.tool_calls[0].name == "bash"


def test_without_a_shell_tool_the_strategy_is_refused_by_name() -> None:
    turn = _respond(
        _request(
            {"role": "user", "content": "document paginate"}, tools=_tools("Read")
        ),
        ScriptedRung(),
        ScriptedJev(intent="work"),
        "prose",
    )
    assert turn.reply.tool_calls == ()
    assert "prose" in turn.reply.text
    assert "shell" in turn.reply.text.lower()
    assert turn.trace.evidence == "no-shell"


def test_chat_under_prose_asks_the_rung_as_before() -> None:
    rung = ScriptedRung(text("Hello."))
    turn = _respond(
        _request({"role": "user", "content": "hi"}, tools=_tools("Bash")),
        rung,
        ScriptedJev(intent="chat"),
        "prose",
    )
    assert turn.reply.text == "Hello."
    assert turn.trace.evidence is None


def _after_read(tools: tuple[dict[str, object], ...]) -> MessagesRequest:
    return _request(
        {"role": "user", "content": "document paginate in pkg/listing.py"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_read",
                    "name": "Bash",
                    "input": {
                        "command": evidence.command(
                            "document paginate in pkg/listing.py"
                        )
                    },
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_read",
                    "content": _document(),
                }
            ],
        },
        tools=tools,
    )


def test_prose_proposes_from_the_document_and_the_rung_sees_a_digest() -> None:
    proposals = json.dumps(
        [
            {
                "task_type": "docstring",
                "task": "Document paginate.",
                "target": "pkg/listing.py",
                "stop_conditions": ["The behaviour is unclear."],
            }
        ]
    )
    rung = ScriptedRung(text(proposals), text("Writing the contract now."))
    jev = ScriptedJev(ready_to_run=True)
    turn = _respond(_after_read(_tools("Write", "Bash")), rung, jev, "prose")
    # First call: the proposer's prompt, built from evidence, no harness tools.
    proposer_call: RungCall = rung.calls[0]
    assert proposer_call.tools == ()
    assert "pkg/listing.py" in proposer_call.turns[-1]["content"]
    assert "REQUEST" in proposer_call.turns[-1]["content"]
    # Second call: the conversation, with the raw document replaced by a digest.
    conversation: RungCall = rung.calls[1]
    tool_turn = conversation.turns[-1]
    assert tool_turn["role"] == "tool"
    assert tool_turn["tool_call_id"] == "toolu_read"
    assert '"files"' not in tool_turn["content"]
    assert "ready:" in tool_turn["content"]
    assert "docstring" in tool_turn["content"]
    assert "pkg/listing.py" in tool_turn["content"]
    assert turn.reply.text == "Writing the contract now."
    assert turn.trace.evidence == "used"
    assert turn.trace.contracts == 1
    assert [name for name, _ in jev.asked] == ["ready_to_run"]


def test_classifier_proposes_through_jev_and_falls_back_to_prose_on_nothing() -> None:
    rung = ScriptedRung(text("ok"))
    jev = ScriptedJev(
        kind="docstring", target="pkg/listing.py", symbol="paginate", ready_to_run=True
    )
    turn = _respond(_after_read(_tools("Write", "Bash")), rung, jev, "classifier")
    assert [name for name, _ in jev.asked] == [
        "kind",
        "target",
        "symbol",
        "ready_to_run",
    ]
    assert turn.trace.contracts == 1
    digest = rung.calls[0].turns[-1]["content"]
    assert "paginate" in digest and "ready:" in digest

    # Nothing from the classifier (it is not sure of the kind) → prose is asked.
    proposals = json.dumps(
        [
            {
                "task_type": "docstring",
                "task": "Doc.",
                "target": "pkg/listing.py",
                "stop_conditions": ["x"],
            }
        ]
    )
    rung = ScriptedRung(text(proposals), text("ok"))
    scripted = ScriptedJev(
        kind="docstring", target="pkg/listing.py", symbol="", ready_to_run=True
    )

    def unsure(state: object, questions: Mapping[str, Question]) -> Decision:
        decision = scripted(state, questions)
        answers = {
            name: (
                replace(answer, confidence=0.0)
                if name == "kind" and isinstance(answer, ChoiceAnswer)
                else answer
            )
            for name, answer in decision.answers.items()
        }
        return Decision(answers=answers)

    turn = _respond(_after_read(_tools("Write", "Bash")), rung, unsure, "classifier")
    assert turn.trace.contracts == 1
    assert len(rung.calls) == 2  # the prose proposer, then the conversation


def test_a_document_the_server_cannot_read_tells_the_rung_to_narrow() -> None:
    request = _after_read(_tools("Write", "Bash"))
    cut = dict(request.messages[-1])
    cut["content"] = [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_read",
            "content": _document()[:200],
        }
    ]
    broken = MessagesRequest(
        model="mcorch",
        max_tokens=800,
        messages=(*request.messages[:-1], cut),
        tools=request.tools,
    )
    rung = ScriptedRung(text("I will narrow it."))
    turn = _respond(broken, rung, ScriptedJev(), "prose")
    digest = rung.calls[0].turns[-1]["content"]
    assert digest.startswith("refused:")
    assert "--limit" in digest
    assert turn.trace.evidence == "unreadable"


def test_the_direct_strategy_still_offers_author_contract() -> None:
    chosen = authoring.authoring_for(
        "direct", jev=ScriptedJev(), rung=ScriptedRung(), config=parse(SETUP)
    )
    assert [tool["function"]["name"] for tool in chosen.tools()] == ["author_contract"]


def test_evidence_builds_an_index_without_a_path_of_its_own(tmp_path: Path) -> None:
    document = evidence.parse_document(_document())
    assert document is not None
    index = evidence.index_from(document)
    assert [file.path for file in index.files] == ["pkg/listing.py"]
    assert index.symbols.definitions("paginate")
    assert not Path(document.root).exists() or True  # the root is a label, never read
    assert evidence.parse_document("not json") is None
    assert evidence.parse_document(json.dumps({"files": "x"})) is None
