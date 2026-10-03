"""`mcgyvr mcorch serve` binds the orchestrator rung and the jev unit from the config.

The server holds no address of its own: :mod:`mcgyvr.mcorch.bind` builds the
two seams from a loaded config — the rung is the ``orchestrator`` role through
:func:`mcgyvr.runner.dispatch_role`, with the harness's turns and tools on the
wire, and Jev is the ``jev`` role through :func:`mcgyvr.decision.classify_role`
— so re-pointing either is a line in ``policy.yaml``. A ``type: mcorch``
orchestrator without a ``jev.unit`` is refused by the loader: mcorch asks Jev
every bounded question and has nowhere to ask without one. The command refuses
a config whose orchestrator is not mcorch, binds the loopback unless ``--bind``
says otherwise, and listens on ``--port``. Every address here is invented and
no model is reached: the wire is scripted at ``runner._post_json`` and
``decision._post_json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import decision, runner
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.decision import Choice
from mcgyvr.exits import Exit
from mcgyvr.mcorch import anthropic, bind, serve
from mcgyvr.mcorch.wire import RungCall
from tests import livejournal as lj
from tests._helpers import write_setup

SETUP = """\
profile: dev
deployment: local-only
users: 2
units:
  big:
    address: http://box.invalid:8080
    model: big-model
    rig: box
    width: 2
    window: 65536
  small:
    address: http://box.invalid:8081
    model: small-model
    rig: box
    width: 4
    window: 4096
ladder:
- small
orchestrator:
  type: mcorch
  unit: big
  authoring: direct
  tools: [Read, Bash]
jev:
  unit: small
"""


def _posted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    posted: list[tuple[str, dict[str, Any]]] = []

    def rung_wire(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append((url, payload))
        return {
            "model": "big-model",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "Bash",
                                    "arguments": '{"command": "ls"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    def jev_wire(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append((url, payload))
        return {
            "model": "small-model",
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "top_logprobs": [
                                    {"token": "A", "logprob": -0.1},
                                    {"token": "B", "logprob": -2.0},
                                ]
                            }
                        ]
                    }
                }
            ],
        }

    monkeypatch.setattr(runner, "_post_json", rung_wire)
    monkeypatch.setattr(decision, "_post_json", jev_wire)
    return posted


def test_the_rung_is_the_orchestrator_role_with_turns_and_tools_on_the_wire(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    posted = _posted(monkeypatch)
    config = parse(SETUP, path=tmp_path)
    bound = bind.bind(config, journal_dir=tmp_path / "journal")
    reply = bound.rung(
        RungCall(
            system="be brief",
            turns=({"role": "user", "content": "list the files"},),
            tools=({"type": "function", "function": {"name": "Bash"}},),
            max_output_tokens=256,
        )
    )
    url, payload = posted[0]
    assert url.startswith("http://box.invalid:8080")
    assert payload["model"] == "big-model"
    assert payload["messages"][0] == {"role": "system", "content": "be brief"}
    assert payload["messages"][1] == {"role": "user", "content": "list the files"}
    assert payload["tools"][0]["function"]["name"] == "Bash"
    assert payload["max_tokens"] == 256
    assert reply.tool_calls[0].name == "Bash"
    assert reply.tool_calls[0].arguments == '{"command": "ls"}'
    assert reply.output_tokens == 5


def test_jev_is_the_jev_role_asked_for_a_single_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    posted = _posted(monkeypatch)
    config = parse(SETUP, path=tmp_path)
    bound = bind.bind(config, journal_dir=tmp_path / "journal")
    answer = bound.jev({"x": 1}, {"pick": Choice("Pick.", {"a": "a", "b": "b"})})
    url, payload = posted[0]
    assert url.startswith("http://box.invalid:8081")
    assert payload["model"] == "small-model"
    assert payload["max_tokens"] == 1
    assert payload["logprobs"] is True
    chosen = answer.answers["pick"]
    assert isinstance(chosen, decision.ChoiceAnswer)
    assert chosen.choice == "a"


def test_the_binding_carries_the_prompt_the_writer_and_the_kept_tools(
    tmp_path: Path,
) -> None:
    config = parse(SETUP, path=tmp_path)
    bound = bind.bind(config, journal_dir=tmp_path / "journal")
    assert bound.writer.startswith("mcorch-")
    assert f"--orchestrator {bound.writer}" in bound.system
    assert "{jev_notes}" in bound.system
    assert bound.keep_tools == ("Read", "Bash")
    assert [strategy.name for strategy in bound.internal] == ["direct"]
    assert (
        bound.transcript.path
        == tmp_path / "journal" / "mcorch" / f"{bound.writer}.jsonl"
    )


def test_mcorch_without_a_jev_unit_is_refused_by_the_loader(tmp_path: Path) -> None:
    without = SETUP.replace("jev:\n  unit: small\n", "")
    with pytest.raises(ConfigSchemaError, match=r"jev\.unit"):
        parse(without, path=tmp_path)


def test_the_command_refuses_a_config_whose_orchestrator_is_not_mcorch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = write_setup(tmp_path / "setup", lj.LADDER)
    code = lj.main(["mcorch", "serve", "--config", str(setup)])
    assert code == Exit.REFUSED
    assert "orchestrator.type" in capsys.readouterr().err


def test_the_command_serves_the_facade_at_the_bind_and_port_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = write_setup(tmp_path / "setup", SETUP)
    made: list[tuple[serve.Facade, str, int]] = []

    class _Server:
        server_address = ("0.0.0.0", 9000)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            return None

    def make_server(facade: serve.Facade, *, bind: str, port: int) -> _Server:
        made.append((facade, bind, port))
        return _Server()

    monkeypatch.setattr(serve, "make_server", make_server)
    code = lj.main(
        [
            "mcorch",
            "serve",
            "--config",
            str(setup),
            "--bind",
            "0.0.0.0",
            "--port",
            "9000",
        ]
    )
    assert code == Exit.OK
    (facade, address, port) = made[0]
    assert (address, port) == ("0.0.0.0", 9000)
    assert facade.model == serve.MODEL_ID
    out = capsys.readouterr().out
    assert "http://0.0.0.0:9000" in out
    assert "mcorch-" in out  # the writer id, so a reader can find the transcript


def test_the_command_binds_the_loopback_and_the_default_port_unless_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = write_setup(tmp_path / "setup", SETUP)
    made: list[tuple[str, int]] = []

    class _Server:
        server_address = (serve.DEFAULT_BIND, serve.FACADE_PORT)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            return None

    def make_server(facade: serve.Facade, *, bind: str, port: int) -> _Server:
        made.append((bind, port))
        return _Server()

    monkeypatch.setattr(serve, "make_server", make_server)
    assert lj.main(["mcorch", "serve", "--config", str(setup)]) == Exit.OK
    assert made == [(serve.DEFAULT_BIND, serve.FACADE_PORT)]


def test_a_turn_through_the_command_is_journaled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted = _posted(monkeypatch)
    journal = tmp_path / "journal"
    config = parse(SETUP + f"journal:\n  dir: {journal}\n", path=tmp_path)
    bound = bind.bind(config, journal_dir=journal)
    facade = bind.facade(bound)
    request = anthropic.parse_request(
        json.dumps(
            {
                "model": "claude-sonnet-x",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "list the files"}],
                "tools": [
                    {
                        "name": "Bash",
                        "description": "run",
                        "input_schema": {"type": "object"},
                    },
                    {
                        "name": "WebSearch",
                        "description": "s",
                        "input_schema": {"type": "object"},
                    },
                ],
            }
        ).encode("utf-8")
    )
    assert isinstance(request, anthropic.MessagesRequest)
    turn = facade.respond(request)
    assert facade.on_turn is not None
    facade.on_turn(request, turn, "tool_use", 0.1)
    rows = [json.loads(line) for line in bound.transcript.path.read_text().splitlines()]
    assert rows[0]["dropped_tools"] == ["WebSearch"]
    assert rows[0]["intent"] == "work"
    assert rows[0]["stop_reason"] == "tool_use"
    # Jev was asked first (the small unit), then the rung (the big unit).
    assert [url.split("/v1")[0] for url, _ in posted] == [
        "http://box.invalid:8081",
        "http://box.invalid:8080",
    ]
