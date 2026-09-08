"""The default selection does not reject a line the bundled formatter cannot wrap.

``DEFAULT_RUFF_SELECT`` (``src/mcgyvr/gate/adapters/python.py:54``) judges every
repository that declares no ruff configuration of its own, and the family ``E``
carries E501, line-too-long. E501 is the one rule in that selection ``ruff
format`` structurally cannot satisfy: the formatter rewraps *code*, and never a
long string, comment or docstring.

That combination costs the ladder whole replies. :mod:`mcgyvr.cleanup` tidies a
change "when every reason the gate gave for rejecting it is one the formatter
itself raised" — E501 arrives as a *lint* finding, so cleanup correctly declines,
the attempt is spent, and nothing is produced over a docstring a few characters
too wide. Counted over the live journal (23 files, 341 correction records
carrying gate findings): E501 is 104 of 220 lint findings, and **39 records are
rejected on E501 and nothing else**. Two live rounds against
``local_qwen3.6-35b-a3b`` put E501 at 18 of 26 findings, with
``p019-run-transactions`` and ``p020-gapped-match`` — complete, otherwise clean
files — rejected on E501 alone.

Line length has not stopped mattering, and the two tests at the bottom are what
say so: ``DEFAULT_RUFF_LINE_LENGTH`` is unchanged, ``ruff format`` still reflows
code at 88 and the format rung still rejects for it. What changed is only that a
line the formatter *cannot* wrap is no longer a rejection. And a repository that
states its own ruff config keeps it, E501 included: the default is for the
repository that said nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcgyvr.gate import Gate
from mcgyvr.gate.adapters.python import DEFAULT_RUFF_LINE_LENGTH, ruff_config_args
from mcgyvr.gate.changeset import ChangeSet

#: 80 characters of filler, so the docstring line below is 117 wide without this
#: test file itself carrying a line over 88 for its own linter to object to.
FILLER = "x" * 80

#: Correct, complete, import-sorted and byte-for-byte what ``ruff format``
#: produces — except that its docstring runs to 117 characters. Nothing but the
#: width is wrong with it.
WIDE_DOCSTRING = (
    "def stride(items: list[int], step: int) -> list[int]:\n"
    f'    """Return every step-th item, starting at the first. {FILLER}"""\n'
    "    if step <= 0:\n"
    '        raise ValueError("step must be positive")\n'
    "    return items[::step]\n"
)

#: The same file with the width in a comment rather than a docstring. The
#: formatter is equally powerless over both, and both used to reject.
WIDE_COMMENT = (
    "def stride(items: list[int], step: int) -> list[int]:\n"
    '    """Return every step-th item, starting at the first."""\n'
    f"    # {FILLER} explaining why the step has to be positive here\n"
    "    if step <= 0:\n"
    '        raise ValueError("step must be positive")\n'
    "    return items[::step]\n"
)

#: Over-wide *code*, which the formatter can and does rewrap. This is the case
#: the line length still governs, and it must keep rejecting.
WIDE_CODE = (
    "def stride(items: list[int], step: int) -> list[int]:\n"
    '    """Return every step-th item, starting at the first."""\n'
    "    return [item for index, item in enumerate(items) "
    "if index % step == 0 and item is not None]\n"
)

_PLAIN_PYPROJECT = '[project]\nname = "x"\nversion = "0"\n'


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )


def repo_with(tmp_path: Path, *, pyproject: str, solution: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "solution.py").write_text(solution, encoding="utf-8")
    return repo


def verdict(repo: Path) -> tuple[bool, set[str], set[str]]:
    """The gate's own answer — accepted, the codes it gave, the rungs it gave them
    on. Asserted on rather than the ruff argv, because an argv assertion passes
    while the behaviour it is standing in for stays broken."""
    result = Gate().run(ChangeSet.detect(repo, "HEAD"))
    return (
        result.accepted,
        {f.code for f in result.findings if f.code},
        {f.check for f in result.findings},
    )


def test_a_docstring_wider_than_the_limit_is_not_a_rejection(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, pyproject=_PLAIN_PYPROJECT, solution=WIDE_DOCSTRING)
    accepted, codes, checks = verdict(repo)
    assert "E501" not in codes, codes
    assert accepted, (codes, checks)


def test_a_comment_wider_than_the_limit_is_not_a_rejection(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, pyproject=_PLAIN_PYPROJECT, solution=WIDE_COMMENT)
    accepted, codes, checks = verdict(repo)
    assert "E501" not in codes, codes
    assert accepted, (codes, checks)


def test_a_repo_that_selects_e501_itself_still_gets_e501(tmp_path: Path) -> None:
    """The invariant the fix must not leak past: a repository that stated its own
    rules is judged by them, even where they are the rule the default drops."""
    own = f'{_PLAIN_PYPROJECT}\n[tool.ruff.lint]\nselect = ["E501"]\n'
    repo = repo_with(tmp_path, pyproject=own, solution=WIDE_DOCSTRING)
    assert ruff_config_args(repo) == []
    accepted, codes, _ = verdict(repo)
    assert "E501" in codes, codes
    assert not accepted


def test_the_formatter_still_wraps_code_at_the_same_width(tmp_path: Path) -> None:
    """Line length still governs what the formatter reflows, so the format rung
    still rejects — the change is only about the line it *cannot* reflow."""
    assert DEFAULT_RUFF_LINE_LENGTH == 88
    repo = repo_with(tmp_path, pyproject=_PLAIN_PYPROJECT, solution=WIDE_CODE)
    accepted, _, checks = verdict(repo)
    assert "format" in checks, checks
    assert not accepted
