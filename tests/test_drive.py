"""Pattern C — the driver, exercised against real programs and a real sandbox.

The 2026-08-29 pressure test's pattern C is that the port's call graph "is five
disconnected fragments, none rooted anywhere reachable", and that closing it
needs two things: a ``ToolStep`` executor and a dispatch binding. Both are in
:mod:`mcgyvr.drive` and both are driven here for real — ruff actually runs, the
sandbox is an actual git workspace, and the gate reaches its verdict over an
actual diff.

Nothing here stubs the thing under test. The one thing that is substituted is a
model, because a test that needed one would not run on a machine with no
backend — and the seam that lets it be substituted (``dispatch`` takes a rung
name and a source map) is the same seam the whole project is built on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.availability import Verdict as AvailabilityVerdict
from mcgyvr.contract import loads as load_contract
from mcgyvr.cooldown import Cooldown
from mcgyvr.deterministic import tool_steps
from mcgyvr.drive import (
    PromptTooLargeError,
    UnrunnableStepError,
    dispatch_prompt,
    gate_in_sandbox,
    run_tool_step,
)
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

# Valid Python that ruff format will rewrite: the double-quoted string stays,
# the spacing does not.
UNFORMATTED = "x = {  'a':1,'b':2 }\n"

FORMAT_CONTRACT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

RENAME_CONTRACT = """
id: rename
task_type: rename_symbol
task: Rename the helper.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "messy.py").write_text(UNFORMATTED, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


# --- the ToolStep executor --------------------------------------------------


def test_the_floor_actually_formats_the_file(repo: Path) -> None:
    """The whole of pattern C's first half, end to end.

    The plan names a command, the executor runs it, and the file on disk is
    different afterwards. Every one of those existed except the middle, which is
    why a ``format`` contract could be planned and never performed.
    """
    contract = load_contract(FORMAT_CONTRACT)
    (step,) = tool_steps(contract)

    with TempDirSandbox(repo) as sandbox:
        outcome = run_tool_step(step, sandbox)
        after = (sandbox.workspace / contract.target).read_text(encoding="utf-8")

    assert outcome.ok
    assert outcome.ran
    assert after != UNFORMATTED
    assert after == 'x = {"a": 1, "b": 2}\n'


def test_the_users_checkout_is_not_what_gets_formatted(repo: Path) -> None:
    """The executor takes a sandbox, so a contract's target cannot reach a repo.

    ``ruff format`` writes where it is pointed and a ``target`` is a field of a
    document the orchestrator may not have written. The sandbox is what makes
    that survivable, so it is a required argument rather than an option — and
    the source tree is asserted byte-identical, not merely "still there".
    """
    contract = load_contract(FORMAT_CONTRACT)
    (step,) = tool_steps(contract)
    before = (repo / contract.target).read_bytes()

    with TempDirSandbox(repo) as sandbox:
        run_tool_step(step, sandbox)

    assert (repo / contract.target).read_bytes() == before


def test_an_in_process_step_is_refused_rather_than_reported_done(repo: Path) -> None:
    """``rename_symbol`` has no program, and an empty argv is not "nothing to do".

    ``ToolStep.argv`` returns ``()`` deliberately — "an empty tuple is the
    honest answer and is the answer a caller can distinguish". Distinguishing it
    is the executor's half: run it as a command and the contract is reported
    complete over a file nothing opened.
    """
    contract = load_contract(RENAME_CONTRACT)
    (step,) = tool_steps(contract)
    assert step.argv == ()

    with TempDirSandbox(repo) as sandbox, pytest.raises(UnrunnableStepError) as exc:
        run_tool_step(step, sandbox)

    assert "in-process" in str(exc.value)


def test_a_missing_program_is_an_environment_issue_never_a_failure(
    repo: Path,
) -> None:
    """A tool that is not installed is not a change that was rejected.

    The same distinction the acceptance rung draws, read from the same exit
    codes — which is why :data:`mcgyvr.gate.acceptance.DID_NOT_RUN` is one
    constant and not two. A floor that reported "your change failed" when ruff
    was absent would send an operator to look at the diff.
    """
    from dataclasses import replace

    from mcgyvr.deterministic import Tool

    contract = load_contract(FORMAT_CONTRACT)
    (planned,) = tool_steps(contract)
    step = replace(
        planned, tool=Tool(task_type="format", command=("mcgyvr-no-such-program-42",))
    )

    with TempDirSandbox(repo) as sandbox:
        outcome = run_tool_step(step, sandbox)

    assert not outcome.ok
    assert not outcome.ran
    assert "could not run" in outcome.environment_issue
    assert "dearer family" in outcome.environment_issue


# --- the floor's product is judged by the same gate --------------------------


def test_the_floors_own_output_passes_the_gate(repo: Path) -> None:
    """A tool's change is gated like any other, not trusted for being a tool's.

    This is the join the pressure test found missing everywhere: the floor
    produced a tree and nothing carried it to the gate.
    """
    contract = load_contract(FORMAT_CONTRACT)
    (step,) = tool_steps(contract)

    with TempDirSandbox(repo) as sandbox:
        run_tool_step(step, sandbox)
        formatted = (sandbox.workspace / contract.target).read_text(encoding="utf-8")
        result = gate_in_sandbox(contract, sandbox, formatted)

    assert result.accepted, result.findings


def test_a_broken_change_is_rejected_by_the_gate_the_driver_calls(
    repo: Path,
) -> None:
    """The gate the driver calls is the whole gate, not a syntax spot-check.

    Written as a rejection rather than as an acceptance because a driver that
    accidentally passed an empty ``GateResult`` around would satisfy every
    "it passed" assertion in this file.
    """
    contract = load_contract(FORMAT_CONTRACT)

    with TempDirSandbox(repo) as sandbox:
        result = gate_in_sandbox(contract, sandbox, "def broken( :\n")

    assert not result.accepted
    assert "syntax" in result.by_check()


def test_the_contracts_acceptance_commands_actually_run(repo: Path) -> None:
    """``acceptance`` reaches the gate, which no code path did before.

    ``Contract.acceptance`` is a list of command *strings* and
    ``Acceptance`` takes argv; nothing split one into the other, so a
    contract's acceptance bar was declared, validated at load, and never
    executed by anything.
    """
    contract = load_contract(
        """
id: checked
task_type: function_implementation
task: Set the value.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
scope:
  allow: ["src/**"]
"""
    )
    assert contract.acceptance_commands == (
        ("sh", "-c", "grep -q VALUE src/pkg/messy.py"),
    )

    with TempDirSandbox(repo) as sandbox:
        passing = gate_in_sandbox(contract, sandbox, "VALUE = 1\n")
        failing = gate_in_sandbox(contract, sandbox, "OTHER = 1\n")

    assert passing.accepted, passing.findings
    assert not failing.accepted
    assert "acceptance" in failing.by_check()


# --- the dispatch binding ----------------------------------------------------

CONFIG = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""


def test_the_contracts_output_cap_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``limits.max_output_tokens`` is applied, for the first time.

    Computed per task type at contract load, documented as a hard ceiling on one
    execution, and — until there was a binding — read by nothing. Asserted
    against the contract's own value rather than a literal, so a change to the
    per-type table cannot make this pass by coincidence.
    """
    import mcgyvr.drive as drive
    from mcgyvr.config import parse as parse_config
    from mcgyvr.pool import Protocol, source_map
    from mcgyvr.runner import Completion, Request, StopReason
    from mcgyvr.worker.prompt import build_prompt

    contract = load_contract(
        """
id: impl
task_type: function_implementation
task: Add the helper.
target: src/pkg/messy.py
stop_conditions: ["The interface is not stated."]
acceptance: ["sh -c 'exit 0'"]
scope:
  allow: ["src/**"]
"""
    )
    sent: list[Request] = []

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(request)
        return Completion(
            text="```python\nx = 1\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OLLAMA,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    pool = source_map(parse_config(CONFIG))
    prompt = build_prompt(contract)

    dispatch_prompt(pool, "local_qwen-7b", prompt, contract)

    (request,) = sent
    assert request.max_output_tokens == contract.limits.max_output_tokens
    assert request.prompt == prompt.user
    assert request.system == prompt.system  # the language bundle travels too


def test_a_prompt_that_does_not_fit_is_refused_rather_than_truncated() -> None:
    """The fit check ``build_prompt`` pays for is acted on.

    A binding that dispatched an over-budget prompt would make the measurement
    decorative and send a request whose reply is cut at a boundary nobody chose.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.pool import source_map
    from mcgyvr.worker.prompt import build_prompt

    # The ceiling is the smallest the schema allows beside the output cap, and
    # the task text is what overruns it — a contract that could not be loaded
    # at all would test the loader instead of the binding.
    contract = load_contract(
        f"""
id: huge
task_type: function_implementation
task: {"Add the helper. " * 400}
target: src/pkg/messy.py
stop_conditions: ["The interface is not stated."]
acceptance: ["sh -c 'exit 0'"]
context:
  max_input_tokens: 1024
scope:
  allow: ["src/**"]
"""
    )
    prompt = build_prompt(contract)
    assert not prompt.fits

    pool = source_map(parse_config(CONFIG))
    with pytest.raises(PromptTooLargeError) as exc:
        dispatch_prompt(pool, "local_qwen-7b", prompt, contract)

    assert "huge" in str(exc.value)


# --- the composition: one attempt is prompt, dispatch, parse, apply, gate ----

LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
    - name: local_qwen-14b
      source: workstation
      model: qwen2.5-coder:14b
"""

MODEL_CONTRACT = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
scope:
  allow: ["src/**"]
"""


def _completion(text: str):  # type: ignore[no-untyped-def]
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OLLAMA,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _driven(monkeypatch: pytest.MonkeyPatch, *replies: str):  # type: ignore[no-untyped-def]
    """Answer each dispatch from a script, and record the prompts that were sent."""
    import mcgyvr.drive as drive

    sent: list[str] = []
    scripted = list(replies)

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(request.prompt)
        if not scripted:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        return _completion(scripted.pop(0))

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


def test_one_attempt_reaches_a_judgement_over_a_real_gate(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The five steps nothing composed: prompt, dispatch, parse, apply, gate, judge.

    The reply is scripted; everything it passes through is real — the contract's
    acceptance command runs in the sandbox, the gate reads an actual diff, and
    the verdict comes from :func:`mcgyvr.escalate.judge`.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try, Verdict

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    _driven(monkeypatch, "```python\nVALUE = 1\n```")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox)
        judgement = attempt(
            Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1)
        )

    assert judgement.verdict is Verdict.PASSED
    # The bytes the driver returns are the bytes it gated: `worker_attempt`
    # mints the binding with `Accepted.read` off the workspace the gate judged,
    # so this reads the tree back through the verdict rather than through the
    # string the reply happened to carry.
    assert judgement.accepted is not None
    assert judgement.accepted.content == "VALUE = 1\n"
    assert judgement.accepted.accepted is True


def test_a_rejected_attempt_tells_the_next_one_what_failed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry note reaches the second prompt, and only the second.

    ``build_prompt`` has had a ``retry`` parameter with no production caller
    since it was written. This is that caller: the note comes from the previous
    judgement on the same rung, so the loop that owns "how many attempts" stays
    :func:`~mcgyvr.route.climb`'s.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try, Verdict

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    # First reply misses the acceptance command; the second satisfies it.
    sent = _driven(
        monkeypatch, "```python\nOTHER = 1\n```", "```python\nVALUE = 1\n```"
    )
    rung = Rung(name="local_qwen-7b", model="m")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox)
        first = attempt(Try(rung=rung, attempt=1, of=2))
        second = attempt(Try(rung=rung, attempt=2, of=2))

    assert first.verdict is Verdict.FAILED
    assert second.verdict is Verdict.PASSED
    assert "PREVIOUS ATTEMPT WAS REJECTED" not in sent[0]
    assert "PREVIOUS ATTEMPT WAS REJECTED" in sent[1]


def test_the_retry_note_does_not_carry_the_acceptance_command(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#94 on the retry path, asserted where the prompt is actually built.

    ``tests/test_pattern_e_boundaries.py`` pins the rule at the seam; this pins
    it at the one place a real second prompt is assembled, because that is where
    a regression would actually reach a model.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    sent = _driven(
        monkeypatch, "```python\nOTHER = 1\n```", "```python\nVALUE = 1\n```"
    )
    rung = Rung(name="local_qwen-7b", model="m")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox)
        attempt(Try(rung=rung, attempt=1, of=2))
        attempt(Try(rung=rung, attempt=2, of=2))

    assert "grep -q VALUE" not in sent[1]
    assert "acceptance command failed" in sent[1]  # the signal survives


def test_an_unreadable_reply_is_a_failed_attempt_not_an_exception(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker that answers in prose has failed an attempt, not broken the run."""
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try, Verdict

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    _driven(monkeypatch, "Sure! I would start by looking at the file.")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox)
        judgement = attempt(
            Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1)
        )

    assert judgement.verdict is Verdict.FAILED
    assert "could not be read" in judgement.detail


def test_the_attempt_function_plugs_into_escalate(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The root, assembled: a contract climbs a ladder and comes back delivered.

    This is what pattern C said did not exist — ``escalate`` was reachable only
    from tests holding a scripted attempt function. The attempt function is now
    the real one, and the ladder walk is real: the 7b rung answers unusably and
    the 14b rung answers correctly, so the task escalates and is accepted there.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.escalate import Delivered, escalate
    from mcgyvr.pool import source_map

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    _driven(
        monkeypatch,
        "no fenced block here",  # 7b: unreadable
        "```python\nVALUE = 1\n```",  # 14b: correct
    )

    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config, pool, contract, worker_attempt(config, pool, contract, sandbox)
        )

    assert isinstance(outcome, Delivered)
    assert outcome.rung == "local_qwen-14b"
    assert outcome.judgement.accepted is not None
    assert outcome.judgement.accepted.content == "VALUE = 1\n"


# --- the production caller ---------------------------------------------------


def test_the_run_command_drives_a_contract_to_a_commit(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The root of the call graph, exercised as a user reaches it.

    Everything under this was reachable from a test before and from no command,
    which is what "28 of 35 public entry points have no production caller"
    described. The assertion is on the repository, not on the output: a commit
    that exists is the only evidence that a task ran.
    """
    from mcgyvr.cli import main

    contract = tmp_path / "tidy.yaml"
    contract.write_text(FORMAT_CONTRACT, encoding="utf-8")

    code = main(
        ["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir", "--commit"]
    )

    assert code == 0
    assert (repo / "src/pkg/messy.py").read_text(encoding="utf-8") == (
        'x = {"a": 1, "b": 2}\n'
    )
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s", "-1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip().startswith("tidy:")


def test_the_run_command_writes_nothing_without_commit(
    repo: Path, tmp_path: Path
) -> None:
    """A verdict is free; a write to someone's repository is not.

    The sandbox is torn down either way, so the default costs the user nothing
    they did not ask for — which is why committing is the flag rather than the
    other way round.
    """
    from mcgyvr.cli import main

    contract = tmp_path / "tidy.yaml"
    contract.write_text(FORMAT_CONTRACT, encoding="utf-8")
    before = (repo / "src/pkg/messy.py").read_bytes()

    code = main(["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"])

    assert code == 0
    assert (repo / "src/pkg/messy.py").read_bytes() == before


def test_a_model_contract_with_no_ladder_is_told_where_the_ladder_should_be(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A model contract needs a config, and the missing one is named by path.

    This replaces the assertion that a model contract is refused outright. That
    refusal said "which flags select a rung is not yet decided"; the answer is
    that no flag does — the ladder in the config decides, and the only thing
    ``run`` was missing is somewhere to read it from. What is left to check is
    the failure that remains: a config that is not there.

    ``MCGYVR_CONFIG`` is set to a path in ``tmp_path`` rather than left to
    resolution, so the test asserts the same thing on a machine that has a user
    config as on one that does not.
    """
    from mcgyvr.cli import main
    from mcgyvr.config import CONFIG_PATH_ENV

    contract = tmp_path / "impl.yaml"
    contract.write_text(MODEL_CONTRACT, encoding="utf-8")
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"
    monkeypatch.setenv(CONFIG_PATH_ENV, str(absent))

    code = main(["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"])

    assert code == 1
    assert str(absent) in capsys.readouterr().err


# --- E5 · the orchestrator id, carried as a field ---------------------------


def test_an_attempt_is_recorded_under_the_orchestrator_that_made_it(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9: "records carry an orchestrator id", by something that carries one.

    ``telemetry.observe`` has required the field since it was written and had no
    production caller, so nothing ever put an id in it. The driver does, from a
    value the caller constructs — never from the process, which is the
    single-orchestrator assumption §9 exists to prevent.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import Recording, worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try
    from mcgyvr.telemetry import fold

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    _driven(monkeypatch, "```python\nVALUE = 1\n```")
    sink = tmp_path / "telemetry.jsonl"

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(
            config,
            pool,
            contract,
            sandbox,
            recording=Recording(path=sink, orchestrator="agent-a"),
        )
        attempt(Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1))

    (record,) = fold(path=sink)
    assert record["orchestrator"] == "agent-a"
    assert record["rung"] == "local_qwen-7b"
    assert record["ok"] is True
    # The orchestrator is part of the id, not only a field beside it: `fold`
    # keys on the id, so a shared id is a row that erases another's.
    assert record["attempt_id"] == "agent-a:impl:local_qwen-7b:1"


def test_two_orchestrators_share_one_stream_and_stay_distinguishable(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property the field is for, which one recorded row cannot show.

    §9's constraint exists so the v2 queue stays reachable: two orchestrators
    behind one stream. A field that is always the same value would satisfy every
    single-row assertion and none of this.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import Recording, worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try
    from mcgyvr.telemetry import fold

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    _driven(monkeypatch, "```python\nVALUE = 1\n```", "```python\nVALUE = 1\n```")
    sink = tmp_path / "telemetry.jsonl"
    rung = Rung(name="local_qwen-7b", model="m")

    with TempDirSandbox(repo) as sandbox:
        for name in ("agent-a", "agent-b"):
            attempt = worker_attempt(
                config,
                pool,
                contract,
                sandbox,
                recording=Recording(path=sink, orchestrator=name),
            )
            attempt(Try(rung=rung, attempt=1, of=1))

    assert [r["orchestrator"] for r in fold(path=sink)] == ["agent-a", "agent-b"]


def test_a_recording_with_no_orchestrator_is_refused(tmp_path: Path) -> None:
    """An id that may be blank is a field that carries nothing.

    Refused at construction rather than at write, because the row is written
    inside an attempt and a run that discovers its telemetry is anonymous after
    spending a rung has already lost the thing it was recording.
    """
    from mcgyvr.drive import Recording

    with pytest.raises(ValueError, match="orchestrator id"):
        Recording(path=tmp_path / "t.jsonl", orchestrator="  ")


# --- the cooldown lever, wired -------------------------------------------------


def _cooldown() -> Cooldown:
    """A cooldown whose liveness half is a stub, as ``mcgyvr run`` builds one.

    The driver discovers liveness by dispatching, so the probe half must not
    touch the network; it only ever answers "live". Removal can then only come
    from the dispatch failures the cooldown records.
    """

    def live(endpoint: object, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,  # type: ignore[attr-defined]
            live=True,
            reason="",
            how="stub probe, no network",
            elapsed_s=0.0,
        )

    return Cooldown(probe=live)


def test_a_cooling_source_is_declined_without_a_dispatch(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lever fires inside a task: a cooling rung is walked past for free.

    Three consecutive dispatch failures arm the cooldown, and the next attempt
    on that source is declined before a prompt is built — so ``escalate`` walks
    to the next rung instead of spending another attempt on a source that has
    just failed three times.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try, Verdict

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    sent = _driven(monkeypatch, "```python\nVALUE = 1\n```")
    cooldown = _cooldown()
    for _ in range(3):
        cooldown.record_failure("workstation")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox, cooldown=cooldown)
        judgement = attempt(
            Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1)
        )

    assert judgement.verdict is Verdict.DECLINED, (
        f"a cooling source was not declined: {judgement}"
    )
    assert "cooling" in judgement.detail
    assert not sent, f"a cooling rung was still dispatched: {sent}"


def test_a_dispatch_failure_feeds_the_cooldown(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transport failure is recorded, and three of them arm the lever."""
    import mcgyvr.drive as drive
    from mcgyvr.config import parse as parse_config
    from mcgyvr.drive import worker_attempt
    from mcgyvr.pool import Rung, source_map
    from mcgyvr.route import Try
    from mcgyvr.runner import RunnerError

    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(MODEL_CONTRACT)
    cooldown = _cooldown()

    def boom(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        raise RunnerError("the source answered and failed the generation")

    monkeypatch.setattr(drive, "dispatch", boom)
    endpoint = pool.bind("local_qwen-7b")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox, cooldown=cooldown)
        with pytest.raises(RunnerError):
            attempt(Try(rung=Rung(name="local_qwen-7b", model="m"), attempt=1, of=1))

    # One failure is a hiccup; three consecutive arm the removal.
    assert cooldown.unavailable([endpoint]) == {}
    cooldown.record_failure("workstation")
    cooldown.record_failure("workstation")
    assert "workstation" in cooldown.unavailable([endpoint]), (
        "three consecutive dispatch failures did not arm the cooldown"
    )
