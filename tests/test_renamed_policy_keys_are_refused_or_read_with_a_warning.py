"""A renamed policy or fleet key is refused naming its new spelling, or warned about.

A block or unit key that was renamed outright (`orchestrator` is now `proposer`,
a unit's `role` is now `sleep`) is refused, and the refusal names the new
spelling. A key or value that is read for one release under its old name
(`max_redecompositions`, `proposer.authoring: classifier|prose`) loads, and says
`RenamedWarning`.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

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
    with pytest.raises(ConfigSchemaError, match="`orchestrator` is now `proposer`"):
        parse(FLEET + "orchestrator:\n  unit: agent\n")


def test_max_replans_is_read_as_max_redecompositions_with_a_warning() -> None:
    with pytest.warns(RenamedWarning, match="max_redecompositions"):
        config = parse(FLEET + "max_replans: 2\n")

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

    with pytest.raises(ConfigSchemaError, match="`role` is now `sleep`"):
        parse(text)


@pytest.mark.parametrize("value", ["[fill]", "{fill: 1}"])
def test_an_authoring_that_is_not_text_is_refused_by_the_schema(value: str) -> None:
    with pytest.raises(ConfigSchemaError, match=r"proposer\.authoring"):
        parse(FLEET + f"proposer:\n  unit: agent\n  authoring: {value}\n")


def test_a_version_1_delegate_log_is_read_with_its_kinds_renamed(
    tmp_path: Path,
) -> None:
    import json

    from mcgyvr.delegate_log import OLD_SCHEMA_ID, DelegateKind, read

    path = tmp_path / "log.json"
    path.write_text(
        json.dumps(
            {
                "schema": OLD_SCHEMA_ID,
                "kind": "orchestrator_unavailable",
                "message": "m",
                "exit_code": 1,
                "raw_reply_present": False,
                "contracts": [],
                "refusals": [],
            }
        )
    )

    with pytest.warns(RenamedWarning, match="proposer_unavailable"):
        log = read(path)

    assert log.kind is DelegateKind.PROPOSER_UNAVAILABLE
