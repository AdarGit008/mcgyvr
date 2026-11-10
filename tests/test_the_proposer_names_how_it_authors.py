"""The proposer block names how it authors.

``proposer.authoring`` is ``fill`` or ``draft``, or unset; the block has no
``type``. ``SETUP.md`` documents the live key.
"""

from __future__ import annotations

import textwrap

import pytest

from mcgyvr import docgen
from mcgyvr.config import Config, ConfigSchemaError, parse
from tests._paths import REPO

SETUP_PATH = REPO / "skills" / "mcgyvr" / "SETUP.md"


def setup(proposer: str) -> str:
    return textwrap.dedent(
        """\
        units:
          agent:
            address: http://agent.invalid:8080
            model: coder-30b
        ladder: [agent]
        proposer:
          {proposer}
        """
    ).format(proposer=proposer)


def loaded(proposer: str) -> Config:
    return parse(setup(proposer))


def refused(proposer: str) -> str:
    with pytest.raises(ConfigSchemaError) as exc:
        parse(setup(proposer))
    return str(exc.value)


def test_authoring_is_unset_unless_written() -> None:
    config = loaded("unit: agent")
    assert config.get("proposer.authoring") is None


def test_the_proposer_loads_with_each_authoring() -> None:
    for authoring in ("fill", "draft"):
        config = loaded(f"unit: agent\n  authoring: {authoring}")
        assert config.get("proposer.authoring") == authoring


def test_an_authoring_outside_its_choices_is_refused() -> None:
    message = refused("unit: agent\n  authoring: direct")
    assert "proposer.authoring" in message and "fill" in message


def test_the_proposer_has_no_type_key() -> None:
    message = refused("type: proposer\n  unit: agent")
    assert "proposer: unknown key 'type'" in message, message


def test_setup_md_documents_the_authoring_key_as_the_schema_renders_it() -> None:
    text = SETUP_PATH.read_text(encoding="utf-8")
    assert text == docgen.render_setup()
    assert "`proposer.authoring`" in text
