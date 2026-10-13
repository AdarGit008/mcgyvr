"""A result says how its task type was judged, each by its own flow.

Four flows, four honest sentences, and an ``assurance`` label that never claims a
review was expected where none ever is:

- ``code`` a model wrote: ``verified`` by a named reviewer, or ``unverified``
  with the reason — no reviewer configured (set ``verifier.unit``), or the
  configured reviewer's own reason it could not be used.
- ``code`` with a deterministic ``operation``: ``deterministic``, on the
  deterministic gate.
- ``chat`` and ``agent``: ``unchecked`` — no checks, never reviewed (owner,
  e2e run 2 R11: "agent and chat have no gates").
- ``media``: ``checked`` — judged by its own output checks, never reviewed.

``mcgyvr catalog <type>`` says the same thing the result says.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.cli import main
from mcgyvr.contract import loads
from mcgyvr.escalate import Assurance, Review, judge
from mcgyvr.gate import GateResult
from mcgyvr.route import Verdict

LOCAL = catalog().family("local")
DETERMINISTIC = catalog().family("deterministic")

CHAT = """
id: answer
task_type: chat
task: Answer the question.
target: answer.txt
stop_conditions: ["The question is not stated."]
output_schema: prose
scope:
  allow: ["answer.txt"]
"""

AGENT = """
id: brief
task_type: agent
task: Write a brief.
target: brief.txt
stop_conditions: ["The sources are not stated."]
output_schema: prose
sources: ["src/report.txt"]
scope:
  allow: ["brief.txt"]
"""

MEDIA = """
id: picture
task_type: media
task: Draw a red square.
target: out/square.png
stop_conditions: ["The size is not stated."]
output_schema: media_artifact
media_kind: image
scope:
  allow: ["out/**"]
"""

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


def _never() -> Review:
    raise AssertionError("a reply is never sent to a reviewer")


# --- the judgement ---------------------------------------------------------


@pytest.mark.parametrize("document", [CHAT, AGENT])
def test_a_chat_or_agent_reply_is_served_unchecked_and_never_reviewed(
    document: str,
) -> None:
    contract = loads(document)
    verdict = judge(contract, LOCAL, GateResult(), verifier=_never)
    assert verdict.verdict is Verdict.PASSED
    assert verdict.assurance is Assurance.UNCHECKED
    assert verdict.detail == (
        f"served unchecked: {contract.task_type} replies are not checked or reviewed."
    )


@pytest.mark.parametrize(("document", "checks"), [(MEDIA, "media_valid")])
def test_a_media_reply_is_checked_by_its_output_checks(
    document: str, checks: str
) -> None:
    contract = loads(document)
    verdict = judge(contract, LOCAL, GateResult(), verifier=_never)
    assert verdict.verdict is Verdict.PASSED
    assert verdict.assurance is Assurance.CHECKED
    assert verdict.detail == (
        f"accepted on its output checks ({checks}); "
        f"{contract.task_type} replies are never reviewed."
    )


@pytest.mark.parametrize("document", [CHAT, AGENT, MEDIA])
def test_no_reply_reads_as_a_review_that_was_expected(document: str) -> None:
    verdict = judge(loads(document), LOCAL, GateResult())
    said = verdict.detail.lower()
    for wrong in ("unverified", "verifier", "this install has none", "gate alone"):
        assert wrong not in said, said


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


# --- the driver: a configured reviewer is never reported as absent ----------


def test_a_chat_reply_with_a_reviewer_configured_is_not_told_there_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.local_pool import Rung, source_map
    from mcgyvr.route import Try
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from mcgyvr.verify import Reviewer
    from tests.drives import LADDER, _driven, _git

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README").write_text("x\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    def unasked(prompt: str) -> str:
        raise AssertionError("a reply is never sent to a reviewer")

    configured = Reviewer(model="other", ask=unasked, unit="judge-unit")
    config = parse_config(LADDER)
    _driven(monkeypatch, "The sky is blue.")
    with TempDirSandbox(repo) as sandbox:
        judgement = worker_attempt(
            config,
            source_map(config),
            loads(CHAT),
            sandbox,
            reviewers=lambda builder: configured,
        )(Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1))

    assert judgement.assurance is Assurance.UNCHECKED
    assert "this install has none" not in judgement.detail


# --- the result file and the command line -----------------------------------


def test_the_result_file_carries_the_label_and_the_sentence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli
    from mcgyvr.deliver import Accepted
    from mcgyvr.drive import gate_prose_workspace
    from mcgyvr.escalate import Delivered
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from tests.drives import _git

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README").write_text("x\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    contract = loads(CHAT)
    report = RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        orchestrator="t",
    )
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / contract.target).write_text("Hi.\n", encoding="utf-8")
        gated = gate_prose_workspace(contract, sandbox)
        bound = Accepted.read(repo=sandbox.workspace, contract=contract, result=gated)
        judgement = judge(contract, LOCAL, gated)
        outcome = Delivered(
            family=LOCAL,
            rung="local_qwen-7b",
            assurance=Assurance.UNCHECKED,
            judgement=judgement.__class__(
                verdict=judgement.verdict,
                assurance=judgement.assurance,
                detail=judgement.detail,
                accepted=bound,
            ),
            entered=(),
            history=(
                Attempted(rung="local_qwen-7b", attempt=1, verdict=Verdict.PASSED),
            ),
            attempts_spent=1,
            escalations=0,
        )
        code = cli._report_climb(
            argparse.Namespace(commit=False),
            contract,
            sandbox,
            repo,
            outcome,
            None,
            report,
        )
    printed = capsys.readouterr()
    assert code == 0
    assert report.assurance == "unchecked"
    assert (
        report.detail == "served unchecked: chat replies are not checked or reviewed."
    )
    assert "(unchecked)" in printed.out
    assert "UNVERIFIED" not in printed.err


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("chat", "served unchecked: chat replies are not checked or reviewed."),
        ("agent", "served unchecked: agent replies are not checked or reviewed."),
        (
            "media",
            "accepted on its output checks (media_valid); "
            "media replies are never reviewed.",
        ),
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


def test_the_catalog_names_each_reply_types_label(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name, label in (
        ("chat", "unchecked"),
        ("agent", "unchecked"),
        ("media", "checked"),
    ):
        assert main(["catalog", name]) == 0
        out = capsys.readouterr().out
        assert f"assurance `{label}`" in out, out


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
