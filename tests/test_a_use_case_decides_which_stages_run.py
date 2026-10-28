"""A use case decides which of mcgyvr's stages stand between a model and you.

`chat`, `agent` and `code` serve the model raw: no stage runs, and the contract
verbs refuse before any model, gate or proposer is touched, naming
`mcgyvr use mcgyvr-code`. `mcgyvr-code` runs every stage its switches leave on,
and every switch is on by default. Each switch that turns a stage off is read
where the stage runs: the gate (`gate.enabled`), repair (`cleanup.enabled`), the
Jev unit (`jev.enabled`), inferred tree edges (`infer_dependencies`) and
same-file exclusion (`same_file`) are driven here on a stub pipeline, no model.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import (
    RAW_USE_CASES,
    SCHEMA,
    STAGE_NAMES,
    SWITCHES,
    USE_CASES,
    field_at,
    parse,
    requires_mcgyvr_code,
    stages,
)
from mcgyvr.contract import Dependency
from mcgyvr.escalate import Delivered
from mcgyvr.exits import Exit
from mcgyvr.local_pool import source_map
from mcgyvr.tree import Tree
from tests import drives
from tests.decomposes import git
from tests.test_a_dependent_of_a_failed_contract_is_held_not_climbed import (
    RENAME,
    a_contract,
    source,
)

FLEET = """\
units:
  fast:
    address: http://127.0.0.1:9
    model: fast-coder
    width: 2
  smart:
    address: http://127.0.0.1:10
    model: smart-coder
    width: 2
ladder: [fast, smart]
jev:
  unit: fast
"""


def config_for(use_case: str | None, extra: str = "") -> Any:
    stated = f"use_case: {use_case}\n" if use_case is not None else ""
    return parse(FLEET + stated + extra)


@pytest.mark.parametrize("use_case", RAW_USE_CASES)
def test_a_raw_use_case_runs_no_stage(use_case: str) -> None:
    ran = stages(config_for(use_case))

    assert set(ran) == set(STAGE_NAMES)
    assert not any(ran.values())


def test_mcgyvr_code_runs_every_stage_by_default() -> None:
    ran = stages(config_for("mcgyvr-code"))

    assert ran == dict.fromkeys(STAGE_NAMES, True)


def test_a_config_that_names_no_use_case_is_mcgyvr_code() -> None:
    config = config_for(None)

    assert config.use_case == "mcgyvr-code"
    assert stages(config) == stages(config_for("mcgyvr-code"))


@pytest.mark.parametrize(
    ("extra", "stage"),
    [
        ("gate:\n  enabled: false\n", "gate"),
        ("cleanup:\n  enabled: false\n", "repair"),
        ("verifier:\n  enabled: false\n", "reviewer"),
        ("max_replans: 0\n", "replan"),
        ("retry_notes: none\n", "retry_notes"),
        ("max_escalations: 0\n", "ladder"),
        ("infer_dependencies: false\n", "inferred_edges"),
        ("same_file: parallel\n", "same_file"),
        ("orchestrator:\n  authoring: prose\n", "classifier"),
    ],
)
def test_each_switch_turns_its_own_stage_off_and_no_other(
    extra: str, stage: str
) -> None:
    ran = stages(config_for("mcgyvr-code", extra))

    assert ran[stage] is False
    assert all(on for name, on in ran.items() if name not in (stage, "repair"))


def test_jev_off_takes_the_jev_unit_and_classifier_authoring_out() -> None:
    config = parse(
        FLEET.replace("jev:\n  unit: fast\n", "")
        + "use_case: mcgyvr-code\njev:\n  unit: fast\n  enabled: false\n"
    )
    ran = stages(config)

    assert ran["jev"] is False
    assert ran["classifier"] is False
    assert config.authoring == "prose"
    # Every typed decision is asked as if no Jev unit were bound.
    assert source_map(config).role_model("jev") is None


def test_the_gate_off_takes_repair_with_it() -> None:
    ran = stages(config_for("mcgyvr-code", "gate:\n  enabled: false\n"))

    assert ran["gate"] is False
    assert ran["repair"] is False


def test_every_switch_names_keys_the_schema_holds_and_says_what_it_does() -> None:
    assert USE_CASES == ("mcgyvr-code", "code", "chat", "agent")
    named = {key for switch in SWITCHES for key in switch.keys}
    for key in named:
        if key.startswith("--"):
            continue
        assert field_at(key) is not None, key
    for switch in SWITCHES:
        assert switch.doc and "\n" not in switch.doc
    # The four knobs mcgyvr-code exposes are each one switch row.
    assert sorted(s.knob for s in SWITCHES if s.knob is not None) == [1, 2, 3, 4]
    assert {f.name for f in SCHEMA} >= {"infer_dependencies", "same_file"}


# --- the guard the contract verbs call --------------------------------------


@pytest.mark.parametrize("use_case", RAW_USE_CASES)
def test_the_guard_refuses_a_raw_use_case_naming_the_way_back(use_case: str) -> None:
    refusal = requires_mcgyvr_code(config_for(use_case))

    assert refusal is not None
    assert f"use case `{use_case}`" in refusal
    assert "mcgyvr use mcgyvr-code" in refusal


def test_the_guard_lets_mcgyvr_code_through() -> None:
    assert requires_mcgyvr_code(config_for("mcgyvr-code")) is None
    assert requires_mcgyvr_code(config_for(None)) is None


def _untouchable(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every model, gate and proposer entry fail the test if reached."""
    import mcgyvr.delegate as delegate
    import mcgyvr.drive as drive

    touched: list[str] = []

    def reached(name: str) -> Any:
        def boom(*args: Any, **kwargs: Any) -> Any:
            touched.append(name)
            raise AssertionError(f"{name} was reached under a raw use case")

        return boom

    monkeypatch.setattr(drive, "dispatch", reached("worker dispatch"))
    monkeypatch.setattr(drive, "gate_workspace", reached("gate"))
    monkeypatch.setattr(delegate, "dispatch_role", reached("proposer"))
    return touched


def _setup(tmp_path: Path, use_case: str) -> Path:
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(
        "units:\n  fast:\n    address: http://127.0.0.1:9\n    model: m\n",
        encoding="utf-8",
    )
    (setup / "policy.yaml").write_text(
        f"use_case: {use_case}\nladder: [fast]\norchestrator:\n  unit: fast\n"
        f"journal:\n  dir: {tmp_path / 'journal'}\n",
        encoding="utf-8",
    )
    return setup


@pytest.mark.parametrize("use_case", RAW_USE_CASES)
def test_run_refuses_a_raw_use_case_before_any_stage(
    use_case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    touched = _untouchable(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    contract = tmp_path / "c.yaml"
    contract.write_text(drives.SHARE_CONTRACT, encoding="utf-8")
    repo = drives.a_git_repo(tmp_path)

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(_setup(tmp_path, use_case)),
            "--session",
            "t",
            "--result",
            str(tmp_path / "result.json"),
        ]
    )

    assert code == Exit.REFUSED
    assert "mcgyvr use mcgyvr-code" in capsys.readouterr().err
    assert touched == []


@pytest.mark.parametrize("use_case", RAW_USE_CASES)
def test_delegate_refuses_a_raw_use_case_before_the_proposer(
    use_case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    touched = _untouchable(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = drives.a_git_repo(tmp_path)

    code = main(
        [
            "delegate",
            "set VALUE to 1",
            "--repo",
            str(repo),
            "--config",
            str(_setup(tmp_path, use_case)),
        ]
    )

    assert code == Exit.REFUSED
    assert "mcgyvr use mcgyvr-code" in capsys.readouterr().err
    assert touched == []


# --- the stub pipeline under mcgyvr-code ------------------------------------


def _judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str
) -> tuple[Any, list[str]]:
    """Drive one attempt on the stub ladder, recording the gate's rungs."""
    import mcgyvr.drive.gate as drive_gate
    from mcgyvr.gate import runner as gate_runner

    rungs: list[str] = []
    real_typecheck = gate_runner.Gate._run_adapter

    def adapter(self: Any, *args: Any, **kwargs: Any) -> Any:
        rungs.append("language")
        return real_typecheck(self, *args, **kwargs)

    def repaired(*args: Any, **kwargs: Any) -> Any:
        rungs.append("repair")
        raise AssertionError("repair ran")

    monkeypatch.setattr(gate_runner.Gate, "_run_adapter", adapter)
    monkeypatch.setattr(drive_gate, "_repair_and_regate", repaired)
    monkeypatch.setattr("mcgyvr.drive.attempt._repair_and_regate", repaired)
    outcome, _sent, _waker, _journal = drives._run(
        drives.a_git_repo(tmp_path), tmp_path, monkeypatch, policy=policy
    )
    return outcome, rungs


def test_the_gate_judges_a_draw_under_mcgyvr_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outcome, rungs = _judged(tmp_path, monkeypatch, "use_case: mcgyvr-code\n")

    assert "language" in rungs


def test_the_gate_off_accepts_a_changed_draw_unjudged_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, rungs = _judged(
        tmp_path,
        monkeypatch,
        "use_case: mcgyvr-code\ngate:\n  enabled: false\n",
    )

    assert rungs == []
    assert isinstance(outcome, Delivered)
    accepted = outcome.judgement.accepted
    assert accepted is not None
    assert [f.check for f in accepted.observations] == ["ungated"]


def test_a_run_under_the_gate_off_says_ungated_in_its_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from mcgyvr.cli import main

    monkeypatch.setenv("HOME", str(tmp_path))
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(
        "units:\n  fast:\n    address: http://127.0.0.1:9\n    model: m\n",
        encoding="utf-8",
    )
    (setup / "policy.yaml").write_text(
        f"ladder: [fast]\ngate:\n  enabled: false\n"
        f"journal:\n  dir: {tmp_path / 'journal'}\n",
        encoding="utf-8",
    )
    contract = tmp_path / "c.yaml"
    contract.write_text(drives.SHARE_CONTRACT, encoding="utf-8")
    result = tmp_path / "result.json"
    monkeypatch.setattr(
        "mcgyvr.drive.dispatch",
        lambda *a, **k: drives._completion("```python\nVALUE = 1\n```"),
    )

    main(
        [
            "run",
            str(contract),
            "--repo",
            str(drives.a_git_repo(tmp_path)),
            "--config",
            str(setup),
            "--sandbox",
            "tempdir",
            "--session",
            "t",
            "--result",
            str(result),
        ]
    )

    notes = json.loads(result.read_text(encoding="utf-8"))["notes"]
    assert any(note.startswith("ungated:") for note in notes)
    assert "note: ungated:" in capsys.readouterr().err


def test_the_gate_off_still_refuses_a_path_outside_the_scope(
    tmp_path: Path,
) -> None:
    from mcgyvr.drive import gate_workspace
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    repo = drives.a_git_repo(tmp_path)
    config = parse(drives.SHARE_LADDER + "gate:\n  enabled: false\n")
    contract = drives.contract(drives.SHARE_CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "outside.py").write_text("X = 1\n", encoding="utf-8")
        verdict = gate_workspace(contract, sandbox, config=config)

    assert not verdict.accepted
    assert [f.check for f in verdict.findings] == ["scope"]


# --- inferred edges and same-file exclusion ----------------------------------


def _caller() -> Any:
    return a_contract(
        "caller",
        "pkg/report.py",
        "Map each record.",
        deps=(Dependency("pkg/codec.py", "def pairs_of(record) -> list"),),
    )


def test_inferred_edges_order_a_dependent_after_the_sibling_that_creates_its_name() -> (
    None
):
    tree = Tree.of([RENAME, _caller()], source(), tree_id="t")

    assert [e.provider for e in tree.edges("caller")] == ["rename"]


def test_a_batch_builds_its_tree_with_the_policys_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import test_delegate_run_jobs_runs_ready_contracts_at_once as q5

    built: list[bool] = []
    real = Tree.of

    def of(*args: Any, **kwargs: Any) -> Tree:
        built.append(kwargs["infer"])
        return real(*args, **kwargs)

    monkeypatch.setattr(Tree, "of", of)
    monkeypatch.setattr(command, "_fleet_width", lambda _config: 8)
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "pkg" / "a.py").write_text("def a():\n    return 0\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    for stated, inferred in ((False, False), (None, True)):
        policy = q5.Policy(
            {"journal.dir": str(tmp_path / f"journal-{stated}"), "dependents": "hold"}
        )
        if stated is not None:
            policy["infer_dependencies"] = stated
        q5.batch(
            repo, tmp_path, monkeypatch, (q5.code("code-a", "pkg/a.py"),), config=policy
        )
        assert built[-1] is inferred


def test_inference_off_orders_only_by_depends_on() -> None:
    tree = Tree.of([RENAME, _caller()], source(), tree_id="t", infer=False)

    assert tree.edges("caller") == ()
    assert sorted(c.id for c in tree.ready()) == ["caller", "rename"]


def test_same_file_parallel_runs_two_contracts_on_one_file_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import test_delegate_run_jobs_runs_ready_contracts_at_once as q5

    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "pkg" / "a.py").write_text("def a():\n    return 0\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    both = threading.Barrier(2, timeout=q5.WAIT)
    plans = {"code-a1": q5.Plan(before=both.wait), "code-a2": q5.Plan(before=both.wait)}
    policy = q5.Policy(
        {
            "journal.dir": str(tmp_path / "journal"),
            "dependents": "hold",
            "same_file": "parallel",
        }
    )
    monkeypatch.setattr(command, "_fleet_width", lambda _config: 8)

    _code, runs, journal = q5.batch(
        repo,
        tmp_path,
        monkeypatch,
        (q5.code("code-a1", "pkg/a.py"), q5.code("code-a2", "pkg/a.py")),
        plans,
        config=policy,
    )

    # Neither could pass the barrier without the other: they ran at once.
    assert runs.most == 2
    # Nothing is lost: each has its result, landed or named as a conflict.
    assert q5.results(journal, "code-a1") and q5.results(journal, "code-a2")
