"""`coding` is gone, with no alias, and every place that took it says what replaced it.

Today's gated `coding` is `mcgyvr-code`; a coding model served raw is `code`. A
config naming `use_case: coding`, `mcgyvr setup --use-case coding` and
`mcgyvr use coding` are each refused, and the refusal names both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.exits import Exit

FLEET = """\
units:
  fast:
    address: http://127.0.0.1:9
    model: fast-coder
ladder: [fast]
"""


def _names_both(text: str) -> None:
    assert "`coding`" in text
    assert "`mcgyvr-code`" in text
    assert "`code`" in text


def test_a_config_naming_coding_is_refused_naming_what_replaced_it() -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        parse(FLEET + "use_case: coding\n")

    _names_both(str(refused.value))


def test_setup_refuses_coding_naming_what_replaced_it() -> None:
    from mcgyvr.cli.commands.setup import _use_case_refused

    refusal = _use_case_refused("coding")

    assert refusal is not None
    _names_both(refusal)


def test_setup_offers_the_four_use_cases() -> None:
    from mcgyvr.cli.commands.setup import _setup_use_cases

    assert _setup_use_cases() == ("mcgyvr-code", "code", "chat", "agent")


def test_use_refuses_coding_and_leaves_the_policy_as_it_was(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.cli import main

    (tmp_path / "fleet.yaml").write_text(
        "units:\n  fast:\n    address: http://127.0.0.1:9\n    model: m\n",
        encoding="utf-8",
    )
    policy = tmp_path / "policy.yaml"
    policy.write_text("use_case: chat\nladder: [fast]\n", encoding="utf-8")

    code = main(["use", "coding", "--config", str(tmp_path)])

    assert code == Exit.USAGE
    _names_both(capsys.readouterr().err)
    assert policy.read_text(encoding="utf-8") == "use_case: chat\nladder: [fast]\n"


def test_setup_refuses_a_jev_unit_for_a_raw_use_case(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    assert main(["setup", "--use-case", "code", "--jev", "fast"]) == 1

    assert "serves its model raw" in capsys.readouterr().err
