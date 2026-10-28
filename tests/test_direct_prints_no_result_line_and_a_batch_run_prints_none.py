"""Neither ``mcgyvr direct`` nor a run inside a batch ends on a ``result:`` line.

A contract run alone is read through ``--result PATH``: the caller names the
file, so there is no pointer to print. Inside a batch (``direct`` of a set, the
bare verb) each contract's result is read in process, by the Board that settles
the tree and the re-planner, and the paths are in the Board's state file under
``<journal>/trees/``. Printing them on stdout handed the batch caller one
pointer per contract into results it does not own, so a run prints none; the
result file is written all the same.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import load
from mcgyvr.contract import dumps
from mcgyvr.contract import load as load_contract
from mcgyvr.orchestrator.decompose import Decomposition
from mcgyvr.session import Session
from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: code
operation: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


def test_direct_prints_no_result_line_and_writes_the_file_it_was_asked_for(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr().out
    assert code == 0
    assert not [line for line in out.splitlines() if line.startswith("result: ")], out
    assert lj.result_of(contract).is_file()


def test_a_run_inside_a_batch_prints_none(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=journal)
    contract = load_contract(lj.make_contract(tmp_path / "tidy.yaml", FORMAT))
    dec = Decomposition(contracts=(contract,), documents=(dumps(contract),))
    args = argparse.Namespace(
        config=str(config),
        sandbox="tempdir",
        commit=None,
        branch=None,
        record=None,
        session_id=None,
        session=Session("claude-s1"),
    )

    code = command._run_delegated(args, repo, dec, [], load(config))

    out = capsys.readouterr().out
    assert code == 0
    assert not [line for line in out.splitlines() if line.startswith("result: ")], out
    assert lj.results(journal), "the batch's run wrote no result file"
