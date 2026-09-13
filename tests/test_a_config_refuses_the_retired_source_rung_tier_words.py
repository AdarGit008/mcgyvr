"""`mcgyvr.config` refuses the retired `source`/`rung`/`tier` words, naming
their replacement.

A config that names a retired word is refused, naming what replaced it:
`sources` becomes `units` in `fleet.yaml`, `ladder.tiers` becomes the ladder of
unit names in `policy.yaml`, and a `source` key on a unit is refused as a unit
fact. The reader is ``mcgyvr.fleet.files``; these cases pin the wording it must
give for each word, one case per word.
"""

from __future__ import annotations

import pytest

SOURCES = """\
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
"""

TIERS = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
ladder:
  tiers:
    - name: local_qwen-7b
"""

UNIT_SOURCE = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    source: workstation
ladder:
  - local_qwen-7b
"""


def test_a_config_with_the_retired_vocabulary_is_refused_naming_its_replacement() -> (
    None
):
    """The `sources` block is refused, naming `fleet.yaml` and `units`."""
    from mcgyvr import config

    with pytest.raises(config.ConfigError, match=r"fleet\.yaml.*units"):
        config.parse(SOURCES)


def test_the_tier_ladder_is_refused_naming_policy_yaml_and_unit_names() -> None:
    """`ladder.tiers` is refused, naming `policy.yaml` and unit names."""
    from mcgyvr import config

    with pytest.raises(config.ConfigError, match=r"policy\.yaml.*unit names"):
        config.parse(TIERS)


def test_a_source_key_on_a_unit_is_refused_naming_the_unit_term() -> None:
    """A `source` key on a unit is refused: a unit is the one term."""
    from mcgyvr import config

    with pytest.raises(config.ConfigError, match=r"`source` is retired.*unit"):
        config.parse(UNIT_SOURCE)
