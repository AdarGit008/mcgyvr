"""The output checks — the evidence kinds a structural check makes itself.

``safety_pass`` runs the safety classifier over the artifact. A check whose
validator is missing is inconclusive — a rejection — never a clean pass, so a
contract declaring one never reads as clean.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mcgyvr.contract import loads
from mcgyvr.drive import output_checks_for
from mcgyvr.gate.adapter import ToolFailedError, ToolUnavailableError
from mcgyvr.gate.output import SAFETY_PASS, OutputChecks, safety_pass


def test_a_check_whose_validator_is_missing_is_inconclusive_not_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing validator is inconclusive, never clean — the gate's one rule."""
    monkeypatch.setattr("mcgyvr.gate.output.shutil.which", lambda _tool: None)
    report = OutputChecks(
        checks=(SAFETY_PASS,), workspace=tmp_path, target="out.bin"
    ).run()
    assert report.findings == ()
    assert len(report.inconclusive) == 1
    assert report.inconclusive[0].rung == SAFETY_PASS
    assert report.inconclusive[0].tool == "safety-classifier"
    assert len(report.environment_issues) == 1
    assert SAFETY_PASS in report.environment_issues[0]
    assert "is inconclusive" in report.environment_issues[0]
    assert "not available" in report.environment_issues[0]
    assert "skipped" not in report.environment_issues[0]


def test_an_unknown_check_name_is_refused_not_guessed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="check"):
        OutputChecks(checks=("vibes",), workspace=tmp_path, target="out.bin").run()


# --- the drive wiring --------------------------------------------------------


def test_output_checks_for_is_none_for_a_coding_contract() -> None:
    """A coding type declares no structural output kind, so there is no rung."""
    contract = loads(
        """
id: t
task_type: code
task: Do the thing.
target: src/pkg/f.py
stop_conditions: ["An unknown."]
acceptance: ["pytest -q"]
scope:
  allow: ["src/**"]
"""
    )
    assert output_checks_for(contract, Path(".")) is None


def test_output_checks_for_maps_declared_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    fake_type = SimpleNamespace(
        name="safe_output",
        deterministic=False,
        session=False,
        needs_acceptance_commands=False,
        needs_demonstration_commands=False,
        required_evidence=(
            SimpleNamespace(name="gate", needs_commands=False, baseline="pass"),
            SimpleNamespace(name="safety_pass", needs_commands=False, baseline="pass"),
        ),
        guarantee="a safe artifact is produced",
    )
    monkeypatch.setattr(
        "mcgyvr.contract.catalog",
        lambda: SimpleNamespace(
            names=("code",),
            task_types=(SimpleNamespace(name="code"),),
            operations=(),
            require=lambda _name: fake_type,
        ),
    )
    contract = loads(
        """
id: out
task_type: code
task: Produce the output.
target: out.txt
stop_conditions: ["No model is bound."]
scope:
  allow: ["out.txt"]
"""
    )

    output = output_checks_for(contract, tmp_path)

    assert output is not None
    assert output.checks == ("safety_pass",)
    assert output.target == "out.txt"


# --- the tool-backed validator ----------------------------------------------


def test_safety_pass_reports_clean_when_the_classifier_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mcgyvr.gate.output.shutil.which",
        lambda _tool: "/usr/bin/safety-classifier",
    )
    monkeypatch.setattr(
        "mcgyvr.gate.output.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
    )
    assert safety_pass(tmp_path / "out.png") == []


def test_safety_pass_reports_unsafe_when_the_classifier_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mcgyvr.gate.output.shutil.which",
        lambda _tool: "/usr/bin/safety-classifier",
    )
    monkeypatch.setattr(
        "mcgyvr.gate.output.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=b"", stderr=b""),
    )
    findings = safety_pass(tmp_path / "out.png")
    assert [f.code for f in findings] == ["unsafe"]
    assert all(f.check == SAFETY_PASS for f in findings)


def test_safety_pass_raises_when_the_classifier_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mcgyvr.gate.output.shutil.which", lambda _tool: None)
    with pytest.raises(ToolUnavailableError, match="safety-classifier"):
        safety_pass(tmp_path / "out.png")


def test_safety_pass_raises_when_the_classifier_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mcgyvr.gate.output.shutil.which",
        lambda _tool: "/usr/bin/safety-classifier",
    )
    monkeypatch.setattr(
        "mcgyvr.gate.output.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=2, stdout=b"", stderr=b"boom"
        ),
    )
    with pytest.raises(ToolFailedError) as excinfo:
        safety_pass(tmp_path / "out.png")
    assert excinfo.value.exit_code == 2


def test_a_failed_validator_is_inconclusive_with_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mcgyvr.gate.output.shutil.which",
        lambda _tool: "/usr/bin/safety-classifier",
    )
    monkeypatch.setattr(
        "mcgyvr.gate.output.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=2, stdout=b"", stderr=b"boom"
        ),
    )
    report = OutputChecks(
        checks=(SAFETY_PASS,), workspace=tmp_path, target="out.bin"
    ).run()
    assert report.findings == ()
    assert len(report.inconclusive) == 1
    assert report.inconclusive[0].rung == SAFETY_PASS
    assert report.inconclusive[0].tool == "safety-classifier"
    assert report.inconclusive[0].exit_code == 2
    assert len(report.environment_issues) == 1
    assert "exited 2" in report.environment_issues[0]
