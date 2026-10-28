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
    asked = parser.parse_args(["delegate", "x"])
    stated = parser.parse_args(["delegate", "x", "--run", "--jobs", "1"])

    assert isinstance(asked, argparse.Namespace)
    assert asked.jobs is None
    assert stated.jobs == 1


def test_only_mcgyvr_code_provisions_a_local_proposer() -> None:
    assert local_orchestrator(use_case="mcgyvr-code", local_only=True, users=2).provision
    for raw in ("code", "chat", "agent"):
        assert not local_orchestrator(use_case=raw, local_only=True, users=2).provision
