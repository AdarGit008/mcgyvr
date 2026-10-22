"""A result says how its task type was judged, each by its own flow.

Two flows, each with its honest sentence and ``assurance`` label:

- ``code`` a model wrote: ``verified`` by a named reviewer, or ``unverified``
  with the reason — no reviewer configured (set ``verifier.unit``), or the
  configured reviewer's own reason it could not be used.
- ``code`` with a deterministic ``operation``: ``deterministic``, on the
  deterministic gate.

``mcgyvr catalog <type>`` says the same thing the result says.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.cli import main
from mcgyvr.contract import loads
from mcgyvr.escalate import Assurance, Review, judge
from mcgyvr.gate import GateResult

LOCAL = catalog().family("local")
DETERMINISTIC = catalog().family("deterministic")


CODE = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

OPERATION = """
id: tidy
task_type: code
operation: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


# --- the judgement ---------------------------------------------------------


def test_code_with_no_reviewer_says_how_to_configure_one() -> None:
    verdict = judge(loads(CODE), LOCAL, GateResult())
    assert verdict.assurance is Assurance.UNVERIFIED
    assert verdict.detail.startswith(
        "unverified: no reviewer is configured — set `verifier.unit`"
    ), verdict.detail


def test_code_whose_reviewer_cannot_be_used_says_why() -> None:
    why = "review is switched off by `verifier.enabled: false`"
    verdict = judge(loads(CODE), LOCAL, GateResult(), absent=why)
    assert verdict.assurance is Assurance.UNVERIFIED
    assert verdict.detail.startswith(f"unverified: {why}"), verdict.detail


def test_code_a_reviewer_agreed_with_names_the_reviewer() -> None:
    verdict = judge(
        loads(CODE),
        LOCAL,
        GateResult(),
        verifier=lambda: Review.agreed("it does what was asked"),
        reviewer="judge-unit",
    )
    assert verdict.assurance is Assurance.VERIFIED
    assert verdict.detail == "verified by judge-unit: it does what was asked"


def test_a_deterministic_operation_keeps_its_deterministic_wording() -> None:
    verdict = judge(loads(OPERATION), DETERMINISTIC, GateResult())
    assert verdict.assurance is Assurance.DETERMINISTIC
    assert verdict.detail.startswith("accepted on the deterministic gate")


# --- the result file and the command line -----------------------------------


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("code", "`verified`"),
        ("format", "`deterministic`"),
    ],
)
def test_the_catalog_says_what_the_result_says(
    name: str, said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["catalog", name]) == 0
    out = capsys.readouterr().out
    assert said in out, out


def test_a_floor_run_result_is_labelled_deterministic(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `code` contract a tool ran on the floor says so in its result file."""
    import json

    from tests import livejournal as lj

    lj.scripted(monkeypatch)  # nothing scripted: the floor dispatches nothing
    ours = tmp_path / "corpus"
    repo = lj.make_repo(tmp_path / "repo")
    (repo / "src" / "pkg" / "messy.py").write_text("x = {  'a':1 }\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "unformatted")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", OPERATION)

    assert lj.main(lj.run_args(contract, repo, config)) == 0
    (result,) = lj.results(ours)
    written = json.loads(result.read_text(encoding="utf-8"))
    assert written["outcome"] == "accepted"
    assert written["assurance"] == "deterministic"
