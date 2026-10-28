"""``mcgyvr setup`` stages in the data folder and writes nothing where it runs.

No dev copy. A setup run stages its ``fleet.yaml`` and
``policy.yaml`` in ``<data folder>/setup/<run id>/``
(:func:`mcgyvr.fleet.roots.staging_dir`), and emits, starts and samples from
there; the working directory is never written. Only a ``PATH`` argument (or
``--config PATH``) stages elsewhere. The interactive setup writes the staged
setup once from the plan and emits its launch specs once.

Nothing reaches a machine: every step that would is substituted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli
from mcgyvr.fleet.roots import data_home, staging_dir
from mcgyvr.initialize import InitResult

HOSTED = "model=hosted-model,address=https://api.hosted.example/v1,api_key_env=K"


def _no_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcgyvr.detect import Detection

    monkeypatch.setattr(
        "mcgyvr.initialize.detect",
        lambda _targets: Detection(backends=(), provenance={"backends": "none"}),
    )


def test_staging_is_one_folder_per_setup_run_under_the_data_folder() -> None:
    assert staging_dir("run-1") == data_home() / "setup" / "run-1"


def test_the_flag_path_stages_in_the_data_folder_and_not_where_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_backends(monkeypatch)
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)

    assert cli.main(["setup", "--api", HOSTED]) == 0

    out = capsys.readouterr().out
    assert list(here.iterdir()) == [], "setup wrote into the working directory"
    (staged,) = (data_home() / "setup").iterdir()
    assert (staged / "fleet.yaml").is_file() and (staged / "policy.yaml").is_file()
    assert str(staged) in out


def test_a_path_argument_stages_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_backends(monkeypatch)
    target = tmp_path / "mine"

    assert cli.main(["setup", "--api", HOSTED, str(target)]) == 0

    assert (target / "fleet.yaml").is_file()
    assert not (data_home() / "setup").exists()


def test_the_interactive_setup_writes_once_from_the_plan_and_emits_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    calls: list[tuple[Any, ...]] = []

    monkeypatch.setattr(cli.commands.setup, "_stdin_isatty", lambda: True)
    monkeypatch.setattr(
        cli.commands.setup, "_ask_setup_rigs", lambda prompt=None: ("box1",)
    )
    monkeypatch.setattr(
        cli.commands.setup,
        "_setup_scan_rigs",
        lambda rigs: ({}, {"box1": {"read": "once"}}),
    )
    monkeypatch.setattr(
        cli.commands.setup,
        "_setup_placements",
        lambda rigs, scans, use_case: {"box1": {"placement": {"context_length": 4096}}},
    )
    monkeypatch.setattr(
        cli.commands.setup, "_setup_downloads", lambda plans, scans, prompt=None: ()
    )
    monkeypatch.setattr(
        cli.commands.setup,
        "_setup_synthetic_detection",
        lambda plans, window=None: None,
    )

    def fake_initialize(path: Path, **kwargs: Any) -> InitResult:
        calls.append(("initialize", path, kwargs.get("detection", "-")))
        return InitResult(path=path, created=True, written=True)

    monkeypatch.setattr(cli.commands.setup, "initialize", fake_initialize)
    monkeypatch.setattr(cli.commands.setup, "_setup_rooms", lambda path, ctx: {})
    monkeypatch.setattr(
        cli.commands.setup,
        "_setup_emit",
        lambda path, ctx: calls.append(("emit", path, ctx)),
    )
    monkeypatch.setattr(
        cli.commands.setup, "_confirm", lambda question, prompt=None: False
    )
    # Enter on every typed question, but the use case, which has no default.
    monkeypatch.setattr(
        cli.commands.setup,
        "_ask",
        lambda question, prompt=None: "m" if question.startswith("Use case") else "",
    )

    assert cli.main(["setup"]) == 0

    (staged,) = (data_home() / "setup").iterdir()
    assert calls == [("initialize", staged, None), ("emit", staged, 4096)]
    assert list(here.iterdir()) == []
