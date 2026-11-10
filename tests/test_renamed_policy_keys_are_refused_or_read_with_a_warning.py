"""A renamed policy or fleet key is refused naming its new spelling, or warned about.

A block or unit key that was renamed outright (`orchestrator` is now `proposer`,
a unit's `role` is now `sleep`) is refused, and the refusal names the new
spelling. A key or value that is read for one release under its old name
(`max_redecompositions`, `proposer.authoring: classifier|prose`) loads, and says
`RenamedWarning`.
"""

from __future__ import annotations

import textwrap

import pytest

from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.renamed import RenamedWarning

FLEET = textwrap.dedent(
    """\
    units:
      agent:
        address: http://agent.invalid:8080
        model: coder-30b
    ladder: [agent]
    """
)


def test_an_orchestrator_block_is_refused_naming_proposer() -> None:
    with pytest.raises(ConfigSchemaError, match="proposer"):
        parse(FLEET + "orchestrator:\n  unit: agent\n")


def test_max_replans_is_read_as_max_redecompositions_with_a_warning() -> None:
    with pytest.warns(RenamedWarning, match="max_redecompositions"):
        config = parse(FLEET + "max_redecompositions: 2\n")

    assert config.get("max_redecompositions") == 2


@pytest.mark.parametrize(("old", "new"), [("classifier", "fill"), ("prose", "draft")])
def test_an_old_authoring_value_is_read_as_the_new_one_with_a_warning(
    old: str, new: str
) -> None:
    with pytest.warns(RenamedWarning, match=new):
        config = parse(FLEET + f"proposer:\n  unit: agent\n  authoring: {old}\n")

    assert config.get("proposer.authoring") == new


def test_a_unit_role_is_refused_naming_sleep() -> None:
    text = FLEET.replace(
        "    model: coder-30b\n",
        "    model: coder-30b\n    role: sleeps-until-needed\n",
    )

    with pytest.raises(ConfigSchemaError, match="sleep"):
        parse(text)
