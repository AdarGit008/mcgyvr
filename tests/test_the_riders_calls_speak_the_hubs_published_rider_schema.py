"""A rider's calls to the hub's REST API speak the hub's published rider schema.

The hub publishes the REST API a rider's agent uses beside the agent channel
as a schema of its own (``tests/rig_schema.py`` pins it as
:data:`tests.rig_schema.RIDER`): each method of ``/api/v1/me/rungs`` and the
models it takes and answers (``x-paths``), and every refusal of its
OpenAI-compatible ``/v1`` as a code with its one HTTP status
(``x-openai-errors``).

Held here: the path a sync asks is the one published; the ladder a sync
``POST``s is a request the hub takes, which is closed (a key the hub does not
name is refused, so none is sent); and the listing these tests serve as the
hub's answer is one the hub may send. The refusals read off a hub are the
wire's (:mod:`mcgyvr.hubwire`), held to ``x-openai-errors`` in
``tests/test_the_hub_wire_is_defined_once_in_the_product.py``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tests import rig_schema
from tests.rigsyncs import (
    FIRST,
    SECOND,
    Hub,
    a_reporting_hub,
    a_reporting_setup,
    cli,
    sent,
)

__all__ = ["hub", "setup"]  # the fixtures the tests here take


@pytest.fixture(scope="module")
def rider() -> dict[str, Any]:
    return rig_schema.load(rig_schema.RIDER)


def _ref(rider: dict[str, Any], method: str, part: str) -> str:
    from mcgyvr.rig import rungs

    ref: str = rider["x-paths"][rungs.RUNGS_PATH][method][part]["$ref"]
    return ref


@pytest.fixture
def hub(setup: Path) -> Any:
    with a_reporting_hub(setup) as made:
        yield made


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_reporting_setup(tmp_path, monkeypatch)


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
