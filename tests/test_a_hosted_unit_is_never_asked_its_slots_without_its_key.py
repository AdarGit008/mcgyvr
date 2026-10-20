"""A unit that needs a key is never polled for what it has in flight.

The runner's status read fetches ``/slots`` (or ``/metrics``) with no
credential, so it skips an endpoint that names one. The capacity's server
count and the fleet probe both reach that read through
``runner.unit_in_flight``, which once rebuilt the endpoint without its
credential: every hosted rung got an unauthenticated GET to its provider's
``/slots``, blocking up to the status timeout. Each now carries the unit's own
``api_key_env`` through, and only a keyless unit is asked.
"""

from __future__ import annotations

from typing import Any

import pytest

import mcgyvr.runner as runner
from mcgyvr.config import parse
from mcgyvr.fleet import probe
from mcgyvr.local_pool import source_map
from mcgyvr.pressure import server_counts

CONFIG = """\
units:
  local:
    address: http://localhost:8080
    model: coder-7b
    rig: box
    width: 2
  hosted:
    address: https://api.example.com/v1
    model: vendor-large
    rig: vendor
    width: 1
    api_key_env: EXAMPLE_API_KEY
ladder:
- local
- hosted
"""


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    urls: list[str] = []

    def get_text(url: str, timeout: float) -> str | None:
        urls.append(url)
        return None

    monkeypatch.setattr(runner, "_get_text", get_text)
    return urls


def test_the_capacitys_server_count_does_not_poll_a_hosted_unit(
    fetched: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "not-a-real-key")
    count = server_counts(source_map(parse(CONFIG)))
    assert count("hosted") is None
    assert fetched == [], "a unit that needs a key was asked its status without one"
    count("local")
    assert fetched and fetched[0].startswith("http://localhost:8080/"), fetched


def test_the_fleet_probe_does_not_poll_a_hosted_unit(fetched: list[str]) -> None:
    unit: dict[str, Any] = {
        "address": "https://api.example.com/v1",
        "width": 1,
        "api_key_env": "EXAMPLE_API_KEY",
    }
    assert probe.unit_in_flight("hosted", unit) is None
    assert fetched == []
    probe.unit_in_flight("local", {"address": "http://localhost:8080", "width": 2})
    assert fetched and fetched[0].startswith("http://localhost:8080/"), fetched
