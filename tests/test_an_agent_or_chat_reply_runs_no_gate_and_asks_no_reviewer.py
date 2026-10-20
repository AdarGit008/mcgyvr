"""An `agent` reply runs no gate and asks no reviewer, as a `chat` reply does.

An `agent` contract used to never pass — its `grounded` check
rejected every reply — and the run spent its ladder. Agent and
chat have no gates. So, for both session types:

- the catalog declares no evidence for either, and ``mcgyvr catalog`` and
  ``mcgyvr contract`` say so in the result's own words — served unchecked;
- the reply is accepted as it is, labelled ``unchecked``: no output check runs
  (a reply that cites nothing is not rejected) and nothing escalates on a gate
  verdict;
- no reviewer is asked anything — neither the prose verifier nor the gate's
  typed Jev questions — and a verifier the install cannot serve does not
  refuse a session, which would never have asked it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.cli import main
from mcgyvr.contract import loads
from mcgyvr.escalate import Assurance, how_judged, judge
from mcgyvr.gate import GateResult
from mcgyvr.route import Verdict

LOCAL = catalog().family("local")

CHAT = """\
id: sky
task_type: chat
task: Why is the sky blue?
"""

AGENT = """\
id: brief
task_type: agent
task: Summarise the report.
sources: ["src/report.txt"]
"""

UNCHECKED = "served unchecked: {name} replies are not checked or reviewed."


def _never(*_: Any, **__: Any) -> Any:
    raise AssertionError("a session reply is never checked or reviewed")


@pytest.mark.parametrize("name", ["chat", "agent"])
def test_the_catalog_declares_no_evidence_for_a_session(name: str) -> None:
    kind = catalog().require(name)
    assert kind.session
    assert kind.evidence_names == ()
    assert how_judged(kind) == (
        f"{UNCHECKED.format(name=name)} (assurance `unchecked`)"
    )


def test_no_task_type_declares_the_retired_grounded_check() -> None:
    names = {e.name for kind in catalog().task_types for e in kind.required_evidence}
    assert "grounded" not in names
    assert "grounded" not in {e.name for e in catalog().evidence_kinds}


@pytest.mark.parametrize(("name", "document"), [("chat", CHAT), ("agent", AGENT)])
def test_a_session_reply_is_judged_unchecked(name: str, document: str) -> None:
    verdict = judge(loads(document), LOCAL, GateResult(), verifier=_never)
    assert verdict.verdict is Verdict.PASSED
    assert verdict.assurance is Assurance.UNCHECKED
    assert verdict.detail == UNCHECKED.format(name=name)


@pytest.mark.parametrize("document", [CHAT, AGENT])
def test_no_check_runs_on_a_session_reply(document: str, tmp_path: Path) -> None:
    from types import SimpleNamespace
    from typing import cast

    from mcgyvr.drive import SESSION_REPLY, gate_prose_workspace
    from mcgyvr.sandbox.base import Sandbox

    contract = loads(document)
    (tmp_path / SESSION_REPLY).write_text("No citation here.", encoding="utf-8")

    result = gate_prose_workspace(
        contract, cast(Sandbox, SimpleNamespace(workspace=tmp_path))
    )
    assert result.accepted
    assert result.findings == ()


@pytest.mark.parametrize(("name", "document"), [("chat", CHAT), ("agent", AGENT)])
def test_a_configured_reviewer_is_never_asked_about_a_session_reply(
    name: str, document: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither the prose verifier nor the gate's typed Jev questions."""
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.gate.jev import JevCheck
    from mcgyvr.local_pool import Rung, source_map
    from mcgyvr.route import Try
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from mcgyvr.verify import Reviewer
    from tests.drives import LADDER, _driven, _git

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "report.txt").write_text("The sky is blue.\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    asked: list[str] = []

    def seam(name: str) -> Any:
        # Recorded before it raises: the Jev rung turns a raise into an
        # environment issue, so a raise alone would not show it was asked.
        def asking(*_: Any, **__: Any) -> Any:
            asked.append(name)
            raise AssertionError(f"the reviewer's {name} seam was asked")

        return asking

    reviewer = Reviewer(
        model="another-model",
        ask=seam("ask"),
        decide=seam("decide"),
        jev=JevCheck(decide=seam("jev"), blocking=True),
        unit="judge-unit",
    )
    config = parse_config(LADDER)
    _driven(monkeypatch, "It is blue.")
    with TempDirSandbox(repo) as sandbox:
        judgement = worker_attempt(
            config,
            source_map(config),
            loads(document),
            sandbox,
            reviewers=lambda builder: reviewer,
        )(Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1))

    assert asked == []
    assert judgement.verdict is Verdict.PASSED
    assert judgement.assurance is Assurance.UNCHECKED
    assert judgement.detail == UNCHECKED.format(name=name)


# --- through the command line -------------------------------------------------


def _scripted(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    import mcgyvr.drive as drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    sent: list[str] = []
    queue = list(replies)

    def fake_dispatch(source_map: Any, rung: str, request: Any, **_: Any) -> Completion:
        if not queue:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        sent.append(request.prompt)
        return Completion(
            text=queue.pop(0),
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    from tests.drives import _git

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "report.txt").write_text("The sky is blue.\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(
        "units:\n"
        "  local_qwen-7b:\n"
        "    address: http://localhost:11434\n"
        "    model: qwen2.5-coder:7b\n"
        "    rig: workstation\n"
        "    width: 2\n"
        "ladder:\n"
        "- local_qwen-7b\n"
        "journal:\n"
        f"  dir: {tmp_path / 'journal'}\n",
        encoding="utf-8",
    )
    return path


def _run(
    document: str,
    repo: Path,
    config: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, Any], str]:
    contract = tmp_path / "contract.yaml"
    contract.write_text(document, encoding="utf-8")
    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(config),
            "--orchestrator",
            "t",
        ]
    )
    printed = capsys.readouterr()
    last = printed.out.strip().splitlines()[-1]
    assert last.startswith("result: "), printed.out
    result = json.loads(Path(last.removeprefix("result: ")).read_text("utf-8"))
    return code, result, printed.err


def test_an_agent_reply_that_cites_nothing_is_served_on_the_first_rung(
    repo: Path,
    config: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run 2's 4i: both rungs said no sources were given and `grounded` refused."""
    import mcgyvr.verify as verify

    # A session never consults the reviewer, so none is resolved for it.
    monkeypatch.setattr(verify, "reviewers_for", _never)
    sent = _scripted(monkeypatch, "The report says the sky is blue.")

    code, result, err = _run(AGENT, repo, config, tmp_path, capsys)

    assert code == 0, err
    assert result["outcome"] == "accepted"
    assert result["assurance"] == "unchecked"
    assert result["detail"] == UNCHECKED.format(name="agent")
    assert result["answer"] == "The report says the sky is blue."
    assert len(sent) == 1
    assert "[1] src/report.txt\n```\nThe sky is blue.\n```" in sent[0], sent[0]


def test_an_agent_whose_source_is_missing_ends_in_error_and_sends_nothing(
    repo: Path,
    config: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = _scripted(monkeypatch)

    code, result, _ = _run(
        AGENT.replace("src/report.txt", "src/gone.txt"), repo, config, tmp_path, capsys
    )

    assert code != 0
    assert result["outcome"] == "error"
    assert "src/gone.txt" in result["detail"], result["detail"]
    assert sent == []


@pytest.mark.parametrize(("name", "document"), [("chat", CHAT), ("agent", AGENT)])
def test_mcgyvr_contract_and_catalog_say_a_session_is_served_unchecked(
    name: str, document: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "reply.yaml"
    path.write_text(document, encoding="utf-8")

    assert main(["contract", str(path)]) == 0
    assert UNCHECKED.format(name=name) in capsys.readouterr().out

    assert main(["catalog", name]) == 0
    out = capsys.readouterr().out
    assert UNCHECKED.format(name=name) in out, out
    assert "grounded" not in out, out
