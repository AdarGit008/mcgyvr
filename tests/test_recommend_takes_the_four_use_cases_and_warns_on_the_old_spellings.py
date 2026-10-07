"""`mcgyvr recommend` takes the four use cases, and warns on the old spellings.

The product names a use case one way everywhere: chat, agent, coding,
media-gen (the use cases of the shipped catalog, the same names `mcgyvr init
--use-case` takes). `recommend` used to take `--profile coding|chatting|
media_gen|other`, a second spelling of the same idea, and one that reads like
the config's `profile: live|dev`, which is a different setting.

`--use-case` is the option now. `--profile` is still read for one release: it
maps onto the use case it meant and says, on stderr, that it is deprecated and
what to type instead. `other` names no use case, so it warns and plans nothing
(the plan carries no unit). stdout stays the plan alone, so a caller
parsing it is not broken by the warning.

The plan itself is not under test here; the seam is `recommend.plan`, and only
the use case it is handed is checked. One test runs the real plan against a rig
that does not answer, to see the plan name its use case and no profile.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest

from mcgyvr import cli
from mcgyvr import recommend as recommend_module
from mcgyvr.catalog import catalog
from mcgyvr.scan import Unreachable

#: Invented: no such machine exists.
HOST = "rig-x.invalid"

USE_CASES = ("chat", "agent", "coding", "media-gen")


@pytest.fixture
def handed(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stand in for the planner and record what it was handed."""
    calls: list[dict[str, Any]] = []

    def fake_plan(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"use_case": kwargs["use_case"], "rigs": {}}

    monkeypatch.setattr(recommend_module, "plan", fake_plan)
    return calls


def _run(*flags: str) -> int:
    argv: Sequence[str] = ["recommend", *flags, "--users", "single", "--host", HOST]
    return cli.main(list(argv))


def test_the_four_use_cases_are_the_catalogs() -> None:
    assert tuple(sorted(u.name for u in catalog().use_cases)) == tuple(
        sorted(USE_CASES)
    )


@pytest.mark.parametrize("use_case", USE_CASES)
def test_each_use_case_reaches_the_plan_without_a_warning(
    use_case: str,
    handed: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run("--use-case", use_case)
    out, err = capsys.readouterr()
    assert code == 0
    assert [call["use_case"] for call in handed] == [use_case]
    assert json.loads(out)["use_case"] == use_case
    assert err == ""


@pytest.mark.parametrize(
    ("old", "new"),
    [("coding", "coding"), ("chatting", "chat"), ("media_gen", "media-gen")],
)
def test_an_old_profile_maps_to_its_use_case_and_warns(
    old: str,
    new: str,
    handed: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run("--profile", old)
    out, err = capsys.readouterr()
    assert code == 0
    assert [call["use_case"] for call in handed] == [new]
    # stdout is still the plan and nothing else.
    assert json.loads(out)["use_case"] == new
    assert "deprecated" in err
    assert f"--use-case {new}" in err
    # The warning keeps the two meanings of "profile" apart.
    assert "live|dev" in err


def test_the_old_profile_other_warns_and_plans_nothing(
    handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run("--profile", "other")
    out, err = capsys.readouterr()
    assert code == 0
    assert [call["use_case"] for call in handed] == [None]
    assert json.loads(out)["rigs"] == {}
    assert "deprecated" in err
    assert "nothing is planned" in err
    for name in USE_CASES:
        assert name in err


@pytest.mark.parametrize("spelling", ["chatting", "media_gen", "other"])
def test_an_old_spelling_is_not_a_use_case(
    spelling: str,
    handed: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        _run("--use-case", spelling)
    assert exited.value.code == 2
    assert not handed


def test_use_case_and_profile_together_are_refused(
    handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        _run("--use-case", "chat", "--profile", "chatting")
    assert exited.value.code == 2
    assert not handed


def test_a_use_case_is_required_and_the_error_names_it(
    handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        _run()
    assert exited.value.code == 2
    assert "--use-case" in capsys.readouterr().err
    assert not handed


def test_the_plan_names_its_use_case_and_no_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unreachable(host: str) -> Any:
        raise Unreachable(host)

    monkeypatch.setattr(recommend_module, "_scan_host", unreachable)
    code = _run("--use-case", "media-gen")
    plan = json.loads(capsys.readouterr().out)
    assert code == 0
    assert plan["use_case"] == "media-gen"
    assert "profile" not in plan
    assert [entry["host"] for entry in plan["unreachable"]] == [HOST]
    assert plan["rigs"] == {}
