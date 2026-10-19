"""``mcgyvr setup`` refuses the ``media-gen`` use case, naming the three left.

Owner, #731 item 4: ``media-gen`` has no sample, so setup could not sample it.
It is off until its sample is built: setup offers ``coding``, ``chat`` and
``agent``, coding first as the default, and a ``--use-case media-gen`` or a
config naming it is refused in one plain line naming those three. The
``media`` task type and its catalog use case are untouched.
"""

from __future__ import annotations

import pytest

from mcgyvr import cli, config
from mcgyvr.cli.commands.setup import _setup_use_cases
from mcgyvr.fleet.roots import data_home

THE_THREE = "`coding`, `chat` or `agent`"

MEDIA_GEN_CONFIG = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
ladder:
  - local_qwen-7b
use_case: media-gen
"""


def test_setup_offers_three_use_cases_and_coding_is_the_default() -> None:
    assert _setup_use_cases() == ("coding", "chat", "agent")


def test_use_case_media_gen_is_refused_in_one_line_naming_the_three(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["setup", "--use-case", "media-gen"]) == 1

    captured = capsys.readouterr()
    (line,) = captured.err.splitlines()
    assert line.startswith("error: --use-case `media-gen` is retired"), line
    assert THE_THREE in line, line
    assert captured.out == ""
    assert not (data_home() / "setup").exists(), "nothing is staged"


def test_a_use_case_setup_never_offered_is_refused_naming_the_three(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["setup", "--use-case", "poetry"]) == 1

    (line,) = capsys.readouterr().err.splitlines()
    assert "`poetry` is not a use case" in line and "coding, chat or agent" in line


def test_a_config_naming_media_gen_is_refused_naming_the_three() -> None:
    with pytest.raises(config.ConfigError, match=r"`media-gen` is retired") as raised:
        config.parse(MEDIA_GEN_CONFIG)

    assert THE_THREE in str(raised.value)
