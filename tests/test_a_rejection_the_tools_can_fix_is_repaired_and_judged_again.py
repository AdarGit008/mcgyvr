"""A draw the gate rejects on what a tool can fix is repaired and judged again
on the same rung, with nothing asked of the config: the formatter runs after a
rung on purpose, to improve on every task the deterministic tiers alone could
not achieve.

A rejection on a reflowed line, whitespace on a blank line or an unsorted import
block would otherwise pay a climb. A config that says nothing repairs
(:func:`mcgyvr.repair.repair`, called by the live drive); ``cleanup.enabled:
false`` is the way to have the gate's rejection stand. What is delivered is the
repaired tree; the journal keeps the reply the model sent; the verdict says a
repair ran.
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
    result = json.loads(lj.result_of(contract).read_text(encoding="utf-8"))
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


#: The repair test's contract, whose demonstration needs the line as the
#: formatter writes it: a ``VALUE=1`` reply is a rejection the repair turns into
#: an acceptance, whether or not the format rung is the one that rejects it.
NEEDS_THE_FORMATTED_LINE = lj.MODEL_CONTRACT.replace(
    "demonstration: [\"sh -c 'grep -q VALUE src/pkg/messy.py'\"]",
    'demonstration: ["sh -c \'grep -qx \\"VALUE = 1\\" src/pkg/messy.py\'"]',
)
assert NEEDS_THE_FORMATTED_LINE != lj.MODEL_CONTRACT

#: The note a run under ``gate.ruff: false`` carries.
RUFF_OFF_NOTE = "python: lint and format not judged"


def _repairs_seen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every call the driver makes to the repair and to the tidy."""
    import mcgyvr.drive as drive
    import mcgyvr.repair as repair_module

    seen: list[str] = []
    real_repair, real_tidy = repair_module.repair, drive.tidy

    def repair_spy(**kwargs):  # type: ignore[no-untyped-def]
        seen.append("repair")
        return real_repair(**kwargs)

    def tidy_spy(**kwargs):  # type: ignore[no-untyped-def]
        seen.append("tidy")
        return real_tidy(**kwargs)

    monkeypatch.setattr(repair_module, "repair", repair_spy)
    monkeypatch.setattr(drive, "tidy", tidy_spy)
    return seen


def _run_needing_the_formatted_line(
    tmp_path: Path, policy: str
) -> tuple[int, Path, list[str]]:
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    lj.append_policy(config, policy)
    contract = lj.make_contract(tmp_path / "impl.yaml", NEEDS_THE_FORMATTED_LINE)
    code = lj.main(lj.run_args(contract, repo, config))
    result = json.loads(lj.result_of(contract).read_text(encoding="utf-8"))
    return code, repo, [str(note) for note in result["notes"]]


def test_with_the_key_unset_that_rejection_is_repaired_and_accepted(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fixture is a rejection the repair fixes, and unset says nothing new."""
    lj.scripted(monkeypatch, UNFORMATTED_REPLY)
    seen = _repairs_seen(monkeypatch)

    code, repo, notes = _run_needing_the_formatted_line(tmp_path, "")

    out = capsys.readouterr()
    assert code == 0, (out.out, out.err)
    assert "repair" in seen
    assert (repo / "src" / "pkg" / "messy.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not any(note.startswith(RUFF_OFF_NOTE) for note in notes), notes
    assert RUFF_OFF_NOTE not in out.err


def test_a_setup_that_said_no_to_ruff_runs_no_repair_on_that_rejection(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`gate.ruff: false` is the driver's `tidying` switch: no repair, no tidy,
    the rejection stands, and the run says lint and format were not judged."""
    lj.scripted(monkeypatch, UNFORMATTED_REPLY)
    seen = _repairs_seen(monkeypatch)

    code, repo, notes = _run_needing_the_formatted_line(
        tmp_path, "gate:\n  ruff: false\n"
    )

    out = capsys.readouterr()
    assert seen == [], f"gate.ruff is false and the driver still ran {seen}"
    assert code != 0, (out.out, out.err)
    assert (repo / "src" / "pkg" / "messy.py").read_text(encoding="utf-8") == "x = 0\n"
    assert any(note.startswith(RUFF_OFF_NOTE) for note in notes), notes
    assert f"note: {RUFF_OFF_NOTE}" in out.err
