"""A hosted stand-in is said to come from below the verifier on the ladder.

:func:`~mcgyvr.verify.stand_in_rung` takes a hosted stand-in for a hosted
``verifier.unit`` only from the rungs below it on the climb: a rule of place,
read off the ladder, not of price. The words around it said "cheaper": the
reason a run gives when nothing could stand in, the ``verifier.unit``
documentation and the sentence ``setup`` prints about hosted review. A reader
with two hosted units, the cheaper one written above, would be told a rung
qualifies that the rule passes over. Each now says what the rule reads: the
rung's place below the verifier on the ladder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import field_at
from mcgyvr.config import parse as parse_config
from mcgyvr.initialize import initialize, parse_api_unit
from mcgyvr.local_pool import source_map
from mcgyvr.verify import NoReviewer, reviewers_for
from tests.machine_shapes import detection, shape

KEY = "ZETA_TEST_KEY"

#: Two hosted rungs, the lower one named to review: it wrote the change and
#: the only other rung is above it, so nothing may stand in.
HOSTED_PAIR_LOWER_REVIEWS = f"""\
units:
  flash:
    address: https://flash.example.invalid
    model: zeta-flash
    rig: cloud-a
    api_key_env: {KEY}
  pro:
    address: https://pro.example.invalid
    model: zeta-pro
    rig: cloud-b
    api_key_env: {KEY}
ladder:
- flash
- pro
verifier:
  unit: flash
"""


@pytest.fixture(autouse=True)
def _hosted_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted rungs are offered."""
    monkeypatch.setenv(KEY, "invented")


def test_the_no_stand_in_reason_names_the_ladder_not_the_price() -> None:
    config = parse_config(HOSTED_PAIR_LOWER_REVIEWS)
    chosen = reviewers_for(config, source_map(config))("flash")

    assert isinstance(chosen, NoReviewer), chosen
    assert "below a hosted `verifier.unit` on the ladder" in chosen.reason, (
        chosen.reason
    )
    assert "cheaper" not in chosen.reason, chosen.reason


def test_the_verifier_unit_doc_names_the_ladder_not_the_price() -> None:
    unit = field_at("verifier.unit")
    assert unit is not None
    assert "below it on the ladder" in unit.doc, unit.doc
    assert "cheaper than it" not in unit.doc, unit.doc


def test_setup_says_a_hosted_unit_stands_in_from_below_on_the_ladder(
    tmp_path: Path,
) -> None:
    spec = (
        "model=claude-opus-5,"
        "address=https://api.anthropic.com,"
        "api_key_env=ANTHROPIC_API_KEY"
    )
    result = initialize(
        tmp_path / "setup",
        detection=detection(shape("bare")),
        api_units=(parse_api_unit(spec),),
    )
    said = " ".join(" ".join(result.limits).split())
    assert "stands in for a hosted named one above it on the ladder" in said, said
    assert "dearer named one" not in said, said
