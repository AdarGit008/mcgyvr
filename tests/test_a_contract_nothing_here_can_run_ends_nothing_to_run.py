"""A contract no rung on this machine can run ends ``nothing_to_run``, not ``error``.

`SKILL.md` gives the two outcomes different remedies: ``error`` is a failure in
the machinery, ``nothing_to_run`` says the machine offered nothing for this
work, which no rewrite of the contract can fix — the remedy is setup. `_climb`
finds an empty ascent before `escalate` is ever called, so it is the CLI that
has to say ``nothing_to_run``; `escalate`'s own ``NOTHING_TO_RUN`` is never
reached from `mcgyvr direct`.

The machine here has one hosted unit and not the credential it names, so the
pool skips it: no family from the contract's floor upward offers a rung.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj

KEY = "MCGYVR_TEST_NOTHING_TO_RUN_KEY"

FLEET = f"""\
units:
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    width: 1
    api_key_env: {KEY}
"""

POLICY = """\
ladder:
- api_big
"""


def test_a_contract_no_rung_can_run_ends_nothing_to_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.delenv(KEY, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(home, "s1")
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = tmp_path / "setup"
    config.mkdir()
    (config / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (config / "policy.yaml").write_text(
        POLICY + f"journal:\n  dir: {journal}\n", encoding="utf-8"
    )
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr().out
    result = json.loads(lj.result_of(contract).read_text(encoding="utf-8"))
    assert code == 1, out
    assert result["outcome"] == "nothing_to_run", result
    assert result["attempts"] == [], result
    assert KEY in result["detail"], result
