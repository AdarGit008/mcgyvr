"""A sync reports the rider's ladder to the hub, and nothing else.

``mcgyvr rig rungs sync`` ``POST``s ``{"ladder": ...}`` to ``/api/v1/me/rungs``
so the hub can place each host's model against the rider's own: above their
ceiling, below their floor, or within. What is sent is the ladder's shape:

* the model rungs, in the order work climbs them — families cheapest first,
  and the ladder's own order within a family — each with its model, its family
  (``local`` or ``api``), the weights file's size where the product knows it
  (a unit's geometry scan), and its parameter count in billions where the
  product knows it (the scan, else the shipped capability table); ``null``
  where it does not;
* ``floor``, the rung work starts on, and ``ceiling``, the highest rung
  ``max_escalations`` lets it reach from there.

Never an address, a key, or the name of a variable holding one; never a
relief rung, which is not the rider's ladder. The body is checked against the
contract before it is sent, and a ladder the contract cannot carry is refused
without asking the hub.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_rig_rungs_sync_writes_only_the_relief_rungs import (
    FIRST,
    KEY,
    TOKEN,
    Hub,
    cli,
    serving,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gguf_geometry.json"
SCANNED = "4b-Q4_K_M.gguf"

FLEET = """\
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
    launch:
      geometry_json: geometry.json
  local_big:
    address: http://big-box.example:8001
    model: "qwen2.5-coder:7b"
    width: 1
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    width: 1
    api_key_env: EXAMPLE_API_KEY
"""


def policy(ladder: str, escalations: int) -> str:
    return f"ladder: [{ladder}]\nfanout: idle\nmax_escalations: {escalations}\n"


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "setup"
    folder.mkdir()
    (folder / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (folder / "policy.yaml").write_text(
        policy("local_fast, local_big, api_big", 1), encoding="utf-8"
    )
    row = json.loads(FIXTURE.read_text(encoding="utf-8"))[SCANNED]
    (folder / "geometry.json").write_text(json.dumps(row), encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(folder))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "config-folder"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data-folder"))
    monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "e" * 24)
    return folder


@pytest.fixture
def hub(setup: Path) -> Any:
    from mcgyvr.rig import credentials

    with serving(Hub()) as running:
        credentials.save(credentials.Credentials(hub=running.address, token=TOKEN))
        running.answer(running.listing(FIRST))
        yield running


def sent(hub: Hub) -> dict[str, Any]:
    (asked,) = hub.asked[-1:]
    assert asked["content_type"] == "application/json"
    body: dict[str, Any] = json.loads(asked["body"])
    return body


def test_the_ladder_is_posted_in_climbing_order_with_what_the_product_knows(
    setup: Path, hub: Hub
) -> None:
    scan = json.loads(FIXTURE.read_text(encoding="utf-8"))[SCANNED]

    assert cli() == 0

    assert sent(hub) == {
        "ladder": {
            "rungs": [
                {
                    "model": "qwen2.5-coder-3b",
                    "family": "local",
                    "size_bytes": scan["size_bytes"],
                    "params_b": scan["params_total"] / 1e9,
                },
                {
                    "model": "qwen2.5-coder:7b",
                    "family": "local",
                    "size_bytes": None,
                    "params_b": 7.0,
                },
                {
                    "model": "vendor-large",
                    "family": "api",
                    "size_bytes": None,
                    "params_b": None,
                },
            ],
            "floor": 0,
            "ceiling": 1,
        }
    }


@pytest.mark.parametrize(("escalations", "ceiling"), [(0, 0), (1, 1), (5, 2)])
def test_the_ceiling_is_as_far_as_max_escalations_lets_work_climb(
    setup: Path, hub: Hub, escalations: int, ceiling: int
) -> None:
    (setup / "policy.yaml").write_text(
        policy("local_fast, local_big, api_big", escalations), encoding="utf-8"
    )

    assert cli() == 0

    assert (sent(hub)["ladder"]["floor"], sent(hub)["ladder"]["ceiling"]) == (
        0,
        ceiling,
    )


def test_a_ladder_written_out_of_order_is_reported_in_the_order_work_climbs(
    setup: Path, hub: Hub
) -> None:
    (setup / "policy.yaml").write_text(
        policy("api_big, local_big", 1), encoding="utf-8"
    )

    assert cli() == 0

    rungs = sent(hub)["ladder"]["rungs"]
    assert [r["family"] for r in rungs] == ["local", "api"]


def test_no_address_key_or_variable_name_is_ever_sent(setup: Path, hub: Hub) -> None:
    assert cli() == 0
    raw = hub.asked[-1]["body"].decode("utf-8")

    for never in (
        "fast-box.example",
        "big-box.example",
        "api.example.com",
        "http",
        "EXAMPLE_API_KEY",
        "MCGYVR_HUB_API_KEY",
        KEY,
        "e" * 24,
        TOKEN,
        "geometry.json",
    ):
        assert never not in raw
    body = json.loads(raw)
    assert set(body) == {"ladder"}
    assert set(body["ladder"]) == {"rungs", "floor", "ceiling"}
    for each in body["ladder"]["rungs"]:
        assert set(each) == {"model", "family", "size_bytes", "params_b"}


def test_a_relief_rung_is_not_part_of_the_reported_ladder(
    setup: Path, hub: Hub
) -> None:
    assert cli() == 0
    assert (setup / "relief.yaml").is_file()

    assert cli() == 0

    raw = hub.asked[-1]["body"].decode("utf-8")
    assert "hitchhike" not in raw
    assert len(json.loads(raw)["ladder"]["rungs"]) == 3


def test_a_ladder_the_contract_cannot_carry_is_refused_before_asking(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    fleet = (setup / "fleet.yaml").read_text(encoding="utf-8")
    (setup / "fleet.yaml").write_text(
        fleet.replace("model: vendor-large", "model: vendor large"), encoding="utf-8"
    )

    assert cli() == Exit.ERROR
    assert hub.asked == []
    assert "vendor large" in capsys.readouterr().err


def test_a_scan_that_cannot_be_read_leaves_the_size_unknown(
    setup: Path, hub: Hub
) -> None:
    (setup / "geometry.json").write_text("{}", encoding="utf-8")

    assert cli() == 0

    first = sent(hub)["ladder"]["rungs"][0]
    assert (first["size_bytes"], first["params_b"]) == (None, None)
