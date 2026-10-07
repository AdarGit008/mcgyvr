"""`mcgyvr recommend` can choose any candidate it assembled, on any rig.

The plan is units per rig, each picked from candidates assembled on that rig.
The pick is a name: the bound Jev unit answers one question per rig with one
of that rig's candidates' names, and the plan places the candidate of that
name, on that rig. Two things once broke that:

* the names were not unique. A local checkpoint was named only by its
  speculative head, and a catalog pick only by engine and model, so the same
  name stood for a checkpoint on every rig, and for every checkpoint in a
  store. The lookup by name kept the last one, so most candidates could never
  be chosen;
* the placement said nothing about the rig it was for.

So: every candidate's name is its own and carries its rig, every candidate is
reachable by its name, and every unit is planned under the rig it was sized
for. The rigs are invented and answer through the read-only ssh seam; the
decision is faked at `mcgyvr.decision.classify` and names each option in turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import availability, decision
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from tests.test_recommend import (
    CHECKPOINT,
    FAKE_LIBRARY,
    OTHER,
    SIZE_BYTES,
    STORE_DIR,
    RecordedSsh,
    by_path,
    run_and_parse,
)

#: Invented rigs: no such machines exist.
HOSTS = ("rig-a.invalid", "rig-b.invalid")

#: A setup that binds a Jev unit, so the decision is asked. Invented.
JEV_CONFIG = """\
units:
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- judge
jev:
  unit: judge
"""


class Picks:
    """A stand-in for ``decision.classify`` that names, on every rig, the
    option it is told."""

    def __init__(self) -> None:
        self.pick = 0
        self.options: list[dict[str, tuple[str, ...]]] = []

    def __call__(
        self,
        endpoint: Any,
        model: str,
        state: Any,
        questions: Mapping[str, Any],
        *,
        timeout_s: float,
    ) -> decision.Decision:
        asked = {key: tuple(q.options) for key, q in questions.items()}
        self.options.append(asked)
        answers = {}
        for key, options in asked.items():
            chosen = options[self.pick]
            answers[key] = decision.ChoiceAnswer(
                choice=chosen, probabilities={chosen: 1.0}, confidence=1.0
            )
        return decision.Decision(answers=answers)


@pytest.fixture
def setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, RecordedSsh, Picks]:
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(JEV_CONFIG, encoding="utf-8")
    ssh = RecordedSsh(*HOSTS)
    monkeypatch.setattr(scan_module, "_ssh", ssh)
    picks = Picks()
    monkeypatch.setattr(decision, "classify", picks)

    def live(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source, live=True, reason="stub", how="stub", elapsed_s=0.0
        )

    monkeypatch.setattr(availability, "probe_endpoint", live)
    return str(config), ssh, picks


def _placed(plan: Mapping[str, Any]) -> set[tuple[str, str]]:
    """Where each unit landed: its rig, and the file it serves."""
    return {
        (rig, unit["args"]["--model"])
        for rig, laid in plan["rigs"].items()
        for unit in laid["units"]
    }


def _every_pick(
    capsys: pytest.CaptureFixture[str],
    picks: Picks,
    config: str,
    *model_stores: str,
) -> tuple[dict[str, tuple[str, ...]], set[tuple[str, str]]]:
    """Name each option in turn; return the options and where each landed."""
    code, plan = run_and_parse(
        capsys, "coding", "single", *model_stores, hosts=HOSTS, config=config
    )
    assert code == 0, plan
    options = picks.options[-1]
    placed = _placed(plan)
    for index in range(1, min(len(o) for o in options.values())):
        picks.pick = index
        code, plan = run_and_parse(
            capsys, "coding", "single", *model_stores, hosts=HOSTS, config=config
        )
        assert code == 0, plan
        assert plan["decision"]["by"] == "jev"
        placed |= _placed(plan)
    return options, placed


def test_every_local_checkpoint_on_every_rig_is_its_own_choice(
    setup: tuple[str, RecordedSsh, Picks], capsys: pytest.CaptureFixture[str]
) -> None:
    """Two rigs x two checkpoints: each rig asked once, of its own two top
    rungs (the small one alone, or the MoE above it)."""
    config, ssh, picks = setup
    ssh.ggufs = [CHECKPOINT, OTHER]
    ssh.header_builder = by_path
    ssh.header_sizes[CHECKPOINT] = SIZE_BYTES
    ssh.header_sizes[OTHER] = 3_000_000_000

    options, placed = _every_pick(capsys, picks, config, STORE_DIR)

    assert set(options) == {f"unit@{host}" for host in HOSTS}
    for host in HOSTS:
        asked = options[f"unit@{host}"]
        assert len(asked) == 2, asked
        assert all(option.startswith(f"{host}: ") for option in asked)
    assert placed == {(host, path) for host in HOSTS for path in (CHECKPOINT, OTHER)}


def test_every_knowledge_pick_on_every_rig_is_its_own_choice(
    setup: tuple[str, RecordedSsh, Picks],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The knowledge's two models, two rigs: each one placeable on each rig."""
    config, _ssh, picks = setup
    monkeypatch.setattr(recommend_module, "load_models", lambda: FAKE_LIBRARY)

    options, placed = _every_pick(capsys, picks, config)

    for host in HOSTS:
        assert len(options[f"unit@{host}"]) == len(FAKE_LIBRARY.models)
    files = {Path(model.file).name for model in FAKE_LIBRARY.models}
    assert {(host, Path(path).name) for host, path in placed} == {
        (host, file) for host in HOSTS for file in files
    }


def test_a_deterministic_plan_also_names_its_rigs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No Jev bound: the fixed rule picks, and every unit is under its rig."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scan_module, "_ssh", RecordedSsh(*HOSTS))

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR, hosts=HOSTS)

    assert code == 0, plan
    assert plan["decision"]["by"] == "deterministic"
    assert set(plan["rigs"]) == set(HOSTS)
    for rig, laid in plan["rigs"].items():
        for unit in laid["units"]:
            assert unit["name"].startswith(f"{rig}-")
