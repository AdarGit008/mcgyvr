"""The orchestrator names its type and how it authors.

``orchestrator.type`` is ``proposer``, the only type: the bound unit drafts
contracts for ``mcgyvr delegate``. ``mcgyvr setup`` writes it from the schema's
own default, so a file that names it loads. ``orchestrator.authoring`` is
``prose`` or ``classifier``, or unset. ``orchestrator.tools`` went with mcorch
and is refused as an unknown key. ``SETUP.md`` documents both live keys.
"""

from __future__ import annotations

import textwrap

import pytest

from mcgyvr import docgen
from mcgyvr.config import Config, ConfigSchemaError, parse
from tests._paths import REPO

SETUP_PATH = REPO / "skills" / "mcgyvr" / "SETUP.md"


def setup(orchestrator: str) -> str:
    return textwrap.dedent(
        """\
        units:
          agent:
            address: http://agent.invalid:8080
            model: coder-30b
        ladder: [agent]
        orchestrator:
          {orchestrator}
        """
    ).format(orchestrator=orchestrator)


def loaded(orchestrator: str) -> Config:
    return parse(setup(orchestrator))


def refused(orchestrator: str) -> str:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(setup(orchestrator))
    return str(exc.value)


def test_an_unset_type_is_the_proposer_and_authoring_is_unset() -> None:
    config = loaded("unit: agent")
    assert config.get("orchestrator.type") == "proposer"
    assert config.get("orchestrator.authoring") is None


def test_the_proposer_loads_with_each_authoring() -> None:
    for authoring in ("prose", "classifier"):
        config = loaded(f"type: proposer\n  unit: agent\n  authoring: {authoring}")
        assert config.get("orchestrator.authoring") == authoring


def test_a_type_or_an_authoring_outside_its_choices_is_refused() -> None:
    message = refused("type: chatty\n  unit: agent")
    assert "orchestrator.type" in message and "proposer" in message
    message = refused("unit: agent\n  authoring: direct")
    assert "orchestrator.authoring" in message and "classifier" in message


def test_the_tools_key_is_refused_as_unknown() -> None:
    message = refused("unit: agent\n  tools: [Read]")
    assert "orchestrator: unknown key 'tools'" in message, message


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


def test_setup_md_documents_the_two_keys_as_the_schema_renders_them() -> None:
    text = SETUP_PATH.read_text(encoding="utf-8")
    assert text == docgen.render_setup()
    for key in ("orchestrator.type", "orchestrator.authoring"):
        assert f"`{key}`" in text, key
    assert "`orchestrator.tools`" not in text
