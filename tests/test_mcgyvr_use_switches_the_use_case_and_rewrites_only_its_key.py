"""`mcgyvr use <chat|agent|code|mcgyvr-code>` switches the use case and nothing else.

It rewrites the `use_case:` line of the setup's policy and leaves every other
byte of the file as it was: comments, key order, the other keys. A policy that
names no use case gets the line added at the end. A setup written as one
document has its own top-level line rewritten. It says what it changed: the use
case before and after, the file, and which stages that turns on or off.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import load
from mcgyvr.exits import Exit

FLEET = """\
units:
  fast:
    address: http://127.0.0.1:9
    model: fast-coder
  smart:
    address: http://127.0.0.1:10
    model: smart-coder
"""

POLICY = """\
# my setup, my comments
use_case: mcgyvr-code   # the gated one
ladder:
- fast
- smart
cleanup:
  enabled: true
"""


def _setup(tmp_path: Path, policy: str = POLICY) -> Path:
    (tmp_path / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(policy, encoding="utf-8")
    return tmp_path


def _use(name: str, setup: Path) -> int:
    from mcgyvr.cli import main

    return main(["use", name, "--config", str(setup)])


def test_use_rewrites_only_the_use_case_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = _setup(tmp_path)

    assert _use("code", setup) == Exit.OK

    after = (setup / "policy.yaml").read_text(encoding="utf-8")
    assert after == POLICY.replace(
        "use_case: mcgyvr-code   # the gated one", "use_case: code   # the gated one"
    )
    assert load(setup).use_case == "code"
    out = capsys.readouterr().out
    assert "mcgyvr-code -> code" in out
    assert str(setup / "policy.yaml") in out
    assert "raw" in out


def test_use_back_to_mcgyvr_code_names_the_stages_it_turns_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = _setup(tmp_path, POLICY.replace("mcgyvr-code", "chat"))

    assert _use("mcgyvr-code", setup) == Exit.OK

    assert load(setup).use_case == "mcgyvr-code"
    out = capsys.readouterr().out
    assert "chat -> mcgyvr-code" in out
    assert "gate" in out and "repair" in out


def test_a_policy_with_no_use_case_gets_the_line_added_and_nothing_else(
    tmp_path: Path,
) -> None:
    bare = "ladder: [fast]\n# trailing comment\n"
    setup = _setup(tmp_path, bare)

    assert _use("chat", setup) == Exit.OK

    assert (setup / "policy.yaml").read_text(encoding="utf-8") == (
        bare + "use_case: chat\n"
    )


def test_the_same_use_case_changes_nothing_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = _setup(tmp_path)
    before = (setup / "policy.yaml").stat().st_mtime_ns

    assert _use("mcgyvr-code", setup) == Exit.OK

    assert (setup / "policy.yaml").stat().st_mtime_ns == before
    assert "already" in capsys.readouterr().out


def test_a_one_document_setup_has_its_own_line_rewritten(tmp_path: Path) -> None:
    document = tmp_path / "mcgyvr.yaml"
    text = FLEET + "ladder: [fast]\nuse_case: chat\n"
    document.write_text(text, encoding="utf-8")

    assert _use("agent", document) == Exit.OK

    assert document.read_text(encoding="utf-8") == text.replace(
        "use_case: chat", "use_case: agent"
    )


def test_a_name_that_is_no_use_case_is_refused_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = _setup(tmp_path)

    assert _use("media-gen", setup) == Exit.USAGE

    assert (setup / "policy.yaml").read_text(encoding="utf-8") == POLICY
    assert "mcgyvr-code, code, chat or agent" in capsys.readouterr().err


def test_an_indented_use_case_key_is_not_the_top_level_one(tmp_path: Path) -> None:
    policy = "ladder: [fast]\njournal:\n  dir: /tmp/x  # use_case: chat\n"
    setup = _setup(tmp_path, policy)

    assert _use("code", setup) == Exit.OK

    assert (setup / "policy.yaml").read_text(encoding="utf-8") == (
        policy + "use_case: code\n"
    )


def test_a_setup_that_would_not_load_is_left_exactly_as_it_was(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = POLICY.replace("- smart\n", "- nowhere\n")
    setup = _setup(tmp_path, broken)

    assert _use("code", setup) == Exit.ERROR

    assert (setup / "policy.yaml").read_text(encoding="utf-8") == broken
    assert "nothing was written" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["", '"chat"', "'chat'"])
def test_an_empty_or_quoted_value_is_rewritten_in_place(
    tmp_path: Path, value: str
) -> None:
    setup = _setup(
        tmp_path, f"use_case: {value}\nladder: [fast]\n".replace(": \n", ":\n")
    )

    assert _use("agent", setup) == Exit.OK

    assert (setup / "policy.yaml").read_text(encoding="utf-8") == (
        "use_case: agent\nladder: [fast]\n"
    )


def test_line_endings_a_byte_order_mark_and_the_mode_are_kept(tmp_path: Path) -> None:
    setup = _setup(tmp_path)
    policy = setup / "policy.yaml"
    policy.write_bytes("\ufeffuse_case: chat\r\nladder: [fast]\r\n".encode())
    policy.chmod(0o600)

    assert _use("code", setup) == Exit.OK

    assert policy.read_bytes() == "\ufeffuse_case: code\r\nladder: [fast]\r\n".encode()
    assert policy.stat().st_mode & 0o777 == 0o600
