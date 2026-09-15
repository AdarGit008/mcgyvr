"""A live run warns when a ladder step's combination is pulled, and still dispatches.

Owner, 2026-09-15: "warn now, enforce later". A live probe alert pulls its
combination (:func:`mcgyvr.fleet.alerts.pulled`), and until now a pull blocked
nothing and was seen only by ``mcgyvr fleet alerts``. The first live probe
(``run-20260915T050342-42b9afd8``) pulled both b-small combinations, and at
least one of those pulls is a tolerance-class bug, so refusing a pulled step
now would refuse work on a false reading. Instead:

* **On the live profile, a pulled step warns once, before it is dispatched,**
  on stderr: the unit, each pulled field with its count, and ``see mcgyvr
  fleet alerts``. Then it is dispatched exactly as it would have been: the same
  rungs, the same attempts, the same outcome.
* **A step whose combination is not pulled, or whose validation is newer than
  its alerts, prints nothing.**
* **Pulls that cannot be read are one warning, and the run goes on.**
* **The dev profile is unchanged.**
* **The units a pull reaches are resolved in** :mod:`mcgyvr.fleet.alerts`, so
  the enforcing change that follows asks the same function.

No rig and no network: the dispatch is substituted at
:data:`mcgyvr.drive.dispatch`, the journal and the lock are files in the test's
own HOME.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/fetch.py"
BASE = "def fetch(url):\n    return url\n"
ACCEPTED = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"

CONTRACT = f"""
id: retry
task_type: function_implementation
task: Give the fetch helper a retry budget named RETRY.
target: {TARGET}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
demonstration: ["sh -c 'grep -q RETRY {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

#: The ladder, cheapest first: the first rung never answers usably, so every
#: run climbs to the second, and a warning that changed the climb would show.
FIRST, SECOND = "srv2_3b", "srv1_deepseek"
UNIT_FIRST = "unt-" + "5" * 64
UNIT_SECOND = "unt-" + "e" * 64
RIG_FIRST = "rig-" + "c" * 64
RIG_SECOND = "rig-" + "0" * 64
FLEET_NAME = "b-small"

#: When the probe that pulled filed its alert, and a validation on either side.
ALERT_AT = "2026-09-15T05:03:42"
OLDER = "2026-09-13T21:44:00Z"
NEWER = "2026-09-15T09:00:00Z"


def fleet(profile: str = "live") -> dict[str, Any]:
    return {
        "profile": profile,
        "units": {
            FIRST: {
                "rig": "srv2",
                "unit_id": UNIT_FIRST,
                "address": "http://127.0.0.1:18001",
                "model": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
                "width": 1,
                "window": 8192,
            },
            SECOND: {
                "rig": "srv1",
                "unit_id": UNIT_SECOND,
                "address": "http://127.0.0.1:18080",
                "model": "deepseek-coder-v2-16b",
                "width": 1,
                "window": 8192,
            },
        },
        "rigs": {"srv2": {"rig_id": RIG_FIRST}, "srv1": {"rig_id": RIG_SECOND}},
        "fleets": {
            FLEET_NAME: {
                "layout": {"srv2": [[FIRST, "awake"]], "srv1": [[SECOND, "awake"]]},
                "next": [],
            }
        },
    }


def combination(rig_id: str) -> str:
    from mcgyvr.fleet.admit import layout_ids

    shape = fleet()
    return layout_ids(shape, shape["fleets"][FLEET_NAME]["layout"])[rig_id]


def home() -> Path:
    """The HOME ``tests/conftest.py`` gave this test."""
    return Path(os.environ["HOME"])


def write_setup(
    where: Path, journal: Path, profile: str, validated: dict[str, str]
) -> None:
    """``fleet.yaml``, ``policy.yaml`` and the lock's ``validated_at`` per rig."""
    where.mkdir(parents=True, exist_ok=True)
    (where / "fleet.yaml").write_text(yaml.safe_dump(fleet(profile)), encoding="utf-8")
    policy = {"ladder": [FIRST, SECOND], "journal": {"dir": str(journal)}}
    (where / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    for rig_id, at in validated.items():
        record = where / "records" / "fleet" / "rigs" / rig_id
        record.mkdir(parents=True, exist_ok=True)
        (record / f"{combination(rig_id)}.json").write_text(
            json.dumps({"validated_at": at}), encoding="utf-8"
        )


def go_live(tmp_path: Path, validated: dict[str, str] | None = None) -> Path:
    """Promote the fleet into this HOME, name it live, and return its journal."""
    journal = tmp_path / "journal"
    folder = home() / ".mcgyvr" / "fleets" / FLEET_NAME
    write_setup(
        folder,
        journal,
        "live",
        validated if validated is not None else {RIG_FIRST: OLDER, RIG_SECOND: OLDER},
    )
    (home() / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": FLEET_NAME, "since": "2026-09-15T00:00:00Z"}),
        encoding="utf-8",
    )
    return journal


def pull(journal: Path, rig: str, unit_id: str, field: str, count: int = 1) -> None:
    """File ``count`` live alerts on ``field``, as the probe files them."""
    from mcgyvr.fleet import alerts

    rig_id = fleet()["rigs"][rig]["rig_id"]
    stamp = {
        "fleet": FLEET_NAME,
        "rig": rig,
        "rig_id": rig_id,
        "combination_id": combination(rig_id),
        "unit_id": unit_id,
    }
    for _ in range(count):
        alerts.record(
            journal / "fleet",
            stamp,
            {
                "field": field,
                "observed": 1.0,
                "run_id": "run-20260915T050342-42b9afd8",
                "lease_id": "probe-42b9afd8",
                "at": ALERT_AT,
                "alert": True,
            },
        )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def _completion(text: str) -> Any:
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="m",
        source="s",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def climb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    config: Path | None = None,
) -> tuple[int, list[str], str]:
    """One ``mcgyvr run`` in a fresh repository: exit, rungs dispatched, stderr."""
    import mcgyvr.drive as drive
    from mcgyvr.cli import main

    repo = tmp_path / f"repo-{label}"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / TARGET).write_text(BASE, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    contract = tmp_path / f"retry-{label}.yaml"
    contract.write_text(CONTRACT, encoding="utf-8")

    dispatched: list[str] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Any:
        dispatched.append(rung)
        if rung == FIRST:
            return _completion("I would rather not write any code today.")
        return _completion(f"```python\n{ACCEPTED}```\n")

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    argv = ["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"]
    if config is not None:
        argv += ["--config", str(config)]
    code = main(argv)
    return code, dispatched, capsys.readouterr().err


def warnings(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("warning:")]


def test_a_pulled_step_warns_once_before_it_is_dispatched_and_is_still_dispatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = go_live(tmp_path)
    clean_code, clean_rungs, clean_err = climb(tmp_path, monkeypatch, capsys, "clean")
    assert warnings(clean_err) == [], clean_err
    assert clean_rungs[0] == FIRST and clean_rungs[-1] == SECOND, clean_rungs
    assert clean_rungs.count(FIRST) >= 1

    pull(journal, "srv2", UNIT_FIRST, "warm_decode_tok_s", count=2)
    pull(journal, "srv2", UNIT_FIRST, "prefill_tok_s")
    pull(journal, "srv1", UNIT_SECOND, "prefill_tok_s", count=3)
    code, rungs, err = climb(tmp_path, monkeypatch, capsys, "pulled")

    said = warnings(err)
    assert len(said) == 2, f"one warning per pulled step, whatever its attempts: {err}"
    first, second = said
    assert FIRST in first and SECOND not in first, first
    assert "warm_decode_tok_s x2" in first and "prefill_tok_s x1" in first, first
    assert SECOND in second and FIRST not in second, second
    assert "prefill_tok_s x3" in second, second
    assert all("see `mcgyvr fleet alerts`" in line for line in said), said
    assert (code, rungs) == (clean_code, clean_rungs), (
        "a warning changes nothing about what is dispatched"
    )


def test_a_step_validated_after_its_alerts_prints_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = go_live(tmp_path, {RIG_FIRST: NEWER, RIG_SECOND: OLDER})
    clean_code, clean_rungs, _ = climb(tmp_path, monkeypatch, capsys, "clean")
    pull(journal, "srv2", UNIT_FIRST, "warm_decode_tok_s")
    pull(journal, "srv1", UNIT_SECOND, "warm_decode_tok_s")

    code, rungs, err = climb(tmp_path, monkeypatch, capsys, "revalidated")

    said = warnings(err)
    assert len(said) == 1, err
    assert SECOND in said[0] and FIRST not in said[0], said
    assert (code, rungs) == (clean_code, clean_rungs)


def test_pulls_that_cannot_be_read_are_one_warning_and_the_run_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = go_live(tmp_path)
    clean_code, clean_rungs, _ = climb(tmp_path, monkeypatch, capsys, "clean")
    pull(journal, "srv2", UNIT_FIRST, "warm_decode_tok_s")
    # A journal file nobody can read: a directory where a row file should be.
    (journal / "fleet" / combination(RIG_FIRST) / "unreadable.jsonl").mkdir()

    code, rungs, err = climb(tmp_path, monkeypatch, capsys, "unreadable")

    said = warnings(err)
    assert len(said) == 1, err
    assert "pulls could not be read" in said[0], said
    assert (code, rungs) == (clean_code, clean_rungs)


def test_a_dev_run_is_unchanged_by_pulls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = go_live(tmp_path)
    dev = tmp_path / "dev-setup"
    write_setup(dev, journal, "dev", {})
    clean_code, clean_rungs, clean_err = climb(
        tmp_path, monkeypatch, capsys, "clean", config=dev
    )
    pull(journal, "srv2", UNIT_FIRST, "warm_decode_tok_s")
    pull(journal, "srv1", UNIT_SECOND, "warm_decode_tok_s")

    code, rungs, err = climb(tmp_path, monkeypatch, capsys, "dev", config=dev)

    assert warnings(err) == warnings(clean_err) == [], err
    assert (code, rungs) == (clean_code, clean_rungs)


def test_the_units_a_pull_reaches_are_resolved_where_enforcement_can_ask_again(
    tmp_path: Path,
) -> None:
    """One function turns the live fleet's pulls into its units, by name."""
    from mcgyvr.fleet import alerts

    assert alerts.live_pulled_units() == {}, "no fleet named live, nothing pulled"
    journal = go_live(tmp_path, {RIG_FIRST: OLDER, RIG_SECOND: NEWER})
    pull(journal, "srv2", UNIT_FIRST, "warm_decode_tok_s", count=2)
    pull(journal, "srv1", UNIT_SECOND, "prefill_tok_s")

    units = alerts.live_pulled_units()

    assert set(units) == {FIRST}, units
    assert [(e["unit_id"], e["field"], e["count"]) for e in units[FIRST]] == [
        (UNIT_FIRST, "warm_decode_tok_s", 2)
    ]
