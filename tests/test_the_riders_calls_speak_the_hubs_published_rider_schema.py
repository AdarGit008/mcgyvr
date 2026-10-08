"""A rider's calls to the hub's REST API speak the hub's published rider schema.

The hub publishes the REST API a rider's agent uses beside the agent channel
as a schema of its own (``tests/rig_schema.py`` pins it as
:data:`tests.rig_schema.RIDER`): each method of ``/api/v1/me/rungs`` and the
models it takes and answers (``x-paths``), and every refusal of its
OpenAI-compatible ``/v1`` as a code with its one HTTP status
(``x-openai-errors``).

Held here: the path a sync asks is the one published; the ladder a sync
``POST``s is a request the hub takes, which is closed (a key the hub does not
name is refused, so none is sent); the listing these tests serve as the
hub's answer is one the hub may send; and every refusal read off a hub, by
its status and code, is a pair the hub publishes, with that status: the busy
answers a sync writes into ``relief.yaml`` (:data:`mcgyvr.rig.rungs.BUSY`),
and those the runner still names itself.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from tests import rig_schema
from tests.test_a_sync_reports_the_riders_ladder_and_nothing_else import (
    hub,
    sent,
    setup,
)
from tests.test_rig_rungs_sync_writes_only_the_relief_rungs import (
    FIRST,
    SECOND,
    Hub,
    cli,
)

__all__ = ["hub", "setup"]  # the fixtures the tests here take


@pytest.fixture(scope="module")
def rider() -> dict[str, Any]:
    return rig_schema.load(rig_schema.RIDER)


def _ref(rider: dict[str, Any], method: str, part: str) -> str:
    from mcgyvr.rig import rungs

    ref: str = rider["x-paths"][rungs.RUNGS_PATH][method][part]["$ref"]
    return ref


def test_the_path_a_sync_asks_is_the_one_the_hub_publishes(
    rider: dict[str, Any],
) -> None:
    from mcgyvr.rig import rungs

    assert set(rider["x-paths"][rungs.RUNGS_PATH]) >= {"get", "post"}
    assert rungs.rungs_url("https://hub.example") == (
        "https://hub.example" + rungs.RUNGS_PATH
    )


def test_the_ladder_a_sync_posts_is_a_request_the_hub_takes(
    rider: dict[str, Any], setup: Any, hub: Hub
) -> None:
    assert cli() == 0
    body = sent(hub)

    rig_schema.validate(body, rider, _ref(rider, "post", "request"))

    widened = copy.deepcopy(body)
    rung = widened["ladder"]["rungs"][0]
    rung["address"] = "http://fast-box.example:8000"
    with pytest.raises(rig_schema.SchemaError):
        rig_schema.validate(widened, rider, _ref(rider, "post", "request"))
    with pytest.raises(rig_schema.SchemaError, match="address"):
        rig_schema.validate(rung, rider, "#/$defs/LadderRungIn")


@pytest.mark.parametrize("ride", [True, False])
def test_the_listing_these_tests_serve_is_an_answer_the_hub_may_send(
    rider: dict[str, Any], ride: bool
) -> None:
    from mcgyvr.rig import rungs

    served = Hub()
    served.address = "http://127.0.0.1:8080"
    listing = served.listing(*((FIRST, SECOND) if ride else ()), ride=ride)
    for method in ("get", "post"):
        rig_schema.validate(listing, rider, _ref(rider, method, "response"))
    read = rungs.read(json.loads(json.dumps(listing)), served.address)
    assert [each.id for each in read.rungs] == ([FIRST, SECOND] if ride else [])


def test_every_busy_answer_a_sync_writes_is_a_published_pair(
    rider: dict[str, Any],
) -> None:
    """The busy answers' home is the hub client: a sync writes them into
    ``relief.yaml``, and the runner reads them from there."""
    from mcgyvr.rig import rungs

    published = rider["x-openai-errors"]
    assert rungs.BUSY
    assert [pair for pair in rungs.BUSY if published.get(pair[1]) != pair[0]] == []


def test_every_hub_refusal_the_runner_reads_is_a_published_pair(
    rider: dict[str, Any],
) -> None:
    """What the runner still names itself: the answers it reads on any rung,
    and the busy answers it falls back to for a ``relief.yaml`` written
    before a sync wrote them."""
    from mcgyvr import runner

    read = set(runner.RELIEF_UNAVAILABLE) | {
        runner.MODEL_UNPLACED,
        runner.UNKNOWN_MODEL,
    }
    published = rider["x-openai-errors"]
    assert [pair for pair in sorted(read) if published.get(pair[1]) != pair[0]] == []
