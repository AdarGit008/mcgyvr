"""An mcorch orchestrator names its rung, how it authors, and what tools it keeps.

``orchestrator.type`` picks what the bound unit is. ``proposer``, the default,
is the behaviour that shipped before the key existed: the unit drafts contracts
for ``mcgyvr delegate``. ``mcorch`` makes the bound unit the conversational
agent itself, served to a harness at an Anthropic Messages address.

An mcorch setup is refused at load, naming the key and the fix, unless:

* ``deployment`` is ``local-only`` — mcorch replaces the API-tier orchestrator
  that ``hybrid`` describes;
* ``orchestrator.unit`` is bound, and that unit states its ``window`` — the one
  fact the agent budgets a conversation by;
* ``orchestrator.authoring`` is bound. No default ships, because which strategy
  a local rung does best is still being measured.

``orchestrator.tools`` names the harness tools kept in the rung's prompt; empty
keeps every tool. ``mcgyvr init`` writes ``type: proposer`` from the schema's
own default, and ``SETUP.md`` documents all three keys.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mcgyvr import docgen
from mcgyvr.config import Config, ConfigSchemaError, parse

SETUP_PATH = Path(__file__).resolve().parent.parent / "skills" / "mcgyvr" / "SETUP.md"

#: The harness tools kept when the file names none: Claude Code's and pi's.
KEPT = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "read",
    "write",
    "edit",
    "bash",
    "grep",
    "find",
    "ls",
]


def setup(
    *,
    deployment: str = "local-only",
    orchestrator: str = "type: mcorch\n  unit: agent\n  authoring: direct",
    window: str = "window: 32768",
) -> str:
    return textwrap.dedent(
        """\
        deployment: {deployment}
        units:
          agent:
            address: http://agent.invalid:8080
            model: coder-30b
            rig: box
            {window}
          small:
            address: http://agent.invalid:8081
            model: coder-3b
            rig: box
            window: 8192
        ladder: [small, agent]
        orchestrator:
          {orchestrator}
        jev:
          unit: small
        """
    ).format(deployment=deployment, orchestrator=orchestrator, window=window)


def loaded(**override: str) -> Config:
    return parse(setup(**override))


def refused(**override: str) -> str:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(setup(**override))
    return str(exc.value)


def test_an_unset_type_is_the_proposer_that_shipped_and_keeps_the_harness_tools() -> (
    None
):
    config = loaded(deployment="hybrid", orchestrator="unit: agent")
    assert config.get("orchestrator.type") == "proposer"
    assert config.get("orchestrator.authoring") is None
    assert config.get("orchestrator.tools") == KEPT


def test_an_mcorch_setup_loads_with_its_rung_its_authoring_and_its_tools() -> None:
    for authoring in ("direct", "prose", "classifier"):
        config = loaded(
            orchestrator=(
                f"type: mcorch\n  unit: agent\n  authoring: {authoring}\n"
                "  tools: [Read, Bash]"
            )
        )
        assert config.get("orchestrator.type") == "mcorch"
        assert config.get("orchestrator.unit") == "agent"
        assert config.get("orchestrator.authoring") == authoring
        assert config.get("orchestrator.tools") == ["Read", "Bash"]


def test_an_empty_tools_list_keeps_every_tool() -> None:
    config = loaded(
        orchestrator="type: mcorch\n  unit: agent\n  authoring: direct\n  tools: []"
    )
    assert config.get("orchestrator.tools") == []


def test_a_type_or_an_authoring_outside_its_choices_is_refused() -> None:
    message = refused(orchestrator="type: chatty\n  unit: agent")
    assert "orchestrator.type" in message and "mcorch" in message
    message = refused(orchestrator="type: mcorch\n  unit: agent\n  authoring: guess")
    assert "orchestrator.authoring" in message and "classifier" in message


def test_mcorch_under_hybrid_is_refused_naming_local_only() -> None:
    message = refused(deployment="hybrid")
    assert "orchestrator.type" in message and "deployment" in message, message
    assert "local-only" in message, message


def test_mcorch_with_no_unit_bound_is_refused() -> None:
    message = refused(orchestrator="type: mcorch\n  authoring: direct")
    assert "orchestrator.unit" in message, message


def test_mcorch_whose_unit_states_no_window_is_refused() -> None:
    message = refused(window="width: 1")
    assert "units.agent.window" in message, message


def test_mcorch_with_no_authoring_bound_is_refused_and_ships_no_default() -> None:
    message = refused(orchestrator="type: mcorch\n  unit: agent")
    assert "orchestrator.authoring" in message, message
    for choice in ("direct", "prose", "classifier"):
        assert choice in message, message


def test_init_writes_the_proposer_type_from_the_schemas_own_default() -> None:
    from mcgyvr.config import ORCHESTRATOR_FIELDS
    from mcgyvr.detect import Detection
    from mcgyvr.initialize import build, render_policy
    from mcgyvr.propose import Proposal

    default = {field.name: field.default for field in ORCHESTRATOR_FIELDS}["type"]
    assert default == "proposer"
    written = build(Detection(), Proposal())
    assert written["orchestrator"]["type"] == default
    assert "type: proposer" in render_policy(written)


def test_setup_md_documents_the_three_keys_as_the_schema_renders_them() -> None:
    text = SETUP_PATH.read_text(encoding="utf-8")
    assert text == docgen.render_setup()
    for key in ("orchestrator.type", "orchestrator.authoring", "orchestrator.tools"):
        assert f"`{key}`" in text, key
