"""`mcgyvr.config` refuses the retired `source`/`rung`/`tier` words, naming the replacement.

RED. ``mcgyvr.config`` still parses ``mcgyvr.yaml`` under the words ``sources``
and ``ladder.tiers`` (``SOURCE_FIELDS``, ``TIER_FIELDS``, ``LADDER_FIELDS``) —
the vocabulary ``records/plans/fleet-identity.md`` §2 retired in favour of
``fleet.yaml`` (``units``) and ``policy.yaml`` (``ladder`` as unit names). The
intent: a config that names a retired word is refused, naming what replaced it,
exactly as ``mcgyvr.fleet.files`` already refuses them. The assertions in the
~90 tests that still feed the old vocabulary are the migration's blast radius,
not evidence that the words are live.
"""

from __future__ import annotations

import pytest

MINIMAL = """\
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""


def test_a_config_with_the_retired_vocabulary_is_refused_naming_its_replacement() -> None:
    from mcgyvr import config

    with pytest.raises(config.ConfigError, match=r"fleet\.yaml|policy\.yaml|units"):
        config.parse(MINIMAL)
