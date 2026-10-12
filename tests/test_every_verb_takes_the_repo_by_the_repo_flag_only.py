"""Every verb that works on a repository takes it as ``--repo PATH``, and only so.

``run`` took ``--repo`` while ``sandbox``, ``index``, ``resolve``, ``read``,
``delegate`` and ``attach`` took the repository by position. An operator who
had learned ``run --repo`` typed ``sandbox --repo`` and was refused, and an
agent guessing the same did the same (e2e run 1, F14). One spelling now: the
flag, defaulting to the current directory, refusing a blank as ``run`` does.

A repository typed by position, the old form, is refused at parse time, exit
2, by a message that names the flag to use instead of argparse's bare
"unrecognized arguments".
"""

from __future__ import annotations

import pytest

from mcgyvr.cli import build_parser

#: Each verb, with the positional arguments it still takes before the repo.
VERBS: tuple[tuple[str, ...], ...] = (
    ("run", "contract.yaml"),
    ("sandbox",),
    ("index",),
    ("resolve", "the fetch helper"),
    ("read", "the fetch helper"),
    ("delegate", "document the helper"),
    ("attach",),
)


def _ids(verbs: tuple[tuple[str, ...], ...]) -> list[str]:
    return [verb[0] for verb in verbs]


@pytest.mark.parametrize("verb", VERBS, ids=_ids(VERBS))
def test_each_verb_takes_the_repo_as_a_flag(verb: tuple[str, ...]) -> None:
    args = build_parser().parse_args([*verb, "--repo", "/some/checkout"])
    assert args.repo == "/some/checkout"


@pytest.mark.parametrize("verb", VERBS, ids=_ids(VERBS))
def test_each_verb_defaults_the_repo_to_the_current_directory(
    verb: tuple[str, ...],
) -> None:
    assert build_parser().parse_args(list(verb)).repo == "."


@pytest.mark.parametrize("verb", VERBS, ids=_ids(VERBS))
def test_each_verb_refuses_a_blank_repo_as_run_does(
    verb: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        build_parser().parse_args([*verb, "--repo", ""])
    assert exit_.value.code == 2
    assert "--repo" in capsys.readouterr().err


@pytest.mark.parametrize("verb", VERBS, ids=_ids(VERBS))
def test_each_verb_refuses_a_repo_typed_by_position_and_names_the_flag(
    verb: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        build_parser().parse_args([*verb, "/some/checkout"])
    err = capsys.readouterr().err
    assert exit_.value.code == 2
    assert f"mcgyvr {verb[0]}: error:" in err
    assert "--repo /some/checkout" in err


@pytest.mark.parametrize("verb", VERBS, ids=_ids(VERBS))
def test_the_hidden_catch_for_the_old_form_is_not_in_the_usage(
    verb: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([verb[0], "--help"])
    out = capsys.readouterr().out
    assert "--repo PATH" in out
    assert "REPO" not in out.replace("--repo", "")
