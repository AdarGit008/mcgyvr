"""What runs where is ``fleet.yaml``; how work moves between units is ``policy.yaml``.

RED. Today one ``mcgyvr.yaml`` holds both, under the words ``sources`` and
``ladder.tiers`` (``src/mcgyvr/config.py``: ``SOURCE_FIELDS``, ``TIER_FIELDS``),
and ``mcgyvr.fleet.files`` does not exist. The intent is
``records/plans/fleet-identity.md`` §2 (owner, 2026-09-10 and 2026-09-11).

* ``fleet.yaml`` is locked. It holds the units, the rigs and the fleets, and a
  unit carries every fact about what it is and can physically do: model,
  width, context window, reply size and request timeout.
* ``policy.yaml`` is not locked. It holds how work moves: the ladder, an
  ordered list of unit names, then fanout, attempts, escalations, the task
  timeout, the window fraction, breadth and cleanup. Deterministic-first and
  cheap-first are code (``src/mcgyvr/route.py:3-16``), not settings.
* "source", "rung" and "tier" are gone: a unit is the one term. A file that
  still uses them is refused naming what replaced them, and a key in the wrong
  file is refused naming the file it belongs in.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.red_port.conftest import required

FLEET = """\
units:
  srv2_7b:
    rig: srv2
    address: http://srv2:8002
    engine: vllm
    model: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    width: 8
    window: 4096
    output_tokens: 1024
    request_timeout_s: 180
fleets:
  flt-05:
    layout: {srv2: [[srv2_7b, awake]]}
    next: []
"""
POLICY = """\
ladder: [srv2_7b]
fanout: idle
attempts: {srv2_7b: 1}
max_escalations: 2
"""


def _files() -> Any:
    return required(
        "read what runs where from fleet.yaml and how work moves from policy.yaml",
        lambda: importlib.import_module("mcgyvr.fleet.files"),
    )


def test_a_unit_carries_its_model_width_window_reply_size_and_timeout() -> None:
    files = _files()
    unit = files.load_fleet(FLEET)["units"]["srv2_7b"]
    assert unit["model"] == "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
    assert (unit["width"], unit["window"]) == (8, 4096)
    assert (unit["output_tokens"], unit["request_timeout_s"]) == (1024, 180)


def test_the_policy_ladder_is_an_ordered_list_of_unit_names() -> None:
    files = _files()
    assert list(files.load_policy(POLICY)["ladder"]) == ["srv2_7b"]


def test_a_unit_fact_in_the_policy_file_is_refused_naming_it() -> None:
    files = _files()
    for key in ("model", "width", "window", "output_tokens", "request_timeout_s"):
        with pytest.raises(files.FleetFileError, match=key):
            files.load_policy(POLICY + f"{key}: 1\n")


def test_a_policy_setting_in_the_fleet_file_is_refused_naming_policy_yaml() -> None:
    files = _files()
    with pytest.raises(files.FleetFileError, match=r"policy\.yaml"):
        files.load_fleet(FLEET + "fanout: idle\n")


def test_the_retired_words_are_refused_naming_what_replaced_them() -> None:
    files = _files()
    with pytest.raises(files.FleetFileError, match="units"):
        files.load_fleet("sources:\n  s: {base_url: 'http://srv2:8001'}\n")
    with pytest.raises(files.FleetFileError, match="unit names"):
        files.load_policy("ladder:\n  tiers:\n    - {name: r, source: s, model: m}\n")
