"""`mcgyvr recommend` asks the bound Jev unit, and no other.

`recommend` used to ask whatever answered on `127.0.0.1:8080`, under the model
name `recommend-decision`: a port and a name nobody configured. A unit that
happens to serve there, a ladder rung say, was asked to choose the placement,
and a Jev unit the owner did bind was never asked.

Jev is always opt-in. So the placement is asked through
`mcgyvr.decision.classify_for` of the unit the config's `jev.unit` binds, at
that unit's address and under its model, and only then. With no `jev.unit`,
or no config at all, nothing is asked and nothing is probed: the pick is the
fixed rule's, and the plan says so. A bound Jev unit that does not answer
leaves the pick to the fixed rule too, and the plan names the unit and why.

The rig is invented and answers through the read-only ssh seam; the wire is
faked at `mcgyvr.decision._post_json`, and the reachability probe at
`mcgyvr.availability.probe_endpoint`. What is asserted is which address and
which model each question went to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import availability, decision
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from tests.test_recommend import STORE_DIR, RecordedSsh, run_and_parse

JUDGE = "http://localhost:18009"
#: The port the old code asked, served here by a ladder rung.
RUNG = "http://127.0.0.1:8080"

UNITS = f"""\
units:
  fast:
    address: {RUNG}
    model: example-coder:3b
    rig: local
  judge:
    address: {JUDGE}
    model: example-judge:1b
    rig: local
ladder:
- fast
"""

JEV = "jev:\n  unit: judge\n"


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Answer option A to every question; return each (url, model) asked."""
    monkeypatch.setattr(scan_module, "_ssh", RecordedSsh())
    sent: list[tuple[str, str]] = []
    top = [{"token": "A", "logprob": -0.1}]

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, str(payload["model"])))
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", fake_post)
    return sent


@pytest.fixture
def probed(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every address the reachability probe is asked about; live unless told."""

    class Probed(list[str]):
        down: set[str] = set()

    calls = Probed()

    def fake(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
        calls.append(endpoint.base_url)
        live = endpoint.base_url not in calls.down
        return AvailabilityVerdict(
            source=endpoint.source,
            live=live,
            reason="stub" if live else "connection refused (stub)",
            how="stub",
            elapsed_s=0.0,
        )

    monkeypatch.setattr(availability, "probe_endpoint", fake)
    return calls


def _config(tmp_path: Path, text: str) -> str:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_bound_jev_unit_is_asked_at_its_own_address_and_model(
    wire: list[tuple[str, str]],
    probed: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path, UNITS + JEV)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR, config=config)

    assert code == 0, plan
    assert wire == [(f"{JUDGE}/v1/chat/completions", "example-judge:1b")]
    assert RUNG not in probed
    assert plan["decision"] == "model"
    assert plan["decision_unit"] == "judge"


def test_with_no_jev_unit_nothing_is_asked_or_probed(
    wire: list[tuple[str, str]],
    probed: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rung answers on the old port; it is not Jev, so it is not asked."""
    config = _config(tmp_path, UNITS)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR, config=config)

    assert code == 0, plan
    assert wire == []
    assert list(probed) == []
    assert plan["decision"] == "deterministic"
    assert plan["decision_unit"] is None
    assert "jev.unit" in plan["decision_why"]


def test_with_no_config_at_all_nothing_is_asked_or_probed(
    wire: list[tuple[str, str]],
    probed: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fresh machine has no config: the bare install plans deterministically."""
    monkeypatch.chdir(tmp_path)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)

    assert code == 0, plan
    assert wire == []
    assert list(probed) == []
    assert plan["decision"] == "deterministic"
    assert plan["decision_unit"] is None


def test_a_named_config_that_is_not_there_is_an_error(
    wire: list[tuple[str, str]],
    probed: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A path somebody typed is not the bare install; it is refused, not ignored."""
    from mcgyvr import cli

    code = cli.main(
        [
            "recommend",
            "--use-case",
            "coding",
            "--users",
            "single",
            "--host",
            "box-7.invalid",
            "--config",
            str(tmp_path / "absent"),
        ]
    )

    assert code != 0
    assert wire == []
    assert "absent" in capsys.readouterr().err


def test_a_bound_jev_unit_that_does_not_answer_leaves_the_pick_to_the_rule(
    wire: list[tuple[str, str]],
    probed: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path, UNITS + JEV)
    probed.down.add(JUDGE)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR, config=config)

    assert code == 0, plan
    assert wire == []
    assert list(probed) == [JUDGE]
    assert plan["decision"] == "deterministic"
    assert plan["decision_unit"] == "judge"
    assert "connection refused (stub)" in plan["decision_why"]
