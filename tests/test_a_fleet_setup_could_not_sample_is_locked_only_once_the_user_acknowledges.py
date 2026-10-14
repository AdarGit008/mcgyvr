"""A fleet ``mcgyvr setup`` could not sample is locked only once the user says so.

Owner, 2026-10-14: a fleet that cannot be sampled -- every unit hosted, the
containers not started, a use case with no sample -- is locked self-approved
on no evidence only after the user acknowledges it. Setup prints why it could
not be sampled and what a lock on no evidence means, and asks "Lock it
approved on no evidence? [y/N]"; on the flag path ``--accept-unsampled`` is
that acknowledgment, and without it nothing is locked and the limits say how.

Nothing reaches a machine: detection is substituted and the door is a fake.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr import cli
from mcgyvr.detect import Detection
from mcgyvr.fleet.roots import live_file
from tests import setup_door as sd

HOSTED = "model=hosted-model,address=https://api.hosted.example/v1,api_key_env=K"
ASK = "Lock it approved on no evidence? [y/N] "
START = "Start the serving containers"


@pytest.fixture
def nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mcgyvr.initialize.detect",
        lambda _targets: Detection(backends=(), provenance={"backends": "none"}),
    )


def test_a_hosted_fleet_is_not_locked_without_the_acknowledgment(
    nothing_found: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["setup", "--api", HOSTED]) == 0

    out = capsys.readouterr().out
    assert not live_file().exists()
    assert "could not be sampled: every unit in it is hosted" in out
    assert "--accept-unsampled" in out
    assert "on no evidence" in out


def test_accept_unsampled_locks_a_hosted_fleet_on_no_evidence_and_names_it_live(
    nothing_found: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["setup", "--accept-unsampled", "--api", HOSTED]) == 0

    out = capsys.readouterr().out
    live = json.loads(live_file().read_text(encoding="utf-8"))["fleet"]
    assert live.startswith("own@")
    assert "could not be sampled: every unit in it is hosted" in out
    assert "A lock on no evidence" in out
    assert "Approved your own fleet for live runs on no evidence" in out


def test_accept_unsampled_is_a_decision_so_setup_does_not_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import argparse

    monkeypatch.setattr(cli, "_stdin_isatty", lambda: True)
    args = cli.build_parser().parse_args(["setup", "--accept-unsampled"])
    assert isinstance(args, argparse.Namespace)
    assert not cli._setup_is_interactive(args)


@pytest.mark.parametrize("yes", [True, False])
def test_declining_to_start_the_containers_asks_before_locking_on_no_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], yes: bool
) -> None:
    rig = sd.FakeRig()
    asked = sd.interactive(monkeypatch, rig, {START: False, "no evidence": yes})

    assert cli.main(["setup"]) == 0

    out = capsys.readouterr().out
    assert asked[-1] == ASK
    assert "could not be sampled: its containers were not started" in out
    assert "A lock on no evidence" in out
    assert rig.calls == [], "nothing was started or read"
    if yes:
        live = json.loads(live_file().read_text(encoding="utf-8"))["fleet"]
        assert live.startswith("own@")
        assert "Approved your own fleet for live runs on no evidence" in out
    else:
        assert not live_file().exists()
        assert "The fleet was not locked or made live" in out


def test_the_setup_help_names_the_acknowledgment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        cli.main(["setup", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "--accept-unsampled" in out
    assert "no evidence" in out
