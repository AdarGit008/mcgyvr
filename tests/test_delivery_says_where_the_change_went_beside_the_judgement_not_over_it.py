"""Delivery says where the change went beside the judgement, not over it (#183).

A climb's result file carried the judgement in ``detail`` — verified by whom,
or unverified and why — and then delivery wrote over it: "change left in …"
when the run did not commit, the refusal when it refused. So the one field a
caller is told to read for how the work was judged said where it landed
instead, and the judgement survived only on the last attempt.

Now the result file has both:

* ``detail`` keeps the judgement on every accepted run, committed or not;
* ``delivery`` says where the change went: left in the tree uncommitted, or
  the commit it landed in;
* a refused delivery is the run's outcome (``delivery_refused``), and an
  outcome that is not ``accepted`` is explained by ``detail`` — so there
  ``detail`` is the refusal, and ``delivery`` says the same.

stdout is unchanged: it already said both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj

TARGET = "src/pkg/messy.py"


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: Path, *extra: str
) -> tuple[int, dict[str, Any]]:
    lj.clean_env(monkeypatch, tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")
    result = tmp_path / "result.json"
    code = lj.main(
        lj.run_args(
            contract,
            repo,
            config,
            "--orchestrator",
            "t",
            "--result",
            str(result),
            *extra,
        )
    )
    return code, json.loads(result.read_text(encoding="utf-8"))


def test_a_change_left_in_the_tree_keeps_the_judgement_in_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = lj.make_repo(tmp_path / "repo")

    code, result = _run(tmp_path, monkeypatch, repo)

    assert code == 0, result
    assert result["outcome"] == "accepted", result
    judged = result["attempts"][-1]["detail"]
    assert judged, result
    assert result["detail"] == judged, result
    assert result["delivery"] == f"not committed; change left in {TARGET}", result


def test_a_committed_change_keeps_the_judgement_and_names_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = lj.make_repo(tmp_path / "repo")

    code, result = _run(tmp_path, monkeypatch, repo, "--commit")

    assert code == 0, result
    assert result["committed"] is True, result
    assert result["detail"] == result["attempts"][-1]["detail"], result
    assert result["delivery"].startswith(
        f"delivered {TARGET} as {result['commit'][:12]}"
    ), result


def test_a_refused_delivery_is_explained_by_detail_and_said_in_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    (repo / TARGET).write_text("x = 2\n", encoding="utf-8")

    code, result = _run(tmp_path, monkeypatch, repo)

    assert code == 1, result
    assert result["outcome"] == "delivery_refused", result
    assert "uncommitted" in result["detail"], result
    assert result["delivery"] == result["detail"], result
