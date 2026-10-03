"""A ridden answer is checked as any remote rung's answer is, by the same path.

The owner's ruling: an answer from a relief rung gets the same gate and the
same review as an answer from any other remote (api) rung, and no path of its
own. So:

* its family is the catalog's rule over its unit — it carries a credential, so
  ``api`` — and the verification policy it is judged under is an api rung's;
* its reviewer is chosen as an api rung's is: the unit ``verifier.unit``
  names when one is named, and otherwise none (a hosted rung reviews only when
  named, and no local rung is dearer than an api one);
* the driver, the gate and the review read no relief flag at all: the only
  places a relief rung is told apart are routing (the spill and the ride) and
  the runner's reading of the hub's answers.

These pin what already holds; they change nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.escalate import required_policy
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import family_of
from mcgyvr.verify import NoReviewer, Reviewer, reviewers_for
from tests.test_a_relief_rung_takes_work_only_when_the_riders_own_rung_is_full import (
    API,
    RELIEF,
    RIDE,
    SETUP,
    contract,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "mcgyvr"


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    monkeypatch.setenv("HUB_KEY", "mhu_" + "0" * 16)


def configured(verifier: str = "") -> tuple[Config, SourceMap]:
    config = parse(SETUP.format(fanout="idle", escalations=1) + verifier + RELIEF)
    return config, source_map(config)


def test_a_relief_rung_is_judged_in_the_api_family_under_its_policy() -> None:
    config, _ = configured()

    assert family_of(config, RIDE) == family_of(config, API) == catalog().family("api")
    assert required_policy(contract(), family_of(config, RIDE)) == required_policy(
        contract(), family_of(config, API)
    )


def test_a_named_verifier_reviews_a_ride_as_it_reviews_an_api_rung() -> None:
    config, pool = configured("verifier:\n  unit: local_fast\n")
    reviewers = reviewers_for(config, pool)

    ridden, hosted = reviewers(RIDE), reviewers(API)

    assert isinstance(ridden, Reviewer) and ridden is hosted


def test_with_no_verifier_named_neither_a_ride_nor_an_api_rung_is_reviewed() -> None:
    config, pool = configured()
    reviewers = reviewers_for(config, pool)

    assert isinstance(reviewers(RIDE), NoReviewer)
    assert isinstance(reviewers(API), NoReviewer)


@pytest.mark.parametrize(
    "module",
    ["drive.py", "verify.py", "deliver.py", "consensus.py", "gate"],
)
def test_the_driver_gate_and_review_read_no_relief_flag(module: str) -> None:
    where = SRC / module
    files = sorted(where.rglob("*.py")) if where.is_dir() else [where]

    for path in files:
        assert "relief" not in path.read_text(encoding="utf-8"), path
