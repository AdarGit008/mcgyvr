"""A setup written before the cut is refused once, naming every retired key.

Every `policy.yaml` that `mcgyvr setup` wrote before the ladder manager and
chat/agent sessions were removed carries a `manager:` block (all comments) and
`sandbox.sessions: tempdir`. The loader refuses keys it does not read, so such a
setup stopped loading — and said so one key at a time: delete `manager`, run
again, learn about `sandbox.sessions`. And `mcgyvr setup` on it said "already
exists — nothing was changed".

It is still refused, since an ignored key is a file that does not do what it
says, but in one error listing every retired key it carries. `mcgyvr setup` on
the folder names the exact lines to delete and, asked at a terminal, deletes
them. The fixture is what `render_policy` wrote on main before the cut, with a
ladder over the example fleet.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.config import ConfigSchemaError, load
from mcgyvr.fleet.files import retired_policy_lines, without_retired_lines

BEFORE = Path(__file__).parent / "fixtures" / "setup_before_the_cut"


@pytest.fixture
def setup(tmp_path: Path) -> Path:
    folder = tmp_path / "fleet"
    shutil.copytree(BEFORE, folder)
    return folder


def test_one_refusal_names_every_retired_key(setup: Path) -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        load(setup)

    said = str(refused.value)
    assert "`manager`" in said and "`sandbox.sessions`" in said, said
    assert "mcgyvr setup" in said, said


def test_a_retired_orchestrator_tools_is_named_too(setup: Path) -> None:
    policy = setup / "policy.yaml"
    text = without_retired_lines(policy.read_text())
    policy.write_text(text.replace("  # tools:  # unset", "  tools: [read]"))

    with pytest.raises(ConfigSchemaError) as refused:
        load(setup)

    said = str(refused.value)
    assert "`orchestrator.tools`" in said and "`manager`" not in said, said


def test_the_lines_named_are_the_keys_their_blocks_and_their_comments(
    setup: Path,
) -> None:
    lines = (setup / "policy.yaml").read_text().splitlines()
    spans = {span.key: span for span in retired_policy_lines("\n".join(lines))}

    assert set(spans) == {"manager", "sandbox.sessions"}
    manager = spans["manager"]
    assert lines[manager.first - 1].startswith("# What the ladder manager")
    assert "manager:" in manager.text
    assert all(not line.startswith("journal") for line in manager.text)
    sessions = spans["sandbox.sessions"]
    assert sessions.text[-1] == "  sessions: tempdir"
    assert sessions.text[0].startswith("  # The sandbox a `chat` or `agent` run")


def test_with_the_retired_lines_deleted_the_setup_loads(setup: Path) -> None:
    policy = setup / "policy.yaml"
    policy.write_text(without_retired_lines(policy.read_text()))
    # A setup from before the cut also says `use_case: coding`, which is refused
    # naming the one command that mends it.
    with pytest.raises(ConfigSchemaError, match="mcgyvr use mcgyvr-code"):
        load(setup)
    assert cli.main(["use", "mcgyvr-code", "--config", str(setup)]) == 0

    config = load(setup)

    text = policy.read_text()
    assert "manager:" not in text and "sessions:" not in text
    assert "\n\n\n\n" not in text, "deleting a block leaves no gap behind it"
    assert config.ladder is not None


def test_setup_without_a_terminal_names_the_lines_and_changes_nothing(
    setup: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.commands.setup, "_stdin_isatty", lambda: False)
    before = (setup / "policy.yaml").read_text()

    assert cli.main(["setup", str(setup)]) == 1

    said = capsys.readouterr()
    for span in retired_policy_lines(before):
        assert f"{span.first}" in said.err and span.text[0] in said.err, said.err
    assert (setup / "policy.yaml").read_text() == before


def test_setup_at_a_terminal_deletes_the_lines_on_a_yes(
    setup: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.commands.setup, "_stdin_isatty", lambda: True)
    asked: list[str] = []

    def yes(question: str) -> bool:
        asked.append(question)
        return True

    monkeypatch.setattr(cli.commands.setup, "_confirm", yes)

    assert cli.main(["setup", str(setup)]) == 0

    (question,) = asked
    assert "policy.yaml" in question
    assert cli.main(["use", "mcgyvr-code", "--config", str(setup)]) == 0
    load(setup)


def test_setup_at_a_terminal_leaves_the_file_on_a_no(
    setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli.commands.setup, "_stdin_isatty", lambda: True)
    monkeypatch.setattr(cli.commands.setup, "_confirm", lambda question: False)
    before = (setup / "policy.yaml").read_text()

    assert cli.main(["setup", str(setup)]) == 1

    assert (setup / "policy.yaml").read_text() == before
