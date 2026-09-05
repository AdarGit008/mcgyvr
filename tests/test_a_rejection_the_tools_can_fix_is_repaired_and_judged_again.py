"""A draw the gate rejects on what a tool can fix is repaired and judged again
on the same rung, with nothing asked of the config (owner, 2026-09-05:
"applying the formatter after a rung is done is on purpose — to improve on
all tasks that were not achievable strictly by the deterministic tiers").

``mcgyvr.repair`` had the loop (D21) and no caller in the live drive; the
tidy behind ``cleanup.enabled`` answered formatting alone and was off. The
first live ladder rejected all nine replies on a reflowed line, whitespace on
a blank line or an unsorted import block, and paid a climb for each. Now a
config that says nothing repairs; ``cleanup.enabled: false`` is the way to
have the gate's rejection stand. What is delivered is the repaired tree; the
journal keeps the reply the model sent; the verdict says a repair ran.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj

#: Correct and unformatted: the formatter rewrites ``VALUE=1`` to ``VALUE = 1``,
#: and the format rung rejects the line until it does.
UNFORMATTED_REPLY = "```python\nVALUE=1\n```"
#: Correct, with two unused imports out of order and whitespace on the value's
#: line: I001, F401 and W291 — every one cleared by the linter's own autofix.
LINTY_REPLY = "```python\nimport sys\nimport os\nVALUE = 1   \n```"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s-repair")
    lj.claude_transcript(home, "s-repair")
    return home


def test_an_unformatted_but_correct_reply_is_accepted_after_repair(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = lj.scripted(monkeypatch, UNFORMATTED_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr()
    assert code == 0, (out.out, out.err)
    assert len(sent) == 1, "the repair must not cost a second dispatch"
    result_line = next(
        line for line in out.out.splitlines() if line.startswith("result:")
    )
    result = json.loads(Path(result_line.split(" ", 1)[1]).read_text(encoding="utf-8"))
    assert result["outcome"] == "accepted", result
    # The accepted file is the repaired tree: formatted, not the reply verbatim.
    assert (repo / "src" / "pkg" / "messy.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_a_reply_the_linters_autofix_can_clear_is_accepted_after_repair(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = lj.scripted(monkeypatch, LINTY_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr()
    assert code == 0, (out.out, out.err)
    assert len(sent) == 1
    assert (repo / "src" / "pkg" / "messy.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_an_install_that_turned_the_cleanup_off_keeps_the_gates_rejection(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, UNFORMATTED_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(
        lj.LADDER
        + f"journal:\n  dir: {tmp_path / 'journal'}\ncleanup:\n  enabled: false\n",
        encoding="utf-8",
    )
    contract = lj.make_contract(tmp_path / "impl.yaml")
    code = lj.main(lj.run_args(contract, repo, config))
    out = capsys.readouterr()
    assert code != 0, (out.out, out.err)
    assert (repo / "src" / "pkg" / "messy.py").read_text(encoding="utf-8") == "x = 0\n"
