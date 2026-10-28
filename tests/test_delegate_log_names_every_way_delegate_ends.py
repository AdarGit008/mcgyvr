"""`mcgyvr PROMPT --log PATH` names every way the command ends, as data.

`mcgyvr PROMPT` says how it ended in English on stderr, and its exit code folds
a dozen failures into 1, so a script that called it could only tell them apart
by matching prose — which broke the first time the prose was reworded. With
`--log PATH` it writes one `mcgyvr.delegate_log/1` record there on every exit
once its arguments are read: the `kind` (one per exit path), the exit code
the process returned, the contracts and refusals, and the facts behind a
failure as data. Each test here drives `mcgyvr.cli.main` down one exit path,
with the orchestrator's reply stood in for at `dispatch_role`, and reads the
record back through the module's own `read`, checked against its own schema.

What the module promises a reader is checked too: the exit-code table covers
every kind, a record from a newer writer with a kind this build does not know
still reads, and a record of another schema version is refused.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.delegate as delegate
import mcgyvr.orchestrator as orchestrator
from mcgyvr.cli.commands import delegate as command
from mcgyvr.delegate_log import (
    KIND_EXIT,
    SCHEMA_ID,
    DelegateKind,
    DelegateLog,
    DelegateLogError,
    json_schema,
    read,
)
from mcgyvr.local_pool import Protocol, SourceUnavailableError
from mcgyvr.orchestrator import IndexBuildError
from mcgyvr.runner import Completion, RunnerError, StopReason
from tests import livejournal as lj
from tests.rig_schema import validate

RECORD = "#/$defs/DelegateLog"

CONFIG = """\
units:
  planner:
    address: http://localhost:11434
    model: planner-model
    rig: workstation
    width: 1
ladder:
- planner
orchestrator:
  unit: planner
  model: planner-model
"""

#: A config that loads and binds no orchestrator role.
UNBOUND = """\
units:
  planner:
    address: http://localhost:11434
    model: planner-model
    rig: workstation
    width: 1
ladder:
- planner
"""

PROPOSAL = {
    "task_type": "code",
    "task": "Fix listing to return the items sorted.",
    "target": "listing.py",
    "stop_conditions": ["the documented behaviour is ambiguous"],
}


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


@pytest.fixture(autouse=True)
def no_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A HOME of the test's own, no session in it and no setup discovered."""
    (tmp_path / "home").mkdir()
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))


def _answer(text: str, stop: StopReason = StopReason.COMPLETE) -> Completion:
    return Completion(
        text=text,
        stop_reason=stop,
        raw_stop_reason="stop" if stop is StopReason.COMPLETE else "length",
        model="planner-model",
        source="planner",
        protocol=Protocol.OPENAI,
        max_output_tokens=2000,
        latency_s=0.0,
        output_tokens=2000 if stop is StopReason.TRUNCATED else 120,
    )


def _reply(monkeypatch: pytest.MonkeyPatch, answer: Any) -> None:
    """The orchestrator answers `answer`: a reply, None, or an exception raised."""

    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, str):
            return _answer(answer)
        return answer

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)


def _config(tmp_path: Path, text: str = CONFIG) -> Path:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _delegate(
    tmp_path: Path, root: Path, *extra: str, config: Path | None = None
) -> tuple[int, DelegateLog]:
    """Run `mcgyvr PROMPT` with `--log`, check the record, return the exit and it.

    It plans (`--output DIR`, which needs no session and runs nothing) unless
    the test names `--output` itself, or `--run` to ask for the default run.
    """
    log = tmp_path / "out" / "delegate-log.json"
    argv = ["Fix listing.", "--repo", str(root), "--log", str(log)]
    if "--run" in extra:
        extra = tuple(a for a in extra if a != "--run")
    elif "--output" not in extra:
        argv += ["--output", str(tmp_path / "plan")]
    if config is not None:
        argv += ["--config", str(config)]
    code = lj.main([*argv, *extra])
    data = json.loads(log.read_text(encoding="utf-8"))
    validate(data, json_schema(), RECORD)
    record = read(log)
    assert record.exit_code == code, (record, code)
    assert record.known
    return code, record


def _ended(
    record: DelegateLog, kind: DelegateKind, *, exit_code: int | None = None
) -> None:
    assert record.kind is kind, record
    assert record.exit_code == (KIND_EXIT[kind] if exit_code is None else exit_code)


# --- the config --------------------------------------------------------------


def test_a_config_that_does_not_load_is_config_invalid(
    tmp_path: Path, root: Path
) -> None:
    code, record = _delegate(
        tmp_path, root, config=_config(tmp_path, "not_a_key_mcgyvr_reads: 1\n")
    )
    _ended(record, DelegateKind.CONFIG_INVALID)
    assert code == 1
    assert record.message
    assert record.detail["path"].endswith("mcgyvr.yaml")


def test_a_named_setup_that_is_not_there_is_config_missing(
    tmp_path: Path, root: Path
) -> None:
    _code, record = _delegate(tmp_path, root, config=tmp_path / "nowhere")
    _ended(record, DelegateKind.CONFIG_MISSING)
    assert record.detail["path"].endswith("nowhere")


def test_a_bare_install_is_config_no_orchestrator(tmp_path: Path, root: Path) -> None:
    code, record = _delegate(tmp_path, root)
    _ended(record, DelegateKind.CONFIG_NO_ORCHESTRATOR)
    assert code == 3
    assert record.detail["bare_install"] is True
    assert "orchestrator role is not configured" in record.message


def test_a_config_binding_no_role_is_config_no_orchestrator_too(
    tmp_path: Path, root: Path
) -> None:
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path, UNBOUND))
    _ended(record, DelegateKind.CONFIG_NO_ORCHESTRATOR)
    assert record.detail["bare_install"] is False


# --- the orchestrator role -----------------------------------------------------


def test_a_role_declared_but_not_runnable_is_orchestrator_unrunnable(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unrunnable(config: Any, pool: Any, **kwargs: Any) -> None:
        raise SourceUnavailableError("unit 'planner' was skipped: no key")

    monkeypatch.setattr(command, "_proposer_for_delegate", unrunnable)
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.ORCHESTRATOR_UNRUNNABLE)
    assert record.detail["error_class"] == "SourceUnavailableError"


def test_a_role_with_no_unit_is_orchestrator_unavailable(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, None)
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.ORCHESTRATOR_UNAVAILABLE)


def test_a_dispatch_that_failed_is_orchestrator_dispatch_failed(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, RunnerError("planner was reached but did not reply"))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.ORCHESTRATOR_DISPATCH_FAILED)
    assert record.message == "planner was reached but did not reply"
    assert record.detail["error_class"] == "RunnerError"


def test_a_source_unusable_at_dispatch_is_source_unavailable(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, SourceUnavailableError("the planner key is unset"))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.SOURCE_UNAVAILABLE)


# --- the repository ------------------------------------------------------------


def test_a_repo_that_cannot_be_attached_is_repo_attach_failed(
    tmp_path: Path, root: Path
) -> None:
    _code, record = _delegate(
        tmp_path, tmp_path / "not-a-repo", config=_config(tmp_path)
    )
    _ended(record, DelegateKind.REPO_ATTACH_FAILED)
    assert record.detail["repo"].endswith("not-a-repo")


def test_a_repo_that_cannot_be_indexed_is_repo_index_failed(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_index(root: Path) -> None:
        raise IndexBuildError("git ls-files failed")

    monkeypatch.setattr(orchestrator, "build_index", no_index)
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.REPO_INDEX_FAILED)


# --- the reply -----------------------------------------------------------------


def test_a_reply_cut_off_is_reply_cut_off_with_its_token_counts(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, _answer('[{"task_type": "co', StopReason.TRUNCATED))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.REPLY_CUT_OFF)
    assert record.raw_reply_present
    assert record.detail["unit"] == "planner"
    assert record.detail["output_tokens"] == 2000
    assert record.detail["max_output_tokens"] == 2000
    assert record.detail["raw_reply_chars"] == len('[{"task_type": "co')


def test_a_reply_that_is_not_json_is_reply_not_json(
    tmp_path: Path,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _reply(monkeypatch, "[1, 2,]")
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.REPLY_NOT_JSON)
    assert record.raw_reply_present
    assert record.detail["line"] == 1
    assert record.detail["body_chars"] == len("[1, 2,]")
    # The message is the sentence stderr carries after `error: `, verbatim.
    assert f"error: {record.message}\n" in capsys.readouterr().err


def test_a_reply_that_is_not_an_array_is_reply_not_array(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, '"just a sentence"')
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.REPLY_NOT_ARRAY)
    assert record.detail["found"] == "string"


def test_an_entry_that_is_not_an_object_is_proposal_not_object(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([PROPOSAL, 7]))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.PROPOSAL_NOT_OBJECT)
    assert record.detail["index"] == 1
    assert record.detail["found"] == "number"


def test_an_entry_missing_a_field_is_proposal_field_missing(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([{"task_type": "code", "target": "listing.py"}]))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.PROPOSAL_FIELD_MISSING)
    assert record.detail == {
        "field": "task",
        "found": "null",
        "index": 0,
        "raw_reply_chars": record.detail["raw_reply_chars"],
    }


def test_an_entry_with_a_field_of_the_wrong_shape_is_proposal_field_invalid(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([{**PROPOSAL, "allow": "listing.py"}]))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.PROPOSAL_FIELD_INVALID)
    assert record.detail["field"] == "allow"
    assert record.detail["index"] == 0


# --- the arguments, before anything is asked ------------------------------------


def test_the_bare_verb_with_no_session_is_session_unresolved_and_asks_nobody(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, AssertionError("the orchestrator was asked"))
    code, record = _delegate(tmp_path, root, "--run", config=_config(tmp_path))
    _ended(record, DelegateKind.SESSION_UNRESOLVED)
    assert code == 2
    assert "--session" in record.message


def test_a_branch_that_cannot_be_honoured_is_usage_invalid(
    tmp_path: Path, root: Path
) -> None:
    code, record = _delegate(
        tmp_path, root, "--branch", "b", "--no-commit", config=_config(tmp_path)
    )
    _ended(record, DelegateKind.USAGE_INVALID)
    assert code == 2


# --- what the decomposition came to -------------------------------------------


def test_contracts_and_no_refusals_is_emitted(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([PROPOSAL]))
    out = tmp_path / "contracts"
    code, record = _delegate(
        tmp_path, root, "--output", str(out), config=_config(tmp_path)
    )
    _ended(record, DelegateKind.EMITTED)
    assert code == 0
    (contract,) = record.contracts
    assert contract.target == "listing.py"
    assert contract.path == str(out / f"{contract.id}.json")
    assert record.refusals == ()


def test_a_planned_contract_is_logged_with_the_path_it_was_written_to(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([PROPOSAL]))
    _code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.EMITTED)
    (contract,) = record.contracts
    assert contract.path == str(tmp_path / "plan" / f"{contract.id}.json")
    assert Path(contract.path).is_file()


def test_contracts_beside_refusals_is_emitted_with_refusals(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refused = {**PROPOSAL, "task_type": "no_such_type", "target": "listing.py"}
    _reply(monkeypatch, json.dumps([PROPOSAL, refused]))
    code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.EMITTED_WITH_REFUSALS)
    assert code == 0
    assert len(record.contracts) == 1
    assert record.refusals and record.refusals[0].reason


def test_a_request_nothing_came_of_is_none_emitted_and_refused(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, "[]")
    code, record = _delegate(tmp_path, root, config=_config(tmp_path))
    _ended(record, DelegateKind.NONE_EMITTED)
    assert code == 3
    assert record.contracts == ()
    assert record.message == "No contracts were emitted."


def test_none_emitted_exits_3_without_a_log_too(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, "[]")
    argv = ["Fix listing.", "--repo", str(root), "--output", str(tmp_path / "plan")]
    code = lj.main([*argv, "--config", str(_config(tmp_path))])
    assert code == 3


# --- a crash, and a log that cannot be written -----------------------------------


def test_a_crash_is_internal_error_and_still_raises(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([PROPOSAL]))
    in_the_way = tmp_path / "a-file"
    in_the_way.write_text("not a directory\n")
    log = tmp_path / "delegate-log.json"

    with pytest.raises(OSError):
        lj.main(
            [
                "Fix listing.",
                "--repo",
                str(root),
                "--config",
                str(_config(tmp_path)),
                "--output",
                str(in_the_way),
                "--log",
                str(log),
            ]
        )

    validate(json.loads(log.read_text()), json_schema(), RECORD)
    record = read(log)
    _ended(record, DelegateKind.INTERNAL_ERROR)
    assert record.detail["error_class"] == "FileExistsError"


def test_a_log_that_cannot_be_written_is_said_and_changes_no_exit(
    tmp_path: Path,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _reply(monkeypatch, "[]")
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    argv = ["Fix listing.", "--repo", str(root), "--output", str(tmp_path / "plan")]
    argv += ["--config", str(_config(tmp_path)), "--log", str(blocker / "log.json")]

    code = lj.main(argv)

    assert code == 3
    assert "error: the delegate log could not be written" in capsys.readouterr().err


# --- what a reader is promised -----------------------------------------------------


def test_every_kind_has_an_exit_code_and_the_schema_lists_them() -> None:
    schema = json_schema()
    assert set(KIND_EXIT) == set(DelegateKind)
    assert schema["x-exit-codes"] == {k.value: int(v) for k, v in KIND_EXIT.items()}
    assert schema["$defs"]["KnownKind"]["enum"] == [k.value for k in DelegateKind]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_a_kind_from_a_newer_writer_still_reads(tmp_path: Path) -> None:
    newer = {
        "schema": SCHEMA_ID,
        "kind": "orchestrator_on_fire",
        "message": "a kind added later under /1",
        "exit_code": 1,
        "raw_reply_present": False,
        "contracts": [],
        "refusals": [],
        "detail": {"temperature": 451},
    }
    validate(newer, json_schema(), RECORD)
    path = tmp_path / "newer.json"
    path.write_text(json.dumps(newer))

    record = read(path)

    assert record.kind == "orchestrator_on_fire"
    assert not record.known


def test_another_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "v2.json"
    path.write_text(json.dumps({"schema": "mcgyvr.delegate_log/2", "kind": "emitted"}))

    with pytest.raises(DelegateLogError, match=r"mcgyvr\.delegate_log/2"):
        read(path)


def test_the_record_is_not_in_the_skill_the_session_agent_reads() -> None:
    skill = Path(__file__).resolve().parents[1] / "skills" / "mcgyvr"
    for path in skill.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert "delegate_log" not in text, path
            assert "--log" not in text, path
