"""`mcgyvr-code` is the use case that opts in, and its opt-ins are on by default.

Every stage switch is on unless the policy turns it off (the mode matrix lives
in `test_a_use_case_decides_which_stages_run`). Beyond the switches: proposals
are authored by the classifier when a Jev unit is bound and on, and by prose
otherwise or when the policy says so; `delegate --run` dispatches `--jobs auto`
(the fleet's slots) unless `--jobs N` says otherwise, while a run with no
setup keeps one at a time; and only `mcgyvr-code` provisions a local proposer
unit under `deployment: local-only`, since the raw use cases have no proposer
in their path.
"""

from __future__ import annotations

import argparse

import pytest

from mcgyvr.config import default_jobs, local_orchestrator, parse

FLEET = """\
units:
  fast:
    address: http://127.0.0.1:9
    model: fast-coder
    width: 2
ladder: [fast]
"""


def test_the_classifier_authors_when_a_jev_unit_is_bound_and_on() -> None:
    assert parse(FLEET + "jev:\n  unit: fast\n").authoring == "classifier"


def test_prose_authors_with_no_jev_unit() -> None:
    assert parse(FLEET).authoring == "prose"


def test_a_stated_authoring_wins() -> None:
    stated = FLEET + "jev:\n  unit: fast\norchestrator:\n  authoring: prose\n"

    assert parse(stated).authoring == "prose"


def test_a_raw_use_case_authors_nothing_by_default() -> None:
    raw = FLEET + "use_case: code\njev:\n  unit: fast\n"

    assert parse(raw).authoring == "prose"


def test_mcgyvr_code_dispatches_the_fleets_slots_by_default() -> None:
    assert default_jobs(parse(FLEET)) == 0
    assert default_jobs(parse(FLEET + "use_case: mcgyvr-code\n")) == 0


@pytest.mark.parametrize("use_case", ["code", "chat", "agent"])
def test_other_use_cases_keep_one_at_a_time(use_case: str) -> None:
    assert default_jobs(parse(FLEET + f"use_case: {use_case}\n")) == 1


def test_delegate_jobs_is_unset_until_the_config_decides_it() -> None:
    from mcgyvr.cli import build_parser

    parser = build_parser()
    asked = parser.parse_args(["direct", "x.yaml"])
    stated = parser.parse_args(["direct", "x.yaml", "--jobs", "1"])

    assert isinstance(asked, argparse.Namespace)
    assert asked.jobs is None
    assert stated.jobs == 1


def test_only_mcgyvr_code_provisions_a_local_proposer() -> None:
    assert local_orchestrator(
        use_case="mcgyvr-code", local_only=True, users=2
    ).provision
    for raw in ("code", "chat", "agent"):
        assert not local_orchestrator(use_case=raw, local_only=True, users=2).provision


# --- fan-out and triage follow the use case (F26, #807) ----------------------

JEV = "jev:\n  unit: fast\n"


def test_mcgyvr_code_fans_out_to_idle_rungs_by_default() -> None:
    assert parse(FLEET).ladder.fanout == "idle"
    assert parse(FLEET).get("fanout") == "idle"


@pytest.mark.parametrize("use_case", ["code", "chat", "agent"])
def test_a_raw_use_case_keeps_no_fanout(use_case: str) -> None:
    assert parse(FLEET + f"use_case: {use_case}\n").ladder.fanout == "none"


def test_a_stated_fanout_wins() -> None:
    assert parse(FLEET + "fanout: none\n").ladder.fanout == "none"
    assert parse(FLEET + "fanout: full\n").ladder.fanout == "full"


def test_mcgyvr_code_triages_with_jev_when_jev_is_on() -> None:
    assert parse(FLEET + JEV).get("triage") == "jev"


def test_with_jev_unbound_or_off_triage_is_none() -> None:
    assert parse(FLEET).get("triage") == "none"
    off = FLEET + "jev:\n  unit: fast\n  enabled: false\n"
    assert parse(off).get("triage") == "none"


def test_a_stated_triage_wins() -> None:
    assert parse(FLEET + JEV + "triage: none\n").get("triage") == "none"


def test_a_raw_use_case_triages_with_nobody() -> None:
    assert parse(FLEET + JEV + "use_case: code\n").get("triage") == "none"


def test_the_defaults_are_not_written_as_if_the_user_stated_them() -> None:
    config = parse(FLEET + JEV)
    assert "fanout" not in config.declared and "triage" not in config.declared
