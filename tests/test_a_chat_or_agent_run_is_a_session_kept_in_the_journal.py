"""A `chat` or `agent` run is a session, and its answer is kept.

Chat and agent are sessions and are logged as such: an answer is never thrown
away. So:

- a `chat` or `agent` contract names no `target` and no `scope`: nothing is
  written, so there is no file to name. One that still gives a target is told
  it is not written, and its reply is never a file (`output_schema` is `prose`);
- `mcgyvr contract` prints no `target:` or `allow:` line for one;
- the run writes a session record under the journal's `sessions/`, holding the
  question, the answer, the unit that answered, timestamps, the assurance and
  the outcome; the result file points at it and stderr names it;
- nothing lands in the repository;
- `mcgyvr sessions` lists the records and shows one.

The command is exercised through ``mcgyvr.cli.main`` with ``drive.dispatch``
scripted, as the recorded-run tests do
(``tests/test_a_recorded_run_is_written_under_the_orchestrator_that_ran_it.py``):
config, route, sandbox, prompt, parse and gate are real.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import ContractSchemaError, loads

CHAT = """\
id: sky
task_type: chat
task: Why is the sky blue?
stop_conditions: ["The question is not stated."]
"""

AGENT = """\
id: brief
task_type: agent
task: Summarise the report.
stop_conditions: ["The sources are not stated."]
sources: ["src/report.txt"]
"""

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_IDENTITY},
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "report.txt").write_text("The sky is blue.\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def journal(tmp_path: Path) -> Path:
    return tmp_path / "journal"


@pytest.fixture
def config(tmp_path: Path, journal: Path) -> Path:
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
        f"  dir: {journal}\n",
        encoding="utf-8",
    )
    return path


def _scripted(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer each dispatch from a script, and keep the prompts that were sent."""
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


def _main(argv: Sequence[str]) -> int:
    from mcgyvr.cli import main

    try:
        return main(list(argv))
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2


def _tree(repo: Path) -> list[str]:
    """Every path in the working tree outside .git, so a stray file shows."""
    return sorted(
        str(p.relative_to(repo))
        for p in repo.rglob("*")
        if ".git" not in p.relative_to(repo).parts
    )


# --- the contract -----------------------------------------------------------


@pytest.mark.parametrize("document", [CHAT, AGENT])
def test_a_chat_or_agent_contract_needs_no_target_and_no_scope(document: str) -> None:
    contract = loads(document)
    assert contract.is_session
    assert contract.target == ""
    assert contract.scope.allow == ()
    # Its reply is never a file: prose is what a session answers in.
    assert contract.output_schema == "prose"


@pytest.mark.parametrize("document", [CHAT, AGENT])
def test_a_chat_or_agent_contract_needs_no_stop_condition(document: str) -> None:
    """A session replies in prose, where no BLOCKED reply is heard."""
    bare = "\n".join(
        line for line in document.splitlines() if not line.startswith("stop_")
    )
    contract = loads(bare)
    assert contract.stop_conditions == ()
    assert contract.output_schema == "prose"


def test_a_chat_contract_that_asks_for_a_file_reply_is_refused() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(CHAT + "output_schema: whole_file\n")
    said = str(exc.value)
    assert said.startswith("output_schema:"), said
    assert "session" in said, said


def test_code_still_needs_its_target() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(
            "id: c\ntask_type: code\ntask: Set VALUE.\nstop_conditions: [x]\n"
            "scope:\n  allow: ['src/**']\n"
        )
    assert str(exc.value).startswith("target: required key is not set"), exc.value


def test_mcgyvr_contract_names_no_file_for_a_chat_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "sky.yaml"
    path.write_text(CHAT, encoding="utf-8")

    assert _main(["contract", str(path)]) == 0

    out = capsys.readouterr().out
    lines = [line.strip() for line in out.splitlines()]
    assert not any(line.startswith(("target:", "allow:")) for line in lines), out
    assert "session" in out, out


def test_mcgyvr_contract_says_a_given_target_is_not_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "sky.yaml"
    path.write_text(
        CHAT + "target: notes/sky.md\nscope:\n  allow: ['notes/**']\n",
        encoding="utf-8",
    )

    assert _main(["contract", str(path)]) == 0

    out = capsys.readouterr().out
    lines = [line.strip() for line in out.splitlines()]
    assert not any(line.startswith(("target:", "allow:")) for line in lines), out
    assert "notes/sky.md is not written" in out, out


# --- the run ----------------------------------------------------------------


def _run(
    contract: Path, repo: Path, config: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, Any], str]:
    code = _main(
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


@pytest.mark.parametrize(
    ("name", "document", "reply", "assurance"),
    [
        ("sky", CHAT, "Rayleigh scattering.", "unchecked"),
        ("brief", AGENT, "The sky is blue [1].", "unchecked"),
    ],
)
def test_a_session_run_keeps_its_answer_in_a_session_record(
    name: str,
    document: str,
    reply: str,
    assurance: str,
    repo: Path,
    config: Path,
    journal: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = _scripted(monkeypatch, reply)
    contract = tmp_path / f"{name}.yaml"
    contract.write_text(document, encoding="utf-8")
    before = _tree(repo)

    code, result, err = _run(contract, repo, config, capsys)

    assert code == 0, err
    assert result["outcome"] == "accepted"
    assert result["answer"] == reply
    assert result["target"] == ""
    # The worker is not told about a file, because none is written.
    assert "TARGET" not in sent[0], sent[0]

    record_path = Path(result["session_record"])
    assert record_path.parent == journal / "sessions"
    assert f"session: {record_path}" in err, err
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["session"] == record_path.stem
    assert record["task_type"] == loads(document).task_type
    assert record["question"] == loads(document).task
    assert record["answer"] == reply
    assert record["unit"] == "local_qwen-7b"
    assert record["assurance"] == assurance
    assert record["outcome"] == "accepted"
    assert record["started"] and record["finished"]
    assert record["contract"]["path"] == str(contract)
    assert (
        record["contract"]["sha256"]
        == hashlib.sha256(contract.read_bytes()).hexdigest()
    )
    assert record["contract"]["text"] == document
    assert record["result"] == str(
        journal / "results" / f"{result['contract']}-{result['run']}.json"
    )
    assert record["orchestrator"] == "t"

    # Nothing in the repository: no file, no change, no commit.
    assert _tree(repo) == before
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"


def test_a_session_that_was_not_accepted_is_kept_too(
    repo: Path,
    config: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A source the tree does not hold: the run ends in error before anything
    # is sent, and the session is kept all the same.
    _scripted(monkeypatch)
    contract = tmp_path / "brief.yaml"
    contract.write_text(
        AGENT.replace("src/report.txt", "src/gone.txt"), encoding="utf-8"
    )

    code, result, _ = _run(contract, repo, config, capsys)

    assert code == 1
    record = json.loads(Path(result["session_record"]).read_text(encoding="utf-8"))
    assert record["outcome"] == result["outcome"] != "accepted"
    assert record["answer"] == ""


def test_mcgyvr_sessions_lists_the_records_and_shows_one(
    repo: Path,
    config: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _scripted(monkeypatch, "Rayleigh scattering.")
    contract = tmp_path / "sky.yaml"
    contract.write_text(CHAT, encoding="utf-8")
    _, result, _ = _run(contract, repo, config, capsys)
    session = Path(result["session_record"]).stem

    assert _main(["sessions", "--config", str(config)]) == 0
    listed = capsys.readouterr().out
    assert session in listed, listed
    assert "Why is the sky blue?" in listed, listed

    assert _main(["sessions", session, "--config", str(config)]) == 0
    shown = capsys.readouterr().out
    assert "Why is the sky blue?" in shown, shown
    assert "Rayleigh scattering." in shown, shown

    assert _main(["sessions", "no-such-session", "--config", str(config)]) == 1
    assert "no-such-session" in capsys.readouterr().err


def test_mcorch_guards_no_file_for_a_session_contract() -> None:
    """A session writes nothing, so a target it gave anyway is no one's to guard."""
    from mcgyvr.mcorch.guard import open_targets

    written = {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "name": "Write",
                "input": {
                    "file_path": "sky.yaml",
                    "content": CHAT + "target: notes/sky.md\n",
                },
            }
        ],
    }
    assert open_targets([written]) == {}


@pytest.mark.parametrize("name", ["chat", "agent"])
def test_the_catalog_says_a_chat_or_agent_run_is_a_session(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(["catalog", name]) == 0
    out = capsys.readouterr().out
    assert "session log" in out, out
    assert "never written" in out, out


@pytest.mark.parametrize(
    ("document", "said"),
    [
        (CHAT, "served unchecked: chat replies are not checked or reviewed."),
        (AGENT, "served unchecked: agent replies are not checked or reviewed."),
    ],
)
def test_mcgyvr_contract_says_how_a_reply_is_judged_as_the_result_does(
    document: str, said: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No gate or reviewer is claimed for a reply: the result's own sentence."""
    path = tmp_path / "reply.yaml"
    path.write_text(document + 'acceptance: ["true"]\n', encoding="utf-8")

    assert _main(["contract", str(path)]) == 0

    out = capsys.readouterr().out
    assert said in out, out
    assert "verified by" not in out, out
    assert "the gate's own checks decide" not in out, out
    assert "$ true" not in out, out
    assert "acceptance: not run" in out, out


def test_mcgyvr_contract_for_code_still_names_its_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "code.yaml"
    path.write_text(
        "id: c\ntask_type: code\ntask: Set VALUE.\ntarget: src/a.py\n"
        "stop_conditions: [x]\nlimits:\n  max_output_tokens: 256\n"
        "scope:\n  allow: ['src/**']\n",
        encoding="utf-8",
    )

    assert _main(["contract", str(path)]) == 0

    out = capsys.readouterr().out
    assert "risk:    medium — verified by gate only" in out, out
    assert "acceptance: none declared — the gate's own checks decide" in out, out
